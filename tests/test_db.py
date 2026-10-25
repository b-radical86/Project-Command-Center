import pytest
import sqlite3
import os
from app.db import get_connection, init_db, log_api_usage, get_quota_telemetry


def test_database_initialization(tmp_path, monkeypatch):
    """Verify tables are initialized with WAL mode in SQLite."""
    test_db = str(tmp_path / "test_projects.db")
    monkeypatch.setattr("app.db.DB_PATH", test_db)

    init_db()
    assert os.path.exists(test_db)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {"repositories", "action_items", "ai_enhancements", "api_quota_log"}
        assert expected_tables.issubset(tables)

        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"


def test_api_quota_logging_and_telemetry(tmp_path, monkeypatch):
    """Verify API usage logging and quota summary calculations."""
    test_db = str(tmp_path / "test_projects.db")
    monkeypatch.setattr("app.db.DB_PATH", test_db)
    init_db()

    # Log several successful and failed calls
    log_api_usage(
        model_name="nvidia/nemotron-3-ultra-550b-a55b:free",
        operation_type="batch_status",
        prompt_tokens=500,
        candidates_tokens=150,
        status="success"
    )
    log_api_usage(
        model_name="nvidia/nemotron-3-ultra-550b-a55b:free",
        operation_type="deep_dive",
        prompt_tokens=800,
        candidates_tokens=300,
        status="success"
    )

    telemetry = get_quota_telemetry()
    assert telemetry["provider"] == "OpenRouter"
    assert telemetry["rpm"] == 2
    assert telemetry["rpm_tokens"] == 1750
    assert telemetry["rpd"] == 2
    assert telemetry["rpd_tokens"] == 1750


def test_ai_enhancements_schema_and_description(tmp_path, monkeypatch):
    """Verify ai_enhancements table supports plain-English description column."""
    test_db = str(tmp_path / "test_projects.db")
    monkeypatch.setattr("app.db.DB_PATH", test_db)
    init_db()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(ai_enhancements);")
        columns = {row[1] for row in cursor.fetchall()}
        assert "description" in columns
        assert "antigravity_prompt" in columns
        assert "rationale" in columns

        # Insert a sample enhancement with plain description
        cursor.execute("""
            INSERT INTO ai_enhancements (category, title, description, rationale, antigravity_prompt)
            VALUES ('synergy', 'Shared Auth Module', 'Lets users log in with the same account across all apps.', 'Eliminates JWT duplication across repos.', 'Create shared auth lib...')
        """)
        conn.commit()

        cursor.execute("SELECT title, description, antigravity_prompt FROM ai_enhancements WHERE title = 'Shared Auth Module'")
        row = cursor.fetchone()
        assert row["title"] == "Shared Auth Module"
        assert row["description"] == "Lets users log in with the same account across all apps."
        assert row["antigravity_prompt"] == "Create shared auth lib..."
