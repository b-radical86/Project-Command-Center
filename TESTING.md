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
```

---

## 3. Manual QA Verification Checklist

Before pushing any major UI or backend refactor:
- [ ] **Kanban Board**: Drag or select a new lifecycle stage for a project; verify the stage updates immediately on the card.
- [ ] **Stage Persistence**: Refresh the page; verify that the manual stage override persists.
- [ ] **AI Toggle**: Click `AI On`/`AI Off` on a card; verify the badge reflects the change and updates SQLite.
- [ ] **Blockers View**: Switch to the **Blockers** tab; verify all pending blocker action items are visible with their source files.
- [ ] **AI Deep Dive Drawer**: Click **AI Deep Dive ✦** in the drawer; click **Analyze Now**; verify Quick Wins and Next Milestones appear with a working **Copy Antigravity Prompt** button.
- [ ] **Telemetry Pill**: Verify that the top navigation badge displays `Model: nemotron-3-ultra-550b-a55b:free`, live RPM, and token count.
