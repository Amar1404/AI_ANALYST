"""MCP Server for AWS Athena queries.

Runs locally with access to AWS credentials. Cowork calls this
via MCP to execute Athena queries without needing credentials in
the sandbox.

Usage:
    python servers/mcp_athena_server.py

Environment variables:
    ATHENA_CONFIG: Path to JSON config file with connection details.
    Falls back to individual env vars if config file not found.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Auto-install dependencies if missing
try:
    import mcp  # noqa: F401
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "mcp[cli]", "pyathena", "boto3", "pyyaml", "pandas"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("athena-query")


# Connection config — reads from config file or env vars
def _load_athena_config() -> dict:
    """Load Athena config from JSON file, falling back to env vars."""
    config_path = os.environ.get("ATHENA_CONFIG", "")
    if config_path and Path(config_path).exists():
        return json.loads(Path(config_path).read_text())
    return {
        "database": os.environ.get("ATHENA_DATABASE", "trayaprod"),
        "s3_staging_dir": os.environ.get("ATHENA_S3_STAGING", "s3://traya-dp-prod/athena-output/"),
        "region_name": os.environ.get("ATHENA_REGION", "ap-south-1"),
        "work_group": os.environ.get("ATHENA_WORKGROUP", "jupyter"),
        "profile_name": os.environ.get("AWS_PROFILE", "prod"),
    }


ATHENA_CONFIG = _load_athena_config()


def _get_connection():
    """Create a PyAthena connection using local AWS credentials."""
    from pyathena import connect
    import boto3

    session = boto3.Session(profile_name=ATHENA_CONFIG["profile_name"])
    return connect(
        s3_staging_dir=ATHENA_CONFIG["s3_staging_dir"],
        region_name=ATHENA_CONFIG["region_name"],
        work_group=ATHENA_CONFIG["work_group"],
        schema_name=ATHENA_CONFIG["database"],
        boto3_session=session,
    )


# PII columns that must never appear in query results
_PII_COLUMNS = {
    "email", "phone_number", "phone", "chat_phone_number",
    "first_name", "last_name", "name",
    "customername", "phone_no",
    "order_meta_shipping_address", "order_meta_billing_address",
}


def _redact_pii(columns: list[str], rows: list) -> tuple[list[str], list, list[str]]:
    """Redact PII columns from query results.

    Returns (clean_columns, clean_rows, redacted_column_names).
    """
    pii_indices = []
    redacted_names = []
    for i, col in enumerate(columns):
        if col.lower() in _PII_COLUMNS:
            pii_indices.append(i)
            redacted_names.append(col)

    if not pii_indices:
        return columns, rows, []

    keep = [i for i in range(len(columns)) if i not in pii_indices]
    clean_columns = [columns[i] for i in keep]
    clean_rows = [tuple(row[i] for i in keep) for row in rows]
    return clean_columns, clean_rows, redacted_names


def _check_pii_in_select(sql: str) -> list[str]:
    """Check if SQL SELECT clause contains PII columns.

    Only checks the SELECT portion (before FROM). PII in WHERE/JOIN is allowed.
    Returns list of PII column names found in SELECT, or empty list.
    """
    sql_upper = sql.upper().strip()
    if not sql_upper.startswith("SELECT"):
        return []

    # Extract the SELECT clause (everything before the first FROM)
    from_pos = sql_upper.find(" FROM ")
    if from_pos == -1:
        return []
    select_clause = sql.lower()[:from_pos]

    # Check if SELECT * (bare wildcard, not COUNT(*) or similar)
    import re as _re
    if _re.search(r'(?<!\w)\*(?!\))', select_clause):
        return ["SELECT * may expose PII columns"]

    found = []
    for pii_col in _PII_COLUMNS:
        # Match whole word only (not substring)
        import re as _re
        if _re.search(r'\b' + _re.escape(pii_col) + r'\b', select_clause):
            found.append(pii_col)
    return found


@mcp.tool()
def query_athena(sql: str) -> str:
    """Execute a SELECT query against AWS Athena and return results as JSON.

    Args:
        sql: The SQL SELECT query to execute. Use fully qualified table names
             for cross-database queries (e.g., trayaprod.engagements_vw).
             Available databases: trayaprod, tatvav2db_public, traya_marts_ez, google_analytics, facebook_ads.
             IMPORTANT:
             - Only SELECT queries are supported. No SHOW, USE, DESCRIBE, or DDL.
             - Always include LIMIT to avoid scanning too much data.
             - PII columns (email, phone, name, address) cannot be in SELECT — use case_id/user_id instead.
             - PREFER aggregated queries (GROUP BY, COUNT, SUM, AVG) over raw row selects.
               Bad:  SELECT * FROM orders WHERE activity_date >= '2026-03-01' LIMIT 1000
               Good: SELECT activity_date, COUNT(*) as orders, SUM(total_amount) as revenue
                     FROM orders WHERE activity_date >= '2026-03-01' GROUP BY activity_date
             - Use sample_table to preview raw data instead of SELECT * with large LIMIT.
             - Keep result sets small — aggregate first, drill down only if needed.

    Returns:
        JSON string with columns and rows, or error message.
    """
    # Pre-execution: block queries that SELECT PII columns
    pii_found = _check_pii_in_select(sql)
    if pii_found:
        return json.dumps({
            "error": "Query blocked: cannot SELECT personally identifiable columns.",
            "blocked_columns": pii_found,
            "suggestion": "Use case_id or user_id as anonymous identifiers instead."
        })

    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall()
        cur.close()
        conn.close()

        # Redact PII columns before returning results
        columns, rows, redacted = _redact_pii(columns, rows)

        data = [dict(zip(columns, row)) for row in rows[:500]]
        result = {
            "columns": columns,
            "row_count": len(rows),
            "data": data,
        }
        if redacted:
            result["redacted_columns"] = redacted
            result["notice"] = f"PII columns removed from results: {', '.join(redacted)}"
        if len(rows) > 500:
            result["truncated"] = True
            result["total_rows"] = len(rows)

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_athena_tables(database: str = "") -> str:
    """List all tables in an Athena/Glue database.

    Args:
        database: Glue catalog database name. Defaults to trayaprod.
                  Common databases: trayaprod, tatvav2db_public,
                  traya_marts_ez, google_analytics.
    """
    try:
        db = database or ATHENA_CONFIG["database"]
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(f"SHOW TABLES IN {db}")
        tables = sorted(row[0] for row in cur.fetchall())
        cur.close()
        conn.close()
        return json.dumps({"database": db, "tables": tables, "count": len(tables)})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def sample_table(table: str, database: str = "", limit: int = 10) -> str:
    """Get a sample of the most recent rows from a table based on activity_date.

    Use this BEFORE writing analytical queries to understand actual data values,
    formats, and patterns. Much cheaper than scanning the full table.

    Args:
        table: Table name (e.g., engagements_vw, orders_vw).
        database: Database name. Defaults to trayaprod.
        limit: Number of rows to return (default 10, max 50).
    """
    try:
        import pandas as pd

        db = database or ATHENA_CONFIG["database"]
        limit = min(limit, 50)
        fqn = f"{db}.{table}"

        conn = _get_connection()
        cur = conn.cursor()

        # Try activity_date first, fall back to no ordering
        sql = f"SELECT * FROM {fqn} WHERE activity_date = (SELECT MAX(activity_date) FROM {fqn}) LIMIT {limit}"
        try:
            cur.execute(sql)
        except Exception:
            cur.execute(f"SELECT * FROM {fqn} LIMIT {limit}")

        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall()
        cur.close()
        conn.close()

        columns, rows, redacted = _redact_pii(columns, rows)
        df = pd.DataFrame(rows, columns=columns)

        result = {
            "table": fqn,
            "row_count": len(df),
            "columns": list(df.columns),
            "dtypes": {col: str(dt) for col, dt in df.dtypes.items()},
            "sample": df.to_dict(orient="records"),
        }
        if redacted:
            result["redacted_columns"] = redacted
        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def describe_athena_table(table: str, database: str = "") -> str:
    """Get column names and types for a table.

    Args:
        table: Table name (e.g., engagements_vw, orders_vw).
        database: Database name. Defaults to trayaprod.
    """
    try:
        db = database or ATHENA_CONFIG["database"]
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = '{db}' AND table_name = '{table}'
            ORDER BY ordinal_position
        """)
        columns = [{"name": row[0], "type": row[1]} for row in cur.fetchall()]
        cur.close()
        conn.close()
        return json.dumps({"database": db, "table": table, "columns": columns})
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
