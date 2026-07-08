---
name: explore-data
description: "Use this skill when the user wants to explore, browse, preview, or understand their data before asking a specific question. Triggers on 'explore', 'browse data', 'what's in this dataset', 'show me the schema', 'what tables do I have', '/explore', '/data', or any request to look at the data structure, preview rows, check distributions, or understand what's available. Also use when a user just connected a new dataset and wants to see what's there. Use this skill for data exploration — it includes quality checks and SWD chart standards that produce professional outputs."
---

# Explore Data — Interactive Data Discovery

## Model conventions

This skill is version-aware. Before starting, apply `skills/MODEL_CONVENTIONS.md` for the model you are: query data rather than inferring numbers (§B, §E), follow instruction scope literally (§A), let response length follow task complexity (§C), and run intelligence-sensitive analysis at high/xhigh effort (§D).

You are helping the user explore their dataset. Keep it fast, visual, and interactive — this is discovery mode, not full analysis.

## Step 0: Load Context

```python
import os, yaml

workspace = os.environ.get('AI_ANALYST_WORKSPACE', '')
if not workspace:
    for d in ['.', './data', '../data']:
        if os.path.isdir(d) and any(f.endswith(('.csv', '.parquet')) for f in os.listdir(d)):
            workspace = os.path.abspath(d)
            break
```

Load schema **per-table, not wholesale**. For a specific table (Mode B), load only that
table's section — `get_page("schema.md", dataset, tables=["<table>"])` (or read just that
table's `## ` section from `.knowledge/datasets/{active}/schema.md`). For a dataset overview
(Mode A), use the table list / index rather than loading every table's columns; pull a table's
full section only when you drill into it. Never load the entire `schema.md` into context.
Load quirks from `.knowledge/datasets/{active}/quirks.md` if available.

If no active dataset, prompt: "No dataset connected. Use `/connect-data` or point me to your CSV files."

**Cached knowledge before live queries.** Exploration answers come from the catalog first:
the knowledge index (`lookup_index`/`get_page`), `.knowledge/datasets/{active}/` files, and a
recent `last_profile.md` from deep-profile (row counts, distributions, completeness are often
already there). Live discovery (`list_athena_tables`, `describe_athena_table`, `sample_table`,
per-table probe queries) is the fallback when the catalog has nothing for what the user asked —
not the default. Reuse a table's schema once resolved; don't re-discover it later in the session.

## Step 1: Choose Exploration Mode

**Mode A: Dataset Overview** (no table specified)
- List tables with row counts and date ranges **from the catalog/index/profile** — do not run
  a live count query per table. If the catalog lacks counts, say so and offer to profile the
  3-5 tables that matter rather than scanning the whole catalog.
- Highlight 3-5 most analytically useful tables
- Show key entities and how they connect
- Suggest 3 starting questions

**Mode B: Table Exploration** (table specified)

Get the column list/types from the catalog (Step 0). Then compute the whole numeric/date
profile in **ONE combined query** — not one query per line below:

```sql
SELECT COUNT(*) AS row_count,
       COUNT(*) FILTER (WHERE col_a IS NULL) AS col_a_nulls,
       MIN(col_a) AS col_a_min, MAX(col_a) AS col_a_max, AVG(col_a) AS col_a_mean,
       approx_percentile(col_a, 0.5) AS col_a_median,
       approx_distinct(col_b) AS col_b_cardinality,
       MIN(event_date) AS date_from, MAX(event_date) AS date_to
FROM t WHERE <partition filter>
```

- Column list with types and null rates
- Sample 5 rows (one `LIMIT 5` query — the only row-level pull)
- Numeric columns: min, max, mean, median (`approx_percentile`)
- Categorical columns: top 5 values with counts — batch several columns via
  `GROUP BY GROUPING SETS ((col_x), (col_y))` when checking more than one
- Date columns: range and coverage
- Flag quality issues (>5% nulls, low cardinality)

Typical Mode B total: **2 queries** (combined profile + sample), plus at most one
top-values query.

**Mode C: Column Deep-Dive** (table + column specified)

One query returns the distribution AND the null/outlier inputs: a bucketed
`GROUP BY` (histogram counts) plus a stats row (nulls, `approx_percentile` for p25/p75 →
IQR) — via GROUPING SETS or two CTEs in the same statement.

- Full distribution chart (histogram or bar chart)
- Null analysis
- Outlier detection (IQR method)
- Suggest related columns for cross-analysis

## Step 2: Chart Standards (If Generating Any Visuals)

**Use exploration mode for data discovery:** Call `explore_style()` instead of `swd_style()`. This gives you a multi-color palette, white background, and grid lines — better for spotting patterns and comparing distributions. Switch to `swd_style()` only when creating final deliverable charts.

```python
import sys
sys.path.insert(0, '<plugin-path>/helpers')
from chart_helpers import explore_style, highlight_bar, histogram, box_plot, action_title, save_chart
```

- **Call `explore_style()` before every chart** (multi-color, grid on)
- Use the full chart catalog — histograms for distributions, box plots for comparisons, sparklines for dashboards
- Descriptive titles are fine in exploration mode
- Clean formatting: no rotated text, remove top/right spines

## Step 3: Quality Flags

Always highlight data issues:
- >20% nulls → BLOCKER (red flag)
- 5-20% nulls → WARNING
- Very low cardinality (< 3 unique values in expected-high column) → NOTE
- Empty table → BLOCKER
- All-null column → BLOCKER

## Step 4: Interactive Follow-Up

After presenting results, offer 2-3 specific next actions:
- "Want to see how {column} varies by {dimension}?"
- "This looks like a good candidate for analysis. Try asking: '{specific question}'"
- "There are quality issues in {column}. Want deeper profiling?"

## Step 5: Save Notes

Write brief exploration notes to `{workspace}/working/explore_notes_{DATE}.md`.
These are available for subsequent analysis agents.

## Rules
1. Keep it fast — batch each step into one combined query where the patterns above allow;
   1-2 queries per step is the norm, 3-4 the ceiling
2. Never modify data during exploration
3. Always cite table and column names
4. Never dump all questions at once — offer 1-3 focused suggestions
