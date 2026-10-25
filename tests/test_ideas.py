import pytest
import sqlite3
from app.db import init_db
from app.ideas_service import (
    calculate_idea_similarity,
    find_duplicate_ideas,
    save_project_idea,
    list_project_ideas,
    update_project_idea,
)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_ideas.db")
    monkeypatch.setattr("app.db.DB_PATH", test_db)
    init_db()


def test_similarity_calculation():
    """Verify similarity scoring detects rephrased ideas and discriminates distinct ideas."""
    title1 = "Crypto Asset Portfolio Tracker"
    desc1 = "A local application to monitor cryptocurrency holdings, calculate capital gains, and sync exchange trades."

    title2 = "Cryptocurrency Portfolio Tracking Tool"
    desc2 = "Track crypto assets and holdings across exchanges with tax reporting and portfolio charts."

    distinct_title = "Smart Garden Soil Moisture Sensor"
    distinct_desc = "ESP32 automated plant irrigation system with ambient temperature and moisture telemetry."

    score_similar, _ = calculate_idea_similarity(title1, desc1, title2, desc2)
    score_distinct, _ = calculate_idea_similarity(title1, desc1, distinct_title, distinct_desc)

    assert score_similar >= 0.65
    assert score_distinct < 0.20


def test_save_and_duplicate_prevention():
    """Verify save_project_idea blocks duplicate ideas unless force=True."""
    # 1. Save original idea
    res1 = save_project_idea(
        title="Automated Real Estate Yield Analyzer",
        description="Scrapes property listings, calculates rental yields, mortgage payments, and tax depreciation.",
        domain_tag="Wealth",
        status="parked",
        notes="Not useful today while interest rates are high, but re-evaluate when capital is available."
    )
    assert res1["created"] is True
    assert res1["idea"]["id"] is not None

    # 2. Attempt to save near-duplicate idea
    res_dup = save_project_idea(
        title="Real Estate Property Yield Calculator",
        description="Tool to calculate rental yields and mortgage cash flows for property investments.",
        domain_tag="Wealth"
    )
    assert res_dup["created"] is False
    assert res_dup["reason"] == "duplicate_found"
    assert "Real Estate" in res_dup["message"]

    # 3. Save with force=True
    res_forced = save_project_idea(
        title="Real Estate Property Yield Calculator",
        description="Tool to calculate rental yields and mortgage cash flows for property investments.",
        domain_tag="Wealth",
        force=True
    )
    assert res_forced["created"] is True


def test_list_and_search_ideas():
    """Verify filtering by status, domain, and keyword search."""
    save_project_idea(
        title="Retro Arcade Emulator Frontend",
        description="Pico-8 and retro game launcher with CRT shader effects.",
        domain_tag="Hobbies",
        status="parked"
    )
    save_project_idea(
        title="B2B Invoice Reconciliation Engine",
        description="Automated matching of PDF invoices to bank statement transactions.",
        domain_tag="Work",
        status="incubating"
    )

    # Search keyword
    arcade_results = list_project_ideas(search="Arcade")
    assert len(arcade_results) == 1
    assert arcade_results[0]["title"] == "Retro Arcade Emulator Frontend"

    # Filter status
    incubating_results = list_project_ideas(status="incubating")
    assert len(incubating_results) == 1
    assert incubating_results[0]["title"] == "B2B Invoice Reconciliation Engine"

    # Filter domain
    hobbies_results = list_project_ideas(domain="Hobbies")
    assert len(hobbies_results) == 1


def test_update_idea_status_and_notes():
    """Verify updating idea status, notes, and graduation to repo."""
    saved = save_project_idea(
        title="Autonomous Night Sky Cloud Sensor",
        description="Wide angle sky camera with infrared cloud detection for amateur astronomy.",
        domain_tag="Hobbies",
        status="parked"
    )
    idea_id = saved["idea"]["id"]

    updated = update_project_idea(
        idea_id=idea_id,
        status="incubating",
        notes="Acquired wide-angle lens, revisit in spring."
    )
    assert updated["status"] == "incubating"
    assert "Acquired wide-angle lens" in updated["notes"]
