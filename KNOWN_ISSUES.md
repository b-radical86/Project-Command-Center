# KNOWN_ISSUES.md — Defect Tracking & Technical Debt

This document tracks known limitations, upstream service anomalies, unresolved defects, and technical debt items.

---

## 1. Upstream AI Provider Anomalies (OpenRouter)

### KI-01: `thinkingmachines/inkling:free` Gated by Agentic Harness (HTTP 403)
- **Description**: OpenRouter returns `403 Forbidden` with message `'thinkingmachines/inkling:free is only available on agentic harnesses'`.
- **Severity**: Low
- **Impact**: Tier 3 in the waterfall cannot be directly invoked via standard OpenAI client headers.
- **Mitigation / Workaround**: The OpenRouter waterfall in `app/openrouter_service.py` catches the 403 error automatically, logs a warning, and cascades to the next tier (`nvidia/nemotron-3-super-120b-a12b:free` or `openrouter/free`).
- **Remediation Plan**: Maintain this tier in the waterfall in case OpenRouter relaxes harness gating, while relying on Tier 1 (`nvidia/nemotron-3-ultra-550b-a55b:free`) and Tier 5 (`openrouter/free`).

### KI-02: `nvidia/nemotron-3-super-120b-a12b:free` Provider Backend 404
- **Description**: OpenRouter returns `404 Not Found` with metadata `'Function Not found for account'` from Nvidia backend provider.
- **Severity**: Low
- **Impact**: Tier 4 is temporarily unavailable upstream.
- **Mitigation / Workaround**: The engine automatically catches the 404 and fails over to `openrouter/free`.
- **Remediation Plan**: Upstream Nvidia provider maintenance issue. Monitored on sync runs.

### KI-03: Thinking / Reasoning Models Outputting to `message.reasoning`
- **Description**: DeepSeek-R1 and similar reasoning models consume tokens in the reasoning phase, occasionally returning `message.content = None` when max tokens is limited.
- **Severity**: Medium
- **Mitigation**: Implemented a fallback in `OpenRouterEngine.generate_structured()` that inspects `message.reasoning` for valid JSON substrings when `message.content` is blank.

---

## 2. Application Limitations & Technical Debt

### KI-04: Local Discovery Root Path Hardcoded to Sibling Directories
- **Description**: `app/parser.py` scans sibling directories by looking at `..`. Projects located outside this tree are only discovered if tracked on GitHub.
- **Severity**: Low
- **Workaround**: Create symlinks in the sibling directory, or rely on GitHub GraphQL remote sync.
- **Remediation Plan**: Add a `LOCAL_PROJECT_PATHS` environment variable to `.env` allowing comma-separated scan paths.

### KI-05: Test Suite Modernization (Formal Pytest Suite Needed)
- **Description**: Testing currently relies on verified Python CLI scripts rather than a consolidated `pytest` suite.
- **Severity**: Low
- **Remediation Plan**: Scaffold `tests/` directory with `test_parser.py`, `test_openrouter.py`, and `test_db.py`.
