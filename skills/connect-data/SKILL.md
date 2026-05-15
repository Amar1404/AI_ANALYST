---
name: connect-data
description: "Triggers on \"connect\", \"add data source\", \"link database\", \"/connect-data\", \"/datasets\"."
triggers:
  - /connect-data
  - /datasets
  - connect my database
  - add a data source
  - link data
  - set up a connection
---

# Skill: Connect Data

## Purpose
Guided wizard to connect a new dataset. Walks the user through selecting
a connection type, configuring credentials, validating the connection,
profiling the schema, and setting up the knowledge brain.

## When to Use
- User says `/connect-data` or "connect my database" or "add a new dataset"
- First-run welcome suggests connecting data
- After `/switch-dataset` when the target dataset doesn't exist yet

## Invocation
`/connect-data` — start the connection wizard
`/connect-data type=postgres` — skip type selection

## Instructions

### Step 1: Choose Connection Type
Ask the user: "What type of data source are you working with? (e.g., CSV, DuckDB, PostgreSQL, BigQuery, Snowflake, Athena, ClickHouse)"

Do NOT use multiple-choice tool. Just ask as a plain text question and match their response to one of: csv, duckdb, motherduck, postgres, bigquery, snowflake, athena, clickhouse.

### Step 2: Collect Connection Details

**For CSV:**
- Ask: "What's the path to your CSV directory? (relative to this repo)"
- Verify the directory exists and contains .csv files
- List found files and ask to confirm

**For DuckDB:**
- Ask: "Path to your .duckdb file?"
- Verify file exists
- Test connection with `SELECT 1`

**For MotherDuck:**
- Ask: "Database name and schema?"
- Note: "MotherDuck connects via MCP. Make sure your token is configured."

**For PostgreSQL / BigQuery / Snowflake:**
- Copy the appropriate template from `connection_templates/`
- Ask user to fill in required fields
- **IMPORTANT:** Never ask for or store passwords directly. Guide the user
  to use environment variables (e.g., `$PG_PASSWORD`).

**For Athena:**
- Ask: "What's your Glue catalog database name?"
- Ask: "S3 staging directory for query results?" (e.g., `s3://my-bucket/athena-results/`)
- Ask: "AWS region?" (e.g., `us-east-1`)
- Ask: "Athena workgroup?" (default: `primary`)
- Ask: "How do you authenticate?"
  - **Default** — IAM role, SSO, or environment variables (recommended)
  - **AWS Profile** — ask for profile name
  - **Access Key Credentials** — guide to set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` env vars
- Copy template from `connection_templates/athena.yaml.example`
- Note: "Column descriptions from your Glue catalog will be pulled automatically during profiling."

**For ClickHouse:**
- Ask: "ClickHouse host?" (default: `localhost`)
- Ask: "HTTP port?" (default: `8123`)
- Ask: "Database name?"
- Ask: "Username?" (default: `default`)
- Ask: "Password?" — guide to set `CLICKHOUSE_PASSWORD` env var
- Ask: "Use HTTPS?" (yes/no, default: no)
- Copy template from `connection_templates/clickhouse.yaml.example`
- Note: "Column descriptions from table comments will be pulled automatically during profiling."

### Step 3: Create Dataset Brain
1. Generate a dataset_id from the display name (lowercase, hyphens)
2. Create `<workspace>/.knowledge/datasets/{id}/` directory
3. Write `manifest.yaml` from the connection template + user inputs
4. Create empty `quirks.md` with section headers
5. Create empty `metrics/index.yaml`

### Step 4: Test Connection
Use `ConnectionManager` from `helpers/connection_manager.py`:
1. Instantiate with the new config
2. Call `test_connection()`
3. If fails: show error, offer to retry or edit config
4. If passes: proceed

### Step 5: Profile Schema
1. Call `list_tables()` to enumerate tables
2. For each table: get column names and types via `get_table_schema()`
3. Generate `schema.md` using `schema_to_markdown()` from `helpers/data_helpers.py`
4. Write to `<workspace>/.knowledge/datasets/{id}/schema.md`
5. Offer to run full data profiling: "Want me to deep-profile this dataset?"

### Step 6: Set Active
1. Update `<workspace>/.knowledge/active.yaml` to point to the new dataset
2. Confirm: "Connected! **{display_name}** is now your active dataset."
3. Show: table count, estimated row count, date range (if detected)
4. Suggest next steps: `/explore` to browse, `/metrics` to define metrics,
   or just ask a question

## Rules
1. Never store credentials in plain text in manifest files
2. Always test the connection before declaring success
3. Always generate a schema.md — it's required for analysis
4. Create the full `<workspace>/.knowledge/datasets/{id}/` tree even if profiling fails
5. If the user already has this dataset, ask before overwriting

## Edge Cases
- **Directory doesn't exist:** Offer to create it
- **No CSV files found:** Check for other formats (.parquet, .json)
- **Connection fails repeatedly:** Suggest checking credentials, firewall, VPN
- **Schema too large (>100 tables):** Profile only, skip per-table details
- **Dataset name collision:** Append a number (e.g., "mydata-2")

## Also: Dataset Management (`/datasets`)

When invoked as `/datasets`, display all connected datasets with their status.

### Step 1: Read the source registry

Read `<workspace>/data_sources.yaml` to get the list of registered sources.

### Step 2: Read the active pointer

Read `<workspace>/.knowledge/active.yaml` to determine which dataset is currently active.

### Step 3: Enrich with brain data

For each registered source, check if `<workspace>/.knowledge/datasets/{name}/manifest.yaml` exists. If it does, read summary stats (table_count, date_range, analysis_count, last_used).

### Step 4: Display the list

```
Connected Datasets:

  * your_dataset (active)
    Your Dataset Name — {table_count} tables, {date_range}
    Connection: {type} ({database})
    Analyses: 0

  - {other_dataset}
    {display_name} — {table_count} tables, {date_range}
    Connection: {type} ({details})
    Analyses: {count}

Commands:
  /switch-dataset {name}  — switch active dataset
  /connect-data           — connect a new dataset
  /data                   — inspect active dataset schema
```

Mark the active dataset with `*`. Mark others with `-`.

### Dataset Management Rules

1. **Never show connection credentials** — display type and database/schema only, never tokens or passwords
2. **Never show datasets that have no registry entry** — orphaned `<workspace>/.knowledge/datasets/` dirs without a `data_sources.yaml` entry should be ignored

## Connection Details & Dialects

See `references/connection-guide.md` for SQL dialect-specific guidance for each connection type.
