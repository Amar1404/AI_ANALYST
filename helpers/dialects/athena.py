"""Athena (Presto/Trino) SQL dialect adapter.

Athena uses Presto/Trino syntax: double-quoted identifiers, date_diff
with unit-first argument order, TRY() for safe division, and
array_join(array_agg(...)) for string aggregation.
"""

from __future__ import annotations

from helpers.dialects.base import SQLDialect


class AthenaDialect(SQLDialect):
    """SQL dialect for AWS Athena (Presto/Trino engine)."""

    name: str = "athena"

    # ------------------------------------------------------------------
    # Table qualification
    # ------------------------------------------------------------------

    def qualify_table(self, table: str, schema: str | None = None) -> str:
        """Athena double-quoted ``"database"."table"``.

        *schema* is the Glue catalog database name.

        >>> AthenaDialect().qualify_table('orders', 'analytics')
        '"analytics"."orders"'
        >>> AthenaDialect().qualify_table('orders')
        '"orders"'
        """
        if schema:
            return f'"{schema}"."{table}"'
        return f'"{table}"'

    # limit_clause — inherited (LIMIT N)

    # ------------------------------------------------------------------
    # Date / time functions
    # ------------------------------------------------------------------

    def date_trunc(self, field: str, unit: str) -> str:
        """Presto date_trunc — lowercase unit, field second.

        >>> AthenaDialect().date_trunc('order_date', 'month')
        "date_trunc('month', order_date)"
        """
        return f"date_trunc('{unit.lower()}', {field})"

    def date_diff(self, unit: str, start: str, end: str) -> str:
        """Presto date_diff — unit first, then start, then end.

        >>> AthenaDialect().date_diff('day', 'start_date', 'end_date')
        "date_diff('day', start_date, end_date)"
        """
        return f"date_diff('{unit.lower()}', {start}, {end})"

    # ------------------------------------------------------------------
    # Safe math
    # ------------------------------------------------------------------

    def safe_divide(self, numerator: str, denominator: str) -> str:
        """Presto TRY() wrapper to catch division-by-zero.

        >>> AthenaDialect().safe_divide('revenue', 'orders')
        'TRY(revenue / orders)'
        """
        return f"TRY({numerator} / {denominator})"

    # ------------------------------------------------------------------
    # String aggregation
    # ------------------------------------------------------------------

    def string_agg(self, column: str, delimiter: str = ",") -> str:
        """Presto array_join + array_agg (no native STRING_AGG).

        >>> AthenaDialect().string_agg('category')
        "array_join(array_agg(category), ',')"
        """
        return f"array_join(array_agg({column}), '{delimiter}')"

    # current_timestamp — inherited (CURRENT_TIMESTAMP)

    # ------------------------------------------------------------------
    # Temp tables
    # ------------------------------------------------------------------

    def create_temp_table(self, name: str, query: str) -> str:
        """Athena CTAS — no TEMP keyword support.

        >>> AthenaDialect().create_temp_table('tmp_agg', 'SELECT 1')
        'CREATE TABLE tmp_agg AS (SELECT 1)'
        """
        return f"CREATE TABLE {name} AS ({query})"

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def sample_rows(self, table: str, n: int) -> str:
        """Athena TABLESAMPLE BERNOULLI with a LIMIT cap.

        >>> AthenaDialect().sample_rows('orders', 100)
        'SELECT * FROM orders TABLESAMPLE BERNOULLI (10) LIMIT 100'
        """
        pct = max(1, min(100, round(n / 100)))
        return (
            f"SELECT * FROM {table} TABLESAMPLE BERNOULLI "
            f"({pct}) {self.limit_clause(n)}"
        )

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def describe_table(self, table: str) -> str:
        """Athena SHOW CREATE TABLE — returns DDL with Glue COMMENT clauses.

        >>> AthenaDialect().describe_table('orders')
        'SHOW CREATE TABLE orders'
        """
        return f"SHOW CREATE TABLE {table}"
