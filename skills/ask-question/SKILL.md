---
name: ask-question
description: "Use this skill for any data question, analytical request, or metric inquiry — it is the entry point for data work. Use it whenever a user asks about data, metrics, trends, churn, revenue, conversion, retention, segments, cohorts, funnels, KPIs, or any quantitative question — even casual ones like 'how are we doing' or 'what happened last month.' Also use when the user says 'analyze', 'compare', 'why did X change', 'show me', 'what's driving', 'break down', or asks for any chart or visualization. If the user has a connected dataset and asks anything about their data, use this skill to answer it rather than answering directly."
---

# Ask Question — AI Analyst

Follow these steps in order. Do not freestyle.

## Model conventions (read first)

This skill is version-aware. Before starting, apply `skills/MODEL_CONVENTIONS.md` for
the model you are. The points that bite most here:
- **Query, don't infer** (conventions §B, §E): never report a number from memory — pull
  it. When a table is unfamiliar, resolve it from the catalog first; `sample_table` is a
  last resort gated by Step 3's narrow exception, not a default.
- **Literal scope** (§A): a step that says "validate segments" means *every* segment, as
  written — don't narrow to the largest on your own, and don't broaden a single-item
  step either.
- **Let length follow the level** (§C): an L1 answer is just the data (a one-line value or
  the rows/handle, no commentary); an L4 finding is as long as it needs. Don't pad or
  compress to hit a feel.
- **Effort** (§D): L3+ analysis wants `high`/`xhigh`. If running at `low`/`medium`, say
  so once and proceed.

## Hard Rules

**REFUSE immediately if the user asks for PII** (emails, phone numbers, names, addresses, user lists with identifiers). Never SELECT PII columns. Never explain why it's blocked. Respond: "I can't provide personally identifiable information. I can analyze aggregated patterns using case_id/user_id instead."

## Step 0: Load Context

Resolve schema and analytical context from the catalog, never by live Athena discovery.

**Connection gate — check before answering.** You need both sides reachable; if either has
nothing, stop and tell the user rather than guessing:
- **Catalog** (for schema/discovery), first that responds:
  `OpenMetadata` → `knowledge index (lookup_index/get_page)` → `.knowledge/ files`.
  "Responds" = a probe returns a real result, not an error/empty/disabled signal.
- **Query engine** (for execution): Athena or Superset — at least one reachable.

### Finding the table you need

Your first action for any table you don't already have by exact name is **catalog search** —
not `list_athena_tables`. Do these in order:

1. **Search the catalog.** Run `search_metadata(query, entityType: "table")` (keyword — the
   reliable workhorse). Also run `semantic_search(query, entityType: "table")` (meaning-based)
   *if it works*; the instant it returns a disabled/permission error or empty-on-an-obvious-match,
   drop it for the rest of the session and rely on `search_metadata` alone — never re-call a
   semantic_search that already failed.
2. **Compare candidates — don't take the first hit.** Pool the top results, then call
   `get_entity_details(entityType, fqn)` on the top 2–3 and check their actual columns against
   what the question needs (e.g. "RTO by pincode" → does it have `destination_pincode` and
   per-stage RTO timestamps, or is it just a generic order view?). Use the exact
   `fullyQualifiedName` from a result; never hand-build the fqn.
3. **Pick the best-fit table.** Prefer purpose-built marts and source tables (often Iceberg)
   over generic `_vw` views. The first keyword hit is usually a broad view, not the right one.

Already have the exact table name? One `search_metadata(name, entityType: "table")` for its
`fullyQualifiedName` is enough.

**If OpenMetadata is unavailable**, use the knowledge index: `lookup_index(terms, dataset)` to
map the question's terms to table names, then `get_page("schema.md", dataset, tables=[...])`
for only those tables' sections. Never load `schema.md` wholesale (~140 tables); a full-file
fetch is the last resort when no table resolves at all. If the index is down too, fall to
`.knowledge/` files (active.yaml → schema.md → quirks.md → profile.md), same principle: read
cached schema, read only the sections you need.

This whole sequence replaces `describe_athena_table`. Live Athena discovery
(`list_athena_tables`, `describe_athena_table`, `sample_table`, `information_schema` via
`query_athena`) is a last resort only after every catalog tier has failed — see Step 3's one
narrow exception. If you do fall back to `describe_athena_table`, describe every table you
need in ONE call (`tables=[...]`) — never one call per table.

**Resolve once per session.** Once a table's schema is resolved (whatever the tier), reuse
it for every follow-up question this session. Do not re-run the catalog search — or any
discovery — for a table you already resolved.

### Loading analytical intelligence

Always via the knowledge index (OpenMetadata has no equivalent):
1. `lookup_index(terms, dataset)` with key terms (metric names, business terms like "O2",
   "retention", "channel"). Apply the returned mandatory pages (PII, partitions) silently,
   every time.
2. `get_page(file, dataset, section)` for the quirk / metric / golden-query sections you need.

### Query results are file-first

For a real *data-answer* query, `query_athena(sql, out_path="")` writes the full result to a
CSV and returns a handle (`file_path`, `row_count`, `columns`, 5-row `preview`), additionally
inlining the rows only when the result is ≤ 50. The 50-row rule — not you — decides whether
bulk data enters context. You control two things:
- **`out_path` is only for a result the user explicitly asked to download.** Every other query
  — probes, validation counts, intermediates — leaves it empty so the CSV lands in the
  self-cleaning session cache. Never write an `outputs/` deliverable for a throwaway.
- **Aggregated vs raw SQL** (see Step 3).

Metadata queries don't apply here because they shouldn't be `query_athena` calls at all (Step 3).

## Step 1: Classify (L1-L5)

| Level | Pattern | Response |
|-------|---------|----------|
| L1 | Data retrieval — "give me / how many / list X" | Return the data (a value OR a set of rows) with minimal context. No interpretation. |
| L2 | Analysis *on* that data — "analyze / interpret / break down / chart this" | Query + interpret: chart and/or 2-3 sentences of what it means |
| L3 | Why/analysis | 2-4 charts, validation, narrative |
| L4 | Investigation | Full analysis + sizing |
| L5 | Presentation | Hand off to run-analysis |

**L1 vs L2 is retrieval vs. interpretation, not number vs. breakdown.** A plain request for
data — one value, a list, or even a grouped/breakdown *table* — is **L1**: return the data,
add minimal context (units, time window), and stop. Don't interpret, chart, or explain "why"
unless the user asked. It becomes **L2** only when the user wants the data *made sense of* —
analyze, interpret, compare-and-explain, or "show me a chart of" it.

L1-L2: Execute immediately. L3+: State plan briefly, then proceed.

**Pre-flight clarification gate (ask before running, narrowly).** Before you query, check
whether the request hinges on a *definition you'd have to assume*. Ask the user a short
question FIRST — instead of assuming and disclosing later — only when BOTH hold:
1. A term in the request maps to **more than one plausible** metric / entity / time-window
   definition that changes the answer, AND
2. The output is an **action artifact** — a downloaded list/CSV, an audience to act on, or a
   number a decision rides on.

When both hold, ask one tight question naming the alternatives, then run. Examples of the
*kind* of ambiguity that triggers it (generic — map to whatever the actual request says):
- An event term that could resolve to one of several timestamped events ("which event marks
  '<X>' — event A's date or event B's date?").
- A status/eligibility term with an "ever" vs "currently/yet" reading ("'<unconverted>' =
  never did Y at all, or hasn't done Y *yet* within a window?").
- **User-supplied input that didn't fully match** (e.g. some IDs/names in a pasted list have
  no data): surface the non-matches and ask whether to drop them or correct them — don't
  silently drop.

Otherwise (obvious mapping, or L1/L2 lookup): proceed and disclose the choice in the receipt
(Step 6.5). Don't interrogate the user on unambiguous or trivial asks — the gate is for
ambiguity that materially moves *who/what is in the answer*, not a blanket confirm step.

## Step 2: Data Quality (L2+)

Check: nulls >20% = BLOCKER, duplicates, date range coverage, sanity (rates 0-100%, positive revenue).

## Step 3: Query

**Silent guardrails:** No PII in SELECT. Always filter on partition column. Use mart tables over raw. Check UTC vs IST.

**Query strategy:**
- **Get structure from the catalog, not from Athena.** Columns, types, table existence — you
  already resolved these in Step 0 (OpenMetadata `get_entity_details`, the knowledge index, or
  `get_page("schema.md", ...)`). Write the query directly from that. Don't run
  `information_schema` / `SHOW` / `DESCRIBE` through `query_athena`, and don't `sample_table`
  "just to be safe" — both are live billable round-trips that pull data back into context for
  something the catalog already answers for free. This re-discovery on every question is the
  main source of slowness and token cost.
- **The narrow exception (when Athena discovery IS allowed):** only when Step 0 returned
  *nothing* for a table you must use (an `unmatched` term in `lookup_index`), OR you genuinely
  cannot infer a column's value format (e.g. an enum/status code) and the query depends on it.
  Then prefer `describe_athena_table` (cheap, `information_schema`, no scan) over `sample_table`,
  and cap `sample_table` at `limit=5`. Record what you learned (Step 8 / feedback-capture) so
  the index covers it next time.
- **Prefer aggregated queries:** Use GROUP BY with COUNT, SUM, AVG for analysis. Use raw row selects only when you specifically need individual records (e.g., inspecting outliers, validating edge cases).
- **One query, not a chain.** Related metrics belong in one SELECT; related breakdowns belong
  in one query. Before running a second query, ask: could the previous query have returned
  this too? Standard patterns:
  - Several metrics on the same table/window → one SELECT with multiple aggregates.
  - The same metric across several dimensions → `GROUP BY GROUPING SETS ((dim_a), (dim_b),
    (dim_c), ())` — one scan returns every breakdown *plus* the grand-total row, so the
    "segments sum to total" check comes free.
  - Different filters/populations → `COUNT(*) FILTER (WHERE ...)` or CASE-inside-aggregate,
    not one query per filter.
  - Period comparisons (WoW/MoM, anomaly vs baseline) → one query spanning both windows with
    a period column, not one query per window.
- **Approximate when exact is overkill.** On large scans prefer `approx_distinct()` and
  `approx_percentile()` over exact `COUNT(DISTINCT)` / percentile sorts unless the user
  needs exact figures.
- **Don't add LIMIT to aggregated or "all of X" queries.** A LIMIT silently truncates the
  answer — you lose categories/rows past the cap and report a wrong total. The file-first
  writer already keeps rows out of context (it streams the full result to a CSV and inlines
  only ≤ 50), so LIMIT is not needed for that. Bound *scan cost* with the partition filter,
  not LIMIT. Use LIMIT only to deliberately preview a handful of raw rows.
- **Deep dive with combined queries:** Drill into dimensions with aggregation queries rather
  than one large raw data pull — and combine the drill-downs per the "one query, not a chain"
  patterns above. A follow-up query is justified only when its shape genuinely depends on the
  previous result (e.g. drilling into the winning segment).

**Result routing (file-first — keep rows out of context):**

| User intent | What you do | What enters context |
|---|---|---|
| "download / export / give me the data for X" | Write an **aggregated** CSV (GROUP BY summary) by default. Set `out_path` to the session's chosen deliverable dir. | handle only |
| Download that **genuinely needs raw rows** (outlier/id list) | **Ask first:** "This needs individual rows rather than a summary — export raw rows (no personal data)?" Only on **yes**, run a raw query. PII is blocked/redacted by the tool regardless. | handle only |
| Bulk/raw pull, no deliverable intent | `query_athena(sql)` with empty `out_path` → self-cleaning temp file. | handle only |
| Explicit analysis ("why did X drop") | Aggregated query via `query_athena(sql)`. | inline rows iff ≤ 50 |

**Serve follow-ups from saved results — do not re-query.** Every `query_athena` call already
wrote a CSV and returned its `file_path`. Keep a short note of `{file_path, sql, row_count,
columns}` for each query this turn. This covers more than downloads:
- "download that" → **copy the existing CSV** to the deliverable dir (`cp`/`mv`, or a bounded
  pandas pass-through) and report the path — do NOT run `query_athena` again.
- A follow-up that is a **reshape of data you already have** (re-sort, filter, per-segment
  share, a chart of it) → compute it from the saved CSV with bounded pandas, not a new query.
- Only run a new query when the answer needs data the saved results don't contain (a new
  column, finer grain, a different window).
The server also caches results by SQL hash for the session: a repeated identical query
returns instantly with `"cached": true` and does not hit Athena. Treat that as a safety net,
not a license to re-issue queries; pass `refresh=true` only when the user explicitly needs
fresher data.

**Reading a written CSV back is bounded only.** If you must peek beyond the 5-row preview,
read `pd.read_csv(path, nrows=N)` or iterate with `chunksize=`. Never `pd.read_csv(path)` on
the whole file.

**Deliverable location — ask once per session.** The first time you produce a deliverable,
ask: "Where should I save the file? (default `./ai-analyst-workspace/data/`)" and reuse that
answer for the rest of the session. Do NOT persist it across sessions.

**Cowork caveat:** a deliverable CSV lives in the ephemeral sandbox. When you produce one,
tell the user its path and that they should download it before the session ends.

**L1 (data retrieval — no interpretation):** Return the requested data with minimal context.
- A single value → the number with its units/time window ("12,450 users in March").
- A set of rows or a breakdown table → return the data (file-first rules apply: handle for
  large pulls, inline if ≤ 50). Add at most a one-line framing (what it is, time window).
- Do NOT add a chart, a "why," or a narrative. If the data invites obvious analysis, you may
  offer it as a follow-up ("Want me to analyze this?") — but don't do it unasked.

**L2 (analysis on the data):** The user wants the data *made sense of* — interpreted, compared,
or charted. Query, then give a chart and/or 2-3 sentences of what it means. End with "Want to
break this down by [dimension]?"

**L3-L4 (analytical thinking — think like the business):** Copy this checklist and track it:

```
Analysis Progress:
- [ ] Observe — quantify what changed
- [ ] Decompose — break into business components
- [ ] Trace upstream — follow the funnel to the cause
- [ ] Validate — segments sum, cross-check, plausible
- [ ] Size — how big is the driver
```

1. **Observe** — what changed? Query the metric over time or across segments.
2. **Decompose** — break it into business components. E.g., if orders dropped:
   - Which order type? O1 (new) vs O2+ (repeat)
   - If O1 dropped → check form submissions, lead volume, booking rates, ad spend
   - If O2+ dropped → check retention, delivery issues, RTO rates, CSAT
   - Which channels? organic vs paid, self-service vs agent-booked
   - Which regions? City tier, specific states
3. **Trace upstream** — follow the funnel backward from the symptom to the cause. Revenue drop → order volume? AOV? Cancellations? Order volume drop → fewer leads? Lower conversion? Churn?
4. **Validate** — do segments sum to total? Can you calculate the same number a different way? Is the finding plausible?
5. **Size the impact** — how big is this? "Maharashtra alone accounts for 40% of the drop"

**L5:** Hand off to `run-analysis` skill for full pipeline + deck.

## Step 4: Charts (L2+)

**Mode:** L2 → `explore_style()` (multi-color). L3+ → `swd_style()` (gray + highlight, takeaway titles). (L1 is data retrieval — no chart unless the user explicitly asked for one.)

**Pick the right type:** bar, line, histogram, box_plot, cohort_curves, retention_heatmap, funnel_waterfall, waterfall_chart, pareto_chart, donut_chart, treemap, slope_chart, diverging_bar, survival_curve, sparkline_grid, bump_chart, marimekko, ridge_plot, bullet_chart, geo_bar_chart, big_number_layout. All in `helpers/chart_helpers.py`.

**Presentation rules:** Gray everything, color only the story. Title = takeaway. Direct labels, no legends. No rotated text.

**Multi-chart narrative (L3+):** Structure as Context (baseline) → Tension (the problem/gap) → Resolution (the driver/recommendation).

## Step 5: Validate (L3+)

Build validation INTO the main query, not as extra queries afterwards: a `GROUPING SETS`
query already returns the grand-total row for the segments-sum check, and the guardrail
counter-metric is one more aggregate column in the same SELECT. Run a separate validation
query only for a genuinely independent cross-check (different table or method).

- Segments sum to total (±1%)
- Rates 0-100%, plausible ranges
- Simpson's Paradox check
- **Metric guardrail:** pair success metric with counter-metric (retention↔revenue/order, conversion↔LTV, volume↔CAC)

## Step 6: Present

L1: The data itself — a value with units/time window, or the rows/handle — plus at most a one-line framing. No interpretation. L2: Chart and/or 2-3 sentences interpreting it + "want to drill into [dimension]?" L3-L4: Headline finding → charts (Context→Tension→Resolution) → key numbers → confidence note (High/Medium/Low) → 2-3 next steps.

## Step 6.5: Receipt (MANDATORY, all levels)

Every answer ends with a **receipt** — the evidence trail that turns a number into a *verified answer*. Most wrong data answers are not SQL syntax errors; they are meaning errors (wrong metric definition, wrong entity, wrong time window) delivered with false confidence. The receipt forces those choices to be explicit and auditable.

Use `helpers/receipt.py` to render a consistent block:

```python
from helpers.receipt import Receipt, MetricRef
print(Receipt(
    interpreted_question="<restate what you actually answered>",
    metric=MetricRef(name="revenue", resolved_as="net_revenue (gross − refunds)", source="metrics.yaml#revenue"),
    time_window="Mar 2026 vs Feb 2026, calendar months, IST",
    tables=["analytics.orders"],
    filters=["activity_date BETWEEN 2026-02-01 AND 2026-03-31"],
    sql="<the SQL you ran>",
    assumptions=["<every non-obvious choice you made>"],
    caveats=["<anything that limits the answer>"],
    governance=["PII columns blocked at query layer"],   # note redaction notice if the query returned one
    data_through="<freshness, if known>",
).render(confidence_badge="A (92/100)"))   # from confidence_scoring.format_confidence_badge, or omit
```

**Scale the receipt to the level:**
- **L1:** Minimal — interpreted question, metric (with its `resolved_as` definition), and the SQL. Render collapsed; one line of substance is fine.
- **L2:** Add tables, filters, and time window.
- **L3–L4:** Full receipt — assumptions, caveats, governance, freshness, and the confidence badge (reuse the badge from Step 5 validation, don't invent a new grade).

**Non-negotiables, even for "simple" questions:**
- If the user's term mapped to more than one possible metric/entity/time definition, the receipt MUST state which one you chose (`resolved_as`) and ideally offer the alternative in your follow-ups.
- The executed SQL always goes in the receipt. No answer ships without its query.
- If the Athena result included a `notice`/`redacted_columns`, surface that under governance.

## Step 7: Follow-ups

Offer 2-3 specific next actions tied to findings.

## Step 8: Compact Context (L3+ only)

After completing an L3+ analysis, summarize what was done so the conversation stays efficient for the next question:

1. **Save findings** — write a brief summary to the working directory: key metric, finding, charts produced, SQL used
2. **Compact** — tell the user: "Analysis complete. I've saved the findings. Context has been compacted — ready for your next question."
3. **Clean up intermediates** — delete the session's `.query-cache/<session_id>/` directory
   (the self-cleaning query files). Deliverables the user asked to keep (written to the chosen
   `out_path`) are NOT touched.

This prevents deep analyses from eating the token budget for subsequent questions in the same session.
