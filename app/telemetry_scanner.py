"""
app/telemetry_scanner.py — Deterministic AST, Manifest, & Local Git Telemetry Scanner

Decoupled static code inspection operating 100% locally with zero LLM token usage.
Extracts:
1. AI & External API Linkage (Google AI Studio, OpenAI, Anthropic, Local, etc.)
2. Model & SDK Currency (google-genai vs legacy google-generativeai, hardcoded model strings)
3. Environment & Secret Readiness (.env.example vs local .env key names, zero values stored)
4. Runtime & Port Topology (FastAPI, Streamlit, Vite, ports, live socket heartbeat)
5. Git & Local Sync Drift (days since commit, dirty working tree, ahead/behind upstream)
6. Engineering Maturity Score (0-100 score: tests, CI, Pydantic/TS, AGENTS/CLAUDE docs, Docker)
7. Data Governance Posture (Data residency warnings for Wealth/Private domains)
"""

import os
import re
import socket
import subprocess
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set

logger = logging.getLogger("project_command_center.telemetry_scanner")

# Ignored directory names during deep walking
IGNORED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".idea", ".vscode", "dist", "build", "coverage", ".next"
}

# Known AI models regex patterns
MODEL_PATTERNS = [
    (r"gemini-2\.5-flash", "gemini-2.5-flash", "Google", False),
    (r"gemini-2\.0-flash", "gemini-2.0-flash", "Google", False),
    (r"gemini-1\.5-flash", "gemini-1.5-flash", "Google", False),
    (r"gemini-1\.5-pro", "gemini-1.5-pro", "Google", False),
    (r"gemini-1\.0-pro", "gemini-1.0-pro", "Google", True), # Deprecated
    (r"gpt-4o(?:-mini)?", "gpt-4o", "OpenAI", False),
    (r"gpt-4-turbo", "gpt-4-turbo", "OpenAI", False),
    (r"gpt-3\.5-turbo", "gpt-3.5-turbo", "OpenAI", True), # Legacy
    (r"claude-3-5-sonnet", "claude-3.5-sonnet", "Anthropic", False),
    (r"claude-3-haiku", "claude-3-haiku", "Anthropic", False),
    (r"nemotron-3-ultra-550b-a55b:free", "nemotron-3-ultra-550b", "OpenRouter Free", False),
    (r"nemotron-3\.5-super-vl:free", "nemotron-3.5-super-vl", "OpenRouter Free", False),
    (r"openrouter/free", "openrouter/free", "OpenRouter Free", False),
]

def check_port_listening(port: Optional[int]) -> str:
    """Fast non-blocking socket check on localhost (< 50ms) to check if a port is live."""
    if not port or port <= 0:
        return "N/A"
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.04)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return "Online" if result == 0 else "Offline"
    except Exception:
        return "Offline"

def extract_env_variable_names(content: str) -> List[str]:
    """Extract environment variable names from .env or .env.example content without storing values."""
    keys: List[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            var_name = line.split("=", 1)[0].strip()
            # Clean export keyword if present
            if var_name.startswith("export "):
                var_name = var_name[7:].strip()
            if var_name and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", var_name):
                if var_name not in keys:
                    keys.append(var_name)
    return keys

def scan_repo_telemetry(
    repo_path: Optional[str],
    domain_tag: str = "General",
    is_private: bool = True,
    fallback_files: Optional[List[str]] = None,
    fallback_docs: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Main deterministic scanner.
    Analyzes local repo working tree (or fallback manifests for remote repos).
    Returns zero-LLM-token enterprise metrics.
    """
    fallback_files = fallback_files or []
    fallback_docs = fallback_docs or {}
    is_local = bool(repo_path and os.path.isdir(repo_path))

    manifest_content = ""
    code_samples = ""
    root_file_names: Set[str] = set()

    # 1. Harvest local manifest and code texts
    if is_local:
        assert repo_path is not None
        try:
            root_file_names = set(os.listdir(repo_path))
        except Exception:
            root_file_names = set()

        for manifest in ["requirements.txt", "pyproject.toml", "package.json", "setup.py", "Pipfile"]:
            mf_path = os.path.join(repo_path, manifest)
            if os.path.isfile(mf_path):
                try:
                    with open(mf_path, "r", encoding="utf-8", errors="replace") as f:
                        manifest_content += "\n" + f.read()
                except Exception as err:
                    logger.debug(f"Could not read {mf_path}: {err}")

        # Scan top-level code files and app/src directories for imports & model strings
        sample_paths = []
        for f in root_file_names:
            if f.endswith((".py", ".ts", ".js", ".sh", ".yaml", ".yml", ".json")):
                sample_paths.append(os.path.join(repo_path, f))

        for sub in ["app", "src"]:
            sub_dir = os.path.join(repo_path, sub)
            if os.path.isdir(sub_dir):
                for entry in os.listdir(sub_dir)[:15]:
                    if entry.endswith((".py", ".ts", ".js")):
                        sample_paths.append(os.path.join(sub_dir, entry))

        for sp in sample_paths:
            try:
                with open(sp, "r", encoding="utf-8", errors="replace") as f:
                    code_samples += "\n" + f.read(15000)
            except Exception:
                pass
    else:
        root_file_names = set(fallback_files)
        # Use harvested docs as code samples
        for doc_content in fallback_docs.values():
            code_samples += "\n" + doc_content[:5000]

    all_text = manifest_content + "\n" + code_samples

    # =========================================================================
    # A. AI & External API Linkage Detection
    # =========================================================================
    providers: List[str] = []
    billing_tier = "None / Local"
    third_party_hooks: List[str] = []

    # Check for OpenRouter
    if "openrouter" in manifest_content.lower() or "openrouter_api_key" in all_text.lower():
        providers.insert(0, "OpenRouter Multi-Model")
        billing_tier = "Free Tier"

    # Check for Google Gemini / GenAI
    has_google_genai = "google-genai" in manifest_content or "from google import genai" in code_samples or "@google/genai" in manifest_content
    has_legacy_gemini = "google-generativeai" in manifest_content or "import google.generativeai" in code_samples or "@google/generative-ai" in manifest_content
    has_vertex = "google-cloud-aiplatform" in manifest_content or "vertexai" in code_samples

    if has_google_genai or has_legacy_gemini:
        providers.append("Google AI Studio (Gemini)")
        if billing_tier == "None / Local":
            billing_tier = "Free Tier"
    if has_vertex:
        providers.append("Google Cloud Vertex AI")
        billing_tier = "Paid Commercial"

    # Check for OpenAI
    if ("openai" in manifest_content or "import openai" in code_samples) and "OpenRouter" not in providers:
        providers.append("OpenAI Platform")
        billing_tier = "Paid Commercial"

    # Check for Anthropic
    if "anthropic" in manifest_content or "@anthropic-ai/sdk" in manifest_content:
        providers.append("Anthropic Claude API")
        billing_tier = "Paid Commercial"

    # Check for Local AI / Ollama
    if "ollama" in all_text.lower() or "localhost:11434" in all_text:
        providers.append("Local Ollama Engine")
        if billing_tier == "None / Local":
            billing_tier = "Local / Free"

    # Third-party hooks detection
    if "homeassistant" in all_text or "HASS_URL" in all_text or "HASS_TOKEN" in all_text:
        third_party_hooks.append("Home Assistant")
    if "yfinance" in all_text or "alpha_vantage" in all_text or "polygon" in all_text or "asx" in all_text:
        third_party_hooks.append("Market Data")
    if "resend" in all_text or "RESEND_API_KEY" in all_text:
        third_party_hooks.append("Resend (Email)")
    if "paho-mqtt" in all_text or "mqtt" in all_text or "MQTT_" in all_text:
        third_party_hooks.append("MQTT Broker")
    if "github" in all_text and ("GITHUB_TOKEN" in all_text or "@octokit" in all_text):
        third_party_hooks.append("GitHub API")
    if "telegram" in all_text or "TELEGRAM_BOT_TOKEN" in all_text:
        third_party_hooks.append("Telegram Bot")

    primary_provider = providers[0] if providers else "Deterministic / Local Only"

    # Data Governance Posture
    if not providers or primary_provider == "Deterministic / Local Only":
        governance_posture = "Deterministic / Local Only"
    elif "Paid Commercial" in billing_tier:
        governance_posture = "Paid Commercial API (Zero-Retention)"
    else:
        governance_posture = "Free Tier Consumer API"

    # Policy Warning for Wealth Domain
    governance_alert = None
    if domain_tag.lower() == "wealth":
        if governance_posture == "Free Tier Consumer API":
            governance_alert = "⚠️ Policy Warning: Wealth project links to consumer free-tier AI API. Financial assets must not be processed via unpaid consumer logging tiers."
        elif not is_private:
            governance_alert = "⚠️ Policy Warning: Wealth project repository has public GitHub visibility."

    ai_linkage = {
        "providers": providers or ["None (Deterministic)"],
        "primary_provider": primary_provider,
        "billing_tier": billing_tier,
        "third_party_hooks": third_party_hooks,
        "governance_posture": governance_posture,
        "governance_alert": governance_alert,
    }

    # =========================================================================
    # B. Model & SDK Currency Detection
    # =========================================================================
    sdk_packages: List[Dict[str, Any]] = []
    deprecation_warnings: List[str] = []

    if has_google_genai:
        sdk_packages.append({"name": "google-genai", "currency": "Current (v1+)", "is_deprecated": False})
    if has_legacy_gemini:
        sdk_packages.append({"name": "google-generativeai", "currency": "Deprecated", "is_deprecated": True})
        deprecation_warnings.append("Uses legacy 'google.generativeai' SDK. Migrate to modern 'google-genai' (from google import genai).")

    if "openai" in manifest_content or "import openai" in code_samples:
        is_legacy_openai = "openai.ChatCompletion.create" in code_samples
        sdk_packages.append({
            "name": "openai",
            "currency": "Deprecated (<1.0.0)" if is_legacy_openai else "Current (v1+)",
            "is_deprecated": is_legacy_openai
        })
        if is_legacy_openai:
            deprecation_warnings.append("Uses legacy OpenAI v0.x client. Upgrade to openai>=1.0.0.")

    # Detected Models in Code
    detected_models: List[str] = []
    for pattern, model_id, prov, is_dep in MODEL_PATTERNS:
        if re.search(pattern, all_text, re.IGNORECASE):
            if model_id not in detected_models:
                detected_models.append(model_id)
            if is_dep:
                deprecation_warnings.append(f"Model ID '{model_id}' is deprecated by {prov}.")

    # Migration prompt if deprecated
    migration_prompt = None
    if deprecation_warnings:
        migration_prompt = (
            f"Upgrade and modernize deprecated AI SDKs and model references. "
            f"Specifically: {'; '.join(deprecation_warnings)}. "
            f"1) Update dependencies in requirements.txt or pyproject.toml. "
            f"2) Refactor imports and client calls to modern SDK interfaces. "
            f"3) Run test suite to verify zero regressions."
        )

    sdk_currency = {
        "packages": sdk_packages,
        "detected_models": detected_models or ["None (Rule-based)"],
        "deprecation_warnings": deprecation_warnings,
        "is_up_to_date": len(deprecation_warnings) == 0,
        "migration_prompt": migration_prompt,
    }

    # =========================================================================
    # C. Environment & Secret Readiness (.env.example vs local .env)
    # =========================================================================
    required_keys: List[str] = []
    present_keys: List[str] = []

    if is_local:
        assert repo_path is not None
        # Check .env.example
        env_ex_path = os.path.join(repo_path, ".env.example")
        if os.path.isfile(env_ex_path):
            try:
                with open(env_ex_path, "r", encoding="utf-8", errors="replace") as f:
                    required_keys = extract_env_variable_names(f.read())
            except Exception:
                pass

        # If .env.example not found, search os.getenv / process.env in code
        if not required_keys:
            found_getenv = re.findall(r"(?:os\.getenv|process\.env|env\.get)\(\s*['\"]([A-Za-z0-9_]+)['\"]", code_samples)
            required_keys = sorted(list(set(found_getenv)))

        # Check local .env
        env_path = os.path.join(repo_path, ".env")
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                    present_keys = extract_env_variable_names(f.read())
            except Exception:
                pass

    missing_keys = [k for k in required_keys if k not in present_keys] if required_keys else []
    total_req = len(required_keys)
    present_count = len(required_keys) - len(missing_keys) if total_req > 0 else len(present_keys)

    if total_req > 0:
        if not missing_keys:
            secret_status = f"Ready ({total_req}/{total_req} Keys Present)"
            is_secret_ready = True
        else:
            secret_status = f"Missing ({present_count}/{total_req} Keys: {', '.join(missing_keys[:2])})"
            is_secret_ready = False
    elif present_keys:
        secret_status = f"Present ({len(present_keys)} Local Keys)"
        is_secret_ready = True
    else:
        secret_status = "No Secrets Required"
        is_secret_ready = True

    secret_readiness = {
        "required_keys": required_keys,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
        "status": secret_status,
        "is_ready": is_secret_ready,
    }

    # =========================================================================
    # D. Runtime & Port Topology
    # =========================================================================
    execution_target = "CLI / Headless Script"
    detected_port: Optional[int] = None

    if "fastapi" in manifest_content or "uvicorn" in manifest_content or "app/main.py" in code_samples or "from fastapi" in code_samples:
        execution_target = "FastAPI / Uvicorn Web API"
        detected_port = 8000
    elif "streamlit" in manifest_content or "import streamlit" in code_samples:
        execution_target = "Streamlit UI"
        detected_port = 8501
    elif "vite" in manifest_content or "vite.config" in all_text:
        execution_target = "Vite / React Frontend"
        detected_port = 5173
    elif "flask" in manifest_content or "from flask" in code_samples:
        execution_target = "Flask Web App"
        detected_port = 5000
    elif "micropython" in all_text or "esp32" in all_text or "platformio" in all_text:
        execution_target = "ESP32 / MicroPython Firmware"
        detected_port = None
    elif "streamlit" in all_text:
        execution_target = "Streamlit UI"
        detected_port = 8501

    # Check for custom port flags in run.sh or Dockerfile
    port_match = re.search(r"(?:--port|-p)\s+([0-9]{4,5})", all_text)
    if port_match:
        try:
            detected_port = int(port_match.group(1))
        except Exception:
            pass

    heartbeat = check_port_listening(detected_port) if (is_local and detected_port) else "N/A"

    runtime_topology = {
        "execution_target": execution_target,
        "port": detected_port,
        "heartbeat": heartbeat,
    }

    # =========================================================================
    # E. Git & Local Sync Drift
    # =========================================================================
    dirty_count = 0
    is_dirty = False
    drift_status = "Synced"
    days_since_commit = 0

    if is_local:
        assert repo_path is not None
        # 1. Uncommitted working tree changes
        try:
            status_res = subprocess.run(
                ["git", "-C", repo_path, "status", "--porcelain"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3.0
            )
            dirty_lines = [l for l in status_res.stdout.strip().splitlines() if l.strip()]
            dirty_count = len(dirty_lines)
            is_dirty = dirty_count > 0
        except Exception:
            pass

        # 2. Ahead / Behind tracking
        try:
            ab_res = subprocess.run(
                ["git", "-C", repo_path, "rev-list", "--left-right", "--count", "@{u}...HEAD"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3.0
            )
            if ab_res.returncode == 0:
                parts = ab_res.stdout.strip().split("\t")
                if len(parts) == 2:
                    behind, ahead = int(parts[0]), int(parts[1])
                    if ahead > 0 and behind > 0:
                        drift_status = f"Diverged (+{ahead}, -{behind})"
                    elif ahead > 0:
                        drift_status = f"Ahead ({ahead} unpushed)"
                    elif behind > 0:
                        drift_status = f"Behind ({behind} commits)"
                    else:
                        drift_status = "Synced with GitHub"
            else:
                drift_status = "Local Only (No upstream)"
        except Exception:
            drift_status = "Unknown"

        # 3. Days since commit
        try:
            date_res = subprocess.run(
                ["git", "-C", repo_path, "log", "-1", "--format=%cI"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3.0
            )
            commit_iso = date_res.stdout.strip()
            if commit_iso:
                c_date = datetime.fromisoformat(commit_iso)
                days_since_commit = (datetime.now(timezone.utc) - c_date.astimezone(timezone.utc)).days
        except Exception:
            pass

    git_drift = {
        "is_dirty": is_dirty,
        "dirty_files_count": dirty_count,
        "drift_status": drift_status,
        "days_since_commit": days_since_commit,
    }

    # =========================================================================
    # F. Engineering Maturity Score (0-100)
    # =========================================================================
    score = 0
    breakdown: List[str] = []

    # 1. Automated Tests (25 pts)
    has_tests = False
    if is_local:
        assert repo_path is not None
        has_tests = os.path.isdir(os.path.join(repo_path, "tests")) or "pytest" in all_text or "vitest" in all_text
    else:
        has_tests = any("test" in f.lower() for f in root_file_names)

    if has_tests:
        score += 25
        breakdown.append("Automated Test Suite (+25)")

    # 2. CI/CD Workflows (20 pts)
    has_ci = False
    if is_local:
        assert repo_path is not None
        wf_dir = os.path.join(repo_path, ".github", "workflows")
        has_ci = os.path.isdir(wf_dir) and len(os.listdir(wf_dir)) > 0
    if has_ci:
        score += 20
        breakdown.append("GitHub Actions CI (+20)")

    # 3. Schema Validation (20 pts)
    has_schema = "pydantic" in all_text or "zod" in all_text or "typescript" in all_text
    if has_schema:
        score += 20
        breakdown.append("Type & Schema Validation (+20)")

    # 4. Agent Context & Framework Docs (20 pts)
    doc_pts = 0
    for doc in ["AGENTS.md", "CLAUDE.md", "README.md", "ARCHITECTURE.md"]:
        if doc in root_file_names or (fallback_docs and doc in fallback_docs):
            doc_pts += 5
    if doc_pts > 0:
        score += doc_pts
        breakdown.append(f"Enterprise Documentation (+{doc_pts})")

    # 5. Container & Deployment Packaging (15 pts)
    has_deploy = "Dockerfile" in root_file_names or "docker-compose.yml" in root_file_names or "run.sh" in root_file_names
    if has_deploy:
        score += 15
        breakdown.append("Containerization / Launch Script (+15)")

    if score >= 90:
        grade = "A+"
    elif score >= 80:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"
    else:
        grade = "D"

    has_agents_md = "AGENTS.md" in root_file_names or (fallback_docs and "AGENTS.md" in fallback_docs)
    has_claude_md = "CLAUDE.md" in root_file_names or (fallback_docs and "CLAUDE.md" in fallback_docs)
    has_readme_md = "README.md" in root_file_names or (fallback_docs and "README.md" in fallback_docs)

    agent_status = "Fully Instrumented (AGENTS.md)" if has_agents_md else ("Partial Context (CLAUDE.md/README)" if (has_claude_md or has_readme_md) else "Missing Agent Context")
    agent_handoff_prompt = (
        f"Generate and document a standardized AGENTS.md operating contract for this repository. "
        f"Detail the core architecture, active branch, environment secrets required, and pre-flight verification test commands."
    )

    engineering_maturity = {
        "score": score,
        "grade": grade,
        "has_tests": has_tests,
        "has_ci": has_ci,
        "has_schema_validation": has_schema,
        "has_agent_context": has_agents_md or has_claude_md,
        "agent_readiness": {
            "has_agents_md": has_agents_md,
            "has_claude_md": has_claude_md,
            "has_readme": has_readme_md,
            "status": agent_status,
            "handoff_prompt": agent_handoff_prompt if not has_agents_md else None,
        },
        "has_docker": "Dockerfile" in root_file_names,
        "breakdown": breakdown,
    }

    return {
        "ai_linkage": ai_linkage,
        "sdk_currency": sdk_currency,
        "secret_readiness": secret_readiness,
        "runtime_topology": runtime_topology,
        "git_drift": git_drift,
        "engineering_maturity": engineering_maturity,
    }
