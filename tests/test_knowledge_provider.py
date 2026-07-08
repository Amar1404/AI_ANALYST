"""Tests for helpers/knowledge_provider.py — KnowledgeProvider adapter."""

import tempfile
from pathlib import Path

import pytest
import yaml

from helpers.knowledge_provider import LocalKnowledgeProvider


@pytest.fixture
def local_knowledge(tmp_path):
    """Create a local .knowledge/ structure."""
    ds = tmp_path / "datasets" / "test-ds"
    ds.mkdir(parents=True)

    (ds / "quirks.md").write_text(
        "# Quirks\n\n## PII\n\n- No email in SELECT.\n\n## Partitions\n\n- Filter activity_date.\n"
    )
    (ds / "schema.md").write_text(
        "# Schema\n\n## db.orders\n\nOrders table.\n\n| Column | Type |\n|--------|------|\n| id | INT |\n"
    )

    metrics_dir = ds / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "kpi.yaml").write_text(yaml.dump({
        "metrics": {
            "revenue": {
                "name": "Revenue",
                "aliases": ["sales"],
                "description": "Total sales.",
            }
        }
    }))

    (ds / "_mandatory.yaml").write_text(yaml.dump({
        "sections": [{"file": "quirks.md", "section": "PII"}]
    }))

    return tmp_path


class TestLocalKnowledgeProvider:
    def test_get_schema(self, local_knowledge):
        provider = LocalKnowledgeProvider(str(local_knowledge))
        schema = provider.get_schema("test-ds")
        assert "db.orders" in schema

    def test_get_quirks(self, local_knowledge):
        provider = LocalKnowledgeProvider(str(local_knowledge))
        quirks = provider.get_quirks("test-ds")
        assert "PII" in quirks

    def test_get_page_full_file(self, local_knowledge):
        provider = LocalKnowledgeProvider(str(local_knowledge))
        content = provider.get_page("quirks.md", "", "test-ds")
        assert "PII" in content
        assert "Partitions" in content

    def test_get_page_specific_section(self, local_knowledge):
        provider = LocalKnowledgeProvider(str(local_knowledge))
        content = provider.get_page("quirks.md", "PII", "test-ds")
        assert "email" in content
        assert "activity_date" not in content

    def test_lookup_index(self, local_knowledge):
        provider = LocalKnowledgeProvider(str(local_knowledge))
        result = provider.lookup_index(["revenue", "PII"], "test-ds")
        assert "mandatory" in result
        matched_terms = list(result["matches"].keys())
        assert "revenue" in matched_terms

    def test_get_schema_missing_dataset(self, local_knowledge):
        provider = LocalKnowledgeProvider(str(local_knowledge))
        result = provider.get_schema("nonexistent")
        assert result == ""
