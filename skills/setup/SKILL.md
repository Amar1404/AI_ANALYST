---
name: setup
description: "USE THIS SKILL when a user wants to set up, configure, or get started with the AI Analyst. Triggers on 'set up', 'get started', 'configure', '/setup', 'onboard me', or any first-time setup request. Also use when the user opens a new session and hasn't configured their profile yet — if you detect no .knowledge/ directory or no profile.md, proactively suggest running setup. This skill runs a conversational 4-phase interview that configures the analytical environment: role & expertise, data connection, business context, and output preferences."
---

# Setup — First-Run Configuration

You are onboarding a new user. Be conversational, not interrogative — you're a colleague getting to know someone, not a form engine.

## Design Principles
1. **2-3 questions at a time, max.** Never dump a wall of questions.
2. **Allow skipping.** Optional fields can be null.
3. **Show progress** after each phase.
4. **Validate responses** — confirm paths exist, normalize metric names.

## Pre-flight: Dependencies

```bash
python3 --version  # Need 3.10+
pip install --break-system-packages pandas numpy matplotlib duckdb scipy seaborn pyyaml pyathena boto3 mcp-clickhouse "mcp[cli]"
```

The workspace has two parts:

1. **Knowledge base (read-only in Cowork)** — lives inside the plugin repo at `.knowledge/`. This is pre-populated with dataset metadata, user profile, and business context. It is read from the plugin root directory (available via `CLAUDE_PLUGIN_ROOT` env var).

2. **Working directory (writable in Cowork)** — for outputs, charts, runs, and temporary files. Created in the Cowork sandbox at the current working directory.

**Do NOT ask the user for a repo path.** The knowledge base path is automatically resolved from the plugin root. The working directory is created in the sandbox.

Read the knowledge base from the plugin directory:
```
$CLAUDE_PLUGIN_ROOT/
├── .knowledge/
│   ├── user/
│   ├── datasets/
│   ├── analyses/
│   ├── corrections/
│   ├── setup-state.yaml
│   └── active.yaml
```

Create the working directory in the sandbox:
```
./ai-analyst-workspace/
├── working/runs/
├── outputs/
└── data/
```

**Session start behavior:** At the beginning of every session, read `repo_path` from `.knowledge/active.yaml` and use it as the workspace root. All skills should resolve `<workspace>` from this path. If `repo_path` is missing, prompt the user to run `/setup`.

## Phase 1: Role & Team

Ask:
1. "What's your role?" (PM, Data Scientist, Engineer, Marketing Analyst, exec)
2. "How technical are you with data?" (Beginner / Intermediate / Advanced)
3. "What team/department?" (optional)
4. "What domain?" (e-commerce, SaaS, fintech, etc.) (optional)

Write to `.knowledge/user/profile.md`.

## Phase 2: Data Connection

Ask: "What data do you have?"
- **CSV files** → ask for path, verify, invoke connect-data
- **DuckDB** → ask for path, verify, invoke connect-data
- **Cloud warehouse (BigQuery, Snowflake)** → invoke connect-data for config setup
- **Athena or ClickHouse** → guide MCP server setup (see below), then invoke connect-data
- **Nothing yet** → offer sample datasets or skip

Don't block on this — continue to Phase 3 even if partial.

### MCP Server Setup for Athena / ClickHouse

Cowork runs in a sandbox and cannot access local AWS credentials or database passwords directly. To run live queries, users must set up an MCP server that runs locally on their machine.

**For Athena:**

1. Install dependencies:
   ```bash
   pip install pyathena boto3 pandas "mcp[cli]"
   ```

2. The MCP server is included in this plugin at `helpers/mcp_athena_server.py`.

3. Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on Mac, or `%APPDATA%\Claude\claude_desktop_config.json` on Windows):
   ```json
   {
     "mcpServers": {
       "athena-query": {
         "command": "python3",
         "args": ["{path-to-plugin}/helpers/mcp_athena_server.py"],
         "env": {
           "AWS_PROFILE": "your-aws-profile"
         }
       }
     }
   }
   ```

4. Restart Claude Desktop. Three tools become available: `query_athena`, `list_athena_tables`, `describe_athena_table`.

**For Superset (self-hosted or cloud):**

Superset acts as a unified data layer with authentication (Google OAuth / LDAP / API key), RBAC, and row-level security. Works with any database Superset can connect to (Athena, Postgres, ClickHouse, BigQuery, etc.).

Three auth options:

**Option A: API Key (recommended)** — works with any Superset auth backend including Google OAuth.
1. Log into Superset (via Google, LDAP, or username/password)
2. Go to Settings → API Keys → Create new key
3. Copy the key (starts with `sst_`)
4. Fill in plugin config:
   - Superset URL: `http://localhost:8088` (or your instance URL)
   - Superset API Key: `sst_...`
   - Superset Database ID: (find via Superset → Data → Databases, use the ID number)
   - Superset Schema: `trayaprod` (or your default schema)

**Option B: Username/Password** — for DB auth or LDAP.
1. Fill in plugin config:
   - Superset URL: `http://localhost:8088`
   - Superset Username: your username
   - Superset Password: your password
   - Superset Auth Provider: `db` (or `ldap`)
   - Superset Database ID and Schema as above

**Option C: Official Superset MCP (Superset 4.x+)** — if Superset has built-in MCP enabled, connect directly without this plugin's server. Configure in Claude Desktop:
```json
{
  "mcpServers": {
    "superset": {
      "url": "http://localhost:8088/mcp",
      "headers": {
        "Authorization": "Bearer sst_your_api_key"
      }
    }
  }
}
```

After setup, verify with: "test superset connection" — this calls `test_superset_connection` to confirm auth and list available databases.

Tools available: `query_superset`, `sample_superset_table`, `list_superset_tables`, `describe_superset_table`, `list_superset_databases`, `test_superset_connection`.

**For ClickHouse:**

Users can use the community `mcp-clickhouse` server:
```bash
pip install mcp-clickhouse
```
Then add to Claude Desktop config:
```json
{
  "mcpServers": {
    "clickhouse-query": {
      "command": "python3",
      "args": ["-m", "mcp_clickhouse"],
      "env": {
        "CLICKHOUSE_HOST": "localhost",
        "CLICKHOUSE_PORT": "8123",
        "CLICKHOUSE_USER": "default",
        "CLICKHOUSE_PASSWORD": ""
      }
    }
  }
}
```

## Phase 2.5: Knowledge Repository

**REQUIRED — always ask this, even if `.knowledge/` already exists.** This configures the MCP knowledge server that agents use for term lookups. Present the three options clearly:

"Now let's set up your knowledge base — this is where schema docs, metric definitions, and data quirks live. You have three options:

1. **GitHub repo** — shared with your team, version-controlled, team-editable (e.g., a data-knowledge repo in your org)
2. **Local directory** — just for you, useful for testing or personal use
3. **Skip** — use the plugin's built-in files (what we're doing now)

Which would you prefer?"

### Option 1: GitHub Repo

  1. Ask for the repo URL: "Paste the GitHub repo URL — SSH (`git@github.com:org/repo.git`) or HTTPS (`https://github.com/org/repo.git`) both work."
  2. Ask for branch (default: `main`).
  3. Validate access:
     ```bash
     git ls-remote <repo-url> 2>&1 | head -3
     ```
     If this fails, troubleshoot: SSH key issues, repo permissions, URL typo.
  4. Ask which dataset ID to use (list folders in `datasets/` from the repo, or let user type one).
  5. Write config:
     ```bash
     cat > "${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugin-data/ai-analyst}/knowledge-config.json" <<EOF
     {
       "repo_url": "<user-provided-url>",
       "branch": "<branch>",
       "datasets": ["<dataset-id>"]
     }
     EOF
     ```
  6. Confirm: "Knowledge repo configured. The MCP knowledge server will clone it on next startup."

### Option 2: Local Directory

  1. Ask for the absolute path to the knowledge directory: "Paste the full path to your knowledge directory (e.g., `/Users/you/data-knowledge`)."
  2. Validate structure:
     ```bash
     ls <path>/datasets/
     ```
     Should contain at least one dataset folder with `schema.md` and `quirks.md`.
  3. Ask which dataset ID to use (list the folders found).
  4. Write config:
     ```bash
     cat > "${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugin-data/ai-analyst}/knowledge-config.json" <<EOF
     {
       "local_path": "<user-provided-path>",
       "datasets": ["<dataset-id>"]
     }
     EOF
     ```
  5. Confirm: "Local knowledge directory configured. The MCP knowledge server will read from it directly."

### Option 3: Skip

  Skip. The plugin will use local `.knowledge/` files. Suggest: "You can set this up later by running `/setup` again."

## Phase 3: Business Context

Ask:
1. "What does your company/product do?"
2. "What 2-3 metrics does your team care about most?"
3. "What question are you trying to answer right now?" (optional)
4. "Any current OKRs or goals?" (optional)

Write to `.knowledge/user/business-context.md`.

## Phase 4: Preferences

Ask:
1. "How much detail in results?" (Executive summary / Standard / Deep dive)
2. "Chart preference?" (Minimal / Standard / Chart-heavy)
3. "How do you share results?" (Deck, email, Slack, brief) (optional)

Update `.knowledge/user/profile.md` with preferences.

## Setup Complete

Display summary and suggest next actions:
```
=== SETUP COMPLETE ===

  Role:         {role} ({technical_level})
  Data:         {dataset} — {N} tables
  Key metrics:  {metrics}
  Detail level: {detail_level}

Get started:
  - Ask a question: "What's our {metric} trend?"
  - Explore data:   /explore
  - Full pipeline:  /run-analysis
```

## Subcommands
- `/setup status` — show current setup state
- `/setup reset` — clear profile and preferences (keeps data connections)
- `/setup reset everything` — full reset (requires typing "reset everything" to confirm)

## Resume Logic
If setup-state.yaml exists with partial completion, resume from first pending phase.
