# DECISIONS.md — Architecture Decision Records (ADRs)

This log records major architectural and technical decisions, their context, alternatives considered, and consequences.

---

## ADR-001: Local-First Architecture with SQLite WAL Mode

- **Date**: 2026-10-25
- **Status**: Accepted
- **Context**: The user manages multiple software repositories across local folders and GitHub. The solution needed fast query performance, persistent caching of summaries and checklists, and zero complex cloud infrastructure overhead (e.g. no external Postgres or Redis).
- **Decision**: Use a single-node FastAPI application backed by a local SQLite 3 database operating in Write-Ahead Logging (`WAL`) mode (`PRAGMA journal_mode=WAL`).
- **Consequences**:
  - *Positive*: Zero-latency queries, file-based persistence (`projects.db`), trivial backup and portability, zero hosting cost.
  - *Negative*: Not designed for multi-tenant, distributed cloud deployments.
- **Alternatives Considered**:
  - PostgreSQL container via Docker Compose (rejected as excessive operational overhead for a local command center).
  - Pure JSON file storage (rejected due to lack of relational querying and concurrent write locking).

---

## ADR-002: Migration from Google Gemini Direct API to OpenRouter

- **Date**: 2026-10-25
- **Status**: Accepted
- **Context**: Earlier builds relied on Google Gemini API (`google-genai` SDK). Frequent model deprecations (e.g., `gemini-2.5-flash` 404s) and rate-limit friction led the user to request a shift to OpenRouter for vendor-neutral model access and resilient failover.
- **Decision**: Migrate the entire LLM service layer to OpenRouter (`https://openrouter.ai/api/v1`) using the standard `openai` Python SDK. Retain backward-compatible re-exports in `app/gemini_service.py` to prevent breaking existing imports.
- **Consequences**:
  - *Positive*: Access to diverse multi-vendor models (Nvidia Nemotron, Meta Llama, Anthropic Claude, DeepSeek, etc.) behind a single API key; flexible fallback routing.
  - *Negative*: Requires managing OpenRouter-specific endpoints and free-tier harness restrictions.
- **Alternatives Considered**:
  - Retain direct Gemini API with dynamic model version discovery (rejected by user request).
  - LiteLLM proxy (rejected as an unnecessary dependency when `openai` SDK works directly with OpenRouter).

---

## ADR-003: Strict Free-Tier Model Waterfall Selection

- **Date**: 2026-10-25
- **Status**: Accepted
- **Context**: The user explicitly instructed that the application **ONLY** use free-tier models and defined an exact priority waterfall to eliminate API costs while maintaining high reasoning quality.
- **Decision**: Enforce the exact 5-tier waterfall in `app/openrouter_service.py`:
  1. `nvidia/nemotron-3-ultra-550b-a55b:free`
  2. `nvidia/nemotron-3.5-super-vl:free`
  3. `thinkingmachines/inkling:free`
  4. `nvidia/nemotron-3-super-120b-a12b:free`
  5. `openrouter/free`
- **Consequences**:
  - *Positive*: \$0 operating cost; automatic cascade if any individual model endpoint experiences downtime or restrictive harness gating.
  - *Negative*: Free endpoints may experience transient congestion; resolved by the multi-tier cascade and 1.0s pacing.

---

## ADR-004: In-Memory Secret Sanitization Pipeline (`app/parser.py`)

- **Date**: 2026-10-25
- **Status**: Accepted
- **Context**: Sending markdown files, documentation, and code excerpts to third-party LLMs introduces the risk of leaking API tokens (`GITHUB_TOKEN`, `OPENROUTER_API_KEY`), private keys, or internal file paths.
- **Decision**: Build an automated regex-based redaction scrubber in `app/parser.py`. Every markdown document harvested from local repositories or GitHub must pass through `sanitize_document()` prior to persistence or AI prompt generation.
- **Consequences**:
  - *Positive*: Prevents accidental credential exfiltration to external LLM providers.
  - *Negative*: Regular expressions must be actively maintained as new token formats emerge.

---

## ADR-005: Hybrid Stage Classification (Deterministic Heuristics + LLM Verification)

- **Date**: 2026-10-25
- **Status**: Accepted
- **Context**: Relying purely on an LLM to classify repository stages led to mature projects (e.g. `Investment Research Aggregator`) being misclassified into early stages (`Ideation & Planning`), while early projects were misclassified as ready.
- **Decision**: Implement a two-tiered classification engine:
  1. Deterministic baseline scoring based on file assets (tests directory, Dockerfile, README, completed vs pending checklist items).
  2. LLM contextual analysis that refines the stage without contradicting established maturity metrics.
  3. Persistent manual stage overrides (`stage_override`) in the database that always supersede automated detections.
- **Consequences**:
  - *Positive*: Rock-solid stage consistency; mature projects stay in `Ready for Next Stage`; early projects stay in `MVP In Progress`.
