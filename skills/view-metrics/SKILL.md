---
name: view-metrics
description: "Triggers on \"metrics\", \"KPIs\", \"metric dictionary\", \"/metrics\"."
triggers:
  - /metrics
  - show me the metrics
  - what metrics do we track
  - metric dictionary
  - KPI
---

# Skill: View Metrics

## Purpose
Browse, search, and display metric definitions from the active dataset's
metric dictionary. Provides quick access to how metrics are defined, computed,
and validated.

## When to Use
- User says `/metrics` or "show me the metrics" or "what metrics do we track?"
- During analysis, to confirm a metric's definition before computing it
- When writing a metric spec, to check for existing definitions

## Invocation
`/metrics` — list all metrics for the active dataset
`/metrics {id}` — show full spec for a specific metric
`/metrics category={cat}` — filter by category (e.g., monetization)
`/metrics search={term}` — search metric names and descriptions

## Instructions

### Step 1: Load Metric Dictionary
1. Read `<workspace>/.knowledge/active.yaml` to identify the active dataset.
2. Read `<workspace>/.knowledge/datasets/{active}/metrics/index.yaml` for the metric list.
3. If no metrics directory exists: "No metric dictionary for this dataset. Use the metric-spec skill to define metrics."

### Step 2: Execute Command

**List all (`/metrics`):**
- Display as a table: id, name, category, direction, validation_status
- Group by category
- Show total count

Example output:
```
Metrics (10 total)

MONETIZATION:
  revenue          Revenue            ↑ Target    ✓ Valid
  mrr              Monthly Recurring   ↑ Target    ✓ Valid
  aov              Avg Order Value     ↑ Target    ⚠ Stale

ENGAGEMENT:
  dau              Daily Active Users  ↑ Target    ✓ Valid
  retention_d7     7-Day Retention     ↑ Target    ? Undefined

...

Use `/metrics {id}` to see full definition.
```

**Show specific (`/metrics {id}`):**
- Read `<workspace>/.knowledge/datasets/{active}/metrics/{id}.yaml`
- Display: name, category, owner, full definition (formula, unit, direction, granularity), source tables, dimensions, guardrails, typical range, validation status

Example output:
```
Metric: revenue

Category:     Monetization
Owner:        Finance Team
Direction:    ↑ Higher is better
Unit:         USD
Granularity:  Daily, Monthly

Formula:
  SELECT DATE(order_date), SUM(amount)
  FROM orders
  WHERE status = 'completed'
  GROUP BY 1

Source tables: orders
Dimensions:    product_category, region, customer_segment

Guardrails:
  - Daily min: $100K (warn if below)
  - Daily max: $5M (alert if above)
  - Typical range: $300K - $2M

Validation:
  Last validated: 2026-03-10
  Status: ✓ Valid
  Notes: Matches finance reporting

Related metrics: mrr, aov, gross_margin
```

**Filter by category (`/metrics category=monetization`):**
- Filter index by category field
- Display filtered table

**Search (`/metrics search=revenue`):**
- Search metric names and descriptions (case-insensitive substring)
- Display matching metrics

Example:
```
/metrics search=revenue

Matches (3):

1. revenue           Monetization    ✓ Valid
2. gross_revenue     Monetization    ✓ Valid
3. net_revenue       Monetization    ✓ Valid
```

### Step 3: Contextual Suggestions
After displaying metrics, suggest relevant actions:
- "Want to validate {metric} against the current data? Use deeper profiling."
- "Need to define a new metric? Use the metric-spec skill."
- "Want to see how {metric} trends over time? Ask me to analyze it."

## Edge Cases
- **No active dataset:** Prompt to connect one
- **Empty metric dictionary:** Suggest using metric-spec skill
- **Metric referenced but not in dictionary:** Offer to create it
- **Stale validation:** Flag metrics where last_validated is >30 days ago

## Metric Dictionary Schema

Each metric in `<workspace>/.knowledge/datasets/{active}/metrics/{id}.yaml` should contain:

```yaml
id: revenue
name: Revenue
category: Monetization
owner: Finance Team
direction: up  # "up" or "down"
unit: USD
granularity:
  - daily
  - monthly

formula: |
  SELECT DATE(order_date), SUM(amount)
  FROM orders
  WHERE status = 'completed'
  GROUP BY 1

source_tables:
  - orders

dimensions:
  - product_category
  - region
  - customer_segment

guardrails:
  min_daily: 100000
  max_daily: 5000000
  typical_range: [300000, 2000000]

validation:
  last_validated: "2026-03-10T00:00:00Z"
  status: valid  # "valid", "stale", "undefined"
  notes: "Matches finance reporting"

related_metrics:
  - mrr
  - aov
  - gross_margin
```

## Anti-Patterns

1. **Never show undefined/stale metrics without warning.** Always flag validation status.
2. **Never assume the user knows what a metric is.** Always show the full formula if asked.
3. **Never suggest metrics without context.** Always relate suggestions to the question.
