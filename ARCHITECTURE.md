# ARCHITECTURE.md — System Architecture & Component Design

## 1. System Topology & Overview

The **Project Command Center** is a local-first application designed for single-developer portfolio orchestration. It bridges local project folders with GitHub cloud metadata and connects to OpenRouter's free-tier LLM waterfall for strategic enhancement planning.

```mermaid
graph TD
    User["Developer Browser (Alpine.js + Tailwind)"] -->|HTTP / SSE Stream| FastAPI["FastAPI Backend (app/main.py)"]
    
    subgraph Local Discovery
        FastAPI -->|Local Walk| FS["Local Git Directories (/Users/...)"]
        FastAPI -->|Read & Parse| Parser["Doc Parser & Sanitizer (app/parser.py)"]
    end
    
    subgraph GitHub Cloud
        FastAPI -->|GraphQL v4 / REST| GH["GitHub API (github.com)"]
    end
    
    subgraph Local Storage
        FastAPI -->|WAL Mode Read/Write| DB[("SQLite Database (projects.db)")]
    end
    
    subgraph AI Intelligence
        FastAPI -->|OpenAI Client| OR["OpenRouter API Gateway"]
        OR -->|Tier 1| M1["nvidia/nemotron-3-ultra-550b-a55b:free"]
        OR -->|Tier 2| M2["nvidia/nemotron-3.5-super-vl:free"]
        OR -->|Tier 3| M3["thinkingmachines/inkling:free"]
        OR -->|Tier 4| M4["nvidia/nemotron-3-super-120b-a12b:free"]
        OR -->|Tier 5| M5["openrouter/free"]
    end
```

---

## 2. Component Details

### 2.1 Frontend Layer (`app/static/index.html`)
- **Technology Stack**: Alpine.js v3, Tailwind CSS (CDN), Heroicons, EventSource (SSE).
- **Architecture**: Single Page Application (SPA) without bundler requirements.
- **Views**:
  - **Kanban Board**: Drag-and-drop or select-to-move lifecycle columns with progress bars.
  - **List / Table View**: Sortable metrics table with test status, Docker flags, and completion percentages.
  - **Blockers Radar**: Centralized tracking for unresolved issues across all repositories.
  - **AI Studio**: Cross-portfolio strategy generation (synergies, weekend quick wins, next milestones).
  - **Inspection Drawer**: Detailed inspection of harvested docs, checklists, and single-repo deep-dive AI generation.
- **Real-Time Telemetry**: Live polling (`/api/quota`) and SSE progress updates during sync (`/api/stream/sync`).

### 2.2 API Server (`app/main.py`)
- **Framework**: FastAPI with Uvicorn.
- **Asynchronous Execution**: Asynchronous endpoint handlers with background task runners for sync operations.
- **Endpoints**:
  - `GET /`: Serves static SPA dashboard.
  - `GET /api/projects`: Retrieves all enriched projects and stage classifications.
  - `GET /api/projects/{repo_id}`: Retrieves single repository details, docs, and action items.
  - `PATCH /api/projects/{repo_id}`: Updates stage overrides, domain tags, or AI toggle.
  - `GET /api/actions`: Retrieves all parsed action items and blockers.
  - `PATCH /api/actions/{action_id}`: Updates action item completion status.
  - `GET /api/enhancements`: Retrieves all generated AI enhancements and prompts.
  - `PATCH /api/enhancements/{id}`: Updates enhancement review status.
  - `POST /api/ideate/repo/{repo_id}`: Triggers single-repo deep dive and Antigravity prompt generation.
  - `POST /api/ideate/portfolio`: Triggers portfolio-wide strategic cross-cutting analysis.
  - `GET /api/quota`: Real-time OpenRouter token and rate-limiting telemetry.
  - `GET /api/sync/stream`: Server-Sent Events (SSE) stream for real-time sync progression.

### 2.3 Secret Scrubbing & Document Sanitizer (`app/parser.py`)
Before any local markdown or code snippet is stored or transmitted to OpenRouter:
- **Regex Redaction Engine**: Scrubs GitHub tokens (`ghp_`, `gho_`), OpenRouter tokens (`sk-or-v1-`), Gemini keys (`AIza`), generic API keys, private keys, AWS secrets, and database connection strings.
- **Path Stripping**: Replaces absolute user paths with relative paths.
- **Size Capping**: Caps harvested document excerpts to prevent prompt bloat and stay within free-tier context limits.

### 2.4 OpenRouter Multi-Model Waterfall (`app/openrouter_service.py`)
- **Client Protocol**: Standard OpenAI Python SDK configured with `base_url="https://openrouter.ai/api/v1"`.
- **Waterfall Mechanics**: Iterates sequentially through `FREE_TIER_WATERFALL`. If any tier fails with 403, 404, 429, or JSON schema validation errors, the next tier is executed immediately.
- **Reasoning Handling**: Automatically falls back to inspecting `message.reasoning` if the thinking model exhausts tokens before writing to `message.content`.
- **Request Pacing**: Hard-pacing at 1.0s between outgoing calls to prevent bursts on free-tier gateways.

---

## 3. Database Schema (`projects.db`)

SQLite 3 configured with Write-Ahead Logging (`WAL` mode) and `PRAGMA synchronous = NORMAL`.

### Tables
1. **`repositories`**:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `name_with_owner`: TEXT UNIQUE
   - `name`: TEXT
   - `owner`: TEXT
   - `is_private`: INTEGER (Boolean)
   - `is_archived`: INTEGER (Boolean)
   - `is_empty`: INTEGER (Boolean)
   - `description`: TEXT
   - `html_url`: TEXT
   - `pushed_at`: TEXT
   - `last_synced_sha`: TEXT
   - `synced_stage`: TEXT
   - `override_stage`: TEXT
   - `domain_tag`: TEXT
   - `ai_enabled`: INTEGER (Boolean)
   - `completion_pct`: REAL
   - `open_issues_count`: INTEGER
   - `summary_json`: TEXT
   - `last_synced_at`: TEXT
   - `created_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   - `updated_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   - `is_local`: INTEGER (Boolean)
   - `local_path`: TEXT
   - `active_branch`: TEXT
   - `commit_count`: INTEGER

2. **`action_items`**:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `repo_id`: INTEGER REFERENCES repositories(id)
   - `source_file`: TEXT
   - `title`: TEXT
   - `is_completed`: BOOLEAN DEFAULT 0
   - `is_blocker`: BOOLEAN DEFAULT 0
   - `created_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

3. **`ai_enhancements`**:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `repo_id`: INTEGER REFERENCES repositories(id)
   - `category`: TEXT ('quick_win', 'next_stage', 'synergy')
   - `title`: TEXT
   - `rationale`: TEXT
   - `antigravity_prompt`: TEXT
   - `status`: TEXT DEFAULT 'suggested'
   - `created_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

4. **`api_quota_log`**:
   - `id`: INTEGER PRIMARY KEY AUTOINCREMENT
   - `model_name`: TEXT
   - `operation_type`: TEXT
   - `prompt_tokens`: INTEGER
   - `candidates_tokens`: INTEGER
   - `status`: TEXT
   - `timestamp`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP
