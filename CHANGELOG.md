# CHANGELOG.md — Project Version History

All notable changes to the **Project Command Center** project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.3.0] - 2026-10-25

### Added
- **Interactive Project Command Dashboard from Kanban Matrix**:
  - Made every project card on the Kanban matrix directly clickable to instantly open a dedicated Project Command Dashboard.
  - Added project-specific blocker badge to each Kanban card showing the exact count of active blockers (`summary_data.blockers`).
  - Added child event stopping (`@click.stop`) on external repository links, stage selectors, and AI toggles to prevent modal collision.
  - Expanded Slide-Over Dashboard (`max-w-3xl`) with ESC key listener (`@keydown.escape.window`).
  - Implemented a dedicated **Project Blockers** dashboard module at the top of the project view specifically listing:
    - Active architectural and dependency blockers with severity indicators.
    - Blocker action items with direct interactive completion checkboxes.
    - Clean positive state indicator when zero blockers are detected.
  - Built a comprehensive Project Command view featuring:
    - Quick metrics strip (Stage status, completion %, active blockers, tasks/issues count).
    - Lifecycle stage override dropdown and domain category switcher.
    - Dual-layer Plain-English project overview and Technical Architecture summary.
    - Key Milestones & Objectives roadmap timeline (`key_milestones`).
    - Codebase details: working tree local path with one-click copy, and key project directories.
    - Quick tasks preview with direct checkbox completion and deep drill-down tabs.

---

## [2.2.0] - 2026-10-25

### Added
- **Non-Technical Project Descriptions in AI Studio Strategist**:
  - Added `description` column to SQLite `ai_enhancements` table with automated schema migration.
  - Updated `SynergyItem`, `WeekendFinisherItem`, `RoadmapItem`, `QuickWinItem`, and `MilestoneItem` Pydantic schemas with plain-English non-technical summary fields.
  - Updated OpenRouter generation prompts in `app/openrouter_service.py` to instruct models to produce 1-2 sentence plain-English overviews free of developer jargon.
  - Updated `app/static/index.html` across all 3 AI Studio columns (Synergies, Weekend Finishers, Next Milestones) and Repo Detail Drawer to render prominent "Plain-English Overview" callout cards.
  - Added HTML5 `<details>` collapsible container for Technical Rationale & Architecture details, keeping the interface uncluttered while retaining deep technical information.
  - Maintained prominent, styled "Copy Antigravity Prompt" button with clipboard confirmation.
  - Added automated unit test `test_ai_enhancements_schema_and_description` in `tests/test_db.py` (total 19/19 tests passing).

---

## [2.1.0] - 2026-10-25

### Added
- **Historical Project Ideas Vault & Duplicate Detection**:
  - Added SQLite `project_ideas` table tracking status (`parked`, `incubating`, `under_review`, `graduated_to_repo`, `discarded`), domain tags, and revisit context notes.
  - Implemented `app/ideas_service.py` with custom domain stemmer and Jaccard + string similarity algorithm to block or warn on duplicate ideas.
  - Added REST endpoints: `GET /api/ideas`, `POST /api/ideas`, `POST /api/ideas/check-duplicate`, `PATCH /api/ideas/{id}`.
  - Added "Ideas Vault" view and modal with real-time duplicate warning banner in `app/static/index.html`.
  - Added unit test suite `tests/test_ideas.py`.
- **Multi-Root Local Workspace Discovery (`LOCAL_PROJECTS_DIR`)**:
  - Enhanced `app/local_scanner.py` with `get_projects_root_dirs()` supporting comma-separated custom paths and canonical path deduplication.
  - Added unit test suite `tests/test_local_scanner.py`.
- **Holistic Completion Scoring for Projects Without Checklists**:
  - Enhanced `evaluate_project_status` in `app/parser.py` to evaluate code metrics, entry points (`main.py`, `app.py`, `run.sh`, `requirements.txt`), and full enterprise documentation suites (`len(doc_keys) >= 6`).
  - Added unit test `test_evaluate_project_status_heuristics` in `tests/test_parser.py`.
- **Formal Pytest Automated Test Suite**:
  - Added `tests/test_parser.py` (secret scrubbing, markdown parsing, status heuristics).
  - Added `tests/test_db.py` (SQLite WAL mode initialization and quota telemetry).
  - Added `tests/test_openrouter.py` (waterfall cascade ordering, markdown fence stripping, reasoning token fallback).
  - Added `pytest>=8.0.0` dependency to `requirements.txt`.
- **OpenRouter Free-Tier Waterfall Engine**:
  - Implemented `app/openrouter_service.py` using `openai` Python SDK with strict 5-tier waterfall:
    1. `nvidia/nemotron-3-ultra-550b-a55b:free`
    2. `nvidia/nemotron-3.5-super-vl:free`
    3. `thinkingmachines/inkling:free`
    4. `nvidia/nemotron-3-super-120b-a12b:free`
    5. `openrouter/free`
  - Added thinking token reasoning fallback extractor to parse JSON when `message.content` is blank.
  - Added secret scrubber pattern for OpenRouter API keys (`sk-or-v1-`).
- **Enterprise Documentation Suite**:
  - Added 12 standardized project documents: `README.md`, `AGENTS.md`, `ARCHITECTURE.md`, `ASSUMPTIONS.md`, `DECISIONS.md`, `HANDOVER.md`, `REQUIREMENTS.md`, `KNOWN_ISSUES.md`, `TESTING.md`, `SECURITY.md`, `CHANGELOG.md`, `OPERATIONS.md`.

### Changed
- Replaced Google Gemini client with OpenRouter client.
- Refactored `app/gemini_service.py` to re-export from `app/openrouter_service.py` for backward compatibility.
- Updated UI branding, headings, and telemetry in `app/static/index.html` to reflect OpenRouter Multi-Model Engine.
- Updated `app/db.py` to record OpenRouter model telemetry, RPM (60), and token counts.

### Fixed
- Fixed Gemini API 404/503 errors caused by deprecated model endpoints.
- Handled OpenRouter harness gating (403 on `thinkingmachines/inkling:free`) via automatic waterfall cascade.

---

## [2.0.0] - 2026-10-25

### Added
- **Core Dashboard & Pipeline**:
  - FastAPI asynchronous backend with SQLite WAL mode persistence.
  - Real-time Server-Sent Events (`/api/stream/sync`) for discovery and analysis progress.
  - GitHub GraphQL v4 multi-repo query client (`app/github_client.py`).
  - Local directory discovery and markdown checklist parser (`app/parser.py`).
  - Kanban board, sortable list view, blocker radar, and AI enhancement drawer.
  - Manual stage override controls persisting to SQLite database.
