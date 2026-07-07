# Descriptive Analytics — Extended Detail

This file holds the situational implementation detail for the Descriptive Analytics agent:
helper-call signatures, code examples, verbose "use X when Y" guidance, and the full output
template. Load it on demand when you need the implementation detail for a step. The core spec
(`agents/descriptive-analytics.md`) carries the workflow skeleton, all HALT/validation gates,
and pointers into this file. Headings below match the core step names.

---

## Step 3: Perform Segmentation Analysis

### 3a+. Rank Dimensions by Explanatory Power

Before deep-diving into segment profiles, use `rank_dimensions()` from `helpers/stats_helpers.py` to objectively prioritize which dimensions explain the most variance in the key metric.

```python
from helpers.stats_helpers import rank_dimensions

# Identify all candidate categorical columns from Step 3a
dimension_cols = ["plan_type", "channel", "region", ...]  # from available columns
metric_col = "..."  # the primary metric from the question/hypothesis

rankings = rank_dimensions(df, metric_col=metric_col, dimension_cols=dimension_cols)

for r in rankings:
    print(f"  #{r['rank']} {r['dimension']}: eta²={r['eta_squared']:.3f} — {r['interpretation']}")
```

Use the ranked output to:
- **Prioritize investigation order**: Start deep-dives with the highest-ranked dimension (largest eta-squared). Dimensions with negligible effect (eta-squared < 0.01) can be deprioritized or skipped.
- **Record effect sizes in findings**: Note the eta-squared value and its interpretation (negligible / small / medium / large) alongside every segmentation finding. This quantifies *how much* a dimension matters, not just *whether* it matters.
- **Narrow the 2-4 dimension selection**: If the initial candidate list is long, use the ranking to trim to the top 2-4 dimensions with meaningful explanatory power.

When comparing specific segment pairs (e.g., "Does paid outperform organic?"), use the **compare segments** pattern: compute the key metric mean for each group, then run `two_sample_mean_test(group_a_values, group_b_values)` to get a p-value, confidence interval, and Cohen's d effect size. This complements `rank_dimensions()` — the ranking tells you *which* dimension to investigate; the pairwise comparison tells you *how big* the gap is between specific groups.

### 3b. Advanced Segmentation (use analytics_helpers)

For user-centric datasets, apply RFM analysis and concentration analysis from `helpers/analytics_helpers.py`:

```python
from helpers.analytics_helpers import rfm_analysis, concentration_analysis, compare_segments

# RFM segmentation (requires user_id, date, and monetary columns)
rfm = rfm_analysis(df, user_col='user_id', date_col='order_date', monetary_col='revenue')
# Returns segments: Champions, Loyal, At Risk, Lost, Other

# Concentration analysis (how concentrated is revenue across users?)
conc = concentration_analysis(df, entity_col='user_id', value_col='revenue')
# Returns Gini coefficient, Pareto ratio, Lorenz curve data

# Pairwise comparison between specific segments
comparison = compare_segments(df, group_col='plan_type', metric_col='revenue')
# Auto-selects Mann-Whitney or t-test, returns p-values with Bonferroni correction + Cohen's d
```

Use RFM when the data has transactional user data (user_id + date + monetary value). Use concentration to quantify skew. Use compare_segments for any pairwise group comparison.

### 3b+. Compute Segment Profiles

Write and execute ONE query across all segmentation dimensions using `GROUP BY GROUPING SETS ((dim_a), (dim_b), ..., ())` — not one query per dimension — then compute the rest in-memory over that single result:
- Segment sizes (count; percentage of total computed in-memory)
- Key metrics per segment (the metrics specified in the question/hypothesis)
- Relative performance: how each segment compares to the overall average (the `()` grand-total row)
- Segment rankings per dimension (in-memory)

```python
# Example: Segmentation by user plan type
# For each plan: count users, compute avg revenue, compute retention rate
# Compare each segment to the overall average
# Flag segments that are >20% above or below average
```

---

## Step 4: Perform Funnel Analysis

### 4b. Compute Funnel Metrics

Write and execute SQL or Python to compute:
- Count of users at each funnel step
- Step-to-step conversion rate (users at step N+1 / users at step N)
- Overall conversion rate (users at final step / users at first step)
- Median time between steps

```python
# Example: Funnel from signup to first purchase
# Step 1: All signups in the period
# Step 2: Completed onboarding (within 7 days of signup)
# Step 3: First product view (within 14 days)
# Step 4: First add-to-cart
# Step 5: First purchase
# Compute: count at each step, conversion rate step-to-step, time between steps
```

---

## Step 7: Triangulate and Validate Findings

### 7a-post. Record Lineage

Log this agent's data flow for traceability:

```python
from helpers.lineage_tracker import track

track(
    step=5,  # pipeline_step from CONTRACT
    agent="descriptive-analytics",
    inputs=[str(DATASET)],
    outputs=["outputs/analysis_report_{{DATE}}.md"],
    metadata={"tables_used": tables_used, "findings_count": len(findings)}
)
```

### 7b. Rank findings by impact (use `score_findings`)

After validation, rank all findings by business impact using `score_findings()` from `helpers/analytics_helpers.py`:

```python
from helpers.analytics_helpers import score_findings

findings = [
    {"description": "...", "metric_value": X, "baseline_value": Y,
     "affected_pct": Z, "actionable": True/False, "confidence": 0.0-1.0},
    ...
]
result = score_findings(findings)
for f in result['ranked_findings']:
    print(f"  Rank {f['rank']}: {f['description']} (score={f['score']})")
```

Use the ranked order to structure the Key Findings section of the report — highest-impact findings first. Include the score in the findings metadata for downstream use by the Story Architect agent.

---

## Step 8: Compile the Analysis Report — Full Output Format

A markdown file saved to `outputs/analysis_report_{{DATE}}.md` with charts saved to `outputs/charts/`. Structure:

```markdown
# Descriptive Analytics Report
**Generated:** {{DATE}}
**Dataset:** {{DATASET}}
**Questions/Hypotheses:** [reference to source document]
**Focus:** [segmentation / funnel / drivers / all]

## Executive Summary
[3-5 sentences: the top findings, stated as insights not descriptions.
 "Mobile users convert at 2x the rate of desktop users, driven primarily by a
 shorter time-to-first-action. The onboarding-to-activation step loses 62% of
 users, with the steepest drop among users acquired via paid search."]

## Key Findings

### Finding 1: [Insight headline — the "so what"]
**Evidence:** [specific numbers, comparisons, chart reference]
**Implication:** [what this means for the business decision]
**Confidence:** [HIGH / MEDIUM / LOW — based on data quality and sample size]
**Chart:** ![Finding 1](charts/finding_1.png)

### Finding 2: [Insight headline]
[same structure]

### Finding 3: [Insight headline]
[same structure]

## Segmentation Analysis

### Dimension: [Segmentation dimension 1]
| Segment | Count | % of Total | [Key Metric] | vs. Average |
|---------|-------|-----------|--------------|-------------|
| [seg A] | [n]   | [%]       | [value]      | +X%         |
| [seg B] | [n]   | [%]       | [value]      | -Y%         |
| ...     | ...   | ...       | ...          | ...         |

**Insight:** [What this segmentation reveals]
**Chart:** ![Segmentation](charts/segmentation_dim1.png)

### Dimension: [Segmentation dimension 2]
[same structure]

## Funnel Analysis

### Funnel: [Funnel name]
| Step | Count | Conversion | Drop-off | Median Time to Next |
|------|-------|-----------|----------|-------------------|
| [Step 1] | [n] | — | — | [time] |
| [Step 2] | [n] | [%] | [%] | [time] |
| [Step 3] | [n] | [%] | [%] | [time] |
| ... | ... | ... | ... | ... |

**Overall conversion:** [first step to last step %]
**Biggest drop-off:** [step name] — [% lost] — [why this matters]
**Chart:** ![Funnel](charts/funnel.png)

### Funnel by Segment
[If funnel was segmented, show comparison table]

## Drivers Analysis

### Top Drivers of [Key Metric]
| Rank | Variable | Method | Strength | Direction | Plain English |
|------|----------|--------|----------|-----------|--------------|
| 1 | [var] | Correlation + Group comparison | Strong | Positive | "Users who X have Y% higher metric" |
| 2 | [var] | ... | ... | ... | ... |
| ... | ... | ... | ... | ... | ... |

**Chart:** ![Drivers](charts/drivers.png)

## Hypothesis Evaluation
[Only present if {{HYPOTHESIS_DOC}} was provided]

| Hypothesis | Result | Evidence | Confidence |
|-----------|--------|----------|------------|
| H1.1: [claim] | CONFIRMED / REJECTED / INCONCLUSIVE | [key number] | HIGH / MEDIUM / LOW |
| H1.2: [claim] | ... | ... | ... |

### Detailed Evaluation
#### H1.1: [Hypothesis text]
- **Expected if true:** [from hypothesis doc]
- **Observed:** [what the data actually showed]
- **Verdict:** [CONFIRMED / REJECTED / INCONCLUSIVE]
- **Reasoning:** [2-3 sentences explaining why]

## Validation Report
| Check | Result | Detail |
|-------|--------|--------|
| Segment sizes sum to total | PASS / FAIL | [numbers] |
| Funnel monotonically decreasing | PASS / FAIL | [numbers] |
| Conversion rate plausible | PASS / FAIL | [range check] |
| Cross-method consistency | PASS / FAIL | [comparison] |

## Data Limitations
- [Limitation 1: what it affects and how]
- [Limitation 2]

## Recommended Next Steps
1. [Specific action based on findings]
2. [Follow-up analysis to run — which agent, what inputs]
3. [Stakeholder conversation to have]
```

---

## Skills Used (detail)

- `.claude/skills/visualization-patterns/skill.md` — for all chart generation in Step 6, including theme selection, color palettes, annotation standards, and chart type selection logic
- `.claude/skills/triangulation/skill.md` — for cross-referencing and sanity-checking all findings in Step 7, including order-of-magnitude checks and consistency validation
- `.claude/skills/data-quality-check/skill.md` — for the data readiness validation in Step 2, using severity ratings to determine whether analysis can proceed
