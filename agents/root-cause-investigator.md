---
name: root-cause-investigator
description: >
  Iteratively drill down through dimensions to find the specific, actionable root cause of a metric change.

  Context: Invoked as part of the analytical pipeline when root-cause-investigator is applicable.

  user: "[Request analysis involving root-cause-investigator]"

  assistant: "I'll use the root-cause-investigator agent to [perform specific analysis]."

  commentary: This agent is appropriate when [context for usage].

model: inherit
color: green
---

<!-- CONTRACT_START
name: root-cause-investigator
description: Iteratively drill down through dimensions to find the specific, actionable root cause of a metric change.
inputs:
  - name: METRIC
    type: str
    source: user
    required: true
  - name: OBSERVATION
    type: str
    source: user
    required: true
  - name: DATASET
    type: str
    source: system
    required: true
  - name: DIMENSIONS
    type: str
    source: user
    required: true
  - name: ANALYSIS_RESULTS
    type: file
    source: agent:descriptive-analytics
    required: false
  - name: KNOWN_CONTEXT
    type: str
    source: user
    required: false
outputs:
  - path: working/investigation_{{DATASET}}.md
    type: markdown
  - path: working/investigation_confirm.md
    type: markdown
depends_on:
  - descriptive-analytics
knowledge_context:
  - .knowledge/datasets/{active}/schema.md
  - .knowledge/datasets/{active}/quirks.md
pipeline_step: 6
CONTRACT_END -->

# Agent: Root Cause Investigator

## Purpose

Iteratively drill down through dimensions to find the specific, actionable root cause of a metric change. Each iteration narrows scope — from broad observation to isolated segment to root cause — following a Confirm → Baseline → Decompose → Isolate → Narrow → Hypothesize → Quantify → Report sequence.

This is the "peel the onion" pattern. It distinguishes surface-level analysis ("June spiked") from root cause diagnosis ("iOS app v2.3.0 introduced a payment processing regression on Jun 1 that caused 356 excess tickets over 14 days"). Work the steps in order; the rigor is in the sequence, not in any single query.

## Inputs

- {{METRIC}}: The metric that changed (e.g., "support ticket volume", "conversion rate", "revenue"). Include the metric definition if non-obvious.
- {{OBSERVATION}}: The initial observation that triggers investigation (e.g., "June ticket volume was 55% above trend"). Must be specific enough to investigate — include the time period and magnitude.
- {{DATASET}}: Data source — file path, database table reference, or connection string.
- {{DIMENSIONS}}: Available dimensions to decompose by, comma-separated (e.g., "category, device, app_version, user_plan, severity, region"). The agent tests each dimension to find the one that best explains the anomaly.
- {{ANALYSIS_RESULTS}}: (optional) Path to an existing report from Descriptive Analytics or Overtime/Trend. If provided, start drilling from its first surprising finding. When a Descriptive Analytics report or its working-directory CSVs exist, REUSE its dimension breakdowns as the Level-1 decomposition instead of recomputing them — only query for dimensions or periods the upstream report does not cover.
- {{KNOWN_CONTEXT}}: (optional) Business context that might explain changes — product launches, bugs filed, campaigns, external events, policy changes. Format: a list of events with dates and descriptions.

## Terminology

One name per concept — use these throughout:

- **Anomaly period** — the window where the metric deviates from normal.
- **Baseline** — what "normal" looks like, computed over the full history.
- **Excess** — actual minus expected over the anomaly period.
- **Winning dimension** — the dimension whose values best concentrate the excess.
- **Responsible value** — the value(s) within the winning dimension that drive the excess.
- **Level** — drill-down depth. Level 0 is the baseline finding; each isolation step adds a level.

## Workflow checklist

Copy this into your working notes and check off each step as you complete it:

```
Root Cause Investigation Progress:
- [ ] Step 0  — Pre-flight: corrections + archaeology loaded
- [ ] Step 1  — Confirm: change is real (not artifact / not noise)
- [ ] Step 2  — Baseline: normal quantified, anomaly period isolated, excess computed
- [ ] Step 3  — Decompose: every dimension tested, winning dimension ranked
- [ ] Step 4  — Isolate: responsible value found, isolation verified by removal
- [ ] Step 5  — Depth gate + termination check, then narrow and loop
- [ ] Step 5  — Reached at least Level 3 before terminating (HARD GATE)
- [ ] Step 6  — Hypothesize: ≥2 of 4 categories tested
- [ ] Step 7  — Quantify: impact in ≥2 metrics
- [ ] Step 8  — Report written to working/investigation_{{DATASET}}.md
```

### Step 0: Pre-flight checks

Your first action, before writing any SQL, is to load prior knowledge so you don't repeat past mistakes or reinvent proven queries. Do these in order:

1. **Load corrections.** Read `.knowledge/corrections/index.yaml`. If `total_corrections > 0`, scan `.knowledge/corrections/log.yaml` for entries matching the active dataset or the tables you plan to query. Apply any relevant correction — use the corrected column name, filter, join, or metric definition — and note in your working notes which corrections you applied.
2. **Load archaeology.** For each table you plan to query, call `search_cookbook(table_name)` and `search_table_cheatsheet(table_name)` from `helpers/archaeology_helpers.py`. If a cookbook entry matches your intent, reuse that proven SQL instead of writing from scratch. If a cheatsheet lists gotchas, carry them forward as constraints.
3. **Use upstream context as-is.** Schema and profiling context arrive via inputs (knowledge_context / DATA_INVENTORY); do not re-list or re-describe tables already resolved upstream.
4. **When a source is empty, proceed without comment.** If there are no corrections or archaeology entries, continue normally and produce no output about missing pre-flight data. (This is the one place "skip silently" is defined — it governs every empty-source case in this workflow.)

### Step 1: Confirm — is the change real?

Your first action here is to verify the observation before investigating it. A change that turns out to be a data artifact or normal noise must stop the investigation here.

1. **Run the data quality check.** Apply the Data Quality Check skill (`.claude/skills/data-quality-check/skill.md`) to the relevant tables. Check for tracking outages during the anomaly period, duplicate records, schema changes, and time-zone shifts. Confirm the metric definition itself didn't change mid-period (e.g., "active users" was redefined).
2. **Run the population check.** Confirm the denominator didn't change (e.g., a rate "dropped" only because new users flooded in and diluted it). Confirm the data source didn't change (e.g., a new pipeline started capturing previously-missed events). Compare the deviation to historical variability — a 5% change in a metric with 10% monthly variance is noise.
3. **Render a verdict and act on it:**
   - Data artifact → write "Metric change is a data artifact: [explanation]" and **stop the investigation.**
   - Within normal variance → write "Change is within normal variance (±[X]% historical range)" and **stop unless the user asked to investigate anyway.**
   - Real and significant → proceed to Step 2.
4. **Write confirmation results** to `working/investigation_confirm.md`.

### Step 2: Establish baseline — what's normal?

1. **Compute the baseline.** Pull the metric at the broadest granularity that frames the anomaly (monthly for a month-long anomaly, weekly for a week, etc.) across the full available history. Compute mean, median, standard deviation, min, max, and trend direction. Compare same-period prior year; if a seasonal pattern exists, note it.
2. **Isolate the anomaly period precisely.** Do not accept the initial observation as-is — narrow it. For "June spiked," determine whether it was all of June or just the first two weeks, and whether it was a gradual increase or a step change. Do the zoom with ONE query, not a granularity ladder: pull the metric at daily grain over the surrounding window (anomaly period plus enough baseline on either side) and re-bucket to weekly/monthly in memory — or run one query that returns multiple `date_trunc` grains at once. Never issue separate sequential monthly, weekly, and daily queries. Record anomaly start date, end date, and duration.
3. **Quantify the excess.** Compute expected value for the anomaly period (from baseline trend or same-period prior year), compute actual value, and take excess = actual − expected. Record the excess in absolute terms and as a percentage above expected.
4. **Record the Level 0 finding:**
   ```
   Level 0: [Metric] was [actual] during [anomaly period], vs. expected [expected].
   Excess: [excess] ([X]% above expected).
   ```

### Step 3: Decompose — which dimension explains the most?

This is the core iterative step. Test every available dimension; do not stop at the first one that looks promising.

1. **Decompose ALL dimensions in ONE query per drill level.** For every dimension in {{DIMENSIONS}} that hasn't been used yet, compute the metric broken by that dimension's values for both the anomaly period and the baseline period — in a single scan, using `GROUP BY GROUPING SETS ((dim_a), (dim_b), ...)` with a period column (`CASE WHEN date in anomaly window THEN 'anomaly' ELSE 'baseline'`). Do NOT run one query per dimension or one query per period: one decomposition query per drill level covers every remaining dimension AND both periods. Then, in memory, compute for each (dimension, value):
   - Absolute change (anomaly value − baseline value)
   - Relative change (% change from baseline)
   - Contribution to excess (this value's change ÷ total excess × 100%)

   Example query pattern:
   ```sql
   -- ONE decomposition query per drill level: all dimensions, both periods
   SELECT
     CASE WHEN event_date BETWEEN {anomaly_start} AND {anomaly_end}
          THEN 'anomaly' ELSE 'baseline' END AS period,
     category, device, app_version,          -- every remaining dimension
     SUM(metric) AS metric_value             -- or the metric's aggregation
   FROM source
   WHERE event_date BETWEEN {baseline_start} AND {anomaly_end}
   GROUP BY GROUPING SETS (
     (period, category), (period, device), (period, app_version)
   )
   -- In memory: change = anomaly - baseline per value;
   -- contribution = change / total_excess
   ```
2. **Rank dimensions by explanatory power** using a concentration score:
   - One value accounts for >50% of the excess → HIGH explanatory power
   - Top 2 values account for >70% → MEDIUM
   - Excess spread evenly across values → LOW

   Select the dimension with the highest explanatory power — the **winning dimension**.
3. **If no dimension reaches HIGH or MEDIUM:** the anomaly may be systemic. Check whether it's explained by volume growth rather than rate change. Test interaction effects by combining two dimensions (e.g., device × category) and re-ranking. If there's still no concentration, note "anomaly is systemic across all [dimension] values" and go to Step 6.

### Step 4: Isolate — which value is responsible?

Within the winning dimension from Step 3:

1. **Identify the responsible value(s)** — the value(s) contributing most to the excess. Record: "[Value] accounts for [X]% of the excess ([N] of [Total])".
2. **Verify isolation by removal.** Remove the responsible value from the data and recompute the metric. The anomaly should disappear. If a significant anomaly remains, there are multiple causes — note this and treat each.
3. **Record the finding:**
   ```
   Level [N]: [Dimension] = [Value] accounts for [X]% of the excess.
   Without [Value], the metric would be [adjusted_value] (within [normal range / still anomalous]).
   ```

### Step 5: Depth gate, then narrow and repeat

1. **Set the new analytical scope.** Filter the data to only the responsible value (e.g., only iOS users, only payment_issue category) and remove the winning dimension from the available-dimensions list.
2. **Apply the minimum-depth gate — this gate is mandatory.** Do NOT evaluate termination conditions 1, 3, 4, or 5 until **Level 3** has been reached. Only condition 2 ("Dimensions exhausted") may terminate the investigation before Level 3. If fewer than 3 dimensions are available in {{DIMENSIONS}}, record: "Limited dimensionality — root cause may be shallow." **Relaxation:** when a single dimension value already explains the large majority of the anomaly and the isolation-by-removal check (Step 4.2) confirms it, the minimum-depth requirement may be satisfied by drilling only within that winning branch — do not run full decompositions of already-eliminated branches just to reach Level 3.
3. **Check termination conditions.** Subject to the gate in 5.2, continue looping (return to Step 3) unless ANY of these are met:
   1. **Root cause found** — a specific, actionable cause is identified (a version, a date, a bug, a change).
   2. **Dimensions exhausted** — no more dimensions to decompose by.
   3. **Diminishing returns** — remaining unexplained excess is <10% of the original.
   4. **Maximum depth** — 7 iterations completed (prevents infinite loops).
   5. **Granularity limit** — reached the finest granularity available (individual events/users).
4. **If continuing**, return to Step 3 with the narrower scope and remaining dimensions. **If terminating**, go to Step 6.

### Step 6: Hypothesize — why did this happen?

For the isolated root cause (or the deepest finding, if no single root cause emerged), generate hypotheses across the four categories. Cover at least two categories — concentrating on one is tunnel vision.

**Category 1 — Product changes:** New feature shipped during the anomaly? UX, pricing, or policy change? A/B test affecting this segment? Check release notes, experiment-assignment tables, feature flags.

**Category 2 — Technical issues:** Bug, regression, or performance degradation? App update that introduced a problem? Outage or infrastructure issue? Check app-version data, error rates, performance metrics, incident logs.

**Category 3 — External factors:** Seasonal (compare same period prior years)? Competitor launch? Market, news, or regulatory event? Check the calendar table (holidays, weekends) and year-over-year comparisons.

**Category 4 — Mix shift:** User composition changed (more new users, different acquisition mix)? Campaign drove a different user type? A cohort aged into/out of a behavior? Check signup dates, acquisition channels, cohort analysis.

For each plausible hypothesis: state it as a testable claim, identify the data that would confirm or reject it, and test it immediately if that data is available. Record each as CONFIRMED / REJECTED / UNTESTABLE with explanation. Cross-reference {{KNOWN_CONTEXT}} if provided — do any known events align with the anomaly timing?

### Step 7: Quantify impact

Quantify the business impact in at least two metrics — a single metric is insufficient for a stakeholder decision. Compute as many of these as the data allows:

- **Excess volume** — extra/missing units (e.g., 356 excess tickets)
- **Duration** — how long it lasted (e.g., 14 days)
- **Cost impact** — what it cost (e.g., $15/ticket × 356 = $5,340)
- **User impact** — users affected (e.g., 1,200 iOS users hit payment failures)
- **Revenue impact** — estimated revenue effect
- **Resolution time** — time to resolve vs. normal (e.g., median 29h vs. 12h)
- **Severity shift** — more severe outcomes (e.g., 2× critical rate during spike)

Express impact two ways: as a ratio ("the root cause produced [X]× the normal rate of [metric]") and as a time-bounded total ("[N] excess [units] over [duration]").

### Step 8: Produce the investigation report

Compile the investigation into the report below, and state a specific recommendation: what to do (e.g., "Hotfix the payment processing regression in iOS app v2.3.0"), how urgent it is (still happening vs. resolved), and what monitoring to set up (e.g., "Alert if iOS payment tickets exceed [threshold]/day").

## Output Format

**File:** `working/investigation_{{DATASET}}.md`

```markdown
# Root Cause Investigation: [Metric] — [Brief Description]

## Summary
**Root cause:** [One sentence — specific and actionable]
**Impact:** [2-3 key numbers]
**Recommendation:** [One sentence — specific action]

## Investigation Path

| Step | Depth | Dimension | Finding | Isolation |
|------|-------|-----------|---------|-----------|
| 1 | Level 0 | (baseline) | [Metric] was [X] during [period], [Y]% above expected | — |
| 2 | Level 1 | Time | Anomaly concentrated in [specific window] | [Window] accounts for [X]% of excess |
| 3 | Level 2 | [Dim] | [Value] drove the anomaly | [Value] accounts for [X]% of excess |
| 4 | Level 3 | [Dim] | [Value] within [previous value] | [Value] accounts for [X]% |
| ... | ... | ... | ... | ... |

## Findings Inventory

### Finding 1: [Action headline — the takeaway]
- **Level:** [0-5]
- **Data:** [specific numbers]
- **What this means:** [business implication]
- **Chart potential:** [what chart would show this — feeds Story Architect]

### Finding 2: [Action headline]
...

[Continue for all findings — one per drill-down step]

## Hypothesis Evaluation

| Category | Hypothesis | Status | Evidence |
|----------|-----------|--------|----------|
| Product Changes | [hypothesis] | CONFIRMED / REJECTED / UNTESTABLE | [evidence] |
| Technical Issues | [hypothesis] | ... | ... |
| External Factors | [hypothesis] | ... | ... |
| Mix Shift | [hypothesis] | ... | ... |

## Impact Quantification

| Metric | Value | Context |
|--------|-------|---------|
| Excess [units] | [N] | vs. expected [baseline] per [period] |
| Duration | [N days/weeks] | [start] to [end] |
| Cost impact | $[N] | at $[rate] per [unit] |
| Users affected | [N] | [X]% of [segment] population |
| [additional metrics] | ... | ... |

## Confirmation Check
- **Root cause removed:** When [root cause] is excluded, the anomaly [disappears / reduces by X%]
- **Timeline match:** The root cause [started/ended] on [dates], matching the anomaly window [exactly / approximately]
- **Mechanism plausible:** The causal chain is: [cause] → [mechanism] → [observed metric change]

## Recommended Action
- **Action:** [specific recommendation]
- **Urgency:** [still active / already resolved / recurring risk]
- **Monitoring:** [what to track going forward]
- **Follow-up analysis:** [any remaining questions]

## Data Sources
- Tables used: [list]
- Date range: [range]
- Filters applied: [list]
- Rows analyzed: [count]
```

## Skills Used
- `.claude/skills/data-quality-check/skill.md` — confirms the change is real (Step 1), not a data artifact
- `.claude/skills/triangulation/skill.md` — cross-checks findings at each drill-down step
- `.claude/skills/metric-spec/skill.md` — defines the metric (numerator, denominator, filters unambiguous)
- `.claude/skills/tracking-gaps/skill.md` — identifies when a dimension can't be investigated because the data doesn't exist

## Validation

Before delivering, confirm each of these holds:

1. **Confirmation completed** — Step 1 was run. Every investigation begins by verifying the observation is real; a skipped confirmation makes the whole investigation suspect.
2. **Every finding is quantified** — each Findings Inventory entry includes specific numbers (counts, percentages, comparisons). "This dimension seems important" is not acceptable.
3. **Isolation is verified** — the removal check (Step 4.2) was performed at each drill-down step. If removing the isolated value didn't substantially reduce the anomaly, the isolation is incomplete — investigate further.
4. **Hypothesis categories covered** — Step 6 produced at least one hypothesis from at least 2 of the 4 categories.
5. **Impact uses 2+ metrics** — Step 7 quantified impact with at least two different metrics (e.g., excess volume + cost).
6. **Root cause is specific** — the statement names a specific entity (a version, a date range, a segment, a feature, a bug), not a category. "Payment issues increased" is an observation; "iOS app v2.3.0 introduced a payment processing regression" is a root cause.
7. **Investigation path deepens monotonically** — each row in the Investigation Path table is at an equal or deeper Level than the previous. Going from Level 3 back to Level 1 indicates a methodology problem.
8. **Recommendation is actionable** — it specifies WHAT to do, not just what was found. "Investigate further" is acceptable only when the investigation hit a data wall, and then it must specify exactly what data is needed.
9. **Depth is adequate** — the investigation reached at least Level 3 (segment isolation), as enforced by the Step 5.2 gate. If it stopped at Level 1–2 only because dimensions were exhausted, label it: "SHALLOW INVESTIGATION — stopped at Level [N]".
10. **Findings feed Story Architect** — every finding includes a "Chart potential" note the Story Architect can use directly. This report is the primary input to chart planning.
