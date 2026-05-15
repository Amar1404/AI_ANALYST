"""SQL dialect adapters for multi-warehouse support.

Each dialect translates common SQL operations into the syntax required
by a specific warehouse backend (DuckDB, PostgreSQL, BigQuery, Snowflake,
Athena, ClickHouse). The router in helpers/sql_dialect.py picks the right
one at runtime.
"""

from helpers.dialects.base import SQLDialect
from helpers.dialects.duckdb_dialect import DuckDBDialect
from helpers.dialects.postgres import PostgresDialect
from helpers.dialects.bigquery import BigQueryDialect
from helpers.dialects.snowflake import SnowflakeDialect
from helpers.dialects.athena import AthenaDialect
from helpers.dialects.clickhouse import ClickHouseDialect

__all__ = [
    "SQLDialect",
    "DuckDBDialect",
    "PostgresDialect",
    "BigQueryDialect",
    "SnowflakeDialect",
    "AthenaDialect",
    "ClickHouseDialect",
]
