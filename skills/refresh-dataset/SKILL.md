---
name: refresh-dataset
description: >
  Reload the knowledge index for the active dataset. Pulls latest changes from
  git (if remote) or re-reads local files. Triggered when users say
  "refresh knowledge", "reload schema", "update dataset", or invoke `/refresh-dataset`.
---

# Skill: Refresh Dataset

## Purpose
Rebuild the knowledge index so that recent edits to schema, quirks, metrics, or glossary files are picked up without restarting the server.

## When to Use
- After editing `schema.md`, `quirks.md`, `metrics/*.yaml`, or `_index.yaml` locally
- After pushing changes to the knowledge repo
- When the agent seems to be using stale schema or missing newly added tables
- Invoke as `/refresh-dataset`

## Instructions

### Step 1: Call the MCP tool

Call the **knowledge** MCP server tool `refresh_knowledge`.

### Step 2: Report the result

Parse the JSON response and display:

```
Knowledge refreshed.
Changes detected: {changes}
Datasets reloaded: {datasets}
Commit: {commit_hash or "local mode"}
```

If the response contains `"status": "error"`, display:

```
Refresh failed: {error}
```

### Step 3: Verify (optional)

If the user refreshed because of a specific table or term, run a quick `lookup_index` for that term to confirm it's now in the index.

## Anti-Patterns

1. **Don't rebuild the index manually** — always use the `refresh_knowledge` MCP tool
2. **Don't assume refresh is needed before every query** — the index is built at startup and stays valid unless files change
