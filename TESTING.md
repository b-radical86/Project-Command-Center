# TESTING.md — Testing Strategy & Verification Protocols

## 1. Overview & Quality Standard

The **Project Command Center** requires all changes to be verified against regression before committing. As an enterprise software project, testing covers:
1. **Module Import & Syntax Integrity**
2. **Database Schema & Migration Validation**
3. **Secret Redaction & Document Sanitization**
4. **OpenRouter Multi-Model Waterfall & Schema Parsing**
5. **FastAPI Endpoints & SSE Streaming**

---

## 2. Automated Test Commands

### 2.0 Consolidated Pytest Test Suite (Recommended)
```bash
# Run the full automated test suite across db, parser, openrouter, local_scanner, ideas, and telemetry_scanner
pytest -v
# Verified: 23 passed across all modules
```

Execute the following test suite from the repository root with `.venv` active:

### 2.1 Smoke & Import Verification
```bash
.venv/bin/python3 -c "
import app.main
import app.openrouter_service
import app.db
import app.parser
import app.github_client
print('✅ All core application modules imported cleanly without errors.')
"
```

### 2.2 Database Initialization & Quota Telemetry Test
```bash
.venv/bin/python3 -c "
from app.db import init_db, get_quota_telemetry
init_db()
telemetry = get_quota_telemetry()
assert telemetry['provider'] == 'OpenRouter', f'Expected OpenRouter, got {telemetry[\"provider\"]}'
print('✅ Database initialized and quota telemetry verified:', telemetry)
"
```

### 2.3 Secret Scrubber Verification
```bash
.venv/bin/python3 -c "
from app.parser import scrub_secrets
sample = 'GITHUB_TOKEN=gho_' + ('a' * 36) + '\n' + 'OPENROUTER_KEY=sk-or-v1-' + ('b' * 64)
clean = scrub_secrets(sample)
assert '[REDACTED_GH_OAUTH]' in clean
assert '[REDACTED_OPENROUTER_KEY]' in clean
print('✅ Secret sanitization pipeline verified:\n', clean)
"
```

### 2.4 OpenRouter Waterfall & Structured Output Test
```bash
.venv/bin/python3 -c "
from app.openrouter_service import ai_engine
from app.schemas import BatchRepoStatusResponse

test_payload = [{
    'name_with_owner': 'b-radical86/test-project',
    'description': 'Test project for testing framework',
    'stage': 'MVP In Progress',
    'action_counts': {'completed': 8, 'total': 10},
    'has_tests': True
}]

res = ai_engine.generate_structured(
    prompt=f'Analyze maturity:\n{test_payload}',
    response_schema=BatchRepoStatusResponse,
    operation_type='unit_test'
)
assert len(res.repos) > 0
print(f'✅ OpenRouter Tier 1 successfully generated response for {res.repos[0].name_with_owner}: {res.repos[0].detected_stage.value}')
"
```

### 2.5 Live HTTP Endpoint Check
```bash
curl -s -f http://127.0.0.1:8000/api/quota > /dev/null && echo "✅ GET /api/quota returned 200 OK"
curl -s -f http://127.0.0.1:8000/api/projects > /dev/null && echo "✅ GET /api/projects returned 200 OK"
curl -s -f http://127.0.0.1:8000/api/matrix/secret-lookup > /dev/null && echo "✅ GET /api/matrix/secret-lookup returned 200 OK"
```

### 2.6 Telemetry & Secret Scanner Verification
```bash
.venv/bin/python3 -c "
from app.telemetry_scanner import scan_repo_telemetry
import os
telemetry = scan_repo_telemetry(os.getcwd(), 'Project Command Center', 'General')
assert telemetry['runtime']['target'] == 'FastAPI'
assert telemetry['runtime']['port'] == 8000
assert telemetry['maturity']['score'] > 80
print('✅ Telemetry scanner verified successfully on Project Command Center:\n', telemetry)
"
```

---

## 3. Manual QA Verification Checklist

Before pushing any major UI or backend refactor:
- [ ] **Comprehensive Portfolio Matrix**: Switch to the **Matrix** view; verify all projects render with telemetry badges (Governance, Model/SDK, Secret Readiness, Port heartbeat, Git drift, Maturity grade).
- [ ] **Secret Blast-Radius Filter**: Select `OPENROUTER_API_KEY` or `GEMINI_API_KEY` in the Secret Rotation lookup dropdown; verify only dependent projects are displayed and the active filter banner is dismissible.
- [ ] **Governance & Drift Filters**: Test filtering by `Free Tier Consumer API`, `Missing Required Keys`, and `Local Dirty Edits`; verify counts and cards filter immediately.
- [ ] **Kanban Board & Project Dashboard**: Click on any project card in the Kanban matrix; verify the Project Command Dashboard opens smoothly, displays project-specific blockers, key milestones, metrics, and tasks.
- [ ] **Stage Persistence**: Select a new stage inside the dashboard; refresh the page; verify that the manual stage override persists.
- [ ] **AI Toggle**: Click `AI On`/`AI Off` on a card; verify the badge reflects the change and updates SQLite.
- [ ] **Blockers View**: Switch to the **Blockers** tab; verify all pending blocker action items are visible with their source files.
- [ ] **AI Deep Dive Drawer**: Click **AI Deep Dive ✦** in the drawer; click **Analyze Now**; verify Quick Wins and Next Milestones appear with a plain-English overview, expandable technical details, and a working **Copy Antigravity Prompt** button.
- [ ] **AI Studio Strategist**: Open the **AI Studio** tab; verify suggestions show non-technical overviews, collapsible technical architecture details, and copy-ready Antigravity buttons.
- [ ] **Telemetry Pill**: Verify that the top navigation badge displays `Model: nemotron-3-ultra-550b-a55b:free`, live RPM, and token count.
