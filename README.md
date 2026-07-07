# AI Analyst Plugin

Ask a business question in plain English. Get validated findings, publication-quality charts, and a slide deck.

## Install

### Claude Cowork

1. Open Claude Cowork and start a Cowork session
2. Click the **+** button in the chat box
3. Click **Plugins**
4. Click **Add Plugin**
5. Click **Personal**
6. Click the **+** button
7. Click **Add marketplace from GitHub**
8. Paste this URL: `https://github.com/Amar1404/AI_ANALYST`
9. Click **Sync**

That's it — the AI Analyst plugin is now available in your Cowork sessions.

### Claude Desktop (via Marketplace)

1. Open the **Claude Desktop** app
2. Open **Settings** → **Plugins**
3. Click **Add Marketplace**
4. Select **Add marketplace from GitHub**
5. Paste this URL: `https://github.com/Amar1404/AI_ANALYST`
6. Click **Sync**
7. Find **AI Analyst Plugin** in the marketplace list and click **Install**
8. Restart Claude Desktop when prompted

The plugin's skills and agents are now available in any Claude Desktop conversation.

## Getting Started

**First time?** Say *"help me set up"* to connect your data and configure your preferences.

**Try it:** Just ask a question like *"Which channel has the highest churn and why?"* or *"Show me MRR trends over time"*

## What You Get

- **37 skills** — question framing, metric definition, data exploration, forecasting, experiment design, and more
- **20 agents** — specialized analytical agents for hypothesis testing, cohort analysis, root cause investigation, storytelling, chart-making, and deck creation
- **Publication-quality charts** — styled visualizations with consistent theming
- **Slide decks** — Marp-powered presentations ready for stakeholder readouts
- **Data validation** — built-in confidence scoring, source tieout, and logical validation

## Integrations

The plugin ships with three MCP servers that connect to your data and business context. Configure them in **Settings → Plugins → AI Analyst Plugin** after install.

### Athena (Data Warehouse)

Query AWS Athena tables directly from any Claude conversation.

**Required settings:**

| Field | Example | Description |
|---|---|---|
| `AWS Profile` | `default` | AWS CLI profile with Athena access |
| `Athena Database` | `databasename` | Default database for queries |
| `Athena S3 Staging` | `s3://my-bucket/athena-output/` | S3 path where Athena writes query results |
| `Athena Region` | `ap-south-1` | AWS region |
| `Athena Workgroup` | `primary` | Athena workgroup name |

**Prerequisites:**
- AWS CLI installed and `aws configure --profile <name>` completed
- IAM permissions: `athena:*`, `glue:GetTable*`, `glue:GetDatabase*`, `s3:GetObject` + `s3:PutObject` on the staging bucket

**How to configure (step-by-step):**

1. Open **Claude Desktop** → click the **gear icon** (top-right) → **Settings**
2. In the left sidebar, click **Plugins**
3. Find **AI Analyst Plugin** in the installed list → click the **⚙ Configure** button next to it
4. Scroll to the **Athena** section. Fill in each field:
   - **AWS Profile** → paste the profile name from your `~/.aws/credentials` file (e.g., `default` or `org-prod`)
   - **Athena Database** → the default database queries should target (e.g., `default`)
   - **Athena S3 Staging** → the full `s3://...` path where Athena writes query results. Must end with `/`
   - **Athena Region** → AWS region of your Athena workgroup (e.g., `ap-south-1`)
   - **Athena Workgroup** → workgroup name (use `primary` if unsure)
5. Click **Save**
6. **Restart Claude Desktop** (Cmd+Q then reopen) — MCP servers only pick up env-var changes on restart

**Start it:** Ask *"list athena tables"* or *"sample the orders table"* — the `athena` MCP tools (`list_athena_tables`, `describe_athena_table`, `query_athena`, `sample_table`) become available automatically once the plugin loads.

### Superset (BI Dashboards)

Connect to a Superset instance to read dashboards, charts, and run SQL via the Superset API.

**Required settings:**

| Field | Example | Description |
|---|---|---|
| `Superset URL` | `https://superset.example.com` | Base URL of your Superset instance |
| `Superset API Key` *(recommended)* | `sst_...` | Create at **Superset → Settings → API Keys** |
| `Superset Username` / `Password` | — | Alternative to API key (DB auth) |
| `Superset Auth Provider` | `db` | `db` (default), `ldap`, or `oauth` |
| `Superset Database ID` | `1` | Default DB connection ID (find at **Data → Databases**) |
| `Superset Schema` | `databaseName` | Default schema for queries |

**How to configure (step-by-step):**

1. **(One-time) Create a Superset API key:**
   - Log into Superset in your browser
   - Click your profile icon (top-right) → **Settings** → **API Keys** (or **Security → API Keys** on older versions)
   - Click **+ Create**, give it a name (e.g., `ai-analyst-plugin`), and copy the generated key (starts with `sst_...`). **You will not be able to see this key again.**
2. **(One-time) Find your Database ID:**
   - In Superset, go to **Data → Databases**
   - Find the database row you want as default → note the numeric ID in the URL when you click into it (e.g., `/databaseview/edit/1` → ID is `1`)
3. Open **Claude Desktop** → **Settings** → **Plugins** → **AI Analyst Plugin** → **⚙ Configure**
4. Scroll to the **Superset** section. Fill in:
   - **Superset URL** → full base URL, no trailing slash (e.g., `https://superset.example.com`)
   - **Superset API Key** → paste the `sst_...` key from step 1 *(recommended)*
   - **Superset Username / Password** → leave empty if using API key; otherwise enter DB-auth credentials
   - **Superset Auth Provider** → `db` for API key or DB auth; `ldap` or `oauth` if your instance uses those
   - **Superset Database ID** → the numeric ID from step 2
   - **Superset Schema** → default schema name (e.g., `default`)
5. Click **Save**, then **restart Claude Desktop**

**Start it:** Leave `Superset URL` empty to skip this integration entirely. Otherwise, the `superset` MCP tools activate on plugin load — ask *"list superset dashboards"* or *"run this query against superset"* to use them.

### OpenMetadata (Live Schema & Descriptions) — optional

When configured, OpenMetadata becomes the **preferred live source** for table/column schema and descriptions: schema and description changes made in OpenMetadata show up immediately, with no manual edits to the knowledge repo. The knowledge repo's `schema.md` remains the offline fallback. Quirks, metric definitions, golden queries, and PII/partition guardrails **always** come from the Knowledge Repo — OpenMetadata does not replace those.

This connects to OpenMetadata's own built-in MCP server (v1.12+), so there is nothing to run locally beyond a small proxy.

**Prerequisite:** **Node / `npx` must be installed.** The connection uses the `mcp-remote` proxy, which is fetched automatically on first run via `npx -y`. (The other integrations are pure Python; this one needs Node.)

**Required settings:**

| Field | Example | Description |
|---|---|---|
| `OpenMetadata URL` | `https://openmetadata.example.com` | Base URL of your OpenMetadata instance (no trailing slash; `/mcp` is appended automatically) |
| `OpenMetadata Personal Access Token` | `eyJ...` | PAT from your OpenMetadata profile |

**How to configure (step-by-step):**

1. **(One-time) Generate a Personal Access Token:**
   - Visit `<YOUR-OpenMetadata-SERVER>/users/<YOUR-USERNAME>/access-token` in your browser
   - Click **Generate New Token** and copy it
2. Open **Claude Desktop** → **Settings** → **Plugins** → **AI Analyst Plugin** → **⚙ Configure**
3. Scroll to the **OpenMetadata** section. Fill in:
   - **OpenMetadata URL** → full base URL, no trailing slash (e.g., `https://openmetadata.example.com`)
   - **OpenMetadata Personal Access Token** → paste the token from step 1
4. Click **Save**, then **restart Claude Desktop**

**Start it:** Leave `OpenMetadata URL` empty to skip this integration entirely — the Knowledge Repo `schema.md` stays the primary schema source. Otherwise, the `semantic_search` (meaning-based table discovery), `search_metadata` (keyword lookup), and `get_entity_details` tools activate on plugin load and become the preferred schema source automatically.

### Knowledge Repo (Business Context)

A GitHub-backed (or local) knowledge base of dataset schemas, metric definitions, business glossary, and SQL patterns. The plugin reads this on every question to ground its answers in your org's reality.

**Required settings — choose ONE source:**

| Field | Example | Description |
|---|---|---|
| `Knowledge Repo URL` | `https://github.com/test/knowledge-repo` | GitHub repo (HTTPS or SSH) |
| `Knowledge Repo Branch` | `main` | Branch to track |
| `Knowledge GitHub Token` | `ghp_...` | Required only for **private** repos |
| `Knowledge Local Path` | `/Users/me/knowledge-repo` | Use a local directory instead of GitHub |
| `Knowledge Datasets` | `org` | Comma-separated dataset IDs (auto-discovered if blank) |

**Expected repo layout:**

```
knowledge-repo/
├── datasets/
│   └── <dataset-id>/
│       ├── schema.yaml
│       ├── metrics.yaml
│       └── glossary.md
└── organizations/
    └── <org>/...
```

**How to configure (step-by-step):**

Pick **one** source — GitHub-backed (recommended for teams) or local (for testing).

**Option A — GitHub-backed knowledge repo:**

1. **(One-time) For private repos only:** create a GitHub Personal Access Token:
   - Go to https://github.com/settings/tokens → **Generate new token (classic)**
   - Scope: check **`repo`**
   - Copy the `ghp_...` token. Public repos can skip this step.
2. Open **Claude Desktop** → **Settings** → **Plugins** → **AI Analyst Plugin** → **⚙ Configure**
3. Scroll to the **Knowledge** section. Fill in:
   - **Knowledge Repo URL** → full HTTPS or SSH URL (e.g., `https://github.com/test/knowledge-repo`)
   - **Knowledge Repo Branch** → branch name (defaults to `main`)
   - **Knowledge GitHub Token** → paste the `ghp_...` token (private repos only; leave empty for public)
   - **Knowledge Datasets** → comma-separated dataset folder names (e.g., `traya-health`). Leave empty to auto-discover all `datasets/*/` folders.
   - **Knowledge Local Path** → **leave empty**
4. Click **Save**, then **restart Claude Desktop**

**Option B — Local knowledge directory (for testing):**

1. Clone or create your knowledge repo locally (e.g., `git clone <url> ~/knowledge-repo`)
2. Open **Settings** → **Plugins** → **AI Analyst Plugin** → **⚙ Configure**
3. Scroll to the **Knowledge** section:
   - **Knowledge Repo URL** → **leave empty**
   - **Knowledge Local Path** → click **Browse**, select the local directory (e.g., `/Users/me/knowledge-repo`)
   - **Knowledge Datasets** → optional, as above
4. Click **Save**, then **restart Claude Desktop**

**Start it:** Once configured, the `knowledge` MCP tools (`list_datasets`, `get_page`, `lookup_index`, `refresh_knowledge`) become available. Run `/refresh-dataset` after pushing changes to your knowledge repo to pull the latest.

### Verifying integrations

After install, run any of these in a Claude conversation to confirm each server is up:

- Athena: *"list athena tables"*
- Superset: *"list superset dashboards"*
- Knowledge: *"list datasets"* or `/business`

If a server fails to start, check **Settings → Plugins → AI Analyst Plugin → Logs** for the underlying Python error (most commonly a missing AWS profile, an unreachable Superset URL, or an invalid GitHub token).
