# REQUIREMENTS.md — System Requirements & Specifications

## 1. Product Objective
The **Project Command Center** is a unified developer dashboard that gives a multi-project engineer immediate visibility into their entire portfolio of repositories. It combines automated local file analysis with GitHub remote tracking and leverages free-tier AI models to identify blockers, cross-project synergies, and copy-ready implementation prompts.

---

## 2. Functional Requirements (FR)

| ID | Requirement | Description | Status |
| :--- | :--- | :--- | :--- |
| **FR-01** | **Multi-Repository Discovery** | Scan local sibling directories (`..`) for Git repositories and fetch remote repositories from GitHub via GraphQL API. | **Implemented** |
| **FR-02** | **Document & Checklist Extraction** | Harvest markdown documentation (`README.md`, `ROADMAP.md`, `ARCHITECTURE.md`) and parse checklist items (`- [ ]`, `- [x]`). | **Implemented** |
| **FR-03** | **Automated Secret Scrubbing** | Redact GitHub tokens, OpenRouter tokens, Gemini keys, AWS keys, and private keys from all harvested documents before storage or LLM submission. | **Implemented** |
| **FR-04** | **Hybrid Stage Classification** | Classify projects into 5 canonical stages (`Ideation & Planning`, `MVP In Progress`, `Debugging & Stabilization`, `Ready for Next Stage`, `Maintenance / Parked`) using deterministic heuristics and LLM verification. | **Implemented** |
| **FR-05** | **User Stage Override** | Allow user to manually change any repository's stage from the UI, persisting the change in SQLite across syncs. | **Implemented** |
| **FR-06** | **OpenRouter Free-Tier Waterfall** | Execute AI generation exclusively against free-tier OpenRouter models in strict priority order with automatic error fallback. | **Implemented** |
| **FR-07** | **Real-Time Sync Telemetry** | Stream live progress updates to the frontend via Server-Sent Events (SSE) during discovery, parsing, and AI classification. | **Implemented** |
| **FR-08** | **Unified Blocker Queue** | Aggregate unresolved issues and blocker action items across all projects in a dedicated radar view. | **Implemented** |
| **FR-09** | **Copy-Ready Antigravity Prompts** | Generate self-contained, copy-ready AI instructions for quick wins (< 2 hrs) and next milestones. | **Implemented** |
| **FR-10** | **Per-Repository AI Toggle** | Allow developers to toggle AI analysis on or off per repository to protect sensitive proprietary projects. | **Implemented** |

---

## 3. Non-Functional Requirements (NFR)

| ID | Requirement | Description | Target Metric |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **Operating Cost** | Zero ongoing cloud API spend by utilizing free-tier OpenRouter models and local execution. | \$0.00 / month |
| **NFR-02** | **Rate Limiting & Pacing** | Prevent HTTP 429 quota exhaustion on free-tier LLM endpoints. | 1.0s minimum interval, 8-repo batching |
| **NFR-03** | **Data Privacy & Secrecy** | Zero credential exfiltration; credentials must never be committed or transmitted to LLMs. | 100% regex sanitization pass |
| **NFR-04** | **Local Performance** | Instant initial dashboard load time from local SQLite cache. | < 200ms initial page load |
| **NFR-05** | **Portability** | Zero heavy infrastructure dependencies (Docker, Redis, external Postgres not required). | Single Python venv + SQLite |
| **NFR-06** | **Resilience** | System continues functioning if GitHub or OpenRouter is offline. | Local cached data displayed normally |
