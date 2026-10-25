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
