# Project Command Center (GitHub & Gemini AI Studio Dashboard) — Master Implementation Plan (v2)

## 1. Executive Summary & System Goals

The **Project Command Center** is a unified, local-first developer dashboard that synchronizes with your GitHub account, reads documentation across all of your repositories, tracks lifecycle progress and open blockers, and uses [Google AI Studio](https://aistudio.google.com/) ([Gemini Developer API Free Tier](https://ai.google.dev/gemini-api/docs/pricing)) to generate next-stage feature roadmaps and cross-project enhancement ideas.

This v2 master specification incorporates all findings from the multi-persona architectural review, including **Two-Stage GraphQL Discovery**, **Batched Cold-Start Status Extraction**, **Free-Tier Privacy & Secret Scrubbing**, and a **Single-Process FastAPI + Alpine.js/Tailwind + SSE** runtime.

### Core Capabilities
* **Two-Stage GitHub Documentation Sync**: Uses the [GitHub GraphQL API](https://docs.github.com/en/graphql) to first diff commit SHAs across all repositories, then case-insensitively harvests Markdown documentation (`README.md`, `PROJECT_OVERVIEW.md`, `PLAN.md`, `TODO.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`) and open issues only for modified repos.
* **Hybrid Lifecycle & Issue Tracking**: Separates deterministic Markdown parsing (`- [ ]` / `- [x]` checkboxes and GitHub Issue counts) from structured AI extraction while preserving manual user overrides (`override_stage`, pinned tasks) across syncs.
* **Free-Tier Optimized Gemini AI Studio Strategist**: Combines 8-repo batched status extraction, automatic model fallback, and single-call cross-portfolio context batching via the [Google Gen AI Python SDK](https://github.com/googleapis/python-genai) (`google-genai`) to stay comfortably within [Gemini API Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits).
* **Privacy & Secret Guardrails**: Provides a per-repo `ai_enabled` toggle (allowing sensitive wealth-management or client work repositories to run in deterministic-only mode) and a pre-flight regex secret scrubber before any text leaves localhost.

## 2. System Architecture & Data Pipeline

| Layer | Component | Technology Stack | Responsibility |
| :--- | :--- | :--- | :--- |
| **Ingestion** | Two-Stage Sync Client | [GitHub GraphQL API](https://docs.github.com/en/graphql) (`httpx`) + Local Git Scanner | Stage 1 diffs commit `oid` SHAs across up to 100 repos; Stage 2 resolves case-insensitive doc paths and fetches blobs for changed repos. |
| **Privacy Filter** | Pre-Flight Sanitizer | Python `re` + `.dashboardignore` | Redacts API keys, tokens, emails, and internal URLs; enforces deterministic-only mode for repos with `ai_enabled=False`. |
| **Storage & Cache** | Local State Store | SQLite (`projects.db` in `WAL` mode) | Stores repo metadata, `synced_stage` vs. `override_stage`, parsed checklist items, cached AI enhancements, and RPM/RPD quota logs. |
| **AI Engine** | Free-Tier Strategist | [Google Gen AI Python SDK](https://github.com/googleapis/python-genai) (`google-genai`) | Executes batched (8 repos/call) Pydantic status extractions, single-call portfolio brainstorms, and per-repo deep dives with tier fallback. |
| **Backend API** | Local Web Server | Python `FastAPI` + `SSE` | Serves REST endpoints and Server-Sent Events (`/api/sync/stream`) for real-time progress and rate-limit pacing. |
| **Frontend UI** | Single-Page Dashboard | `FastAPI StaticFiles` + Tailwind CSS + Alpine.js | Renders Kanban/Table views, domain filters, blocker queues, live Free Tier quota telemetry, and the AI Enhancement Studio drawer. |

## 3. Two-Stage GitHub Sync & Status Resolution

When you click **Sync**, the backend streams progress via Server-Sent Events (`/api/sync/stream`) through a four-step pipeline:

1. **Stage 1 — Lightweight GraphQL SHA Discovery**:
   * Queries up to 100 repositories sorted by `pushedAt` for `nameWithOwner`, `isPrivate`, `isArchived`, `isEmpty`, open issue counts, and `defaultBranchRef { target { oid } }`.
   * Gracefully skips empty/uninitialized repositories (`isEmpty: true` or `defaultBranchRef: null`) and any repositories whose commit `oid` matches the SQLite `last_synced_sha`.
2. **Stage 2 — Case-Insensitive Tree & Blob Harvest**:
   * For changed repositories (in chunks of 5–10), queries the root (`HEAD:`) and `/docs` (`HEAD:docs`) tree entries.
   * Matches target filenames (`readme.md`, `project_overview.md`, `todo.md`, `roadmap.md`, `plan.md`, `claude.md`, `agents.md`) case-insensitively in Python and fetches their text blobs alongside top-level directory names and open GitHub Issues.
3. **Stage 3 — Deterministic Pass & Secret Scrubbing (0 Tokens)**:
   * Extracts completed (`- [x]`) and pending (`- [ ]`) checkboxes, calculates completion percentage, and flags `TODO` / `FIXME` lines.
   * Truncates oversized files (retaining the first 8,000 + last 2,000 characters) and scrubs bearer tokens (`ghp_...`, `AIza...`, `sk-...`), credentials, and private URLs via regex.
4. **Stage 4 — Batched AI Status Pass (On Changed & AI-Enabled Repos Only)**:
   * Groups up to 8 modified, `ai_enabled` repositories into a single `google-genai` call using `response_schema=BatchRepoStatusResponse` to classify each repo into a canonical lifecycle stage:
     * `Ideation & Planning` — Architecture docs or initial scaffolding only.
     * `MVP In Progress` — Core features actively under construction; key checklist items unchecked.
     * `Debugging & Stabilization` — Feature-complete MVP with documented bugs or open issues.
     * `Ready for Next Stage` — Current milestone complete; ready for v2 enhancements.
     * `Maintenance / Parked` — Stable tool in daily use or paused >30 days.

## 4. Google AI Studio Free-Tier Optimization Strategy

To prevent `429 RESOURCE_EXHAUSTED` errors and stay within [Gemini API Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits) on a free [Google AI Studio](https://aistudio.google.com/) key:

* **Cold-Start Batching (8 Repos per Call)**: Initial sync across 32 repositories requires only 4 Gemini Flash API calls instead of 32 individual calls, paced automatically by a sliding-window token bucket.
* **Single-Call Cross-Portfolio Batching**: Compiles compressed digests of all `ai_enabled` repositories into **one single prompt** to identify:
  * **Cross-Project Synergies & Shared Modules**: Reusable components across your repos (e.g., sharing an iOS Shortcut webhook handler or SQLite helper).
  * **High-ROI "Weekend Finisher" Queue**: Projects at 80%+ completion that can reach a milestone in under 2 hours.
  * **Next-Stage Portfolio Roadmap**: 2–3 high-impact next stages per project.
* **On-Demand Single-Project Deep Dive**: Clicking **"Generate Enhancements"** on a specific project card analyzes its full harvested docs and file tree, outputting **Quick Wins (< 2 Hours)**, **Next Milestone Architecture**, and **One-Click Copyable Antigravity Prompts**.
* **Automatic Tier Fallback**: Wraps `client.models.generate_content()` with exponential backoff and automatic fallback (`gemini-2.5-pro` → `gemini-2.5-flash` → `gemini-2.5-flash-lite`) while logging RPM and RPD usage to SQLite.

## 5. SQLite Data Model (`projects.db` in WAL Mode)

| Table | Key Columns | Purpose |
| :--- | :--- | :--- |
| `repositories` | `id`, `name_with_owner`, `is_private`, `last_synced_sha`, `pushed_at`, `synced_stage`, `override_stage`, `domain_tag`, `ai_enabled`, `completion_pct`, `summary_json` | Separates GitHub/AI synced state from user overrides (`override_stage`, `domain_tag`, `ai_enabled`) so manual edits are never wiped on sync. |
| `action_items` | `id`, `repo_id`, `source_type` (`doc_checkbox`, `github_issue`, `ai_blocker`, `manual`), `title`, `file_path`, `is_completed`, `is_dismissed` | Powers the unified Action & Blocker Queue across all projects. |
| `ai_enhancements` | `id`, `repo_id` (nullable for portfolio-wide), `category` (`quick_win`, `next_stage`, `synergy`), `title`, `rationale`, `antigravity_prompt`, `status` | Stores generated Gemini enhancement cards and copy-ready Antigravity implementation prompts. |
| `api_quota_log` | `id`, `timestamp`, `model_name`, `operation_type`, `prompt_tokens`, `candidates_tokens` | Drives the live navbar badge (`Free Tier Quota: RPM / RPD`). |

## 6. Antigravity Implementation Task Checklist

* [ ] **Phase 1: Foundation, SQLite WAL Schema & Privacy Contracts**
  * [ ] Task 1.1: Initialize Python project with `fastapi`, `uvicorn`, `httpx`, `pydantic`, `google-genai`, and `python-dotenv`, plus `.env.example` documenting fine-grained read-only `GITHUB_TOKEN` and `GEMINI_API_KEY`.
  * [ ] Task 1.2: Implement `app/db.py` using SQLite with `PRAGMA journal_mode=WAL;` and create the `repositories`, `action_items`, `ai_enhancements`, and `api_quota_log` tables.
  * [ ] Task 1.3: Define Pydantic structured output schemas (`RepoStatusExtraction`, `BatchRepoStatusResponse`, `ProjectEnhancementPlan`, `CrossPortfolioStrategy`) in `app/schemas.py`.
* [ ] **Phase 2: Two-Stage GitHub GraphQL Sync & Deterministic Parser**
  * [ ] Task 2.1: Build `app/github_client.py` Stage 1 query to fetch all user repositories, `pushedAt`, `isEmpty`, `isArchived`, open issue counts, and `defaultBranchRef.target.oid` with cursor pagination.
  * [ ] Task 2.2: Build Stage 2 tree-and-blob harvester for SHA-changed repos that resolves root and `/docs` markdown files (`README.md`, `PROJECT_OVERVIEW.md`, `PLAN.md`, `TODO.md`, `ROADMAP.md`, `CLAUDE.md`, `AGENTS.md`) case-insensitively.
  * [ ] Task 2.3: Implement `app/parser.py` to deterministically extract `- [ ]` / `- [x]` checkboxes, compute completion percentages, enforce the 10k-character file ceiling, and scrub secrets/tokens via regex.
* [ ] **Phase 3: Rate-Limited Gemini Free-Tier Engine**
  * [ ] Task 3.1: Build `app/gemini_service.py` with a sliding-window RPM/RPD rate limiter, SQLite quota logger, and automatic model fallback (`gemini-2.5-pro` → `gemini-2.5-flash` → `gemini-2.5-flash-lite`).
  * [ ] Task 3.2: Implement 8-repo batched status extraction (`BatchRepoStatusResponse`) for changed `ai_enabled` repositories during sync.
  * [ ] Task 3.3: Implement the single-call Cross-Portfolio Strategist and Per-Project Deep Dive generators with copy-ready Antigravity implementation prompts.
* [ ] **Phase 4: Reactive Dashboard UI & SSE Sync Pipeline**
  * [ ] Task 4.1: Expose FastAPI endpoints (`GET /api/projects`, `PATCH /api/projects/{id}`, `GET /api/sync/stream` via SSE, `POST /api/ideate/portfolio`, `POST /api/ideate/repo/{id}`, `GET /api/quota`).
  * [ ] Task 4.2: Build the single-page frontend (`app/static/index.html` with Tailwind CSS and Alpine.js) featuring Kanban/Table view toggles, domain filters (`Family`, `Wealth`, `Hobbies`, `Hardware`), privacy toggles, and a live Free Tier quota meter.
  * [ ] Task 4.3: Build the Unified Blocker Queue, Repo Inspection Drawer, and Gemini Enhancement Studio with one-click **"Copy Antigravity Prompt"** buttons.
