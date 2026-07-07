"""Tests for servers/mcp_knowledge_server.py — MCP tool logic.

Tests the core functions directly (not over MCP transport).
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from helpers.index_builder import build_index, extract_markdown_sections


@pytest.fixture
def populated_repo(tmp_path):
    """Create a knowledge repo with index built."""
    ds = tmp_path / "datasets" / "demo"
    ds.mkdir(parents=True)

    (ds / "quirks.md").write_text(
        "# Quirks\n\n"
        "## PII Protection\n\n"
        "- Never expose email in SELECT.\n\n"
        "## Partition Columns\n\n"
        "- Always filter on activity_date.\n"
    )
    (ds / "schema.md").write_text(
        "# Schema\n\n## mydb.users\n\nUser table.\n\n"
        "| Column | Type |\n|--------|------|\n| user_id | INT |\n| email | VARCHAR |\n"
    )

    metrics_dir = ds / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "revenue.yaml").write_text(yaml.dump({
        "metrics": {
            "gross_revenue": {
                "name": "Gross Revenue",
                "aliases": ["revenue", "sales"],
                "description": "Total order value.",
            }
        }
    }))

    (ds / "_mandatory.yaml").write_text(yaml.dump({
        "sections": [
            {"file": "quirks.md", "section": "PII Protection"},
        ]
    }))

    # Build index
    index = build_index(tmp_path, "demo")
    (ds / "_index.yaml").write_text(yaml.dump(index, default_flow_style=False))

    return tmp_path


class TestLookupIndex:
    def test_returns_mandatory_pages(self, populated_repo):
        index = yaml.safe_load(
            (populated_repo / "datasets" / "demo" / "_index.yaml").read_text()
        )
        mandatory = index["mandatory"]
        assert any(m["section"] == "PII Protection" for m in mandatory)

    def test_finds_matching_terms(self, populated_repo):
        index = yaml.safe_load(
            (populated_repo / "datasets" / "demo" / "_index.yaml").read_text()
        )
        terms = index["terms"]
        assert "revenue" in terms
        assert "gross_revenue" in terms
        assert "mydb.users" in terms

    def test_no_match_returns_empty_for_term(self, populated_repo):
        index = yaml.safe_load(
            (populated_repo / "datasets" / "demo" / "_index.yaml").read_text()
        )
        assert "nonexistent_xyz" not in index["terms"]


class TestGetPage:
    def test_returns_full_file(self, populated_repo):
        quirks_path = populated_repo / "datasets" / "demo" / "quirks.md"
        content = quirks_path.read_text()
        assert "PII Protection" in content
        assert "Partition Columns" in content

    def test_returns_specific_section(self, populated_repo):
        quirks_path = populated_repo / "datasets" / "demo" / "quirks.md"
        sections = extract_markdown_sections(quirks_path)
        assert "PII Protection" in sections
        assert "email" in sections["PII Protection"]
        # Should NOT include content from other sections
        assert "activity_date" not in sections["PII Protection"]


# ---------------------------------------------------------------------------
# Tests for the new per-table schema slicing on get_page (tables=)
# ---------------------------------------------------------------------------

# Multi-table schema.md fixture. Headings are fully-qualified table names,
# matching the real schema.md convention (## <db>.<table>).
SCHEMA_MD = (
    "# Schema\n\n"
    "## analytics.orders\n\n"
    "The orders table.\n\n"
    "| Column | Type |\n"
    "|--------|------|\n"
    "| order_id | BIGINT |\n"
    "| order_status | VARCHAR |\n"
    "| created_at | TIMESTAMP |\n\n"
    "## analytics.events\n\n"
    "The events table.\n\n"
    "| Column | Type |\n"
    "|--------|------|\n"
    "| event_id | BIGINT |\n"
    "| net_revenue | DECIMAL(18,2) |\n\n"
    "## sales.customers\n\n"
    "The customers table.\n\n"
    "| Column | Type |\n"
    "|--------|------|\n"
    "| customer_id | BIGINT |\n"
    "| signup_pincode | VARCHAR |\n"
)


@pytest.fixture
def schema_repo(tmp_path, monkeypatch):
    """A knowledge repo whose schema.md has multiple FQ-named table sections.

    Points the server at this repo via KNOWLEDGE_LOCAL_PATH and clears the
    server's index cache so tests are isolated.
    """
    import servers.mcp_knowledge_server as srv

    ds = tmp_path / "datasets" / "demo"
    ds.mkdir(parents=True)
    (ds / "schema.md").write_text(SCHEMA_MD)
    (ds / "quirks.md").write_text(
        "# Quirks\n\n## PII Protection\n\n- Never expose email.\n"
    )

    monkeypatch.setenv("KNOWLEDGE_LOCAL_PATH", str(tmp_path))
    # Make sure no stale repo_url config leaks in from the environment.
    monkeypatch.delenv("KNOWLEDGE_REPO_URL", raising=False)
    srv._index_cache.clear()

    return tmp_path, srv


class TestGetPageTables:
    def _source_section(self, table_key):
        """Return the verbatim content stored under a heading in SCHEMA_MD."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(SCHEMA_MD)
            path = Path(f.name)
        return extract_markdown_sections(path)[table_key]

    def test_short_name_returns_only_that_section_verbatim(self, schema_repo):
        _, srv = schema_repo
        out = srv.get_page("schema.md", "demo", tables=["orders"])

        # The matched section's heading is restored.
        assert "## analytics.orders" in out
        # Verbatim content present — a known column line, byte-for-byte.
        verbatim = self._source_section("analytics.orders")
        assert verbatim in out
        assert "| order_id | BIGINT |" in out
        # No other table's columns leaked in.
        assert "net_revenue" not in out
        assert "customer_id" not in out
        assert "analytics.events" not in out

    def test_fully_qualified_name_matches_same_section(self, schema_repo):
        _, srv = schema_repo
        out = srv.get_page(
            "schema.md", "demo", tables=["analytics.orders"]
        )
        assert "## analytics.orders" in out
        assert "| order_id | BIGINT |" in out
        assert "net_revenue" not in out

    def test_multiple_tables_returns_all_matched_no_others(self, schema_repo):
        _, srv = schema_repo
        out = srv.get_page(
            "schema.md", "demo",
            tables=["orders", "events"],
        )
        assert "## analytics.orders" in out
        assert "## analytics.events" in out
        assert "| order_id | BIGINT |" in out
        assert "| net_revenue | DECIMAL(18,2) |" in out
        # The unrequested customers table must not appear.
        assert "sales.customers" not in out
        assert "signup_pincode" not in out

    def test_case_insensitive_table_name(self, schema_repo):
        _, srv = schema_repo
        out = srv.get_page("schema.md", "demo", tables=["ORDERS"])
        assert "## analytics.orders" in out
        assert "| order_id | BIGINT |" in out

    def test_unknown_among_known_returns_matched_plus_not_found_note(self, schema_repo):
        _, srv = schema_repo
        out = srv.get_page(
            "schema.md", "demo",
            tables=["orders", "does_not_exist"],
        )
        # The known section is still returned.
        assert "## analytics.orders" in out
        assert "| order_id | BIGINT |" in out
        # A NOT FOUND note names the unmatched table.
        assert "NOT FOUND" in out
        assert "does_not_exist" in out

    def test_all_unknown_returns_json_error_with_requested(self, schema_repo):
        _, srv = schema_repo
        out = srv.get_page(
            "schema.md", "demo",
            tables=["nope_one", "nope_two"],
        )
        parsed = json.loads(out)
        assert "error" in parsed
        assert parsed["requested"] == ["nope_one", "nope_two"]
        # A sample of available headings helps the caller correct itself.
        assert "available_sample" in parsed

    def test_no_args_returns_full_file_unchanged(self, schema_repo):
        _, srv = schema_repo
        out = srv.get_page("schema.md", "demo")
        # Full file: every table section present.
        assert "## analytics.orders" in out
        assert "## analytics.events" in out
        assert "## sales.customers" in out
        assert out == SCHEMA_MD

    def test_section_arg_still_works_unchanged(self, schema_repo):
        _, srv = schema_repo
        out = srv.get_page(
            "schema.md", "demo", section="sales.customers"
        )
        # Returns just that section's content (existing behavior — no heading line).
        assert "| customer_id | BIGINT |" in out
        assert "signup_pincode" in out
        assert "order_id" not in out

    def test_tables_takes_precedence_over_section(self, schema_repo):
        _, srv = schema_repo
        out = srv.get_page(
            "schema.md", "demo",
            section="sales.customers",
            tables=["orders"],
        )
        # tables wins: orders section returned, not customers.
        assert "## analytics.orders" in out
        assert "| order_id | BIGINT |" in out
        assert "customer_id" not in out
