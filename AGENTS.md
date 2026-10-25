# AGENTS.md — AI Coding Agent Operating Contract & Engineering Standards

## 1. Overview & Purpose
This document establishes **permanent, binding instructions** for any AI coding agent (e.g., Antigravity, Claude Code, Cursor, Copilot) operating on the **Project Command Center** codebase. 

As an enterprise-grade project, all contributors—human and AI—must maintain the highest standard of engineering rigor, strict documentation freshness, zero secret leakage, and thorough verification at every iteration.

---

## 2. Mandatory Documentation Framework Governance

Every AI agent working on this codebase **MUST** keep the project documentation up to date. Before finishing any task or user request, review and update the affected documents:

| Document | Priority | Trigger for Update | What Must Be Recorded |
| :--- | :--- | :--- | :--- |
| **`README.md`** | **Essential** | User-facing changes, installation, dependencies, CLI commands | Setup steps, feature list, running instructions |
| **`AGENTS.md`** | **Essential** | Agent workflows, guardrails, model waterfall changes | Rules of engagement, agent SOPs, model policies |
| **`ARCHITECTURE.md`** | **Essential** | New modules, data flow, DB schema changes, API endpoints | Component diagrams, database schema, data pipeline |
| **`ASSUMPTIONS.md`** | **Essential** | New business logic, heuristic weights, rate limit assumptions | Technical assumptions, validated vs unvalidated hypotheses |
| **`DECISIONS.md`** | **Essential** | Architectural choices, library migrations (e.g. Gemini -> OpenRouter) | ADR format: Context, Decision, Consequences, Alternatives |
| **`HANDOVER.md`** | **Essential** | End of every session / iteration | Current state, completed items, active tasks, next steps |
| **`REQUIREMENTS.md`** | **Essential** | Scope expansion, feature additions, user requests | Functional & non-functional requirements, verification status |
| **`KNOWN_ISSUES.md`** | **Essential** | Discovering bugs, rate limit edges, technical debt, upstream changes | Issue description, impact, workaround, remediation plan |
| **`TESTING.md`** | **Essential** | New tests, test runs, regression gaps | Testing procedures, automated checks, manual QA checklist |
| **`SECURITY.md`** | **Essential** | Secret scrubbers, credential handling, auth logic | Threat model, sanitization pipeline, auth guardrails |
| **`CHANGELOG.md`** | **Recommended** | Every commit / version milestone | Keep a Changelog format: Added, Changed, Deprecated, Fixed |
| **`OPERATIONS.md`** | **Recommended** | Daemon scripts, telemetry, ports, system dependencies | Run instructions, port configs, log locations, troubleshooting |

> [!IMPORTANT]
> **No Phantom Code Changes**: Never make functional code changes without updating `CHANGELOG.md` and `HANDOVER.md`. If an architectural decision or assumption is introduced, log it immediately in `DECISIONS.md` or `ASSUMPTIONS.md`.

---

## 3. Core Architectural Principles & Invariants

1. **Local-First & Hybrid Sync**:
   - The application inspects both local git working trees (in `..` or user-configured folders) and GitHub remote data via GraphQL (`fetch_all_repositories` and `fetch_repository_details`).
   - Local directory discovery takes precedence for code metrics and file inspections; remote GitHub sync enriches issues, PRs, and commit activity.

2. **Strict Secrecy & Zero-Leakage Pipeline**:
   - **Never commit `.env`**. Verify `.env` is gitignored before any commit.
   - `app/parser.py` contains the `sanitize_document()` scrubber. Any markdown or doc content sent to OpenRouter **MUST** pass through this scrubber.
   - Never log raw API tokens (`GITHUB_TOKEN`, `OPENROUTER_API_KEY`) to stdout, files, database logs, or SSE streams.

3. **OpenRouter AI Engine & Waterfall Rule**:
   - The AI engine **MUST ONLY** use free-tier models unless explicitly changed by the user.
   - Waterfall order (strictly enforced in `app/openrouter_service.py`):
     1. `nvidia/nemotron-3-ultra-550b-a55b:free`
     2. `nvidia/nemotron-3.5-super-vl:free`
     3. `thinkingmachines/inkling:free`
     4. `nvidia/nemotron-3-super-120b-a12b:free`
     5. `openrouter/free`
   - Requests are paced with a minimum 1.0s interval.
   - All AI calls require strict Pydantic JSON schema validation (`model_validate_json`). Thinking model outputs must fall back to parsing `message.reasoning` if `message.content` is blank.

4. **Deterministic + Heuristic Stage Classification**:
   - Project lifecycle stages:
     - `Ideation & Planning`
     - `MVP In Progress`
     - `Debugging & Stabilization`
     - `Ready for Next Stage`
     - `Maintenance / Parked`
   - Deterministic checks (tests, docker, completion %, action item ratio) compute a base stage and score. The LLM verifies context without silently regressing mature projects.
   - User overrides via the UI (`stage_override`) **always** take precedence over automated classifications.

---

## 4. Engineering Workflow & Git Hygiene

1. **Pre-flight Checks**:
   - Ensure the virtual environment (`.venv`) is activated.
   - Validate dependencies in `requirements.txt`.
   - Run syntax and import checks before pushing:
     ```bash
     .venv/bin/python3 -c "import app.main; import app.openrouter_service; import app.db"
     ```

2. **Git Commit Standards**:
   - Commit messages follow Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`.
   - Always push clean commits to `origin main`.
   - Ensure `git status` shows zero untracked credential files.

3. **Background Process Management**:
   - The FastAPI server runs on `http://127.0.0.1:8000` via `./run.sh`.
   - Do not kill background servers unless modifying deep daemon configurations; Uvicorn has hot-reload enabled via `watchfiles`.
