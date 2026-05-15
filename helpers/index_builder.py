"""Page index builder — parses knowledge files into a term-to-page map.

The index is a YAML structure mapping terms (table names, metric names,
glossary terms, aliases) to the file + section where they are defined,
plus a short context line.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml


def extract_markdown_sections(filepath: Path) -> dict[str, str]:
    """Parse a markdown file into {heading: content} by ## headings.

    Returns a dict where keys are the ## heading text and values are
    the full content under that heading (up to the next ## or EOF).
    """
    text = filepath.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    current_heading = None
    current_lines: list[str] = []

    for line in text.splitlines():
        match = re.match(r"^##\s+(.+)$", line)
        if match:
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = match.group(1).strip()
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


def _context_line(content: str, max_len: int = 60) -> str:
    """Extract the first meaningful sentence from content as a context line."""
    for line in content.splitlines():
        stripped = line.strip()
        # Skip markdown table rows and separators
        if stripped.startswith("|") or stripped.startswith("---"):
            continue
        cleaned = stripped.lstrip("-*> ").strip()
        cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)  # remove bold markers
        cleaned = re.sub(r"`(.+?)`", r"\1", cleaned)  # remove backticks
        if len(cleaned) > 10:
            return cleaned[:max_len]
    return ""


def extract_yaml_terms(filepath: Path, kind: str) -> list[dict]:
    """Extract searchable terms from a YAML knowledge file.

    Args:
        filepath: Path to the YAML file.
        kind: "metrics" or "glossary" — determines parsing structure.

    Returns:
        List of dicts with keys: term, file, section, context.
    """
    data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
    if data is None:
        return []

    results: list[dict] = []

    if kind == "metrics":
        metrics = data.get("metrics", {})
        if not isinstance(metrics, dict):
            return []
        for metric_id, metric in metrics.items():
            if not isinstance(metric, dict):
                continue
            desc = metric.get("description", "")
            context = desc[:100] if desc else metric.get("name", metric_id)
            entry = {"file": str(filepath), "section": metric_id, "context": context}
            results.append({"term": metric_id, **entry})
            for alias in metric.get("aliases", []):
                results.append({"term": alias, **entry})

    elif kind == "glossary":
        terms = data.get("terms", {})
        if not isinstance(terms, dict):
            return []
        for term_id, term_data in terms.items():
            if not isinstance(term_data, dict):
                continue
            definition = term_data.get("definition", "")
            context = definition[:100] if definition else term_data.get("name", term_id)
            entry = {"file": str(filepath), "section": term_id, "context": context}
            results.append({"term": term_id, **entry})
            for alias in term_data.get("aliases", []):
                results.append({"term": alias, **entry})

    return results


def _extract_column_names(section_content: str) -> list[str]:
    """Extract column names from a markdown table in schema content."""
    columns = []
    for line in section_content.splitlines():
        match = re.match(r"^\|\s*`?(\w+)`?\s*\|", line)
        if match:
            name = match.group(1)
            if name.lower() not in ("column", "-----"):
                columns.append(name)
    return columns


def build_index(repo_dir: Path | str, dataset_id: str) -> dict:
    """Build a complete page index for a dataset.

    Parses all knowledge files in the dataset directory and any linked
    organization glossary, producing a term-to-page mapping.

    Args:
        repo_dir: Root of the knowledge repository.
        dataset_id: Dataset identifier (folder name under datasets/).

    Returns:
        Dict with keys: version, dataset, built_at, mandatory, terms.
    """
    repo_dir = Path(repo_dir)
    ds_dir = repo_dir / "datasets" / dataset_id

    index: dict = {
        "version": 1,
        "dataset": dataset_id,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "mandatory": [],
        "terms": {},
    }

    def _add_term(term: str, file: str, section: str, context: str):
        """Add a term entry to the index, deduplicating."""
        entry = {"file": file, "section": section, "context": context}
        index["terms"].setdefault(term, [])
        # Avoid exact duplicates
        if entry not in index["terms"][term]:
            index["terms"][term].append(entry)

    # --- Mandatory pages ---
    mandatory_path = ds_dir / "_mandatory.yaml"
    if mandatory_path.exists():
        mandatory_data = yaml.safe_load(mandatory_path.read_text(encoding="utf-8")) or {}
        for section_ref in mandatory_data.get("sections", []):
            index["mandatory"].append({
                "file": section_ref["file"],
                "section": section_ref["section"],
            })
    else:
        # Fallback: all quirks sections become mandatory
        quirks_path = ds_dir / "quirks.md"
        if quirks_path.exists():
            for heading in extract_markdown_sections(quirks_path):
                index["mandatory"].append({
                    "file": "quirks.md",
                    "section": heading,
                })

    # --- Quirks sections ---
    mandatory_sections = {m["section"] for m in index["mandatory"]}
    quirks_path = ds_dir / "quirks.md"
    if quirks_path.exists():
        for heading, content in extract_markdown_sections(quirks_path).items():
            ctx = _context_line(content)
            _add_term(heading, "quirks.md", heading, ctx)
            # Extract table/column names mentioned in backticks
            # Skip mandatory sections — they're already force-included
            if heading not in mandatory_sections:
                for ref in re.findall(r"`([a-zA-Z_][a-zA-Z0-9_.]*)`", content):
                    _add_term(ref, "quirks.md", heading, f"See {heading}")

    # --- Schema sections (table names only, not columns) ---
    schema_path = ds_dir / "schema.md"
    if schema_path.exists():
        for heading, content in extract_markdown_sections(schema_path).items():
            ctx = _context_line(content) or heading  # fallback to full table name
            _add_term(heading, "schema.md", heading, ctx)
            # Also index the short table name (without database prefix)
            if "." in heading:
                short_name = heading.split(".")[-1]
                _add_term(short_name, "schema.md", heading, ctx)

    # --- Metrics ---
    metrics_dir = ds_dir / "metrics"
    if metrics_dir.is_dir():
        for yaml_file in sorted(metrics_dir.glob("*.yaml")):
            rel_path = f"metrics/{yaml_file.name}"
            for term_entry in extract_yaml_terms(yaml_file, kind="metrics"):
                _add_term(
                    term_entry["term"],
                    rel_path,
                    term_entry["section"],
                    term_entry["context"],
                )

    # --- Glossary (from organizations/) ---
    orgs_dir = repo_dir / "organizations"
    if orgs_dir.is_dir():
        for org_dir in sorted(orgs_dir.iterdir()):
            glossary_path = org_dir / "business" / "glossary" / "terms.yaml"
            if glossary_path.exists():
                rel_path = "glossary/terms.yaml"
                for term_entry in extract_yaml_terms(glossary_path, kind="glossary"):
                    _add_term(
                        term_entry["term"],
                        rel_path,
                        term_entry["section"],
                        term_entry["context"],
                    )

    return index
