"""Answer receipt — the evidence trail attached to every analytical answer.

A data agent does not just return a number; it returns a *verified answer with
evidence*. The receipt is that evidence: the interpreted question, the metric
definition used, the tables and filters applied, the SQL executed, the
assumptions made, the governance applied, and the confidence grade.

This is the single highest-trust-per-line addition to the analyst: it closes the
"fast answer with no query link or stated assumption" failure mode, and it forces
meaning-resolution (which metric? which entity? which time window?) to be made
explicit rather than guessed silently.

The model assembles a `Receipt` from what it already knows during a question
turn — this module only standardizes the *shape* and the *rendering* so every
answer carries the same audit trail. It deliberately performs no querying and no
LLM calls.

Usage (inside the ask-question flow)::

    from helpers.receipt import Receipt, MetricRef

    receipt = Receipt(
        interpreted_question="Net revenue for March 2026 vs February 2026",
        metric=MetricRef(
            name="revenue",
            resolved_as="net_revenue (gross - refunds - cancellations)",
            source="metrics.yaml#revenue",
        ),
        tables=["table_name"],
        filters=["activity_date BETWEEN 2026-02-01 AND 2026-03-31"],
        time_window="Feb 2026 vs Mar 2026, calendar months, IST",
        sql="SELECT date_trunc('month', activity_date) AS m, SUM(net_amount) ...",
        assumptions=["Refunds attributed to original order month, not refund month"],
        caveats=["RTO orders excluded — they net to zero revenue"],
        governance=["PII columns blocked at query layer"],
        data_through="2026-06-17",
    )
    print(receipt.render(confidence_badge="A (92/100)"))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MetricRef:
    """A resolved metric definition — the answer to 'which X did you mean?'.

    `name` is what the user said ("revenue"); `resolved_as` is the canonical
    definition that was actually computed ("net_revenue = gross - refunds");
    `source` points at where that definition lives so the reader can audit it
    (e.g. "metrics.yaml#revenue"). Surfacing this is what prevents the silent
    metric-ambiguity error — the #1 source of wrong data answers.
    """

    name: str
    resolved_as: str
    source: Optional[str] = None

    def render(self) -> str:
        line = f"{self.name} → {self.resolved_as}"
        if self.source:
            line += f"  _(per {self.source})_"
        return line


@dataclass
class Receipt:
    """The evidence trail for one analytical answer.

    Every field is optional so the receipt scales with question complexity:
    an L1 single-number answer carries a minimal receipt (question + metric +
    SQL), while an L4 investigation carries the full set. `render()` omits any
    empty section so the block stays as short as the answer deserves.
    """

    interpreted_question: str
    metric: Optional[MetricRef] = None
    tables: List[str] = field(default_factory=list)
    filters: List[str] = field(default_factory=list)
    time_window: Optional[str] = None
    sql: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    governance: List[str] = field(default_factory=list)
    data_through: Optional[str] = None

    def render(self, confidence_badge: Optional[str] = None) -> str:
        """Render the receipt as a collapsible Markdown block.

        `confidence_badge` is the string produced by
        ``confidence_scoring.format_confidence_badge`` (e.g. "A (92/100)"). It
        is passed in rather than computed here so the receipt stays decoupled
        from the scoring stack and works even when no formal scoring was run.
        """
        lines: List[str] = ["<details>", "<summary>📋 Receipt — how this answer was derived</summary>", ""]

        lines.append(f"- **Interpreted question:** {self.interpreted_question}")
        if self.metric:
            lines.append(f"- **Metric:** {self.metric.render()}")
        if self.time_window:
            lines.append(f"- **Time window:** {self.time_window}")
        if self.tables:
            lines.append(f"- **Tables:** {', '.join(self.tables)}")
        if self.filters:
            lines.append(f"- **Filters:** {'; '.join(self.filters)}")
        if self.data_through:
            lines.append(f"- **Data current through:** {self.data_through}")
        if self.governance:
            lines.append(f"- **Governance applied:** {'; '.join(self.governance)}")

        if self.assumptions:
            lines.append("- **Assumptions:**")
            lines.extend(f"  - {a}" for a in self.assumptions)
        if self.caveats:
            lines.append("- **Caveats:**")
            lines.extend(f"  - {c}" for c in self.caveats)

        if confidence_badge:
            lines.append(f"- **Confidence:** {confidence_badge}")

        if self.sql:
            lines.extend(["", "**Executed SQL:**", "```sql", self.sql.strip(), "```"])

        lines.extend(["", "</details>"])
        return "\n".join(lines)
