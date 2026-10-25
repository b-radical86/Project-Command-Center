import pytest
import os
from app.telemetry_scanner import scan_repo_telemetry, check_port_listening, extract_env_variable_names
from fastapi.testclient import TestClient
from app.main import app


def test_extract_env_variable_names_no_values():
    """Verify that only key names are parsed and no values are retained."""
    content = """
    # Comments should be ignored
    OPENROUTER_API_KEY=sk-or-v1-secretvalue1234567890
    GITHUB_TOKEN=ghp_dummytoken987654321
    HOST=0.0.0.0
    PORT=8000
    export DB_PATH=/path/to/db.sqlite
    """
    keys = extract_env_variable_names(content)
    assert "OPENROUTER_API_KEY" in keys
    assert "GITHUB_TOKEN" in keys
    assert "HOST" in keys
    assert "PORT" in keys
    assert "DB_PATH" in keys
    # Verify no secret values leaked in output
    for k in keys:
        assert "=" not in k
        assert "secretvalue" not in k
        assert "dummytoken" not in k


def test_scan_repo_telemetry_synthetic(tmp_path):
    """Test deterministic static inspection on a mock repository tree."""
    repo_dir = tmp_path / "synthetic-project"
    repo_dir.mkdir()

    # Create requirements with modern and legacy SDKs
    (repo_dir / "requirements.txt").write_text("fastapi>=0.100.0\nuvicorn>=0.20.0\ngoogle-generativeai>=0.3.0\npydantic>=2.0\npytest>=8.0\n")
    (repo_dir / ".env.example").write_text("GEMINI_API_KEY=your_key_here\nDATABASE_URL=sqlite:///test.db\nSECRET_KEY=change_me\n")
    (repo_dir / ".env").write_text("GEMINI_API_KEY=actual_key\nDATABASE_URL=sqlite:///live.db\n")
    (repo_dir / "run.sh").write_text("#!/bin/bash\nuvicorn app.main:app --port 8000\n")
    (repo_dir / "AGENTS.md").write_text("# AGENTS.md Operating Contract\n")
    (repo_dir / "README.md").write_text("# Synthetic Project\n")

    # Add code file mentioning model
    src_dir = repo_dir / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("import google.generativeai as genai\nmodel = genai.GenerativeModel('gemini-1.5-flash')\n")

    telemetry = scan_repo_telemetry(str(repo_dir), domain_tag="General")

    # 1. AI Linkage
    assert "Google AI Studio (Gemini)" in telemetry["ai_linkage"]["providers"]
    assert telemetry["ai_linkage"]["billing_tier"] == "Free Tier"
    assert telemetry["ai_linkage"]["governance_posture"] == "Free Tier Consumer API"
    assert telemetry["ai_linkage"]["governance_alert"] is None

    # 2. SDK Currency & Deprecation
    assert len(telemetry["sdk_currency"]["deprecation_warnings"]) > 0
    assert any("google.generativeai" in w for w in telemetry["sdk_currency"]["deprecation_warnings"])
    assert "gemini-1.5-flash" in telemetry["sdk_currency"]["detected_models"]
    assert telemetry["sdk_currency"]["migration_prompt"] is not None

    # 3. Secret Readiness
    assert telemetry["secret_readiness"]["is_ready"] is False # Missing SECRET_KEY
    assert "SECRET_KEY" in telemetry["secret_readiness"]["missing_keys"]
    assert "GEMINI_API_KEY" in telemetry["secret_readiness"]["present_keys"]

    # 4. Runtime Topology
    assert "FastAPI" in telemetry["runtime_topology"]["execution_target"]
    assert telemetry["runtime_topology"]["port"] == 8000

    # 5. Engineering Maturity
    assert telemetry["engineering_maturity"]["score"] >= 60
    assert telemetry["engineering_maturity"]["has_schema_validation"] is True
    assert telemetry["engineering_maturity"]["has_agent_context"] is True


def test_wealth_data_residency_policy_alert(tmp_path):
    """Verify that repositories tagged 'Wealth' that connect to free consumer APIs trigger a governance warning."""
    wealth_repo = tmp_path / "private-ledger"
    wealth_repo.mkdir()
    (wealth_repo / "requirements.txt").write_text("google-genai>=1.0.0\n")
    (wealth_repo / ".env.example").write_text("GEMINI_API_KEY=\n")
    (wealth_repo / ".env").write_text("GEMINI_API_KEY=test\n")

    # Tagged Wealth with Consumer Free Tier API
    telemetry = scan_repo_telemetry(str(wealth_repo), domain_tag="Wealth", is_private=True)
    assert telemetry["ai_linkage"]["governance_alert"] is not None
    assert "Policy Warning" in telemetry["ai_linkage"]["governance_alert"]
    assert "Wealth project links to consumer free-tier AI API" in telemetry["ai_linkage"]["governance_alert"]


def test_api_secret_lookup_endpoint():
    """Verify the cross-repo secret rotation blast radius endpoint."""
    client = TestClient(app)
    res = client.get("/api/matrix/secret-lookup")
    assert res.status_code == 200
    data = res.json()
    assert "all_secret_keys" in data
    assert isinstance(data["all_secret_keys"], list)

    # Query for a known key
    res_key = client.get("/api/matrix/secret-lookup?key_name=OPENROUTER_API_KEY")
    assert res_key.status_code == 200
    key_data = res_key.json()
    assert key_data["queried_key"] == "OPENROUTER_API_KEY"
    assert "affected_repos" in key_data
