import os
import subprocess
import httpx
from typing import List, Dict, Any, Optional, Tuple

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

def get_github_token() -> str:
    """Retrieve GitHub token from environment or fallback to 'gh auth token'."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token and not token.startswith("your_") and not token.startswith("gho_your_"):
        return token
    try:
        res = subprocess.run(["gh", "auth", "token"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        token = res.stdout.strip()
        if token:
            return token
    except Exception:
        pass
    return token

STAGE1_QUERY = """
query GetRepositories($after: String) {
  viewer {
    repositories(
      first: 100
      affiliations: [OWNER, COLLABORATOR]
      orderBy: {field: PUSHED_AT, direction: DESC}
      after: $after
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        nameWithOwner
        name
        owner {
          login
        }
        isPrivate
        isArchived
        isEmpty
        description
        url
        pushedAt
        openIssues: issues(states: OPEN) {
          totalCount
        }
        defaultBranchRef {
          name
          target {
            ... on Commit {
              oid
            }
          }
        }
      }
    }
  }
}
"""

STAGE2_QUERY = """
query GetRepoDetails($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      name
      target {
        ... on Commit {
          oid
          tree {
            entries {
              name
              type
              object {
                ... on Blob {
                  text
                }
              }
            }
          }
        }
      }
    }
    docsFolder: object(expression: "HEAD:docs") {
      ... on Tree {
        entries {
          name
          type
          object {
            ... on Blob {
              text
            }
          }
        }
      }
    }
    issues(first: 10, states: OPEN, orderBy: {field: CREATED_AT, direction: DESC}) {
      totalCount
      nodes {
        number
        title
        url
        createdAt
      }
    }
  }
}
"""

# Case-insensitive target docs
TARGET_DOC_BASENAMES = {
    "readme.md",
    "project_overview.md",
    "plan.md",
    "todo.md",
    "roadmap.md",
    "claude.md",
    "agents.md",
    "architecture.md",
    "handover.md",
    "requirements.md",
    "known_issues.md",
    "decisions.md",
    "antigravity_handover.md"
}

async def fetch_all_repositories(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Stage 1: Fetch metadata and commit SHAs for all repos using cursor pagination."""
    token = get_github_token()
    if not token:
        raise ValueError("GitHub token not configured. Please set GITHUB_TOKEN or login with 'gh auth login'.")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Project-Command-Center",
    }
    
    repos = []
    after_cursor = None
    
    while True:
        resp = await client.post(
            GITHUB_GRAPHQL_URL,
            json={"query": STAGE1_QUERY, "variables": {"after": after_cursor}},
            headers=headers,
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub GraphQL error: {resp.status_code} - {resp.text}")
        
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"GraphQL returned errors: {data['errors']}")
            
        repo_data = data.get("data", {}).get("viewer", {}).get("repositories", {})
        nodes = repo_data.get("nodes", [])
        
        for node in nodes:
            default_branch_ref = node.get("defaultBranchRef")
            latest_sha = None
            if default_branch_ref and default_branch_ref.get("target"):
                latest_sha = default_branch_ref["target"].get("oid")
                
            repos.append({
                "nameWithOwner": node.get("nameWithOwner"),
                "name": node.get("name"),
                "owner": node.get("owner", {}).get("login"),
                "isPrivate": bool(node.get("isPrivate")),
                "isArchived": bool(node.get("isArchived")),
                "isEmpty": bool(node.get("isEmpty")),
                "description": node.get("description") or "",
                "htmlUrl": node.get("url"),
                "pushedAt": node.get("pushedAt"),
                "openIssuesCount": node.get("openIssues", {}).get("totalCount", 0),
                "latestCommitSha": latest_sha,
                "defaultBranch": default_branch_ref.get("name") if default_branch_ref else None,
            })
            
        page_info = repo_data.get("pageInfo", {})
        if page_info.get("hasNextPage") and page_info.get("endCursor"):
            after_cursor = page_info["endCursor"]
        else:
            break
            
    return repos

async def fetch_repository_details(client: httpx.AsyncClient, owner: str, name: str) -> Dict[str, Any]:
    """Stage 2: Harvest root and /docs markdown files, top-level directories, and open issues."""
    token = get_github_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Project-Command-Center",
    }
    
    resp = await client.post(
        GITHUB_GRAPHQL_URL,
        json={"query": STAGE2_QUERY, "variables": {"owner": owner, "name": name}},
        headers=headers,
        timeout=30.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Stage 2 fetch error for {owner}/{name}: {resp.status_code} - {resp.text}")
        
    data = resp.json()
    repo_node = data.get("data", {}).get("repository") or {}
    
    docs: Dict[str, str] = {}
    directories: List[str] = []
    
    # 1. Harvest root tree
    default_branch = repo_node.get("defaultBranchRef") or {}
    target_commit = default_branch.get("target") or {}
    tree = target_commit.get("tree") or {}
    root_entries = tree.get("entries") or []
    
    for entry in root_entries:
        entry_name = entry.get("name", "")
        entry_type = entry.get("type")
        if entry_type == "tree":
            directories.append(entry_name)
        elif entry_type == "blob":
            lower_name = entry_name.lower()
            if lower_name in TARGET_DOC_BASENAMES or lower_name.endswith(".md"):
                blob_text = entry.get("object", {}).get("text")
                if blob_text:
                    docs[entry_name] = blob_text
                    
    # 2. Harvest /docs folder if exists
    docs_folder = repo_node.get("docsFolder")
    if docs_folder and "entries" in docs_folder:
        for entry in docs_folder.get("entries", []):
            entry_name = entry.get("name", "")
            if entry.get("type") == "blob" and entry_name.lower().endswith(".md"):
                blob_text = entry.get("object", {}).get("text")
                if blob_text:
                    docs[f"docs/{entry_name}"] = blob_text
                    
    # 3. Harvest open issues
    issues_data = repo_node.get("issues", {})
    issues_nodes = issues_data.get("nodes", [])
    open_issues = [
        {
            "number": item.get("number"),
            "title": item.get("title"),
            "url": item.get("url"),
            "created_at": item.get("createdAt"),
        }
        for item in issues_nodes
    ]
    
    return {
        "docs": docs,
        "directories": directories,
        "open_issues": open_issues,
    }
