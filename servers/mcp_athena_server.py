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

# File-first result behavior (see docs/superpowers/specs/2026-06-19-file-first-query-results-design.md)
CHUNK = 5000              # rows per fetchmany batch — server never full-loads a result
INLINE_THRESHOLD = 50    # results <= this many rows are inlined into context; larger -> handle only
PREVIEW_ROWS = 5         # rows in the handle preview for large results
STALE_SWEEP_SECONDS = 86400  # 24h — query-cache dirs older than this are swept on startup


# Connection config — reads from config file or env vars
def _load_athena_config() -> dict:
    """Load Athena config from JSON file, falling back to env vars."""
    config_path = os.environ.get("ATHENA_CONFIG", "")
    if config_path and Path(config_path).exists():
        return json.loads(Path(config_path).read_text())
    return {
        "database": os.environ.get("ATHENA_DATABASE", "default"),
        "s3_staging_dir": os.environ.get("ATHENA_S3_STAGING", "s3://traya-athena-bucket/jupyter-query/"),
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


def _write_result_csv(cursor, columns, out_path) -> tuple[int, list[str]]:
    """Stream cursor results to a CSV at out_path, chunk by chunk.

    Redacts PII per chunk before writing. Header is written exactly once, using
    the post-redaction columns. Returns (rows_written, redacted_names). Writes a
    header-only file when there are no rows. The full result set is never held in
    memory — only one CHUNK-sized batch at a time.
    """
    import csv as _csv

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    total = 0
    header_written = False
    redacted_names: list[str] = []
    clean_columns = columns

    with open(out_path, "w", newline="") as f:
        writer = _csv.writer(f)
        while True:
            batch = cursor.fetchmany(CHUNK)
            if not batch:
                break
            clean_columns, clean_rows, redacted = _redact_pii(columns, batch)
            if redacted:
                redacted_names = redacted
            if not header_written:
                writer.writerow(clean_columns)
                header_written = True
            for row in clean_rows:
                writer.writerow(["" if v is None else v for v in row])
            total += len(clean_rows)

        if not header_written:
            # zero rows: still emit the (redacted) header
            clean_columns, _, redacted = _redact_pii(columns, [])
            writer.writerow(clean_columns)
            if redacted:
                redacted_names = redacted

    return total, redacted_names


def _fallback_workspace() -> Path:
    """Writable workspace of last resort, under the system temp dir.

    Hosts like Claude Desktop/Cowork launch MCP servers with cwd='/' on a
    read-only filesystem, so cwd cannot be assumed writable.
    """
    import tempfile as _tempfile

    d = Path(_tempfile.gettempdir()) / "ai-analyst-workspace"
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def _workspace_root() -> Path:
    """Workspace root: AI_ANALYST_WORKSPACE if a real dir, else a writable cwd,
    else a temp-dir fallback."""
    ws = os.environ.get("AI_ANALYST_WORKSPACE", "")
    if ws and Path(ws).is_dir():
        return Path(ws).resolve()
    cwd = Path.cwd().resolve()
    if os.access(cwd, os.W_OK):
        return cwd
    return _fallback_workspace()


def _session_cache_dir() -> Path:
    """Per-session, self-cleaning cache dir for intermediate query CSVs."""
    import tempfile as _tempfile

    sid = os.environ.get("AI_ANALYST_SESSION_ID") or str(os.getpid())
    for root in (_workspace_root(), _fallback_workspace()):
        d = root / ".query-cache" / sid
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except OSError:
            continue
    return Path(_tempfile.mkdtemp(prefix="ai-analyst-query-cache-"))


def _slugged_temp_path() -> str:
    """A unique CSV path inside the session cache dir (q1.csv, q2.csv, ...)."""
    cache = _session_cache_dir()
    n = len(list(cache.glob("q*.csv"))) + 1
    path = cache / f"q{n}.csv"
    while path.exists():
        n += 1
        path = cache / f"q{n}.csv"
    return str(path)


def _query_cache_key(sql: str) -> str:
    """Stable key for a query: whitespace-normalized SQL, trailing ';' dropped.

    Case is preserved — lowercasing would conflate string literals that differ
    only by case.
    """
    import hashlib as _hashlib

    normalized = " ".join(sql.split()).rstrip(";").strip()
    return _hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _cache_paths(key: str) -> tuple[Path, Path]:
    """(csv_path, meta_path) for a cache key inside the session cache dir."""
    cache = _session_cache_dir()
    return cache / f"q_{key}.csv", cache / f"q_{key}.meta.json"


def _cache_lookup(sql: str) -> dict | None:
    """Return {"csv": Path, "meta": dict} when this SQL already ran this session."""
    csv_path, meta_path = _cache_paths(_query_cache_key(sql))
    if not (csv_path.exists() and meta_path.exists()):
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return None
    if "row_count" not in meta:
        return None
    return {"csv": csv_path, "meta": meta}


def _cache_store(key: str, result_path: str, total: int, redacted: list[str]) -> None:
    """Record a finished result in the session cache. Best-effort."""
    import shutil as _shutil

    try:
        csv_path, meta_path = _cache_paths(key)
        if str(csv_path) != str(result_path):
            _shutil.copyfile(result_path, csv_path)
        meta_path.write_text(
            json.dumps({"row_count": total, "redacted_columns": redacted})
        )
    except OSError:
        pass


def _resolve_out_dir(out_path: str):
    """Return (final_path:str, is_deliverable:bool, warning:str|None).

    Empty out_path -> a self-cleaning temp file in the session cache.
    A path inside the workspace -> a retained deliverable at that path.
    A path that escapes the workspace -> fall back to the cache + a warning.
    """
    if not out_path:
        return _slugged_temp_path(), False, None

    ws = _workspace_root()
    candidate = (Path(out_path) if os.path.isabs(out_path) else ws / out_path).resolve()
    try:
        candidate.relative_to(ws)
    except ValueError:
        warn = (
            f"out_path '{out_path}' is outside the workspace; "
            f"wrote to the session cache instead."
        )
        return _slugged_temp_path(), False, warn
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        warn = (
            f"could not create directory for out_path '{out_path}' ({e}); "
            f"wrote to the session cache instead."
        )
        return _slugged_temp_path(), False, warn
    return str(candidate), True, None


def _sweep_stale_cache() -> int:
    """Delete .query-cache/* subdirs older than STALE_SWEEP_SECONDS. Best-effort."""
    import time as _time
    import shutil as _shutil

    removed = 0
    try:
        root = _workspace_root() / ".query-cache"
        if not root.is_dir():
            return 0
        now = _time.time()
        for sub in root.iterdir():
            try:
                if sub.is_dir() and (now - sub.stat().st_mtime) > STALE_SWEEP_SECONDS:
                    _shutil.rmtree(sub, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    except OSError:
        return removed
    return removed


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


def _strip_pii_from_select(sql: str) -> tuple[str, list[str]]:
    """Drop any PII columns from the SELECT clause of a query.

    Used on the S3-direct delivery path, where Athena writes the result to S3
    server-side and we copy that file without per-row Python redaction — so the
    PII columns must be excluded in the SQL itself. Returns (cleaned_sql,
    removed_columns). Only rewrites the projection (before the first FROM);
    PII referenced in WHERE/JOIN is left untouched.
    """
    import re as _re

    from_pos = sql.upper().find(" FROM ")
    if from_pos == -1:
        return sql, []

    select_clause = sql[:from_pos]
    rest = sql[from_pos:]

    # Split the projection on top-level commas (no nested parens — these are
    # plain column projections; aggregates/functions have no PII columns).
    head = select_clause[: select_clause.lower().find("select") + len("select")]
    projection = select_clause[len(head):]
    items = [c.strip() for c in projection.split(",")]

    removed = []
    kept = []
    for item in items:
        # The output name is the last identifier token in the item.
        token = _re.split(r"\s+", item.strip())[-1].strip('`"').lower()
        if token in _PII_COLUMNS:
            removed.append(token)
        else:
            kept.append(item)

    if not removed:
        return sql, []

    cleaned = f"{head} {', '.join(kept)}{rest}"
    return cleaned, removed


def _deliver_from_s3(output_location: str, out_path: str, s3_client) -> None:
    """Copy Athena's S3 result object to a local deliverable path, atomically.

    Downloads to a `<out_path>.partial` staging file, then renames onto out_path
    only after the download completes — so an interrupted transfer never leaves a
    partial file masquerading as a finished deliverable.
    """
    if not output_location.startswith("s3://"):
        raise ValueError(f"not an S3 location: {output_location}")
    bucket, _, key = output_location[len("s3://"):].partition("/")

    final = Path(out_path)
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = final.with_suffix(final.suffix + ".partial")

    try:
        s3_client.download_file(Bucket=bucket, Key=key, Filename=str(staging))
        os.replace(staging, final)
    except BaseException:
        try:
            staging.unlink()
        except OSError:
            pass
        raise


def _result_handle(
    final_path: str,
    total: int,
    is_deliverable: bool,
    redacted: list[str],
    warning: str | None,
    fallback_columns: list[str] | None = None,
    cached: bool = False,
) -> str:
    """Build the JSON result handle for a finished CSV, reading back only a
    bounded preview — never full-loading the file."""
    import csv as _csv

    preview_rows = []
    clean_columns = fallback_columns or []
    with open(final_path, newline="") as f:
        reader = _csv.reader(f)
        header = next(reader, None)
        if header is not None:
            clean_columns = header
        cap = total if total <= INLINE_THRESHOLD else PREVIEW_ROWS
        for i, row in enumerate(reader):
            if i >= cap:
                break
            preview_rows.append(row)

    result = {
        "file_path": final_path,
        "row_count": total,
        "columns": clean_columns,
        "is_deliverable": is_deliverable,
    }
    if cached:
        result["cached"] = True
        result["notice"] = (
            "Served from the session query cache — this exact SQL already ran. "
            "Reuse this file instead of re-querying; pass refresh=true only if "
            "you need fresher data."
        )
    if total <= INLINE_THRESHOLD:
        result["data"] = [dict(zip(clean_columns, r)) for r in preview_rows]
    else:
        result["preview"] = [dict(zip(clean_columns, r)) for r in preview_rows]
    if redacted:
        result["redacted_columns"] = redacted
        result["notice"] = f"PII columns removed from results: {', '.join(redacted)}"
    if warning:
        result["warning"] = warning
    return json.dumps(result, default=str)


def _serve_cached(entry: dict, out_path: str) -> str:
    """Answer a repeated query from the session cache without touching Athena.

    When the caller asked for a deliverable, copy the cached CSV to that path so
    the download semantics match a fresh run.
    """
    import shutil as _shutil

    src = str(entry["csv"])
    meta = entry["meta"]
    final_path, is_deliverable, warning = src, False, None

    if out_path:
        candidate, is_deliverable, warning = _resolve_out_dir(out_path)
        if is_deliverable:
            try:
                _shutil.copyfile(src, candidate)
                final_path = candidate
            except OSError as e:
                is_deliverable = False
                warning = (
                    f"could not copy the cached result to '{out_path}' ({e}); "
                    f"serving the cached file instead."
                )

    return _result_handle(
        final_path,
        meta["row_count"],
        is_deliverable,
        meta.get("redacted_columns") or [],
        warning,
        cached=True,
    )


def _run_query(cursor, out_path: str = "", cache_key: str | None = None) -> str:
    """Execute against an open cursor: write the full result to a CSV and return a
    handle. Inline the rows only when the result is small (<= INLINE_THRESHOLD).

    The result set is never full-loaded: it is streamed to disk in chunks, and the
    preview is read back with a bounded reader. On a write failure, degrade
    gracefully to a bounded inline result rather than losing the answer entirely.
    """
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    if not out_path and cache_key:
        # Name the file by SQL hash so a repeat of this query is a cache hit.
        final_path, is_deliverable, warning = str(_cache_paths(cache_key)[0]), False, None
    else:
        final_path, is_deliverable, warning = _resolve_out_dir(out_path)

    try:
        total, redacted = _write_result_csv(cursor, columns, final_path)
    except OSError as e:
        # Could not write the CSV — degrade to a bounded inline result.
        clean_columns, clean_rows, redacted = _redact_pii(
            columns, cursor.fetchmany(INLINE_THRESHOLD)
        )
        out = {
            "row_count": len(clean_rows),
            "columns": clean_columns,
            "data": [dict(zip(clean_columns, r)) for r in clean_rows],
            "notice": (
                f"Could not write results to {final_path}: {e}. "
                f"Returned the first {len(clean_rows)} rows inline instead."
            ),
        }
        if redacted:
            out["redacted_columns"] = redacted
        return json.dumps(out, default=str)

    if cache_key:
        _cache_store(cache_key, final_path, total, redacted)

    return _result_handle(
        final_path, total, is_deliverable, redacted, warning, fallback_columns=columns
    )


@mcp.tool()
def query_athena(sql: str, out_path: str = "", refresh: bool = False) -> str:
    """Execute a SELECT against Athena. Writes the full result to a CSV and returns
    a handle (file_path, row_count, columns, 5-row preview). Inlines the rows
    directly only when the result is small (<= 50 rows).

    Repeated identical SQL is served from a per-session result cache without
    re-running Athena — the handle carries "cached": true. This makes re-asking
    safe, but prefer combining related metrics/breakdowns into ONE query
    (CTEs, GROUP BY GROUPING SETS, UNION ALL) over issuing several small ones.

    Args:
        sql: The SQL SELECT query to execute. Use fully qualified table names
             (database.table) for cross-database queries.
             IMPORTANT:
             - Only SELECT queries are supported. No SHOW, USE, DESCRIBE, or DDL.
             - BATCH related asks into one query: multiple metrics belong in one
               SELECT; multi-dimension breakdowns belong in one GROUP BY GROUPING SETS
               query (which also returns the grand-total row for validation) instead of
               one query per dimension or a separate total/count query.
             - Do NOT add LIMIT to aggregated or "give me all of X" queries — a LIMIT
               silently truncates the answer (you lose categories/rows past the cap and
               get a wrong total). The full result is streamed to a CSV either way, so
               LIMIT is not needed to keep results out of context. Use LIMIT only when you
               are deliberately previewing or spot-checking a few raw rows.
             - Control scan cost with the PARTITION FILTER, not LIMIT. Always filter on the
               partition column (e.g. activity_date) — that bounds bytes scanned (what
               Athena bills), which a LIMIT does not.
             - On large tables prefer approx_distinct() / approx_percentile() over exact
               COUNT(DISTINCT) / percentiles when close-enough answers are acceptable.
             - PII columns (email, phone, name, address) cannot be in SELECT — use case_id/user_id instead.
             - PREFER aggregated queries (GROUP BY, COUNT, SUM, AVG) over raw row selects.
               Bad:  SELECT * FROM orders WHERE activity_date >= '2026-03-01'
               Good: SELECT activity_date, COUNT(*) as orders, SUM(total_amount) as revenue
                     FROM orders WHERE activity_date >= '2026-03-01' GROUP BY activity_date
             - Aggregate first, drill down only if needed — the writer handles result size.
        out_path: Optional. When set (a deliverable the user asked to download), the
             CSV is written there and kept. When empty, it goes to a self-cleaning
             session cache dir. Paths outside the workspace are rejected and fall
             back to the cache (a warning is returned).
        refresh: Set true only when the user explicitly needs fresher data than a
             result already fetched this session — bypasses the result cache.

    Returns:
        JSON string with a result handle (and inline rows if small), or an error.
    """
    # Pre-execution: block queries that SELECT PII columns
    pii_found = _check_pii_in_select(sql)
    if pii_found:
        return json.dumps({
            "error": "Query blocked: cannot SELECT personally identifiable columns.",
            "blocked_columns": pii_found,
            "suggestion": "Use case_id or user_id as anonymous identifiers instead."
        })

    if not refresh:
        try:
            entry = _cache_lookup(sql)
        except OSError:
            entry = None
        if entry:
            return _serve_cached(entry, out_path)

    conn = None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(sql)
        return _run_query(cur, out_path, cache_key=_query_cache_key(sql))
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@mcp.tool()
def list_athena_tables(database: str = "") -> str:
    """List all tables in an Athena/Glue database.

    Args:
        database: Glue catalog database name. Defaults to the configured database
                  (ATHENA_DATABASE).
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
        table: Table name.
        database: Database name. Defaults to the configured database (ATHENA_DATABASE).
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
def describe_athena_table(table: str = "", database: str = "", tables: list[str] | None = None) -> str:
    """Get column names and types for one or MORE tables in a single call.

    When you need the schema of several tables, pass them all at once via
    `tables=[...]` — one information_schema query covers them all. Do not call
    this tool once per table.

    Args:
        table: Single table name (legacy form; returns {table, columns}).
        database: Database name. Defaults to the configured database (ATHENA_DATABASE).
        tables: List of table names to describe together. Returns
                {tables: {name: [{name, type}, ...]}, missing: [...]}.
    """
    try:
        db = database or ATHENA_CONFIG["database"]
        names = [t.strip() for t in (tables or []) if t and t.strip()]
        if table and table not in names:
            names.insert(0, table)
        if not names:
            return json.dumps({"error": "provide `table` or `tables`"})

        in_list = ", ".join("'" + n.replace("'", "''") + "'" for n in names)
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = '{db}' AND table_name IN ({in_list})
            ORDER BY table_name, ordinal_position
        """)
        grouped: dict[str, list] = {}
        for tname, cname, dtype in cur.fetchall():
            grouped.setdefault(tname, []).append({"name": cname, "type": dtype})
        cur.close()
        conn.close()

        if table and not tables:
            return json.dumps({"database": db, "table": table, "columns": grouped.get(table, [])})
        missing = [n for n in names if n not in grouped]
        return json.dumps({"database": db, "tables": grouped, "missing": missing})
    except Exception as e:
        return json.dumps({"error": str(e)})


# Best-effort cleanup of stale query-cache dirs from prior (crashed) sessions.
try:
    _sweep_stale_cache()
except Exception:
    pass


if __name__ == "__main__":
    mcp.run()
