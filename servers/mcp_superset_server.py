"""MCP Server for Apache Superset — SQL execution via Superset REST API.

Drop-in alongside mcp_athena_server.py. Returns responses in the same format
so skills work with either backend. Superset handles auth (Google OAuth /
JWT / API key), RBAC, row-level security, and multi-database routing.

Supports three auth modes:
  1. API key (SUPERSET_API_KEY) — preferred, works with any Superset auth backend
  2. Username/password (SUPERSET_USERNAME + SUPERSET_PASSWORD) — DB or LDAP auth
  3. Google OAuth — user authenticates in browser, creates API key in Superset,
     then uses that key here

Usage:
    python servers/mcp_superset_server.py

Environment variables:
    SUPERSET_BASE_URL:      Superset instance URL (e.g., http://localhost:8088)
    SUPERSET_USERNAME:      Username for DB auth (optional if using API key)
    SUPERSET_PASSWORD:      Password for DB auth (optional if using API key)
    SUPERSET_API_KEY:       API key (sst_...) — preferred over user/pass
    SUPERSET_AUTH_PROVIDER: Auth provider: 'db' (default), 'ldap', 'oauth'
    SUPERSET_DATABASE_ID:   Default database ID in Superset for queries
    SUPERSET_SCHEMA:        Default schema (e.g., trayaprod)
"""

import json
import os
import re
import subprocess
import sys
import time

# Auto-install dependencies if missing
try:
    import mcp  # noqa: F401
    import httpx  # noqa: F401
    import pandas  # noqa: F401
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "mcp[cli]", "httpx", "pandas"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

import httpx
import pandas as pd
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

mcp_server = FastMCP("superset-query")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    return {
        "base_url": os.environ.get("SUPERSET_BASE_URL", "http://localhost:8088").rstrip("/"),
        "username": os.environ.get("SUPERSET_USERNAME", ""),
        "password": os.environ.get("SUPERSET_PASSWORD", ""),
        "api_key": os.environ.get("SUPERSET_API_KEY", ""),
        "auth_provider": os.environ.get("SUPERSET_AUTH_PROVIDER", "db"),
        "database_id": int(os.environ.get("SUPERSET_DATABASE_ID", "1")),
        "schema": os.environ.get("SUPERSET_SCHEMA", "trayaprod"),
    }


CONFIG = _load_config()


# ---------------------------------------------------------------------------
# Auth — API key or JWT (user/pass) with auto-refresh
# ---------------------------------------------------------------------------

class _AuthManager:
    def __init__(self, config: dict):
        self._cfg = config
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._csrf_token: str | None = None
        self._expires_at: float = 0

    def get_headers(self, client: httpx.Client, need_csrf: bool = False) -> dict:
        if self._cfg["api_key"]:
            h = {"Authorization": f"Bearer {self._cfg['api_key']}", "Content-Type": "application/json"}
            if need_csrf:
                h["X-CSRFToken"] = self._fetch_csrf(client, self._cfg["api_key"])
            return h

        token = self._get_jwt(client)
        h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if need_csrf:
            h["X-CSRFToken"] = self._fetch_csrf(client, token)
        return h

    def _get_jwt(self, client: httpx.Client) -> str:
        if self._access_token and time.time() < self._expires_at - 30:
            return self._access_token

        # Try refresh
        if self._refresh_token:
            try:
                resp = client.post(
                    f"{self._cfg['base_url']}/api/v1/security/refresh",
                    headers={"Authorization": f"Bearer {self._refresh_token}"},
                )
                resp.raise_for_status()
                self._access_token = resp.json()["access_token"]
                self._expires_at = time.time() + 900
                self._csrf_token = None
                return self._access_token
            except Exception:
                self._refresh_token = None

        # Full login
        resp = client.post(
            f"{self._cfg['base_url']}/api/v1/security/login",
            json={
                "username": self._cfg["username"],
                "password": self._cfg["password"],
                "provider": self._cfg["auth_provider"],
                "refresh": True,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._expires_at = time.time() + 900
        self._csrf_token = None
        return self._access_token

    def _fetch_csrf(self, client: httpx.Client, token: str) -> str:
        if self._csrf_token:
            return self._csrf_token
        resp = client.get(
            f"{self._cfg['base_url']}/api/v1/security/csrf_token/",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        self._csrf_token = resp.json()["result"]
        return self._csrf_token

    def invalidate(self):
        self._access_token = None
        self._refresh_token = None
        self._csrf_token = None
        self._expires_at = 0


_auth = _AuthManager(CONFIG)
_http = httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0), follow_redirects=True, verify=True, trust_env=True)


def _request(method: str, endpoint: str, json_data: dict | None = None, params: dict | None = None) -> dict:
    """Authenticated Superset API request with auto-retry on 401."""
    url = f"{CONFIG['base_url']}{endpoint}"
    need_csrf = method.upper() in ("POST", "PUT", "DELETE")
    headers = _auth.get_headers(_http, need_csrf=need_csrf)
    resp = _http.request(method, url, headers=headers, json=json_data, params=params)
    if resp.status_code == 401:
        _auth.invalidate()
        headers = _auth.get_headers(_http, need_csrf=need_csrf)
        resp = _http.request(method, url, headers=headers, json=json_data, params=params)
    resp.raise_for_status()
    return resp.json() if resp.status_code != 204 else {"status": "ok"}


# ---------------------------------------------------------------------------
# PII guardrails (same logic as athena server)
# ---------------------------------------------------------------------------

_PII_COLUMNS = {
    "email", "phone_number", "phone", "chat_phone_number",
    "first_name", "last_name", "name",
    "customername", "phone_no",
    "order_meta_shipping_address", "order_meta_billing_address",
}


def _check_pii_in_select(sql: str) -> list[str]:
    sql_upper = sql.upper().strip()
    if not sql_upper.startswith("SELECT"):
        return []
    from_pos = sql_upper.find(" FROM ")
    if from_pos == -1:
        return []
    select_clause = sql.lower()[:from_pos]
    if re.search(r'(?<!\w)\*(?!\))', select_clause):
        return ["SELECT * may expose PII columns"]
    found = []
    for pii_col in _PII_COLUMNS:
        if re.search(r'\b' + re.escape(pii_col) + r'\b', select_clause):
            found.append(pii_col)
    return found


def _redact_pii_dicts(rows: list[dict], columns: list[str]) -> tuple[list[dict], list[str], list[str]]:
    redacted = [c for c in columns if c.lower() in _PII_COLUMNS]
    if not redacted:
        return rows, columns, []
    redacted_lower = {c.lower() for c in redacted}
    clean_columns = [c for c in columns if c.lower() not in redacted_lower]
    clean_rows = [{k: v for k, v in row.items() if k.lower() not in redacted_lower} for row in rows]
    return clean_rows, clean_columns, redacted


# ---------------------------------------------------------------------------
# Superset response → Athena-compatible format
# ---------------------------------------------------------------------------

def _parse_response(resp: dict) -> tuple[list[dict], list[str]]:
    """Extract rows and column names from Superset execute response."""
    rows = resp.get("data", resp.get("rows", []))
    columns: list[str] = []
    if resp.get("columns"):
        columns = [c["name"] if isinstance(c, dict) else c for c in resp["columns"]]
    elif rows:
        columns = list(rows[0].keys())
    return rows, columns


def _format_result(rows: list[dict], columns: list[str], redacted: list[str], max_rows: int = 500) -> dict:
    """Build response dict matching Athena server format."""
    result: dict = {
        "columns": columns,
        "row_count": len(rows),
        "data": rows[:max_rows],
    }
    if redacted:
        result["redacted_columns"] = redacted
        result["notice"] = f"PII columns removed from results: {', '.join(redacted)}"
    if len(rows) > max_rows:
        result["truncated"] = True
        result["total_rows"] = len(rows)
    return result


def _error_from_http(e: httpx.HTTPStatusError) -> str:
    detail = ""
    try:
        detail = e.response.json().get("message", e.response.text[:500])
    except Exception:
        detail = e.response.text[:500]
    return json.dumps({"error": f"Superset API error ({e.response.status_code}): {detail}"})


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp_server.tool()
def query_superset(sql: str, database_id: int = 0, schema: str = "") -> str:
    """Execute a SELECT query via Superset and return results as JSON.

    Superset applies row-level security and RBAC automatically based on
    the authenticated user's role.

    Args:
        sql: The SQL SELECT query to execute.
             IMPORTANT:
             - Only SELECT queries are supported.
             - Always include LIMIT to avoid scanning too much data.
             - PII columns (email, phone, name, address) cannot be in SELECT.
             - PREFER aggregated queries (GROUP BY, COUNT, SUM, AVG) over raw row selects.
             - Use sample_superset_table to preview raw data first.
        database_id: Superset database connection ID. Defaults to configured value.
        schema: Schema name. Defaults to configured value.

    Returns:
        JSON string with columns, row_count, and data (list of row dicts).
    """
    pii_found = _check_pii_in_select(sql)
    if pii_found:
        return json.dumps({
            "error": "Query blocked: cannot SELECT personally identifiable columns.",
            "blocked_columns": pii_found,
            "suggestion": "Use case_id or user_id as anonymous identifiers instead."
        })

    try:
        resp = _request("POST", "/api/v1/sqllab/execute/", json_data={
            "database_id": database_id or CONFIG["database_id"],
            "sql": sql,
            "schema": schema or CONFIG["schema"],
            "limit": 500,
            "timeout": 120,
        })

        rows, columns = _parse_response(resp)
        rows, columns, redacted = _redact_pii_dicts(rows, columns)
        return json.dumps(_format_result(rows, columns, redacted), default=str)

    except httpx.HTTPStatusError as e:
        return _error_from_http(e)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp_server.tool()
def sample_superset_table(table: str, database: str = "", limit: int = 10) -> str:
    """Get a sample of the most recent rows from a table based on activity_date.

    Use this BEFORE writing analytical queries to understand actual data values,
    formats, and patterns.

    Args:
        table: Table name (e.g., engagements_vw, orders_vw).
        database: Schema name. Defaults to configured schema.
        limit: Number of rows to return (default 10, max 50).
    """
    try:
        db = database or CONFIG["schema"]
        limit = min(limit, 50)
        fqn = f"{db}.{table}"
        payload = {
            "database_id": CONFIG["database_id"],
            "schema": db,
            "limit": limit,
            "timeout": 30,
        }

        try:
            payload["sql"] = f"SELECT * FROM {fqn} WHERE activity_date = (SELECT MAX(activity_date) FROM {fqn}) LIMIT {limit}"
            resp = _request("POST", "/api/v1/sqllab/execute/", json_data=payload)
        except Exception:
            payload["sql"] = f"SELECT * FROM {fqn} LIMIT {limit}"
            resp = _request("POST", "/api/v1/sqllab/execute/", json_data=payload)

        rows, columns = _parse_response(resp)
        rows, columns, redacted = _redact_pii_dicts(rows, columns)
        df = pd.DataFrame(rows)

        result = {
            "table": fqn,
            "row_count": len(df),
            "columns": columns,
            "dtypes": {col: str(dt) for col, dt in df.dtypes.items()} if not df.empty else {},
            "sample": rows,
        }
        if redacted:
            result["redacted_columns"] = redacted
        return json.dumps(result, default=str)

    except httpx.HTTPStatusError as e:
        return _error_from_http(e)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp_server.tool()
def list_superset_tables(database: str = "") -> str:
    """List all datasets/tables registered in Superset.

    Args:
        database: Filter by database or schema name (optional).
    """
    try:
        resp = _request("GET", "/api/v1/dataset/", params={
            "q": "(page_size:500,order_column:table_name,order_direction:asc)"
        })
        datasets = resp.get("result", [])
        tables = []
        for ds in datasets:
            ds_name = ds.get("table_name", "")
            ds_schema = ds.get("schema", "")
            ds_db = ds.get("database", {}).get("database_name", "")
            if database and database.lower() not in (ds_db.lower(), ds_schema.lower()):
                continue
            tables.append(f"{ds_schema}.{ds_name}" if ds_schema else ds_name)

        return json.dumps({"database": database or "all", "tables": sorted(tables), "count": len(tables)})
    except httpx.HTTPStatusError as e:
        return _error_from_http(e)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp_server.tool()
def describe_superset_table(table: str, database: str = "") -> str:
    """Get column names and types for a table via Superset.

    Args:
        table: Table name (e.g., engagements_vw).
        database: Schema name. Defaults to configured schema.
    """
    try:
        db = database or CONFIG["schema"]
        sql = f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = '{db}' AND table_name = '{table}'
            ORDER BY ordinal_position
        """
        resp = _request("POST", "/api/v1/sqllab/execute/", json_data={
            "database_id": CONFIG["database_id"],
            "sql": sql,
            "schema": "information_schema",
            "timeout": 30,
        })
        rows, _ = _parse_response(resp)
        columns = [{"name": r.get("column_name", ""), "type": r.get("data_type", "")} for r in rows]
        return json.dumps({"database": db, "table": table, "columns": columns})
    except httpx.HTTPStatusError as e:
        return _error_from_http(e)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp_server.tool()
def list_superset_databases() -> str:
    """List all database connections in Superset with their IDs.

    Use this to find the right database_id for queries.
    """
    try:
        resp = _request("GET", "/api/v1/database/", params={"q": "(page_size:100)"})
        databases = [
            {"id": db.get("id"), "name": db.get("database_name"), "backend": db.get("backend")}
            for db in resp.get("result", [])
        ]
        return json.dumps({"databases": databases, "count": len(databases)})
    except httpx.HTTPStatusError as e:
        return _error_from_http(e)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp_server.tool()
def test_superset_connection() -> str:
    """Test the Superset connection and authentication.

    Returns the current user info and available databases if successful.
    Use this to verify the setup is working.
    """
    try:
        # Test auth by fetching current user info
        user_resp = _request("GET", "/api/v1/me/")

        # List databases
        db_resp = _request("GET", "/api/v1/database/", params={"q": "(page_size:10)"})
        databases = [
            {"id": db.get("id"), "name": db.get("database_name")}
            for db in db_resp.get("result", [])
        ]

        return json.dumps({
            "status": "connected",
            "base_url": CONFIG["base_url"],
            "auth_method": "api_key" if CONFIG["api_key"] else "username_password",
            "user": user_resp.get("result", {}),
            "databases": databases,
        }, default=str)
    except httpx.HTTPStatusError as e:
        return _error_from_http(e)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "base_url": CONFIG["base_url"]})


# ---------------------------------------------------------------------------
# Interactive setup via MCP Elicitation
# ---------------------------------------------------------------------------

class SupersetURLConfig(BaseModel):
    """Collect Superset URL and auth method."""
    base_url: str = Field(description="Superset URL (e.g., http://localhost:8088)")
    auth_method: str = Field(description="How do you authenticate?", json_schema_extra={"enum": ["username_password", "google_sso", "api_key"]})


class SupersetCredentials(BaseModel):
    """Collect username/password for DB auth."""
    username: str = Field(description="Superset username")
    password: str = Field(description="Superset password")


class SupersetAPIKeyInput(BaseModel):
    """Collect API key."""
    api_key: str = Field(description="Paste your Superset API key (starts with sst_)")


class SupersetDatabaseChoice(BaseModel):
    """Collect default database and schema."""
    database_id: int = Field(description="Database ID to use as default")
    schema_name: str = Field(description="Default schema (e.g., trayaprod)")


@mcp_server.tool()
async def connect_superset(ctx: Context) -> str:
    """Interactive Superset setup — authenticate, discover databases, and configure.

    Walks you through connecting to Superset step by step using interactive
    prompts. Supports username/password, Google SSO, and API key auth.
    """
    global CONFIG, _auth, _http

    # Step 1: Get URL and auth method
    await ctx.info("Starting Superset setup...")
    result = await ctx.elicit(
        "Let's connect to Superset. Enter your Superset URL and how you log in.",
        SupersetURLConfig,
    )
    if result.action != "accept" or not result.data:
        return json.dumps({"status": "cancelled", "message": "Setup cancelled."})

    base_url = result.data.base_url.rstrip("/")
    auth_method = result.data.auth_method

    # Verify URL is reachable
    try:
        test_resp = _http.get(f"{base_url}/health", timeout=10)
        if test_resp.status_code != 200:
            # Try /api/v1/health as fallback
            test_resp = _http.get(f"{base_url}/api/v1/health", timeout=10)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Cannot reach {base_url}: {e}"})

    await ctx.info(f"Superset at {base_url} is reachable.")

    # Step 2: Authenticate based on method
    api_key = ""
    username = ""

    if auth_method == "api_key":
        # User already has a key
        key_result = await ctx.elicit(
            "Paste your Superset API key.",
            SupersetAPIKeyInput,
        )
        if key_result.action != "accept" or not key_result.data:
            return json.dumps({"status": "cancelled"})
        api_key = key_result.data.api_key

    elif auth_method == "google_sso":
        # Open browser for Google login, then guide to API key creation
        import uuid
        elicit_id = f"superset-oauth-{uuid.uuid4().hex[:8]}"

        await ctx.elicit_url(
            "Sign in to Superset with Google. After logging in, I'll guide you to create an API key.",
            f"{base_url}/login/",
            elicit_id,
        )

        await ctx.info("Now let's create an API key for persistent access.")

        # Open the API key creation page
        elicit_id2 = f"superset-apikey-{uuid.uuid4().hex[:8]}"
        await ctx.elicit_url(
            "In Superset, go to Settings → API Keys → + Create. Name it 'ai-analyst-plugin', copy the key, then come back.",
            f"{base_url}/user/profile/",
            elicit_id2,
        )

        # Collect the key
        key_result = await ctx.elicit(
            "Paste the API key you just created (starts with sst_).",
            SupersetAPIKeyInput,
        )
        if key_result.action != "accept" or not key_result.data:
            return json.dumps({"status": "cancelled"})
        api_key = key_result.data.api_key

    elif auth_method == "username_password":
        # Collect credentials and auto-create API key
        cred_result = await ctx.elicit(
            "Enter your Superset username and password.",
            SupersetCredentials,
        )
        if cred_result.action != "accept" or not cred_result.data:
            return json.dumps({"status": "cancelled"})

        username = cred_result.data.username
        password = cred_result.data.password

        # Login and create API key automatically
        await ctx.info("Logging in and creating API key...")
        try:
            login_resp = _http.post(
                f"{base_url}/api/v1/security/login",
                json={"username": username, "password": password, "provider": "db", "refresh": True},
            )
            login_resp.raise_for_status()
            access_token = login_resp.json()["access_token"]

            # Get CSRF token
            csrf_resp = _http.get(
                f"{base_url}/api/v1/security/csrf_token/",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            csrf_resp.raise_for_status()
            csrf_token = csrf_resp.json()["result"]

            # Create API key
            key_resp = _http.post(
                f"{base_url}/api/v1/security/api_keys/",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-CSRFToken": csrf_token,
                    "Content-Type": "application/json",
                    "Referer": base_url,
                },
                json={"name": "ai-analyst-plugin"},
            )
            if key_resp.status_code < 400:
                key_data = key_resp.json()
                api_key = key_data.get("result", {}).get("key", "")
                if api_key:
                    await ctx.info(f"API key created automatically: {api_key[:10]}...")

            # Fall back to username/password if API key creation not supported
            if not api_key:
                await ctx.info("API key creation not available on this Superset version. Using username/password auth.")

        except httpx.HTTPStatusError as e:
            return json.dumps({"status": "error", "message": f"Login failed: {e.response.text[:200]}"})

    # Step 3: Update config and test connection
    CONFIG["base_url"] = base_url
    if api_key:
        CONFIG["api_key"] = api_key
        CONFIG["username"] = ""
        CONFIG["password"] = ""
    else:
        CONFIG["username"] = username
        CONFIG["password"] = password
        CONFIG["api_key"] = ""

    _auth = _AuthManager(CONFIG)

    # Verify auth works
    try:
        headers = _auth.get_headers(_http)
        me_resp = _http.get(f"{base_url}/api/v1/me/", headers=headers)
        me_resp.raise_for_status()
        user_info = me_resp.json().get("result", {})
        await ctx.info(f"Authenticated as: {user_info.get('username', 'unknown')}")
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Authentication failed: {e}"})

    # Step 4: Discover databases
    try:
        db_resp = _request("GET", "/api/v1/database/", params={"q": "(page_size:100)"})
        databases = db_resp.get("result", [])
        db_list = "\n".join(
            f"  {db.get('id')}: {db.get('database_name')} ({db.get('backend', 'unknown')})"
            for db in databases
        )
        await ctx.info(f"Available databases:\n{db_list}")
    except Exception:
        databases = []

    # Step 5: Choose default database and schema
    db_result = await ctx.elicit(
        f"Choose your default database ID and schema.\n\nAvailable databases:\n{db_list if databases else '(none found)'}",
        SupersetDatabaseChoice,
    )
    if db_result.action == "accept" and db_result.data:
        CONFIG["database_id"] = db_result.data.database_id
        CONFIG["schema"] = db_result.data.schema_name

    # Step 6: Test with a real query
    try:
        test_query = "SELECT 1 as connected"
        _request("POST", "/api/v1/sqllab/execute/", json_data={
            "database_id": CONFIG["database_id"],
            "sql": test_query,
            "schema": CONFIG["schema"],
            "timeout": 10,
        })
        await ctx.info("Test query successful — connection is working!")
    except Exception as e:
        await ctx.info(f"Test query failed: {e}. You may need to check the database ID or schema.")

    # Return config summary for the user to save in plugin settings
    config_summary = {
        "status": "connected",
        "message": "Superset is configured! Update your plugin settings with these values:",
        "config": {
            "superset_url": CONFIG["base_url"],
            "superset_api_key": f"{api_key[:10]}..." if api_key else "(using username/password)",
            "superset_database_id": str(CONFIG["database_id"]),
            "superset_schema": CONFIG["schema"],
        },
        "user": user_info.get("username", ""),
    }
    return json.dumps(config_summary, default=str)


if __name__ == "__main__":
    mcp_server.run()
