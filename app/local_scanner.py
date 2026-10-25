import os
import re
import subprocess
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("local_scanner")

IGNORED_DIR_NAMES = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".coverage", "dist", "build",
    "_archive", "logs", ".vscode", ".idea"
}

CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".html", ".css", ".yaml", ".yml", ".json"}

def get_projects_root_dirs() -> List[str]:
    """Find all configured local parent directories containing git repositories."""
    dirs: List[str] = []
    env_dir = os.environ.get("LOCAL_PROJECTS_DIR") or os.environ.get("LOCAL_PROJECT_PATHS")
    if env_dir:
        # Support comma or semicolon separated paths
        parts = [p.strip() for p in re.split(r"[,;]", env_dir) if p.strip()]
        for p in parts:
            abs_p = os.path.abspath(os.path.expanduser(p))
            if os.path.isdir(abs_p) and abs_p not in dirs:
                dirs.append(abs_p)

    # Always include parent directory of Project Command Center as default
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parent_dir = os.path.dirname(current_dir)
    if os.path.isdir(parent_dir) and parent_dir not in dirs:
        dirs.append(parent_dir)

    return dirs

def get_projects_root_dir() -> str:
    """Backward compatibility wrapper returning the primary projects root directory."""
    dirs = get_projects_root_dirs()
    return dirs[0] if dirs else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def scan_markdown_files(repo_path: str) -> Dict[str, str]:
    """Recursively harvest markdown documentation from root and /docs (up to 3 levels)."""
    docs: Dict[str, str] = {}
    
    # 1. Scan root files
    try:
        for entry in os.listdir(repo_path):
            full_path = os.path.join(repo_path, entry)
            if os.path.isfile(full_path) and entry.lower().endswith(".md") and not entry.startswith("."):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        docs[entry] = f.read()
                except Exception as read_err:
                    logger.warning(f"Failed to read {full_path}: {read_err}")
    except Exception as dir_err:
        logger.warning(f"Failed to list root of {repo_path}: {dir_err}")

    # 2. Scan docs/ directory recursively
    docs_dir = os.path.join(repo_path, "docs")
    if os.path.isdir(docs_dir):
        for root, dirs, files in os.walk(docs_dir):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
            rel_dir = os.path.relpath(root, repo_path)
            for file in files:
                if file.lower().endswith(".md") and not file.startswith("."):
                    rel_path = os.path.join(rel_dir, file)
                    full_file = os.path.join(root, file)
                    try:
                        with open(full_file, "r", encoding="utf-8", errors="replace") as f:
                            docs[rel_path] = f.read()
                    except Exception as read_err:
                        logger.warning(f"Failed to read {full_file}: {read_err}")

    return docs

def count_code_and_test_files(repo_path: str) -> Dict[str, Any]:
    """Calculate code metrics across the repository."""
    code_count = 0
    test_count = 0
    has_ci = False
    
    ci_path = os.path.join(repo_path, ".github", "workflows")
    if os.path.isdir(ci_path) and os.listdir(ci_path):
        has_ci = True

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in CODE_EXTENSIONS:
                code_count += 1
            if f.startswith("test_") or f.endswith("_test.py") or f.endswith(".test.ts"):
                test_count += 1

    has_tests = test_count > 0 or os.path.isdir(os.path.join(repo_path, "tests"))

    return {
        "code_files_count": code_count,
        "test_files_count": test_count,
        "has_tests": has_tests,
        "has_ci": has_ci,
    }

def scan_all_local_repositories() -> List[Dict[str, Any]]:
    """Scan all configured local parent directories for git repositories and extract rich technical telemetry."""
    projects_dirs = get_projects_root_dirs()
    results: List[Dict[str, Any]] = []
    seen_paths: set = set()
    seen_identifiers: set = set()

    for projects_dir in projects_dirs:
        if not os.path.isdir(projects_dir):
            logger.warning(f"Configured projects directory not found: {projects_dir}")
            continue

        for item in sorted(os.listdir(projects_dir)):
            repo_path = os.path.join(projects_dir, item)
            git_dir = os.path.join(repo_path, ".git")

            # Skip non-directories or items without .git
            if not os.path.isdir(repo_path) or not os.path.exists(git_dir):
                continue

            real_path = os.path.realpath(repo_path)
            if real_path in seen_paths:
                continue
            seen_paths.add(real_path)

        try:
            # 1. Remote URL & Repo Identifier
            r_cmd = subprocess.run(
                ["git", "-C", repo_path, "remote", "get-url", "origin"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0
            )
            remote_url = r_cmd.stdout.strip()
            name_with_owner = None
            owner = "b-radical86"
            repo_name = item

            if remote_url:
                m = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)", remote_url)
                if m:
                    owner = m.group(1)
                    repo_name = m.group(2)
                    name_with_owner = f"{owner}/{repo_name}"

            if not name_with_owner:
                clean_name = item.replace(" ", "-")
                name_with_owner = f"b-radical86/{clean_name}"

            # 2. Git metadata
            branch_cmd = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0
            )
            active_branch = branch_cmd.stdout.strip() or "master"

            sha_cmd = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "HEAD"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0
            )
            latest_sha = sha_cmd.stdout.strip()

            commit_count_cmd = subprocess.run(
                ["git", "-C", repo_path, "rev-list", "--count", "HEAD"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0
            )
            try:
                commit_count = int(commit_count_cmd.stdout.strip())
            except Exception:
                commit_count = 1

            log_cmd = subprocess.run(
                ["git", "-C", repo_path, "log", "-1", "--format=%s|||%cI"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0
            )
            log_parts = log_cmd.stdout.strip().split("|||")
            latest_commit_msg = log_parts[0] if len(log_parts) > 0 else ""
            pushed_at = log_parts[1] if len(log_parts) > 1 else None

            # 3. Root files and directories
            root_files = []
            directories = []
            for entry in sorted(os.listdir(repo_path)):
                if entry.startswith(".") or entry in IGNORED_DIR_NAMES:
                    continue
                full_entry = os.path.join(repo_path, entry)
                if os.path.isfile(full_entry):
                    size_kb = round(os.path.getsize(full_entry) / 1024, 1)
                    root_files.append(f"{entry} ({size_kb} KB)")
                elif os.path.isdir(full_entry):
                    directories.append(entry)

            # 4. Harvest Markdown documents
            docs = scan_markdown_files(repo_path)

            # 5. Code metrics
            metrics = count_code_and_test_files(repo_path)

            results.append({
                "name_with_owner": name_with_owner,
                "name": repo_name,
                "owner": owner,
                "local_path": repo_path,
                "is_local": True,
                "remote_url": remote_url or None,
                "active_branch": active_branch,
                "commit_count": commit_count,
                "latest_commit_sha": latest_sha,
                "latest_commit_msg": latest_commit_msg,
                "pushed_at": pushed_at,
                "root_files": root_files,
                "directories": directories,
                "docs": docs,
                "metrics": metrics,
            })
        except Exception as scan_err:
            logger.error(f"Error scanning local repository at {repo_path}: {scan_err}")

    return results
