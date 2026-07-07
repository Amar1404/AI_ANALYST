"""Tests for helpers/index_builder.py — page index construction."""

import tempfile
from pathlib import Path

import pytest
import yaml

from helpers.index_builder import build_index, extract_markdown_sections, extract_yaml_terms


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def knowledge_dir(tmp_path):
    """Create a minimal knowledge repo structure in a temp directory."""
    ds = tmp_path / "datasets" / "test-dataset"
    ds.mkdir(parents=True)

    # quirks.md with two sections
    (ds / "quirks.md").write_text(
        "# Quirks: Test\n\n"
        "## PII Protection\n\n"
        "- Never expose email or phone in SELECT.\n\n"
        "## Partition Columns\n\n"
        "- Always filter on activity_date.\n"
    )

    # schema.md with one table section
    (ds / "schema.md").write_text(
        "# Schema: Test\n\n"
        "## testdb.orders\n\n"
        "Order table.\n\n"
        "| Column | Type |\n"
        "|--------|------|\n"
        "| order_id | INT |\n"
        "| case_id | VARCHAR |\n"
        "| activity_date | STRING |\n"
    )

    # metrics/retention.yaml
    metrics_dir = ds / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "retention.yaml").write_text(yaml.dump({
        "metrics": {
            "repeat_purchase_rate": {
                "name": "Repeat Purchase Rate",
                "aliases": ["retention", "O2 rate"],
                "description": "Percentage of users who order again.",
                "source_tables": ["testdb.orders"],
            }
        }
    }))

    # _mandatory.yaml
    (ds / "_mandatory.yaml").write_text(yaml.dump({
        "sections": [
            {"file": "quirks.md", "section": "PII Protection"},
            {"file": "quirks.md", "section": "Partition Columns"},
        ]
    }))

    # organizations/test-org/business/glossary/terms.yaml
    glossary_dir = tmp_path / "organizations" / "test-org" / "business" / "glossary"
    glossary_dir.mkdir(parents=True)
    (glossary_dir / "terms.yaml").write_text(yaml.dump({
        "terms": {
            "O1": {
                "name": "First Order",
                "aliases": ["order 1", "first purchase"],
                "definition": "First delivered order, order_sequence = 1.",
            },
            "O2": {
                "name": "Second Order",
                "aliases": ["order 2"],
                "definition": "Second delivered order.",
            },
        }
    }))

    return tmp_path


# ---------------------------------------------------------------------------
# extract_markdown_sections
# ---------------------------------------------------------------------------

class TestExtractMarkdownSections:
    def test_extracts_h2_sections(self, knowledge_dir):
        quirks_path = knowledge_dir / "datasets" / "test-dataset" / "quirks.md"
        sections = extract_markdown_sections(quirks_path)
        assert "PII Protection" in sections
        assert "Partition Columns" in sections
        assert "Never expose email" in sections["PII Protection"]

    def test_extracts_table_names_from_schema(self, knowledge_dir):
        schema_path = knowledge_dir / "datasets" / "test-dataset" / "schema.md"
        sections = extract_markdown_sections(schema_path)
        assert "testdb.orders" in sections
        assert "order_id" in sections["testdb.orders"]


# ---------------------------------------------------------------------------
# extract_yaml_terms
# ---------------------------------------------------------------------------

class TestExtractYamlTerms:
    def test_extracts_metric_names_and_aliases(self, knowledge_dir):
        metrics_path = knowledge_dir / "datasets" / "test-dataset" / "metrics" / "retention.yaml"
        terms = extract_yaml_terms(metrics_path, kind="metrics")
        # Should have entries for "repeat_purchase_rate", "retention", "O2 rate"
        term_keys = [t["term"] for t in terms]
        assert "repeat_purchase_rate" in term_keys
        assert "retention" in term_keys
        assert "O2 rate" in term_keys

    def test_extracts_glossary_terms_and_aliases(self, knowledge_dir):
        glossary_path = (
            knowledge_dir / "organizations" / "test-org" / "business" / "glossary" / "terms.yaml"
        )
        terms = extract_yaml_terms(glossary_path, kind="glossary")
        term_keys = [t["term"] for t in terms]
        assert "O1" in term_keys
        assert "order 1" in term_keys
        assert "O2" in term_keys


# ---------------------------------------------------------------------------
# build_index
# ---------------------------------------------------------------------------

class TestBuildIndex:
    def test_builds_complete_index(self, knowledge_dir):
        index = build_index(knowledge_dir, "test-dataset")
        assert index["version"] == 1
        assert index["dataset"] == "test-dataset"
        assert "built_at" in index

    def test_mandatory_pages_loaded(self, knowledge_dir):
        index = build_index(knowledge_dir, "test-dataset")
        mandatory_sections = [m["section"] for m in index["mandatory"]]
        assert "PII Protection" in mandatory_sections
        assert "Partition Columns" in mandatory_sections

    def test_term_entries_exist(self, knowledge_dir):
        index = build_index(knowledge_dir, "test-dataset")
        terms = index["terms"]
        # From glossary
        assert "O1" in terms
        assert "O2" in terms
        # From metrics
        assert "retention" in terms
        # From schema — table name
        assert "testdb.orders" in terms

    def test_term_entries_have_required_fields(self, knowledge_dir):
        index = build_index(knowledge_dir, "test-dataset")
        for term, entries in index["terms"].items():
            for entry in entries:
                assert "file" in entry, f"Missing 'file' in term '{term}'"
                assert "section" in entry, f"Missing 'section' in term '{term}'"
                assert "context" in entry, f"Missing 'context' in term '{term}'"

    def test_schema_columns_are_indexed(self, knowledge_dir):
        """Column names from schema.md tables must resolve via the index, so a
        question about a column never needs live Athena discovery."""
        index = build_index(knowledge_dir, "test-dataset")
        terms = index["terms"]
        assert "order_id" in terms
        assert "case_id" in terms
        entry = terms["order_id"][0]
        assert entry["file"] == "schema.md"
        assert entry["section"] == "testdb.orders"

    def test_fallback_mandatory_when_no_yaml(self, tmp_path):
        """When _mandatory.yaml is missing, all quirks sections become mandatory."""
        ds = tmp_path / "datasets" / "bare"
        ds.mkdir(parents=True)
        (ds / "quirks.md").write_text(
            "# Quirks\n\n## Section A\n\nContent A.\n\n## Section B\n\nContent B.\n"
        )
        (ds / "schema.md").write_text("# Schema\n")
        index = build_index(tmp_path, "bare")
        mandatory_sections = [m["section"] for m in index["mandatory"]]
        assert "Section A" in mandatory_sections
        assert "Section B" in mandatory_sections
