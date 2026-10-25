# Project Command Center ⚡

> **Unified Developer Command Center & OpenRouter AI Studio for Multi-Repository Portfolios**

Project Command Center is a local-first, developer-centric dashboard designed to organize, track, and strategically elevate multi-project software portfolios. It integrates local file system scans with GitHub GraphQL data, applies deterministic maturity heuristics alongside free-tier OpenRouter AI models, and produces copy-ready Antigravity AI prompts for rapid implementation.

---

## Key Features

- **Hybrid Discovery & Real-Time Sync**:
  - Automatically identifies local Git workspaces alongside GitHub remote metadata via GitHub GraphQL.
  - Extracts task checklists, documentation assets (`README.md`, `ROADMAP.md`, `ARCHITECTURE.md`), and issue backlogs.
- **OpenRouter Free-Tier AI Engine**:
  - Automatically analyzes repositories using an enterprise-grade free-tier model waterfall:
    1. `nvidia/nemotron-3-ultra-550b-a55b:free`
    2. `nvidia/nemotron-3.5-super-vl:free`
    3. `thinkingmachines/inkling:free`
    4. `nvidia/nemotron-3-super-120b-a12b:free`
    5. `openrouter/free`
  - Strict JSON validation via Pydantic schemas with automatic reasoning-token fallback.
- **Stage Lifecycle Classification**:
  - Classifies projects into 5 canonical stages:
    - `Ideation & Planning`
    - `MVP In Progress`
    - `Debugging & Stabilization`
    - `Ready for Next Stage`
    - `Maintenance / Parked`
  - User override capabilities that persist across syncs.
- **Centralized Blocker Queue**:
  - Surfaces active architectural and implementation blockers across all projects in a dedicated radar view.
- **Copy-Ready Antigravity Prompts**:
  - Generates precise, high-context prompts for Antigravity pair programming, enabling single-click task kickoff.
- **Real-Time SSE Streaming**:
  - Server-Sent Events (SSE) provide live progress telemetry during discovery, sanitization, and AI batch processing.

---

## Quick Start

### 1. Prerequisites
- **Python 3.10+** (Tested on Python 3.15)
- **GitHub Account** (Optional: GitHub CLI `gh` installed and authenticated, or a personal access token)
- **OpenRouter API Key** (Free tier available at [openrouter.ai/keys](https://openrouter.ai/keys))

### 2. Setup & Installation
```bash
# Clone the repository
git clone https://github.com/b-radical86/Project-Command-Center.git
cd Project-Command-Center

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

### 3. Configure Credentials in `.env`
Edit `.env` (strictly gitignored):
```env
GITHUB_TOKEN=gho_your_github_token_here
OPENROUTER_API_KEY=sk-or-v1-your_openrouter_api_key_here
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
HOST=127.0.0.1
PORT=8000
```

### 4. Run Application
```bash
chmod +x run.sh
./run.sh
```
Open your browser at **`http://127.0.0.1:8000`**.

---

## Documentation Framework

This repository adheres to an enterprise developer documentation framework. Refer to specific files for deep dives:

| Document | Purpose |
| :--- | :--- |
| **[`AGENTS.md`](AGENTS.md)** | Permanent instructions & engineering standards for AI agents |
| **[`ARCHITECTURE.md`](ARCHITECTURE.md)** | System topology, component interactions, and data model |
| **[`ASSUMPTIONS.md`](ASSUMPTIONS.md)** | Technical assumptions, rate limits, and heuristics |
| **[`DECISIONS.md`](DECISIONS.md)** | Architecture Decision Records (ADRs) |
| **[`HANDOVER.md`](HANDOVER.md)** | Live session state and onboarding for incoming agents |
| **[`REQUIREMENTS.md`](REQUIREMENTS.md)** | Product and functional specification |
| **[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md)** | Known bugs, limitations, and technical debt |
| **[`TESTING.md`](TESTING.md)** | Test strategies, test suites, and verification commands |
| **[`SECURITY.md`](SECURITY.md)** | Threat model, secret scrubbing, and privacy controls |
| **[`CHANGELOG.md`](CHANGELOG.md)** | Chronological record of material changes |
| **[`OPERATIONS.md`](OPERATIONS.md)** | Deployment, monitoring, logging, and troubleshooting |
