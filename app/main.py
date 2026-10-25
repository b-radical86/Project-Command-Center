import os
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import httpx

load_dotenv()

from app.db import (
    init_db,
    get_connection,
    get_quota_telemetry,
    log_api_usage
)
from app.schemas import (
    ProjectUpdateSchema,
    ActionItemUpdateSchema,
    EnhancementStatusUpdateSchema,
    CanonicalStage
)
from app.parser import process_harvested_docs
from app.github_client import (
    fetch_all_repositories,
    fetch_repository_details
)
from app.gemini_service import (
    analyze_repo_batch,
    generate_repo_enhancements,
    generate_cross_portfolio_strategy
)

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database on startup
    init_db()
    logger.info("Database initialized with WAL mode.")
    yield

app = FastAPI(
    title="Project Command Center API",
    description="Unified GitHub & Gemini AI Studio Developer Command Center",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Repository API Endpoints
# ---------------------------------------------------------

@app.get("/api/projects")
def list_projects(
    domain: Optional[str] = None,
    stage: Optional[str] = None,
    search: Optional[str] = None
):
    """List all synchronized repositories with computed status, completion, and blockers."""
    conn = get_connection()
    try:
        query = "SELECT * FROM repositories WHERE is_empty = 0"
        params = []

        if domain and domain.lower() != "all":
            query += " AND domain_tag = ?"
            params.append(domain)

        if stage and stage.lower() != "all":
            query += " AND COALESCE(override_stage, synced_stage) = ?"
            params.append(stage)

        if search:
            query += " AND (name_with_owner LIKE ? OR description LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term])

        query += " ORDER BY pushed_at DESC"
        rows = conn.execute(query, params).fetchall()

        results = []
        for r in rows:
            item = dict(r)
            # Effective stage prioritizes user override
            item["effective_stage"] = item["override_stage"] or item["synced_stage"] or "Ideation & Planning"
            
            # Parse summary_json if present
            if item.get("summary_json"):
                try:
                    item["summary_data"] = json.loads(item["summary_json"])
                except Exception:
                    item["summary_data"] = {}
            else:
                item["summary_data"] = {}

            # Count action items
            action_counts = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_completed = 1 THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN is_completed = 0 AND is_dismissed = 0 THEN 1 ELSE 0 END) as pending
                FROM action_items
                WHERE repo_id = ?
            """, (item["id"],)).fetchone()
            
            item["action_counts"] = {
                "total": action_counts["total"] if action_counts else 0,
                "completed": action_counts["completed"] if action_counts else 0,
                "pending": action_counts["pending"] if action_counts else 0,
            }
            results.append(item)

        return results
    finally:
        conn.close()


@app.get("/api/projects/{repo_id}")
def get_project_details(repo_id: int):
    """Retrieve complete project details, action items, and AI enhancements."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Repository not found")

        repo = dict(row)
        repo["effective_stage"] = repo["override_stage"] or repo["synced_stage"] or "Ideation & Planning"
        
        if repo.get("summary_json"):
            try:
                repo["summary_data"] = json.loads(repo["summary_json"])
            except Exception:
                repo["summary_data"] = {}
        else:
            repo["summary_data"] = {}

        # Fetch action items
        action_rows = conn.execute("""
            SELECT * FROM action_items 
            WHERE repo_id = ? AND is_dismissed = 0
            ORDER BY is_completed ASC, id DESC
        """, (repo_id,)).fetchall()
        repo["action_items"] = [dict(a) for a in action_rows]

        # Fetch AI enhancements
        enhancement_rows = conn.execute("""
            SELECT * FROM ai_enhancements
            WHERE repo_id = ?
            ORDER BY id DESC
        """, (repo_id,)).fetchall()
        repo["enhancements"] = [dict(e) for e in enhancement_rows]

        return repo
    finally:
        conn.close()


@app.patch("/api/projects/{repo_id}")
def update_project(repo_id: int, payload: ProjectUpdateSchema):
    """Update manual overrides: stage, domain tag, and AI toggle."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Repository not found")

        updates = []
        params = []
        if payload.override_stage is not None:
            # Empty string or 'clear' clears the override
            val = None if payload.override_stage in ("", "clear") else payload.override_stage
            updates.append("override_stage = ?")
            params.append(val)

        if payload.domain_tag is not None:
            updates.append("domain_tag = ?")
            params.append(payload.domain_tag)

        if payload.ai_enabled is not None:
            updates.append("ai_enabled = ?")
            params.append(1 if payload.ai_enabled else 0)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE repositories SET {', '.join(updates)} WHERE id = ?"
            params.append(repo_id)
            conn.execute(sql, params)
            conn.commit()

        updated_row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        return dict(updated_row)
    finally:
        conn.close()


# ---------------------------------------------------------
# Action Items & Blocker Queue Endpoints
# ---------------------------------------------------------

@app.get("/api/actions")
def list_action_items(
    repo_id: Optional[int] = None,
    completed: Optional[bool] = None,
    source_type: Optional[str] = None
):
    """Unified cross-project action item and blocker queue."""
    conn = get_connection()
    try:
        query = """
            SELECT a.*, r.name_with_owner, r.domain_tag
            FROM action_items a
            JOIN repositories r ON a.repo_id = r.id
            WHERE a.is_dismissed = 0
        """
        params = []
        if repo_id:
            query += " AND a.repo_id = ?"
            params.append(repo_id)
        if completed is not None:
            query += " AND a.is_completed = ?"
            params.append(1 if completed else 0)
        if source_type:
            query += " AND a.source_type = ?"
            params.append(source_type)

        query += " ORDER BY a.is_completed ASC, a.id DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.patch("/api/actions/{action_id}")
def update_action_item(action_id: int, payload: ActionItemUpdateSchema):
    """Toggle action item completion or dismissal."""
    conn = get_connection()
    try:
        updates = []
        params = []
        if payload.is_completed is not None:
            updates.append("is_completed = ?")
            params.append(1 if payload.is_completed else 0)
        if payload.is_dismissed is not None:
            updates.append("is_dismissed = ?")
            params.append(1 if payload.is_dismissed else 0)

        if updates:
            sql = f"UPDATE action_items SET {', '.join(updates)} WHERE id = ?"
            params.append(action_id)
            conn.execute(sql, params)
            conn.commit()

        row = conn.execute("SELECT * FROM action_items WHERE id = ?", (action_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Action item not found")
        return dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------
# AI Enhancement Studio Endpoints
# ---------------------------------------------------------

@app.get("/api/enhancements")
def list_enhancements(repo_id: Optional[int] = None, category: Optional[str] = None):
    """Retrieve stored AI enhancement cards."""
    conn = get_connection()
    try:
        query = """
            SELECT e.*, r.name_with_owner
            FROM ai_enhancements e
            LEFT JOIN repositories r ON e.repo_id = r.id
            WHERE 1=1
        """
        params = []
        if repo_id is not None:
            query += " AND e.repo_id = ?"
            params.append(repo_id)
        if category:
            query += " AND e.category = ?"
            params.append(category)

        query += " ORDER BY e.id DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.patch("/api/enhancements/{enhancement_id}")
def update_enhancement(enhancement_id: int, payload: EnhancementStatusUpdateSchema):
    """Update status of an AI enhancement card ('accepted', 'completed', 'dismissed')."""
    conn = get_connection()
    try:
        conn.execute("UPDATE ai_enhancements SET status = ? WHERE id = ?", (payload.status, enhancement_id))
        conn.commit()
        row = conn.execute("SELECT * FROM ai_enhancements WHERE id = ?", (enhancement_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Enhancement not found")
        return dict(row)
    finally:
        conn.close()


@app.post("/api/ideate/repo/{repo_id}")
async def trigger_repo_deep_dive(repo_id: int):
    """On-demand single-project deep dive enhancement generator."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Repository not found")

        repo_dict = dict(row)
        summary_data = json.loads(repo_dict.get("summary_json") or "{}")

        payload = {
            "name_with_owner": repo_dict["name_with_owner"],
            "description": repo_dict["description"],
            "stage": repo_dict["override_stage"] or repo_dict["synced_stage"] or "MVP In Progress",
            "completion_pct": repo_dict["completion_pct"],
            "directories": summary_data.get("directories", []),
            "open_issues": summary_data.get("open_issues", []),
            "sanitized_docs": summary_data.get("sanitized_docs", {}),
        }

        # Run Gemini enhancement plan
        plan = generate_repo_enhancements(payload)

        # Store enhancements into database
        for qw in plan.quick_wins:
            conn.execute("""
                INSERT INTO ai_enhancements (repo_id, category, title, rationale, antigravity_prompt, status)
                VALUES (?, 'quick_win', ?, ?, ?, 'suggested')
            """, (repo_id, qw.title, qw.rationale, qw.antigravity_prompt))

        for nm in plan.next_milestones:
            conn.execute("""
                INSERT INTO ai_enhancements (repo_id, category, title, rationale, antigravity_prompt, status)
                VALUES (?, 'next_stage', ?, ?, ?, 'suggested')
            """, (repo_id, nm.title, nm.rationale, nm.antigravity_prompt))

        conn.commit()
        return plan.model_dump()
    finally:
        conn.close()


@app.post("/api/ideate/portfolio")
async def trigger_portfolio_brainstorm():
    """Single-call cross-portfolio strategist."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM repositories 
            WHERE is_empty = 0 AND ai_enabled = 1
            ORDER BY pushed_at DESC
        """).fetchall()

        if not rows:
            raise HTTPException(status_code=400, detail="No active AI-enabled repositories found")

        portfolio_payload = []
        for r in rows:
            rd = dict(r)
            s_data = json.loads(rd.get("summary_json") or "{}")
            portfolio_payload.append({
                "name_with_owner": rd["name_with_owner"],
                "domain_tag": rd["domain_tag"],
                "stage": rd["override_stage"] or rd["synced_stage"] or "MVP In Progress",
                "completion_pct": rd["completion_pct"],
                "description": rd["description"],
                "summary": s_data.get("ai_summary", rd["description"]),
                "blockers": s_data.get("blockers", []),
            })

        strategy = generate_cross_portfolio_strategy(portfolio_payload)

        # Store synergies
        for syn in strategy.synergies:
            conn.execute("""
                INSERT INTO ai_enhancements (repo_id, category, title, rationale, antigravity_prompt, status)
                VALUES (NULL, 'synergy', ?, ?, ?, 'suggested')
            """, (syn.title, f"Affected repos: {', '.join(syn.affected_repos)}. {syn.rationale}", syn.antigravity_prompt))

        # Store weekend finishers
        for wf in strategy.weekend_finishers:
            repo_row = conn.execute("SELECT id FROM repositories WHERE name_with_owner = ? OR name = ?", (wf.repo_name, wf.repo_name)).fetchone()
            r_id = repo_row["id"] if repo_row else None
            conn.execute("""
                INSERT INTO ai_enhancements (repo_id, category, title, rationale, antigravity_prompt, status)
                VALUES (?, 'quick_win', ?, ?, ?, 'suggested')
            """, (r_id, f"[Weekend Finisher] {wf.title}", wf.rationale, wf.antigravity_prompt))

        conn.commit()
        return strategy.model_dump()
    finally:
        conn.close()


@app.get("/api/quota")
def get_quota():
    """Live Free Tier quota metrics."""
    return get_quota_telemetry()


# ---------------------------------------------------------
# Two-Stage Sync Pipeline with Server-Sent Events (SSE)
# ---------------------------------------------------------

@app.get("/api/sync/stream")
async def sync_stream():
    """
    Stream Server-Sent Events (SSE) during GitHub sync:
    1. Stage 1: GraphQL SHA Discovery
    2. Stage 2: Case-insensitive tree & blob harvest
    3. Stage 3: Deterministic pass & secret scrubbing
    4. Stage 4: Batched AI status pass (8 repos/call)
    """
    async def event_generator():
        client = httpx.AsyncClient(timeout=45.0)
        try:
            # Stage 1: Discovery
            yield f"data: {json.dumps({'event': 'stage1_start', 'message': 'Stage 1: Connecting to GitHub GraphQL and querying repository commit SHAs...'})}\n\n"
            await asyncio.sleep(0.1)

            all_repos = await fetch_all_repositories(client)
            yield f"data: {json.dumps({'event': 'stage1_done', 'total_repos': len(all_repos), 'message': f'Discovered {len(all_repos)} repositories on GitHub'})}\n\n"
            await asyncio.sleep(0.1)

            conn = get_connection()
            try:
                # Compare SHAs to determine which repos need Stage 2 blob harvest
                changed_repos = []
                for repo in all_repos:
                    name_with_owner = repo["nameWithOwner"]
                    existing = conn.execute(
                        "SELECT id, last_synced_sha, override_stage, domain_tag, ai_enabled FROM repositories WHERE name_with_owner = ?",
                        (name_with_owner,)
                    ).fetchone()

                    # Skip empty repos
                    if repo.get("isEmpty") or not repo.get("latestCommitSha"):
                        continue

                    if not existing or existing["last_synced_sha"] != repo["latestCommitSha"]:
                        changed_repos.append((repo, existing))
                    else:
                        # Update push time and issues count even if commit hasn't changed
                        conn.execute("""
                            UPDATE repositories 
                            SET pushed_at = ?, open_issues_count = ?, is_archived = ?, is_private = ?
                            WHERE id = ?
                        """, (repo["pushedAt"], repo["openIssuesCount"], 1 if repo["isArchived"] else 0, 1 if repo["isPrivate"] else 0, existing["id"]))
                conn.commit()

                yield f"data: {json.dumps({'event': 'stage2_start', 'changed_count': len(changed_repos), 'message': f'Found {len(changed_repos)} changed or newly added repositories'})}\n\n"

                ai_batch_queue = []

                # Process changed repos in chunks
                for idx, (repo_meta, existing_record) in enumerate(changed_repos, start=1):
                    name_with_owner = repo_meta["nameWithOwner"]
                    owner = repo_meta["owner"]
                    name = repo_meta["name"]

                    yield f"data: {json.dumps({'event': 'stage2_harvest', 'current': idx, 'total': len(changed_repos), 'repo': name_with_owner, 'message': f'Harvesting docs for {name_with_owner} ({idx}/{len(changed_repos)})...'})}\n\n"
                    await asyncio.sleep(0.05)

                    try:
                        # Stage 2: Harvest trees and blobs
                        details = await fetch_repository_details(client, owner=owner, name=name)
                    except Exception as harvest_err:
                        logger.warning(f"Failed to harvest {name_with_owner}: {harvest_err}")
                        continue

                    # Stage 3: Deterministic pass & secret scrubbing
                    processed = process_harvested_docs(details["docs"])

                    # Default domain tag deduction if new
                    domain_tag = "General"
                    lower_name = name.lower()
                    if "wealth" in lower_name or "cash" in lower_name or "invest" in lower_name or "hnw" in lower_name:
                        domain_tag = "Wealth"
                    elif "garden" in lower_name or "arcade" in lower_name or "game" in lower_name:
                        domain_tag = "Hobbies"
                    elif "family" in lower_name or "home" in lower_name:
                        domain_tag = "Family"
                    elif "hardware" in lower_name or "esp" in lower_name or "sensor" in lower_name:
                        domain_tag = "Hardware"

                    ai_enabled = 1
                    override_stage = None
                    if existing_record:
                        domain_tag = existing_record["domain_tag"]
                        ai_enabled = existing_record["ai_enabled"]
                        override_stage = existing_record["override_stage"]

                    summary_payload = {
                        "directories": details["directories"],
                        "open_issues": details["open_issues"],
                        "sanitized_docs": processed["sanitized_docs"],
                        "harvested_doc_count": len(processed["sanitized_docs"]),
                    }

                    # Determine initial deterministic stage
                    det_stage = "MVP In Progress"
                    if processed["completion_pct"] >= 100.0 and processed["total_completed"] > 0:
                        det_stage = "Ready for Next Stage"
                    elif processed["completion_pct"] == 0.0 and len(processed["sanitized_docs"]) <= 1:
                        det_stage = "Ideation & Planning"

                    # Upsert repo into database
                    conn.execute("""
                        INSERT INTO repositories (
                            name_with_owner, name, owner, is_private, is_archived, is_empty,
                            description, html_url, pushed_at, last_synced_sha, synced_stage,
                            override_stage, domain_tag, ai_enabled, completion_pct,
                            open_issues_count, summary_json, last_synced_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(name_with_owner) DO UPDATE SET
                            description = excluded.description,
                            html_url = excluded.html_url,
                            pushed_at = excluded.pushed_at,
                            last_synced_sha = excluded.last_synced_sha,
                            synced_stage = excluded.synced_stage,
                            completion_pct = excluded.completion_pct,
                            open_issues_count = excluded.open_issues_count,
                            summary_json = excluded.summary_json,
                            last_synced_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        name_with_owner, name, owner,
                        1 if repo_meta["isPrivate"] else 0,
                        1 if repo_meta["isArchived"] else 0,
                        1 if repo_meta["isEmpty"] else 0,
                        repo_meta["description"],
                        repo_meta["htmlUrl"],
                        repo_meta["pushedAt"],
                        repo_meta["latestCommitSha"],
                        det_stage,
                        override_stage,
                        domain_tag,
                        ai_enabled,
                        processed["completion_pct"],
                        repo_meta["openIssuesCount"],
                        json.dumps(summary_payload)
                    ))
                    conn.commit()

                    # Retrieve repo_id
                    repo_id = conn.execute("SELECT id FROM repositories WHERE name_with_owner = ?", (name_with_owner,)).fetchone()["id"]

                    # Synchronize action items
                    # Clear previous deterministic items for this repo (preserve manual ones)
                    conn.execute("DELETE FROM action_items WHERE repo_id = ? AND source_type IN ('doc_checkbox', 'github_issue')", (repo_id,))

                    for item in processed["all_action_items"]:
                        conn.execute("""
                            INSERT INTO action_items (repo_id, source_type, title, file_path, line_number, is_completed)
                            VALUES (?, 'doc_checkbox', ?, ?, ?, ?)
                        """, (repo_id, item["title"], item.get("file_path"), item.get("line_number"), 1 if item.get("is_completed") else 0))

                    for issue in details["open_issues"]:
                        conn.execute("""
                            INSERT INTO action_items (repo_id, source_type, title, file_path, line_number, is_completed)
                            VALUES (?, 'github_issue', ?, ?, NULL, 0)
                        """, (repo_id, f"#{issue['number']} {issue['title']}", issue.get("url")))

                    conn.commit()

                    if ai_enabled:
                        ai_batch_queue.append({
                            "repo_id": repo_id,
                            "name_with_owner": name_with_owner,
                            "description": repo_meta["description"],
                            "directories": details["directories"],
                            "open_issues": details["open_issues"],
                            "completion_pct": processed["completion_pct"],
                            "sanitized_docs": processed["sanitized_docs"],
                        })

                # Stage 4: Batched AI Status Pass (8 repos per call)
                if ai_batch_queue:
                    yield f"data: {json.dumps({'event': 'stage4_start', 'total_ai_repos': len(ai_batch_queue), 'message': f'Stage 4: Running Gemini Free-Tier status extraction across {len(ai_batch_queue)} AI-enabled repositories in batches of 8...'})}\n\n"
                    await asyncio.sleep(0.1)

                    batch_size = 8
                    for i in range(0, len(ai_batch_queue), batch_size):
                        batch = ai_batch_queue[i : i + batch_size]
                        yield f"data: {json.dumps({'event': 'stage4_batch', 'batch_num': (i // batch_size) + 1, 'repos': [r['name_with_owner'] for r in batch], 'message': f'Analyzing batch {(i // batch_size) + 1} ({len(batch)} repos)...'})}\n\n"

                        try:
                            batch_response = analyze_repo_batch(batch)
                            for extraction in batch_response.repos:
                                # Match back to repo
                                repo_match = next((b for b in batch if b["name_with_owner"] == extraction.name_with_owner), None)
                                if repo_match:
                                    # Update synced_stage and summary in database
                                    r_id = repo_match["repo_id"]
                                    existing_summary = conn.execute("SELECT summary_json FROM repositories WHERE id = ?", (r_id,)).fetchone()
                                    current_summary = json.loads(existing_summary["summary_json"] or "{}") if existing_summary else {}
                                    current_summary["ai_summary"] = extraction.summary
                                    current_summary["blockers"] = extraction.blockers
                                    current_summary["key_milestones"] = extraction.key_milestones
                                    current_summary["ai_confidence"] = extraction.confidence

                                    conn.execute("""
                                        UPDATE repositories
                                        SET synced_stage = ?, summary_json = ?, updated_at = CURRENT_TIMESTAMP
                                        WHERE id = ?
                                    """, (extraction.detected_stage.value, json.dumps(current_summary), r_id))

                                    # Insert AI blockers into action_items if not already present
                                    for blk in extraction.blockers:
                                        conn.execute("""
                                            INSERT INTO action_items (repo_id, source_type, title, is_completed)
                                            VALUES (?, 'ai_blocker', ?, 0)
                                        """, (r_id, f"[AI Blocker] {blk}"))

                            conn.commit()
                        except Exception as batch_err:
                            logger.error(f"Error analyzing batch: {batch_err}")
                            yield f"data: {json.dumps({'event': 'stage4_error', 'message': f'AI Batch Warning: {str(batch_err)[:100]}'})}\n\n"

                yield f"data: {json.dumps({'event': 'sync_complete', 'message': 'Sync complete! Project Command Center is up to date.'})}\n\n"

            finally:
                conn.close()

        except Exception as e:
            logger.exception("Sync failed with error")
            yield f"data: {json.dumps({'event': 'error', 'message': f'Sync failed: {str(e)}'})}\n\n"
        finally:
            await client.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------
# Static Files & Dashboard UI Route
# ---------------------------------------------------------

static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_dashboard():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Project Command Center Backend is running. Frontend static/index.html not found yet."}
