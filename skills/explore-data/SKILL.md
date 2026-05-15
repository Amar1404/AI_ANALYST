---
name: explore-data
description: "USE THIS SKILL when the user wants to explore, browse, preview, or understand their data before asking a specific question. Triggers on 'explore', 'browse data', 'what's in this dataset', 'show me the schema', 'what tables do I have', '/explore', '/data', or any request to look at the data structure, preview rows, check distributions, or understand what's available. Also use when a user just connected a new dataset and wants to see what's there. Do NOT skip this skill for data exploration — it includes quality checks and SWD chart standards that produce professional outputs."
---

# Explore Data — Interactive Data Discovery

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

Load schema from `.knowledge/datasets/{active}/schema.md` if available.
Load quirks from `.knowledge/datasets/{active}/quirks.md` if available.

If no active dataset, prompt: "No dataset connected. Use `/connect-data` or point me to your CSV files."

## Step 1: Choose Exploration Mode

**Mode A: Dataset Overview** (no table specified)
- List all tables with row counts and date ranges
- Highlight 3-5 most analytically useful tables
- Show key entities and how they connect
- Suggest 3 starting questions

**Mode B: Table Exploration** (table specified)
- Column list with types and null rates
- Sample 5 random rows
- Numeric columns: min, max, mean, median
- Categorical columns: top 5 values with counts
- Date columns: range and coverage
- Flag quality issues (>5% nulls, low cardinality)

**Mode C: Column Deep-Dive** (table + column specified)
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
1. Keep it fast — max 3-4 queries per step
2. Never modify data during exploration
3. Always cite table and column names
4. Never dump all questions at once — offer 1-3 focused suggestions
