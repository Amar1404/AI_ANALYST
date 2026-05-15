"""ClickHouse SQL dialect adapter.

ClickHouse uses unquoted identifiers, camelCase functions like dateDiff
and nullIf, arrayStringConcat for string aggregation, now() for
current timestamp, and Memory engine for temporary tables.
"""

from __future__ import annotations

from helpers.dialects.base import SQLDialect


class ClickHouseDialect(SQLDialect):
    """SQL dialect for ClickHouse."""

    name: str = "clickhouse"

    # ------------------------------------------------------------------
    # Table qualification
    # ------------------------------------------------------------------

    def qualify_table(self, table: str, schema: str | None = None) -> str:
        """ClickHouse ``database.table`` — no quoting needed.

        >>> ClickHouseDialect().qualify_table('orders', 'analytics')
        'analytics.orders'
        >>> ClickHouseDialect().qualify_table('orders')
        'orders'
        """
        if schema:
            return f"{schema}.{table}"
        return table

    # limit_clause — inherited (LIMIT N)

    # ------------------------------------------------------------------
    # Date / time functions
    # ------------------------------------------------------------------

    def date_trunc(self, field: str, unit: str) -> str:
        """ClickHouse date_trunc — same as Postgres since 21.8+.

        >>> ClickHouseDialect().date_trunc('order_date', 'month')
        "date_trunc('month', order_date)"
        """
        return f"date_trunc('{unit.lower()}', {field})"

    def date_diff(self, unit: str, start: str, end: str) -> str:
        """ClickHouse dateDiff — camelCase, unit first.

        >>> ClickHouseDialect().date_diff('day', 'start_date', 'end_date')
        "dateDiff('day', start_date, end_date)"
        """
        return f"dateDiff('{unit.lower()}', {start}, {end})"

    # ------------------------------------------------------------------
    # Safe math
    # ------------------------------------------------------------------

    def safe_divide(self, numerator: str, denominator: str) -> str:
        """ClickHouse nullIf-based safe division.

        >>> ClickHouseDialect().safe_divide('revenue', 'orders')
        'revenue / nullIf(orders, 0)'
        """
        return f"{numerator} / nullIf({denominator}, 0)"

    # ------------------------------------------------------------------
    # String aggregation
    # ------------------------------------------------------------------

    def string_agg(self, column: str, delimiter: str = ",") -> str:
        """ClickHouse arrayStringConcat + groupArray.

        >>> ClickHouseDialect().string_agg('category')
        "arrayStringConcat(groupArray(category), ',')"
        """
        return f"arrayStringConcat(groupArray({column}), '{delimiter}')"

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------

    def current_timestamp(self) -> str:
        """ClickHouse now() function.

        >>> ClickHouseDialect().current_timestamp()
        'now()'
        """
        return "now()"

    # ------------------------------------------------------------------
    # Temp tables
    # ------------------------------------------------------------------

    def create_temp_table(self, name: str, query: str) -> str:
        """ClickHouse Memory engine table (session-scoped equivalent).

        >>> ClickHouseDialect().create_temp_table('tmp_agg', 'SELECT 1')
        'CREATE TABLE tmp_agg ENGINE = Memory AS (SELECT 1)'
        """
        return f"CREATE TABLE {name} ENGINE = Memory AS ({query})"

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def sample_rows(self, table: str, n: int) -> str:
        """ClickHouse random sampling via ORDER BY rand().

        >>> ClickHouseDialect().sample_rows('orders', 100)
        'SELECT * FROM orders ORDER BY rand() LIMIT 100'
        """
        return f"SELECT * FROM {table} ORDER BY rand() {self.limit_clause(n)}"

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def describe_table(self, table: str) -> str:
        """ClickHouse SHOW CREATE TABLE — returns DDL with COMMENT clauses.

        >>> ClickHouseDialect().describe_table('orders')
        'SHOW CREATE TABLE orders'
        """
        return f"SHOW CREATE TABLE {table}"
