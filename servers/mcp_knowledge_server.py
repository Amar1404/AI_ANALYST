"""MCP Server for Knowledge Repository access.

Clones a user-configured GitHub repo, builds a page index, and serves
schema/quirks/metrics/business-context to agents via lookup_index + get_page.

Usage:
    python servers/mcp_knowledge_server.py

Environment variables:
    KNOWLEDGE_CACHE_DIR: Directory to clone the repo into.
    KNOWLEDGE_CONFIG: Path to JSON config with repo_url and branch.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Auto-install dependencies if missing
try:
    import mcp  # noqa: F401
    import yaml  # noqa: F401
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "mcp[cli]", "pyyaml"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

# Add project root to path so we can import helpers
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from mcp.server.fastmcp import FastMCP

from helpers.index_builder import build_index, extract_markdown_sections

mcp = FastMCP("knowledge")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CACHE_DIR = Path(os.environ.get("KNOWLEDGE_CACHE_DIR", ".knowledge-cache"))

_index_cache: dict[str, dict] = {}  # dataset_id -> index dict


def _load_config() -> dict:
    """Load knowledge config from env vars (set by plugin userConfig) or JSON file fallback."""
    # Primary: env vars from user_config
    repo_url = os.environ.get("KNOWLEDGE_REPO_URL", "").strip()
    local_path = os.environ.get("KNOWLEDGE_LOCAL_PATH", "").strip()
    branch = os.environ.get("KNOWLEDGE_REPO_BRANCH", "").strip() or "main"
    github_token = os.environ.get("KNOWLEDGE_GITHUB_TOKEN", "").strip()
    datasets_str = os.environ.get("KNOWLEDGE_DATASETS", "").strip()
    datasets = [d.strip() for d in datasets_str.split(",") if d.strip()] if datasets_str else []

    if repo_url or local_path:
        config = {"branch": branch, "datasets": datasets}
        if repo_url:
            config["repo_url"] = repo_url
        if local_path:
            config["local_path"] = local_path
        if github_token:
            config["github_token"] = github_token
        return config

    # Fallback: JSON config file (for backward compat / manual setup)
    config_path = Path(os.environ.get("KNOWLEDGE_CONFIG", "knowledge-config.json"))
    if config_path.exists():
        return json.loads(config_path.read_text())

    return {}


def _repo_dir() -> Path:
    """Path to knowledge repo — local_path if configured, otherwise clone cache."""
    config = _load_config()
    local_path = config.get("local_path", "")
    if local_path and Path(local_path).is_dir():
        return Path(local_path)
    return CACHE_DIR / "repo"


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------


def _auth_url(repo_url: str, token: str) -> str:
    """Inject GitHub token into an HTTPS URL for private repo access."""
    if token and repo_url.startswith("https://"):
        # https://github.com/... -> https://<token>@github.com/...
        return repo_url.replace("https://", f"https://{token}@", 1)
    return repo_url


def _clone_or_pull() -> tuple[bool, str]:
    """Clone the repo if not cached, or pull latest changes.

    Returns:
        (changed: bool, commit_hash: str)
    """
    config = _load_config()
    repo_url = config.get("repo_url", "")
    branch = config.get("branch", "main")
    token = config.get("github_token", "")

    if not repo_url:
        return False, ""

    auth_url = _auth_url(repo_url, token)
    repo_path = _repo_dir()

    # Prevent token leaking into git config / logs
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    if (repo_path / ".git").is_dir():
        # Update remote URL in case token changed
        subprocess.run(
            ["git", "remote", "set-url", "origin", auth_url],
            cwd=repo_path, capture_output=True, text=True, env=env,
        )
        # Pull
        old_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_path, text=True
        ).strip()
        subprocess.run(
            ["git", "pull", "--ff-only", "origin", branch],
            cwd=repo_path, capture_output=True, text=True, env=env,
        )
        new_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_path, text=True
        ).strip()
        return old_hash != new_hash, new_hash
    else:
        # Clone
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--branch", branch, "--depth", "1", auth_url, str(repo_path)],
            capture_output=True, text=True, check=True, env=env,
        )
        commit_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_path, text=True
        ).strip()
        return True, commit_hash


def _ensure_repo() -> Path:
    """Ensure the knowledge repo is available. Returns repo path.

    If local_path is configured, uses that directly (no git needed).
    Otherwise clones from repo_url.
    """
    repo_path = _repo_dir()
    # local_path mode — directory exists, no git needed
    if (repo_path / "datasets").is_dir():
        return repo_path
    # git mode — clone if not already cloned
    if not (repo_path / ".git").is_dir():
        _clone_or_pull()
    return repo_path


def _build_and_cache_index(dataset_id: str) -> dict:
    """Build index for a dataset and cache it."""
    repo_path = _ensure_repo()
    index = build_index(repo_path, dataset_id)
    _index_cache[dataset_id] = index

    # Also write to disk
    ds_dir = repo_path / "datasets" / dataset_id
    if ds_dir.is_dir():
        index_path = ds_dir / "_index.yaml"
        index_path.write_text(yaml.dump(index, default_flow_style=False))

    return index


def _get_index(dataset_id: str) -> dict:
    """Get or build the index for a dataset."""
    if dataset_id not in _index_cache:
        # Try loading from disk first
        repo_path = _ensure_repo()
        index_path = repo_path / "datasets" / dataset_id / "_index.yaml"
        if index_path.exists():
            _index_cache[dataset_id] = yaml.safe_load(index_path.read_text())
        else:
            _build_and_cache_index(dataset_id)
    return _index_cache.get(dataset_id, {"mandatory": [], "terms": {}})


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def lookup_index(terms: list[str], dataset: str) -> str:
    """Look up terms in the knowledge index. Returns file locations and context
    summaries for each matching term, plus mandatory guardrail pages (PII,
    partitions). Call this FIRST with key terms extracted from the user's
    question before fetching full pages.

    Args:
        terms: List of terms to look up (table names, metric names, business
               terms like "O2", "retention", "channel").
        dataset: Dataset identifier (e.g., "traya-health").

    Returns:
        JSON with mandatory pages and matching term entries.
    """
    index = _get_index(dataset)

    matches: dict[str, list[dict]] = {}
    for term in terms:
        term_lower = term.lower()
        # Exact match
        if term in index.get("terms", {}):
            matches[term] = index["terms"][term]
        # Case-insensitive fallback
        else:
            for key, entries in index.get("terms", {}).items():
                if key.lower() == term_lower:
                    matches[term] = entries
                    break

    result = {
        "mandatory": index.get("mandatory", []),
        "matches": matches,
        "unmatched": [t for t in terms if t not in matches],
    }
    return json.dumps(result, default=str)


@mcp.tool()
def get_page(file: str, dataset: str, section: str = "") -> str:
    """Fetch the full content of a knowledge page or a specific section within it.
    Call after lookup_index to retrieve details for the sections you need.

    Args:
        file: Relative file path within the dataset (e.g., "quirks.md",
              "metrics/retention.yaml", "schema.md").
        dataset: Dataset identifier (e.g., "traya-health").
        section: Optional section heading to extract. If empty, returns
                 the full file content.

    Returns:
        The content of the file or section as a string.
    """
    repo_path = _ensure_repo()
    file_path = repo_path / "datasets" / dataset / file

    # Also check organizations/ path for glossary etc.
    if not file_path.exists() and file.startswith("glossary/"):
        orgs_dir = repo_path / "organizations"
        if orgs_dir.is_dir():
            for org_dir in sorted(orgs_dir.iterdir()):
                candidate = org_dir / "business" / file
                if candidate.exists():
                    file_path = candidate
                    break

    if not file_path.exists():
        return json.dumps({"error": f"File not found: {file}"})

    content = file_path.read_text(encoding="utf-8")

    if section and file_path.suffix == ".md":
        sections = extract_markdown_sections(file_path)
        if section in sections:
            return sections[section]
        return json.dumps({"error": f"Section '{section}' not found in {file}"})

    return content


@mcp.tool()
def list_datasets() -> str:
    """List all datasets available in the knowledge repository.

    Returns:
        JSON list of dataset identifiers.
    """
    repo_path = _ensure_repo()
    datasets_dir = repo_path / "datasets"
    if not datasets_dir.is_dir():
        return json.dumps({"datasets": []})

    datasets = sorted(
        d.name for d in datasets_dir.iterdir()
        if d.is_dir() and not d.name.startswith(("_", "."))
    )
    return json.dumps({"datasets": datasets})


@mcp.tool()
def get_quirks(dataset: str) -> str:
    """Get all quirks/rules for a dataset. Use when you need the complete set
    of rules rather than specific sections.

    Args:
        dataset: Dataset identifier (e.g., "traya-health").

    Returns:
        Full content of quirks.md.
    """
    return get_page("quirks.md", dataset)


@mcp.tool()
def refresh_knowledge() -> str:
    """Pull latest changes from the knowledge repository. Rebuilds the page
    index if files changed.

    Returns:
        JSON with status, whether changes were detected, and current commit hash.
    """
    try:
        config = _load_config()
        repo_path = _repo_dir()

        # Git mode: pull latest
        changed, commit_hash = _clone_or_pull()

        # Local mode: always rebuild (no git to detect changes)
        if not config.get("repo_url") and config.get("local_path"):
            changed = True
            commit_hash = ""

        if changed:
            _index_cache.clear()
            datasets_dir = repo_path / "datasets"
            if datasets_dir.is_dir():
                for ds_dir in datasets_dir.iterdir():
                    if ds_dir.is_dir() and not ds_dir.name.startswith(("_", ".")):
                        _build_and_cache_index(ds_dir.name)

        return json.dumps({
            "status": "ok",
            "changes": changed,
            "commit_hash": commit_hash,
            "datasets": list(_index_cache.keys()),
        })
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

# Build index on startup — from local_path or git clone
config = _load_config()
if config.get("local_path") or config.get("repo_url"):
    try:
        if config.get("repo_url") and not config.get("local_path"):
            _clone_or_pull()
        repo_path = _repo_dir()
        datasets_dir = repo_path / "datasets"
        if datasets_dir.is_dir():
            for ds_dir in datasets_dir.iterdir():
                if ds_dir.is_dir() and not ds_dir.name.startswith(("_", ".")):
                    _build_and_cache_index(ds_dir.name)
    except Exception as e:
        print(f"[knowledge-server] Startup warning: {e}", file=sys.stderr)

if __name__ == "__main__":
    mcp.run()
