---
name: ask-question
description: "USE THIS SKILL for ANY data question, analytical request, or metric inquiry. This is the MANDATORY entry point whenever a user asks about data, metrics, trends, churn, revenue, conversion, retention, segments, cohorts, funnels, KPIs, or any quantitative question — even casual ones like 'how are we doing' or 'what happened last month.' Also use when user says 'analyze', 'compare', 'why did X change', 'show me', 'what's driving', 'break down', or asks for any chart or visualization. If the user has a connected dataset and asks ANYTHING about their data, use this skill. Do NOT attempt to answer data questions without this skill."
---

# Ask Question — AI Analyst

Follow these steps in order. Do not freestyle.

## Hard Rules

**REFUSE immediately if the user asks for PII** (emails, phone numbers, names, addresses, user lists with identifiers). Never SELECT PII columns. Never explain why it's blocked. Respond: "I can't provide personally identifiable information. I can analyze aggregated patterns using case_id/user_id instead."

## Step 0: Load Context

**If knowledge MCP available:** Call `lookup_index(terms, dataset)` with key terms from the question. Apply mandatory pages (PII, partitions) silently. Call `get_page` for sections needing detail.

**Fallback:** Load from `.knowledge/` — active.yaml → schema.md → quirks.md → profile.md.

## Step 1: Classify (L1-L5)

| Level | Pattern | Response |
|-------|---------|----------|
| L1 | Single number | Direct query, return number |
| L2 | Comparison/breakdown | Query + chart |
| L3 | Why/analysis | 2-4 charts, validation, narrative |
| L4 | Investigation | Full analysis + sizing |
| L5 | Presentation | Hand off to run-analysis |

L1-L2: Execute immediately. L3+: State plan briefly, then proceed.

## Step 2: Data Quality (L2+)

Check: nulls >20% = BLOCKER, duplicates, date range coverage, sanity (rates 0-100%, positive revenue).

## Step 3: Query

**Silent guardrails:** No PII in SELECT. Always filter on partition column. Use mart tables over raw. Check UTC vs IST.

**Query strategy:**
- **Sample first:** Call `sample_table` only when querying a table you haven't seen before in this session or when the schema/column values are unclear. Skip if you already know the table's structure and data formats.
- **Prefer aggregated queries:** Use GROUP BY with COUNT, SUM, AVG for analysis. Use raw row selects only when you specifically need individual records (e.g., inspecting outliers, validating edge cases).
- **Deep dive with queries:** Do multiple focused aggregation queries to drill into dimensions rather than one large raw data pull.

**L1:** Single query, return number with context ("12,450 users in March, up 8% from Feb").

**L2:** Query + one chart. Give 2-3 sentences interpreting it. End with "Want to break this down by [dimension]?"

**L3-L4 (analytical thinking — think like the business):**
1. **Observe** — what changed? Query the metric over time or across segments.
2. **Decompose** — break it into business components. E.g., if orders dropped:
   - Which order type? O1 (new) vs O2+ (repeat)
   - If O1 dropped → check form submissions, lead volume, booking rates, ad spend
   - If O2+ dropped → check retention, delivery issues, RTO rates, CSAT
   - Which channels? Organic vs paid, self-service vs agent-booked
   - Which regions? City tier, specific states
3. **Trace upstream** — follow the funnel backward from the symptom to the cause. Revenue drop → order volume? AOV? Cancellations? Order volume drop → fewer leads? Lower conversion? Churn?
4. **Validate** — do segments sum to total? Can you calculate the same number a different way? Is the finding plausible?
5. **Size the impact** — how big is this? "Maharashtra alone accounts for 40% of the drop"

**L5:** Hand off to `run-analysis` skill for full pipeline + deck.

## Step 4: Charts (L2+)

**Mode:** L1-L2 → `explore_style()` (multi-color). L3+ → `swd_style()` (gray + highlight, takeaway titles).

**Pick the right type:** bar, line, histogram, box_plot, cohort_curves, retention_heatmap, funnel_waterfall, waterfall_chart, pareto_chart, donut_chart, treemap, slope_chart, diverging_bar, survival_curve, sparkline_grid, bump_chart, marimekko, ridge_plot, bullet_chart, geo_bar_chart, big_number_layout. All in `helpers/chart_helpers.py`.

**Presentation rules:** Gray everything, color only the story. Title = takeaway. Direct labels, no legends. No rotated text.

**Multi-chart narrative (L3+):** Structure as Context (baseline) → Tension (the problem/gap) → Resolution (the driver/recommendation).

## Step 5: Validate (L3+)

- Segments sum to total (±1%)
- Rates 0-100%, plausible ranges
- Simpson's Paradox check
- **Metric guardrail:** pair success metric with counter-metric (retention↔revenue/order, conversion↔LTV, volume↔CAC)

## Step 6: Present

L1: One sentence with context. L2: Chart + 2-3 sentences + "want to drill into [dimension]?" L3-L4: Headline finding → charts (Context→Tension→Resolution) → key numbers → confidence note (High/Medium/Low) → 2-3 next steps.

## Step 7: Follow-ups

Offer 2-3 specific next actions tied to findings.

## Step 8: Compact Context (L3+ only)

After completing an L3+ analysis, summarize what was done so the conversation stays efficient for the next question:

1. **Save findings** — write a brief summary to the working directory: key metric, finding, charts produced, SQL used
2. **Compact** — tell the user: "Analysis complete. I've saved the findings. Context has been compacted — ready for your next question."

This prevents deep analyses from eating the token budget for subsequent questions in the same session.
