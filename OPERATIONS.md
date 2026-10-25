# OPERATIONS.md — Operations, Deployment & Troubleshooting

## 1. Runtime Environment & Configuration

The **Project Command Center** runs locally as a lightweight FastAPI service backed by SQLite.

### 1.1 Environment Variables
All configuration is loaded from `.env` via `python-dotenv`:

| Variable | Required | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `GITHUB_TOKEN` | Yes | (or `gh auth token`) | GitHub Personal Access Token for GraphQL queries |
| `OPENROUTER_API_KEY` | Yes | None | OpenRouter API Key for free-tier AI requests |
| `OPENROUTER_MODEL` | No | `nvidia/nemotron-3-ultra-550b-a55b:free` | Primary model in waterfall |
| `HOST` | No | `127.0.0.1` | Local listening IP (do not set to `0.0.0.0`) |
| `PORT` | No | `8000` | Local port number |

---

## 2. Process Management

### 2.1 Starting the Application
```bash
# Using the provided launcher script (recommended):
chmod +x run.sh
./run.sh

# Or starting manually with Uvicorn:
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2.2 Verifying Server Health
```bash
# Health & telemetry check:
curl -s http://127.0.0.1:8000/api/quota
```

### 2.3 Stopping the Application
- If running in foreground: Press `Ctrl + C`.
- If running in background: Find and kill the process:
  ```bash
  lsof -ti :8000 | xargs kill -9
  ```

---

## 3. Database Maintenance (`projects.db`)

The application uses SQLite in Write-Ahead Logging (`WAL`) mode. 

### 3.1 Backup
Because SQLite is file-based and WAL mode ensures transactional consistency:
```bash
# Safe backup while the server is running:
sqlite3 projects.db ".backup 'projects_backup_$(date +%Y%m%d).db'"
```

### 3.2 Compacting & Vacuuming
```bash
sqlite3 projects.db "VACUUM; PRAGMA optimize;"
```

---

## 4. Operational Troubleshooting

| Symptom | Probable Cause | Resolution |
| :--- | :--- | :--- |
| **`Address already in use (Errno 48)`** | Another instance or process is using port 8000. | Run `lsof -i :8000` and terminate the conflicting process with `kill -9 <PID>`. |
| **`401 Unauthorized (GitHub)`** | Expired or missing `GITHUB_TOKEN`. | Run `gh auth login` or generate a new token at `github.com/settings/tokens` with `repo` and `read:org` scopes. |
| **`ValueError: OpenRouter API key is not configured`** | `OPENROUTER_API_KEY` missing from `.env`. | Add your valid key from `openrouter.ai/keys` to `.env`. |
| **`403 Forbidden on OpenRouter`** | Specific model endpoint has restrictive harness gating (e.g. Inkling). | The waterfall automatically cascades to the next tier. No manual action needed. |
| **High Token / Rate Limit Congestion** | Rapid manual sync calls. | Built-in 1.0s request pacing prevents bursts. Observe the telemetry pill in the UI. |
