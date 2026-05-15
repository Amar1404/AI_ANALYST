"""
Connection Manager — unified interface for multi-warehouse connections.

Manages connection lifecycle for different data warehouse backends:
MotherDuck/DuckDB (native), PostgreSQL, BigQuery, Snowflake, Athena,
and ClickHouse.

Usage:
    from helpers.connection_manager import ConnectionManager

    mgr = ConnectionManager()
    conn = mgr.connect()          # Uses active dataset config
    mgr.test_connection()          # Health check
    tables = mgr.list_tables()     # Enumerate tables
    mgr.close()                    # Cleanup

    # Or use as context manager:
    with ConnectionManager() as mgr:
        tables = mgr.list_tables()
"""

import os
import re
from pathlib import Path

import pandas as pd

# Optional imports — each warehouse backend is optional.
try:
    import duckdb
    _DUCKDB_AVAILABLE = True
except ImportError:
    _DUCKDB_AVAILABLE = False

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# Supported connection types and their required packages.
SUPPORTED_TYPES = {
    "motherduck": {"package": "duckdb", "installed": _DUCKDB_AVAILABLE},
    "duckdb": {"package": "duckdb", "installed": _DUCKDB_AVAILABLE},
    "csv": {"package": None, "installed": True},
    "postgres": {"package": "psycopg2", "installed": False},
    "bigquery": {"package": "google-cloud-bigquery", "installed": False},
    "snowflake": {"package": "snowflake-connector-python", "installed": False},
    "athena": {"package": "pyathena", "installed": False},
    "clickhouse": {"package": "clickhouse-connect", "installed": False},
}


# ---------------------------------------------------------------------------
# DDL column parser (shared by Athena and ClickHouse)
# ---------------------------------------------------------------------------

def _parse_columns_from_ddl(ddl_text):
    """Parse column names, types, and descriptions from SHOW CREATE TABLE DDL.

    Handles both Athena (Presto) and ClickHouse DDL formats where columns
    may have COMMENT clauses.

    Args:
        ddl_text: Raw DDL string from SHOW CREATE TABLE.

    Returns:
        list[dict]: Each dict has keys: name, type, nullable, description.
    """
    columns = []
    # Match column definitions: name type [optional_stuff] [COMMENT 'desc']
    # Stops at COMMENT, comma, or closing paren
    col_pattern = re.compile(
        r"^\s+`?(\w+)`?\s+"           # column name (optionally backtick-quoted)
        r"([A-Za-z0-9_()., ]+?)"      # data type
        r"(?:\s+COMMENT\s+'((?:[^']*(?:'')*)*)')?"  # optional COMMENT 'desc'
        r"\s*[,)]",                    # trailing comma or closing paren
        re.MULTILINE,
    )
    for match in col_pattern.finditer(ddl_text):
        col_name = match.group(1)
        col_type = match.group(2).strip()
        comment = match.group(3) or ""
        # Unescape doubled single quotes
        comment = comment.replace("''", "'")
        columns.append({
            "name": col_name,
            "type": col_type,
            "nullable": True,
            "description": comment,
        })
    return columns


class ConnectionManager:
    """Unified connection manager for multi-warehouse data access.

    Reads connection config from the active dataset's manifest, connects
    to the appropriate backend, and provides a common interface for
    table listing, health checks, and query execution.

    Args:
        config: Optional connection config dict. If None, reads from
            the active dataset manifest via data_helpers.
        dataset_id: Optional dataset ID to connect to. If None, uses
            the active dataset.
    """

    def __init__(self, config=None, dataset_id=None):
        self._config = config
        self._dataset_id = dataset_id
        self._connection = None
        self._conn_type = None
        self._schema_prefix = ""
        self._csv_dir = None

        if config is None:
            self._config = self._load_config(dataset_id)

        self._conn_type = self._config.get("type", "csv")
        self._schema_prefix = self._config.get("schema_prefix", "")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config(dataset_id=None):
        """Load connection config from the knowledge system.

        Reads .knowledge/active.yaml (or uses dataset_id) and loads the
        dataset's manifest.yaml for connection details.

        Returns:
            dict with connection configuration.
        """
        try:
            from helpers.data_helpers import detect_active_source
            source = detect_active_source()
            return {
                "type": source.get("type", "csv"),
                "dataset_id": source.get("source", "unknown"),
                "display_name": source.get("display_name", "Unknown"),
                "schema_prefix": source.get("schema_prefix", ""),
                "duckdb_path": source.get("duckdb_path"),
                "csv_path": source.get("csv_path"),
                "connection": source.get("connection", {}),
            }
        except Exception as exc:
            raise RuntimeError(
                "Failed to load dataset config — no active dataset found. "
                "Use /connect-data to configure a dataset, or pass a config dict "
                f"to ConnectionManager directly. Original error: {exc}"
            )

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self):
        """Establish connection to the configured data source.

        Returns:
            self (for chaining).

        Raises:
            ConnectionError: If the connection cannot be established.
        """
        conn_type = self._conn_type

        if conn_type in ("motherduck", "duckdb"):
            self._connect_duckdb()
        elif conn_type == "postgres":
            self._connect_postgres()
        elif conn_type == "bigquery":
            self._connect_bigquery()
        elif conn_type == "snowflake":
            self._connect_snowflake()
        elif conn_type == "athena":
            self._connect_athena()
        elif conn_type == "clickhouse":
            self._connect_clickhouse()
        elif conn_type == "csv":
            self._connect_csv()
        else:
            raise ConnectionError(
                f"Unsupported connection type: {conn_type}. "
                f"Supported types: {list(SUPPORTED_TYPES.keys())}"
            )

        return self

    def close(self):
        """Close the active connection and release resources."""
        if self._connection is not None:
            try:
                if hasattr(self._connection, "close"):
                    self._connection.close()
            except Exception:
                pass
            self._connection = None

    def test_connection(self):
        """Test connectivity with a lightweight probe.

        Returns:
            dict: {ok: bool, type: str, message: str}
        """
        try:
            if self._conn_type in ("motherduck", "duckdb"):
                if self._connection is None:
                    self.connect()
                self._connection.sql("SELECT 1").fetchone()
                return {"ok": True, "type": self._conn_type, "message": "Connected"}

            elif self._conn_type == "postgres":
                if self._connection is None:
                    self.connect()
                cur = self._connection.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
                return {"ok": True, "type": "postgres", "message": "Connected"}

            elif self._conn_type == "athena":
                if self._connection is None:
                    self.connect()
                cur = self._connection.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
                return {"ok": True, "type": "athena", "message": "Connected"}

            elif self._conn_type == "clickhouse":
                if self._connection is None:
                    self.connect()
                self._connection.query("SELECT 1")
                return {"ok": True, "type": "clickhouse", "message": "Connected"}

            elif self._conn_type == "csv":
                csv_dir = self._csv_dir or self._config.get("csv_path", "")
                if Path(csv_dir).is_dir():
                    count = len(list(Path(csv_dir).glob("*.csv")))
                    return {"ok": count > 0, "type": "csv", "message": f"{count} CSV files"}
                return {"ok": False, "type": "csv", "message": f"Directory not found: {csv_dir}"}

            else:
                return {"ok": False, "type": self._conn_type, "message": "Not yet implemented"}

        except Exception as exc:
            return {"ok": False, "type": self._conn_type, "message": str(exc)}

    # ------------------------------------------------------------------
    # Table operations
    # ------------------------------------------------------------------

    def list_tables(self):
        """List all available tables in the connected source.

        Returns:
            list[str]: Sorted table names.
        """
        if self._conn_type in ("motherduck", "duckdb") and self._connection:
            try:
                df = self._connection.sql("SHOW TABLES").df()
                return sorted(df["name"].tolist()) if "name" in df.columns else []
            except Exception:
                return []

        elif self._conn_type == "postgres" and self._connection:
            try:
                cur = self._connection.cursor()
                schema = self._schema_prefix or "public"
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = %s ORDER BY table_name",
                    (schema,),
                )
                tables = [row[0] for row in cur.fetchall()]
                cur.close()
                return tables
            except Exception:
                return []

        elif self._conn_type == "athena" and self._connection:
            try:
                database = self._schema_prefix or self._config.get("connection", {}).get("database", "")
                cur = self._connection.cursor()
                cur.execute(f"SHOW TABLES IN {database}")
                tables = [row[0] for row in cur.fetchall()]
                cur.close()
                return sorted(tables)
            except Exception:
                return []

        elif self._conn_type == "clickhouse" and self._connection:
            try:
                database = self._schema_prefix or self._config.get("connection", {}).get("database", "")
                result = self._connection.query(f"SHOW TABLES FROM {database}")
                return sorted(row[0] for row in result.result_rows)
            except Exception:
                return []

        elif self._conn_type == "csv":
            csv_dir = self._csv_dir or self._config.get("csv_path", "")
            if Path(csv_dir).is_dir():
                return sorted(p.stem for p in Path(csv_dir).glob("*.csv"))
            return []

        return []

    def get_table_schema(self, table_name):
        """Get column names and types for a specific table.

        Args:
            table_name: Name of the table to inspect.

        Returns:
            list[dict]: Each dict has keys: name, type, nullable.
                For Athena/ClickHouse, also includes description from
                COMMENT clauses.
        """
        if self._conn_type in ("motherduck", "duckdb") and self._connection:
            try:
                df = self._connection.sql(f"DESCRIBE {table_name}").df()
                columns = []
                for _, row in df.iterrows():
                    columns.append({
                        "name": row.get("column_name", row.get("Field", "")),
                        "type": row.get("column_type", row.get("Type", "")),
                        "nullable": row.get("null", "YES") == "YES",
                    })
                return columns
            except Exception:
                return []

        elif self._conn_type == "athena" and self._connection:
            try:
                cur = self._connection.cursor()
                cur.execute(f"SHOW CREATE TABLE {table_name}")
                ddl = "\n".join(row[0] for row in cur.fetchall())
                cur.close()
                # DDL parsing works for base tables; views return
                # "CREATE VIEW ... AS /* Presto View */" with no columns.
                columns = _parse_columns_from_ddl(ddl)
                if columns:
                    return columns
                # Fallback: information_schema for views
                database = self._schema_prefix or self._config.get("connection", {}).get("database", "")
                cur = self._connection.cursor()
                cur.execute(
                    "SELECT column_name, data_type "
                    "FROM information_schema.columns "
                    f"WHERE table_schema = '{database}' "
                    f"AND table_name = '{table_name}' "
                    "ORDER BY ordinal_position"
                )
                columns = [
                    {"name": row[0], "type": row[1], "nullable": True, "description": ""}
                    for row in cur.fetchall()
                ]
                cur.close()
                return columns
            except Exception:
                return []

        elif self._conn_type == "clickhouse" and self._connection:
            try:
                result = self._connection.query(f"SHOW CREATE TABLE {table_name}")
                ddl = result.result_rows[0][0] if result.result_rows else ""
                return _parse_columns_from_ddl(ddl)
            except Exception:
                return []

        elif self._conn_type == "csv":
            csv_dir = self._csv_dir or self._config.get("csv_path", "")
            csv_path = Path(csv_dir) / f"{table_name}.csv"
            if csv_path.exists():
                df = pd.read_csv(csv_path, nrows=5, low_memory=False)
                return [
                    {"name": col, "type": str(df[col].dtype), "nullable": True}
                    for col in df.columns
                ]
            return []

        return []

    def query(self, sql):
        """Execute a SQL query and return results as a DataFrame.

        Args:
            sql: SQL query string.

        Returns:
            pandas.DataFrame with query results.

        Raises:
            RuntimeError: If no SQL-capable connection is available.
        """
        if self._conn_type in ("motherduck", "duckdb") and self._connection:
            return self._connection.sql(sql).df()

        elif self._conn_type == "postgres" and self._connection:
            return pd.read_sql(sql, self._connection)

        elif self._conn_type == "athena" and self._connection:
            cur = self._connection.cursor()
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            cur.close()
            return pd.DataFrame(rows, columns=columns)

        elif self._conn_type == "clickhouse" and self._connection:
            result = self._connection.query(sql)
            return pd.DataFrame(
                result.result_rows,
                columns=[col_name for col_name in result.column_names],
            )

        raise RuntimeError(
            f"SQL queries not supported for connection type: {self._conn_type}. "
            "Use read_table() for CSV data."
        )

    def read_table(self, table_name):
        """Read an entire table as a DataFrame.

        Works for all connection types including CSV.

        Args:
            table_name: Name of the table to read.

        Returns:
            pandas.DataFrame
        """
        if self._conn_type in ("motherduck", "duckdb") and self._connection:
            return self._connection.sql(f"SELECT * FROM {table_name}").df()

        elif self._conn_type == "csv":
            csv_dir = self._csv_dir or self._config.get("csv_path", "")
            csv_path = Path(csv_dir) / f"{table_name}.csv"
            if csv_path.exists():
                return pd.read_csv(csv_path, low_memory=False)
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        elif self._conn_type == "postgres" and self._connection:
            schema = self._schema_prefix or "public"
            return pd.read_sql(f"SELECT * FROM {schema}.{table_name}", self._connection)

        elif self._conn_type == "athena" and self._connection:
            schema = self._schema_prefix
            qualified = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
            return self.query(f"SELECT * FROM {qualified}")

        elif self._conn_type == "clickhouse" and self._connection:
            schema = self._schema_prefix
            qualified = f"{schema}.{table_name}" if schema else table_name
            return self.query(f"SELECT * FROM {qualified}")

        raise RuntimeError(f"Cannot read table for connection type: {self._conn_type}")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connection_type(self):
        """Return the active connection type string."""
        return self._conn_type

    @property
    def schema_prefix(self):
        """Return the SQL schema prefix for the active connection."""
        return self._schema_prefix

    @property
    def is_connected(self):
        """Return True if a connection is currently active."""
        if self._conn_type == "csv":
            csv_dir = self._csv_dir or self._config.get("csv_path", "")
            return Path(csv_dir).is_dir()
        return self._connection is not None

    @property
    def dataset_id(self):
        """Return the active dataset ID."""
        return self._config.get("dataset_id", self._dataset_id or "unknown")

    # ------------------------------------------------------------------
    # Backend-specific connectors (private)
    # ------------------------------------------------------------------

    def _connect_duckdb(self):
        """Connect to local DuckDB or MotherDuck fallback."""
        if not _DUCKDB_AVAILABLE:
            raise ConnectionError("duckdb package not installed. pip install duckdb")

        db_path = self._config.get("duckdb_path")
        if db_path and Path(db_path).exists():
            self._connection = duckdb.connect(str(db_path), read_only=True)
            self._conn_type = "duckdb"
        else:
            # Fallback to CSV
            self._conn_type = "csv"
            self._connect_csv()

    def _connect_csv(self):
        """Set up CSV-based access."""
        csv_path = self._config.get("csv_path")
        if not csv_path:
            raise ConnectionError(
                "No csv_path configured for CSV connection. "
                "Set csv_path in the dataset manifest or pass it in the config dict."
            )
        self._csv_dir = csv_path
        self._conn_type = "csv"

    def _connect_postgres(self):
        """Connect to PostgreSQL. Requires psycopg2."""
        try:
            import psycopg2
        except ImportError:
            raise ConnectionError(
                "psycopg2 not installed. Install with: pip install psycopg2-binary"
            )

        conn_config = self._config.get("connection", {})
        self._connection = psycopg2.connect(
            host=conn_config.get("host", "localhost"),
            port=conn_config.get("port", 5432),
            database=conn_config.get("database", ""),
            user=conn_config.get("user", ""),
            password=conn_config.get("password", ""),
        )
        self._schema_prefix = conn_config.get("schema", "public")

    def _connect_bigquery(self):
        """Connect to BigQuery. Requires google-cloud-bigquery."""
        try:
            from google.cloud import bigquery
        except ImportError:
            raise ConnectionError(
                "google-cloud-bigquery not installed. "
                "Install with: pip install google-cloud-bigquery"
            )

        conn_config = self._config.get("connection", {})
        project = conn_config.get("project")
        self._connection = bigquery.Client(project=project)
        self._schema_prefix = conn_config.get("dataset", "")
        self._conn_type = "bigquery"

    def _connect_snowflake(self):
        """Connect to Snowflake. Requires snowflake-connector-python."""
        try:
            import snowflake.connector
        except ImportError:
            raise ConnectionError(
                "snowflake-connector-python not installed. "
                "Install with: pip install snowflake-connector-python"
            )

        conn_config = self._config.get("connection", {})
        self._connection = snowflake.connector.connect(
            account=conn_config.get("account", ""),
            user=conn_config.get("user", ""),
            password=conn_config.get("password", ""),
            warehouse=conn_config.get("warehouse", ""),
            database=conn_config.get("database", ""),
            schema=conn_config.get("schema", "public"),
        )
        self._schema_prefix = conn_config.get("schema", "public")
        self._conn_type = "snowflake"

    def _connect_athena(self):
        """Connect to AWS Athena via PyAthena. Requires pyathena."""
        try:
            from pyathena import connect as athena_connect
        except ImportError:
            raise ConnectionError(
                "pyathena not installed. Install with: pip install pyathena"
            )

        conn_config = self._config.get("connection", {})
        s3_staging_dir = conn_config.get("s3_staging_dir")
        if not s3_staging_dir:
            raise ConnectionError(
                "s3_staging_dir is required for Athena connections. "
                "Set it in the dataset manifest under connection.s3_staging_dir"
            )

        connect_kwargs = {
            "s3_staging_dir": s3_staging_dir,
            "region_name": conn_config.get("region_name", "us-east-1"),
            "work_group": conn_config.get("work_group", "primary"),
            "schema_name": conn_config.get("database", ""),
        }

        auth_type = conn_config.get("auth_type", "default")
        if auth_type == "profile":
            profile_name = conn_config.get("profile_name", "")
            if profile_name:
                import boto3
                session = boto3.Session(profile_name=profile_name)
                connect_kwargs["boto3_session"] = session
        elif auth_type == "credentials":
            access_key_env = conn_config.get("access_key_env", "AWS_ACCESS_KEY_ID")
            secret_key_env = conn_config.get("secret_key_env", "AWS_SECRET_ACCESS_KEY")
            connect_kwargs["aws_access_key_id"] = os.environ.get(access_key_env, "")
            connect_kwargs["aws_secret_access_key"] = os.environ.get(secret_key_env, "")
        # auth_type == "default": no extra kwargs, boto3 chain handles it

        self._connection = athena_connect(**connect_kwargs)
        self._schema_prefix = conn_config.get("database", "")
        self._conn_type = "athena"

    def _connect_clickhouse(self):
        """Connect to ClickHouse via clickhouse-connect. Requires clickhouse-connect."""
        try:
            import clickhouse_connect
        except ImportError:
            raise ConnectionError(
                "clickhouse-connect not installed. "
                "Install with: pip install clickhouse-connect"
            )

        conn_config = self._config.get("connection", {})
        password_env = conn_config.get("password_env", "CLICKHOUSE_PASSWORD")
        password = os.environ.get(password_env, "")

        self._connection = clickhouse_connect.get_client(
            host=conn_config.get("host", "localhost"),
            port=int(conn_config.get("port", 8123)),
            database=conn_config.get("database", "default"),
            username=conn_config.get("username", "default"),
            password=password,
            secure=conn_config.get("secure", False),
        )
        self._schema_prefix = conn_config.get("database", "default")
        self._conn_type = "clickhouse"
