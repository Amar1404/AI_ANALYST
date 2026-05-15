# helpers package — ai-analyst plugin edition
#
# Context detection: determines whether we're running inside the ai-analyst
# git repo or as a Cowork plugin, and resolves paths accordingly.

import os
import sys
from pathlib import Path


def _detect_context():
    """Detect whether we're in plugin context or repo context."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root and Path(plugin_root).exists():
        return "plugin", Path(plugin_root)

    helpers_dir = Path(__file__).parent
    repo_root = helpers_dir.parent
    if (repo_root / "CLAUDE.md").exists():
        return "repo", repo_root

    return "plugin", helpers_dir.parent


CONTEXT, ROOT = _detect_context()


def get_workspace_path():
    """Get the workspace path for persistent state and outputs."""
    workspace = os.environ.get("AI_ANALYST_WORKSPACE")
    if workspace:
        p = Path(workspace)
        p.mkdir(parents=True, exist_ok=True)
        return p

    if CONTEXT == "repo":
        return ROOT

    cwd = Path.cwd()
    for candidate in [
        cwd / "mnt" / "outputs" / "ai-analyst",
        Path("/sessions") / cwd.name / "mnt" / "outputs" / "ai-analyst",
    ]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue

    fallback = cwd / "ai-analyst-workspace"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_knowledge_path():
    """Get the path to the knowledge directory."""
    if CONTEXT == "repo":
        return ROOT / ".knowledge"
    return get_workspace_path() / "knowledge"


def get_plugin_root():
    """Get the plugin root directory."""
    return ROOT


def ensure_workspace():
    """Create the workspace directory structure if it doesn't exist."""
    ws = get_workspace_path()
    for subdir in [
        "state", "state/checkpoints", "working", "outputs", "outputs/charts",
        "knowledge", "knowledge/datasets", "knowledge/organizations",
        "knowledge/corrections", "knowledge/learnings", "knowledge/analyses",
        "knowledge/user", "runs",
    ]:
        (ws / subdir).mkdir(parents=True, exist_ok=True)
    return ws
