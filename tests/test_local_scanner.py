import pytest
import os
import subprocess
from app.local_scanner import get_projects_root_dirs, scan_all_local_repositories


def test_get_projects_root_dirs_default():
    """Verify default returns parent directory."""
    dirs = get_projects_root_dirs()
    assert len(dirs) >= 1
    assert os.path.isdir(dirs[0])


def test_get_projects_root_dirs_custom(monkeypatch, tmp_path):
    """Verify multiple custom comma-separated paths are parsed and resolved."""
    dir1 = tmp_path / "workspace1"
    dir2 = tmp_path / "workspace2"
    dir1.mkdir()
    dir2.mkdir()

    custom_env = f"{dir1},{dir2}"
    monkeypatch.setenv("LOCAL_PROJECTS_DIR", custom_env)

    dirs = get_projects_root_dirs()
    assert str(dir1) in dirs
    assert str(dir2) in dirs


def test_scan_all_local_repositories_mock(monkeypatch, tmp_path):
    """Verify repository detection and path deduplication."""
    workspace = tmp_path / "code"
    workspace.mkdir()

    # Create dummy git repo
    repo1 = workspace / "dummy-repo"
    repo1.mkdir()
    (repo1 / ".git").mkdir()
    (repo1 / "README.md").write_text("# Dummy Repo\n- [x] Done\n")

    monkeypatch.setenv("LOCAL_PROJECTS_DIR", str(workspace))

    repos = scan_all_local_repositories()
    matched = [r for r in repos if r["name"] == "dummy-repo"]
    assert len(matched) == 1
    assert matched[0]["is_local"] is True
    assert "README.md" in matched[0]["docs"]
