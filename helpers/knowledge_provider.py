"""KnowledgeProvider — abstraction for accessing knowledge from local files or MCP.

Provides a Protocol that both LocalKnowledgeProvider and MCPKnowledgeProvider
implement, so existing helpers can switch backends transparently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import yaml

from helpers.index_builder import build_index, extract_markdown_sections


class KnowledgeProvider(Protocol):
    """Protocol for knowledge access backends."""

    def get_schema(self, dataset: str) -> str: ...
    def get_quirks(self, dataset: str) -> str: ...
    def get_page(self, file: str, section: str, dataset: str) -> str: ...
    def lookup_index(self, terms: list[str], dataset: str) -> dict: ...


class LocalKnowledgeProvider:
    """Reads knowledge from a local directory (existing .knowledge/ behavior)."""

    def __init__(self, knowledge_dir: str):
        self._root = Path(knowledge_dir)
        self._index_cache: dict[str, dict] = {}

    def _dataset_dir(self, dataset: str) -> Path:
        return self._root / "datasets" / dataset

    def _get_index(self, dataset: str) -> dict:
        if dataset not in self._index_cache:
            ds_dir = self._dataset_dir(dataset)
            index_path = ds_dir / "_index.yaml"
            if index_path.exists():
                self._index_cache[dataset] = yaml.safe_load(index_path.read_text())
            elif ds_dir.is_dir():
                self._index_cache[dataset] = build_index(self._root, dataset)
            else:
                self._index_cache[dataset] = {"mandatory": [], "terms": {}}
        return self._index_cache[dataset]

    def get_schema(self, dataset: str) -> str:
        path = self._dataset_dir(dataset) / "schema.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_quirks(self, dataset: str) -> str:
        path = self._dataset_dir(dataset) / "quirks.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_page(self, file: str, section: str, dataset: str) -> str:
        file_path = self._dataset_dir(dataset) / file

        # Also check organizations/ for glossary paths
        if not file_path.exists() and file.startswith("glossary/"):
            orgs_dir = self._root / "organizations"
            if orgs_dir.is_dir():
                for org_dir in sorted(orgs_dir.iterdir()):
                    candidate = org_dir / "business" / file
                    if candidate.exists():
                        file_path = candidate
                        break

        if not file_path.exists():
            return ""

        content = file_path.read_text(encoding="utf-8")

        if section and file_path.suffix == ".md":
            sections = extract_markdown_sections(file_path)
            return sections.get(section, "")

        return content

    def lookup_index(self, terms: list[str], dataset: str) -> dict:
        index = self._get_index(dataset)

        matches: dict[str, list[dict]] = {}
        for term in terms:
            term_lower = term.lower()
            if term in index.get("terms", {}):
                matches[term] = index["terms"][term]
            else:
                for key, entries in index.get("terms", {}).items():
                    if key.lower() == term_lower:
                        matches[term] = entries
                        break

        return {
            "mandatory": index.get("mandatory", []),
            "matches": matches,
            "unmatched": [t for t in terms if t not in matches],
        }
