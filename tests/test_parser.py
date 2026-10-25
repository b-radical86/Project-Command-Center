import pytest
from app.parser import (
    scrub_secrets,
    truncate_text,
    parse_markdown_content,
    process_harvested_docs,
    evaluate_project_status,
)


def test_scrub_secrets_comprehensive():
    """Verify regex redactor cleans all known secret formats without leaking keys."""
    fake_gh = "gho_" + ("a" * 36)
    fake_or = "sk-or-v1-" + ("b" * 64)
    fake_gemini = "AIza" + ("c" * 35)
    fake_openai = "sk-" + ("d" * 32)
    fake_resend = "re_" + ("e" * 24)

    sample = f"""
    GITHUB_TOKEN={fake_gh}
    OPENROUTER_API_KEY={fake_or}
    GEMINI_API_KEY={fake_gemini}
    OPENAI_API_KEY={fake_openai}
    RESEND_KEY={fake_resend}
    DB_URL=postgres://user:secretpassword@localhost:5432/mydb
    RSA_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0\n-----END RSA PRIVATE KEY-----
    EMAIL=developer@example.com
    """

    cleaned = scrub_secrets(sample)

    assert "[REDACTED_GH_OAUTH]" in cleaned
    assert "[REDACTED_OPENROUTER_KEY]" in cleaned
    assert "[REDACTED_GEMINI_KEY]" in cleaned
    assert "[REDACTED_API_KEY]" in cleaned
    assert "[REDACTED_RESEND_KEY]" in cleaned
    assert "://user:[REDACTED_PWD]@" in cleaned
    assert "[REDACTED_PRIVATE_KEY]" in cleaned
    assert "[REDACTED_EMAIL]" in cleaned


def test_parse_markdown_content_checklists():
    """Verify markdown checklist item parsing."""
    md = """
    # Roadmap
    - [x] Initial design
    - [x] Scaffold repository
    - [ ] Add unit tests
    - [ ] Deploy to staging
    * [x] Star asterisk format
    * [ ] Open asterisk format
    """
    res = parse_markdown_content(md, file_path="ROADMAP.md")
    assert res["total_checkboxes"] == 6
    assert res["completed_count"] == 3
    assert res["pending_count"] == 3
    assert res["completion_pct"] == 50.0
    assert len(res["completed_items"]) == 3
    assert len(res["pending_items"]) == 3


def test_process_harvested_docs():
    """Verify multi-doc aggregation and completion percentage."""
    docs = {
        "README.md": "# Readme\n- [x] Step 1\n- [ ] Step 2",
        "ROADMAP.md": "# Roadmap\n- [x] Phase 1\n- [x] Phase 2",
    }
    processed = process_harvested_docs(docs)
    assert processed["total_checkboxes"] == 4
    assert processed["total_completed"] == 3
    assert processed["total_pending"] == 1
    assert processed["completion_pct"] == 75.0
    assert len(processed["all_action_items"]) == 1


def test_truncate_text():
    """Verify text truncation safeguards."""
    long_text = "A" * 15000
    truncated = truncate_text(long_text)
    assert len(truncated) <= 10100
    assert "... [TRUNCATED 5000 CHARACTERS FOR EFFICIENCY] ..." in truncated


def test_evaluate_project_status_heuristics():
    """Verify status evaluation for mature projects without checklists."""
    # 1. Mature repo with 0 checkboxes but full docs suite
    docs = {
        "README.md": "Overview",
        "ARCHITECTURE.md": "Arch",
        "HANDOVER.md": "Handover",
        "REQUIREMENTS.md": "Reqs",
        "SECURITY.md": "Sec",
        "OPERATIONS.md": "Ops",
        "TESTING.md": "Testing",
    }
    processed = {"completion_pct": 0.0, "total_checkboxes": 0, "sanitized_docs": docs}
    metrics = {"code_files_count": 10, "has_tests": True, "has_ci": False}
    pct, stage = evaluate_project_status(processed, metrics, commit_count=5, root_files=["run.sh", "requirements.txt"])
    assert pct >= 80.0
    assert stage == "Ready for Next Stage"

    # 2. Early MVP project with spec
    processed_early = {"completion_pct": 0.0, "total_checkboxes": 0, "sanitized_docs": {"project_plan.md": "Plan"}}
    metrics_early = {"code_files_count": 2, "has_tests": False, "has_ci": False}
    pct_early, stage_early = evaluate_project_status(processed_early, metrics_early, commit_count=2, root_files=[])
    assert 25.0 <= pct_early <= 60.0
    assert stage_early == "MVP In Progress"

    # 3. Empty repo
    processed_empty = {"completion_pct": 0.0, "total_checkboxes": 0, "sanitized_docs": {}}
    pct_empty, stage_empty = evaluate_project_status(processed_empty, None, commit_count=0, root_files=[])
    assert pct_empty == 0.0
    assert stage_empty == "Ideation & Planning"

