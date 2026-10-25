# SECURITY.md — Security Architecture & Data Protection

## 1. Security Philosophy & Threat Model

The **Project Command Center** operates on a **defense-in-depth, local-first privacy** model. Because this application processes developer source code, configuration files, and documentation across personal and proprietary software projects, data governance and secret leakage prevention are critical architectural priorities.

### Primary Threat Vectors:
1. **Accidental Git Exposure**: Committing API keys (`OPENROUTER_API_KEY`, `GITHUB_TOKEN`) or credentials to public or shared GitHub repositories.
2. **Third-Party LLM Exfiltration**: Transmitting sensitive proprietary source code, secrets, or internal server paths to cloud AI providers.
3. **Local Network Exposure**: Exposing the API server to unauthorized local network clients.

---

## 2. Security Controls & Protections

### 2.1 Credential Secrecy & Git Isolation
- **Strict Gitignore**: The `.env` file is explicitly gitignored and verified by `git check-ignore .env`.
- **Pre-Commit Verification**: Automated tests and git inspection ensure no untracked `.env` files are staged.
- **Template Separation**: Only `.env.example` containing dummy placeholder values is committed to version control.

### 2.2 Sanitization Pipeline (`app/parser.py`)
Before any text extracted from local markdown files or GitHub repositories is persisted or sent to OpenRouter, it is piped through `sanitize_document()`:
- **Redaction Patterns**:
  - GitHub Personal Access Tokens (`ghp_[A-Za-z0-9_]{36}`, `gho_[A-Za-z0-9_]{36}`)
  - OpenRouter API Keys (`sk-or-v1-[A-Za-z0-9]{64}`)
  - Google Gemini API Keys (`AIza[0-9A-Za-z\-_]{35}`, `AQ\.[A-Za-z0-9\-_]{40,}`)
  - OpenAI & Generic Secret Keys (`sk-[A-Za-z0-9\-_]{32,}`)
  - Resend Keys (`re_[A-Za-z0-9_]{24,}`)
  - Private Keys (`-----BEGIN RSA PRIVATE KEY-----`, `-----BEGIN PRIVATE KEY-----`)
  - Database Connection Strings (`postgres://...`, `mysql://...`, `mongodb://...`)
- **Path Sanitization**: User home directory paths (e.g. `/Users/username/...`) are normalized to relative directory paths.

### 2.3 Network Surface & Localhost Binding
- By default, the Uvicorn server binds strictly to `127.0.0.1` (`HOST=127.0.0.1` in `.env`).
- It does **not** bind to `0.0.0.0`, preventing exposure to other devices on local Wi-Fi or LAN networks.
- Cross-Origin Resource Sharing (CORS) is enabled only for local development workflows.

### 2.4 Per-Repository AI Opt-Out
- Developers can selectively disable AI scanning for any specific repository via the `ai_enabled` toggle in the dashboard.
- When `ai_enabled` is set to `False`, the repository is completely bypassed during OpenRouter batch status extractions and enhancement plans.

---

## 3. Vulnerability Reporting

If you identify a security defect, secret leakage risk, or vulnerability in this repository, please report it directly to the repository maintainer rather than opening a public issue.
