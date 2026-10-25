import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects.db"))

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Repositories table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS repositories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name_with_owner TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        owner TEXT NOT NULL,
        is_private INTEGER NOT NULL DEFAULT 0,
        is_archived INTEGER NOT NULL DEFAULT 0,
        is_empty INTEGER NOT NULL DEFAULT 0,
        description TEXT,
        html_url TEXT,
        pushed_at TEXT,
        last_synced_sha TEXT,
        synced_stage TEXT DEFAULT 'Ideation & Planning',
        override_stage TEXT,
        domain_tag TEXT DEFAULT 'General',
        ai_enabled INTEGER NOT NULL DEFAULT 1,
        completion_pct REAL DEFAULT 0.0,
        open_issues_count INTEGER DEFAULT 0,
        summary_json TEXT,
        last_synced_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Action items table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS action_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo_id INTEGER NOT NULL,
        source_type TEXT NOT NULL, -- 'doc_checkbox', 'github_issue', 'ai_blocker', 'manual'
        title TEXT NOT NULL,
        file_path TEXT,
        line_number INTEGER,
        is_completed INTEGER NOT NULL DEFAULT 0,
        is_dismissed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
    );
    """)

    # 3. AI enhancements table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_enhancements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo_id INTEGER, -- nullable for portfolio-wide synergies
        category TEXT NOT NULL, -- 'quick_win', 'next_stage', 'synergy'
        title TEXT NOT NULL,
        rationale TEXT NOT NULL,
        antigravity_prompt TEXT NOT NULL,
        status TEXT DEFAULT 'suggested', -- 'suggested', 'accepted', 'completed', 'dismissed'
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
    );
    """)

    # 4. API quota log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS api_quota_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        model_name TEXT NOT NULL,
        operation_type TEXT NOT NULL, -- 'batch_status', 'portfolio_brainstorm', 'deep_dive'
        prompt_tokens INTEGER DEFAULT 0,
        candidates_tokens INTEGER DEFAULT 0,
        status TEXT DEFAULT 'success' -- 'success', 'rate_limited', 'failed'
    );
    """)

    conn.commit()
    conn.close()

def log_api_usage(model_name: str, operation_type: str, prompt_tokens: int = 0, candidates_tokens: int = 0, status: str = "success"):
    conn = get_connection()
    try:
        now_utc = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO api_quota_log (timestamp, model_name, operation_type, prompt_tokens, candidates_tokens, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (now_utc, model_name, operation_type, prompt_tokens, candidates_tokens, status))
        conn.commit()
    finally:
        conn.close()

def get_quota_telemetry() -> Dict[str, Any]:
    conn = get_connection()
    try:
        # Requests in the last 60 seconds (RPM)
        rpm_row = conn.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(prompt_tokens + candidates_tokens), 0) as tokens
            FROM api_quota_log
            WHERE datetime(timestamp) >= datetime('now', '-60 seconds')
              AND status != 'failed'
        """).fetchone()

        # Requests in the current UTC day (RPD)
        rpd_row = conn.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(prompt_tokens + candidates_tokens), 0) as tokens
            FROM api_quota_log
            WHERE date(timestamp) = date('now')
              AND status != 'failed'
        """).fetchone()

        rpm_count = rpm_row["count"] if rpm_row else 0
        rpm_tokens = rpm_row["tokens"] if rpm_row else 0
        rpd_count = rpd_row["count"] if rpd_row else 0
        rpd_tokens = rpd_row["tokens"] if rpd_row else 0

        # Limits for standard free tier: 15 RPM, 1500 RPD, 1M TPM
        return {
            "rpm": rpm_count,
            "rpm_limit": 15,
            "rpm_tokens": rpm_tokens,
            "tpm_limit": 1000000,
            "rpd": rpd_count,
            "rpd_limit": 1500,
            "rpd_tokens": rpd_tokens,
        }
    finally:
        conn.close()
