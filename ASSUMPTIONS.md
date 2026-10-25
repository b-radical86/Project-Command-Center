# ASSUMPTIONS.md — Technical & Operational Assumptions

This document records the underlying assumptions made during the design and development of the **Project Command Center**, categorized by domain and tracked for empirical validation.

---

## 1. Environment & Infrastructure Assumptions

| ID | Assumption | Rationale | Validation Status |
| :--- | :--- | :--- | :--- |
| **ENV-01** | Running in a POSIX-compliant environment (macOS / Linux). | Bash scripts (`run.sh`) and path manipulations assume forward slashes. | **Validated** (Running on macOS with Zsh/Bash). |
| **ENV-02** | Python 3.10+ runtime available in `.venv`. | Modern typing (`list[str]`, `|` union operators) and Pydantic v2. | **Validated** (Tested on Python 3.15). |
| **ENV-03** | Local single-tenant execution. | SQLite WAL mode without network locking or multi-user auth guards. | **Validated** (Designed as personal developer command center). |
| **ENV-04** | Port `8000` is locally available. | Default port for FastAPI/Uvicorn server. | **Validated** (Configurable via `PORT` in `.env`). |

---

## 2. Directory & Local Git Assumptions

| ID | Assumption | Rationale | Validation Status |
| :--- | :--- | :--- | :--- |
| **DIR-01** | Sibling directory discovery (`..`). | Local projects are organized under common root coding directories (e.g. `Documents/Coding/Antigravity/..`). | **Validated** (Matches user workspace layout). |
| **DIR-02** | Valid Git roots contain `.git`. | Local scanner checks for `.git` presence to identify repository boundaries. | **Validated**. |
| **DIR-03** | Local folder name matches GitHub repository name. | Matches GitHub repo `name` with local directory basename for metadata merging. | **Validated** (Falls back to remote-only if local directory absent). |

---

## 3. GitHub API Assumptions

| ID | Assumption | Rationale | Validation Status |
| :--- | :--- | :--- | :--- |
| **GH-01** | GitHub Personal Access Token or `gh auth token` provides read access. | `fetch_all_repositories` queries GraphQL `viewer { repositories }`. | **Validated** (Personal access token configured and tested). |
| **GH-02** | GitHub GraphQL API Rate Limit is 5,000 points/hr. | Standard authenticated rate limit is more than sufficient for batches of 30-100 repos. | **Validated**. |

---

## 4. OpenRouter & AI Engine Assumptions

| ID | Assumption | Rationale | Validation Status |
| :--- | :--- | :--- | :--- |
| **AI-01** | OpenRouter provides free-tier model access with an API key. | Models with suffix `:free` or `openrouter/free` require a key but incur \$0 cost. | **Validated** (`nvidia/nemotron-3-ultra-550b-a55b:free` tested and verified). |
| **AI-02** | Free tier rate limits are ~20-60 RPM. | Rate-pacing at 1.0s and 8-repo batching ensures zero 429 quota exhaustion. | **Validated** (Paced request loop implemented). |
| **AI-03** | Thinking/reasoning models may place responses in `message.reasoning`. | DeepSeek-R1 and similar architectures output thought tokens; parser must extract JSON if `content` is empty. | **Validated** (Fallback parser implemented in `openrouter_service.py`). |
| **AI-04** | Certain free endpoints have restrictions (e.g. `thinkingmachines/inkling:free` gating). | Waterfall cascade gracefully skips 403/404 models and reaches operational tiers. | **Validated** (Waterfall skipped inkling 403 and proceeded). |

---

## 5. Lifecycle Stage Maturity Heuristics

| ID | Assumption | Rationale | Validation Status |
| :--- | :--- | :--- | :--- |
| **HEUR-01** | High action item completion (> 70%) indicates maturity. | Repositories with completed task lists and stable tests should be in `Ready for Next Stage`. | **Validated**. |
| **HEUR-02** | User manual stage overrides must be immutable to auto-sync. | An automated sync must never overwrite a developer's explicit manual stage selection. | **Validated** (`stage_override` takes absolute precedence). |
| **HEUR-03** | Brand new or early repos without tests/docker default to `MVP In Progress` or `Ideation`. | Protects projects in active genesis from premature completion classification. | **Validated**. |
