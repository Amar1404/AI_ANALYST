# Checkpoint Logic

Checkpoints are gates between pipeline phases. They verify quality before advancing. Checkpoints fire based on which agents just completed, not on hardcoded step numbers.

---

## Checkpoint 1 — Frame Verification (after hypothesis completes)

**Type:** B (user-facing). **Plans:** full_presentation, deep_dive.

Self-checks:
- [ ] Business question is specific and decision-oriented
- [ ] Analysis design spec names specific tables/columns
- [ ] At least 3 hypotheses span multiple cause categories
- [ ] Agent files were read from disk

Present summary:
> "Questions framed. Design spec ready.
> - Business question: [summary]
> - Tables: [list]
> - Hypotheses: [count] across [N] categories
>
> Proceed to analysis?"

**Skip if:** User said "just do it" or provided all params.

---

## Checkpoint 2 — Analysis Verification (after opportunity-sizer completes)

**Type:** A (automated). **Plans:** full_presentation, deep_dive.

Verify:
- [ ] Source tie-out passed
- [ ] Root cause is specific and actionable
- [ ] Findings are validated (SQL spot-checked)
- [ ] Data quality issues documented
- [ ] Opportunity sizing includes sensitivity analysis

If root cause is vague, re-run root-cause-investigator.

---

## Checkpoint 2.5 — Storyboard Review (after narrative-coherence-reviewer completes)

**Type:** B (user-facing). **Plans:** full_presentation only (L5).

Present storyboard summary with beat headlines and arc structure.

**Skip if:** User said "just do it" or reviewer flagged issues (go to revision).

---

## Checkpoint 3 — Story & Charts (after visual-design-critic chart-level completes)

**Type:** A (automated). **Plans:** full_presentation, quick_chart.

Verify: R2 (title collision scan), R3 (backgrounds), R5 (banned words), R7 (chart figsize), story arc, chart fan-out results. Print title collision table.

### Chart Fan-Out Protocol

When chart-maker becomes READY (after narrative-coherence-reviewer):

1. **Parse storyboard:** Read `<workspace>/working/storyboard_{{DATASET}}.md`. For each beat, traverse the `slides` array and collect slides with `type: chart-full`, `chart-left`, or `chart-right`. Each chart-type slide references its parent beat's chart spec.
2. **Build chart_specs list:** `[{beat_number, slide_index, headline, chart_spec, output_name}, ...]`
3. **Sequential execution:** Invoke Chart Maker once per chart spec, one at a time (no parallelism). For each invocation:
   - Pass the specific `chart_spec`, `output_name`, and shared pipeline context
   - Charts are generated at standard (10, 6) figsize (R7)
   - Track: `chart_results[beat] = {status, files, error}`
   - On failure: log error, mark chart as `failed`, continue to next chart
4. **Batch review:** After ALL charts are generated, invoke Visual Design Critic once with the full set of chart files for batch review. Pass all `chart_results` output paths.
5. **Verify:** Check all output files exist (base PNG + SVG per chart). Report missing/failed charts at Checkpoint 3 for retry.

### Fix Loop (chart-maker-fixes)

After the visual-design-critic completes, read `<workspace>/working/design_review_{{DATASET}}.md` and extract the verdict:

1. **APPROVED** → Mark `chart-maker-fixes` as `skipped` in pipeline_state.json. Proceed to storytelling tier.

2. **APPROVED WITH FIXES** → Extract the fix report section from the design review. Set `chart-maker-fixes` to `ready`. Pass the fix report as `FIX_REPORT` input. The chart-maker-fixes agent (same file as chart-maker, with `FIX_REPORT` provided) re-generates only the charts listed in the fix report. After completion, re-run visual-design-critic as a quick re-check. If still `APPROVED WITH FIXES` after the re-check, proceed anyway (one fix loop iteration max).

3. **NEEDS REVISION** → HALT the pipeline with message: `"Design critic returned NEEDS REVISION. Manual intervention required. Review: <workspace>/working/design_review_{{DATASET}}.md"`. Do NOT proceed to storytelling.

---

## Checkpoint 4 — Final Deck (after deck-creator and visual-design-critic slide-level complete)

**Type:** A (automated). **Plans:** full_presentation, refresh_deck.

Verify: R1 (theme), R2 (titles), R3 (backgrounds), R4 (recommendation order), R5 (banned words), R6 (breathing slides), R7 (chart figsize), R10 (HTML components), R11 (export), deck size 8-22 slides, speaker notes present.

### Marp Lint Gate (R10)

Run `helpers/marp_linter.py` against the deck output. Print the lint report.

```python
from helpers.marp_linter import lint_deck, format_report

result = lint_deck("outputs/deck_{{DATASET_NAME}}_{{DATE}}.marp.md")
print(format_report(result))

if not result["summary"]["pass"]:
    # FAIL checkpoint — report errors
    print(f"CHECKPOINT 4 FAIL: {result['summary']['errors']} lint errors")
    for issue in result["issues"]:
        if issue["severity"] == "ERROR":
            print(f"  - {issue['code']}: {issue['message']}")
```

Lint errors that FAIL Checkpoint 4:
- `FM-*`: Missing or wrong frontmatter keys
- `COMP-MIN`: Fewer than 3 HTML component types
- `CLASS-INVALID`: Invalid slide class (e.g., `breathing`)
- `R2-COLLISION`: Chart title identical to slide headline

Lint warnings that are reported but do NOT fail the checkpoint:
- `COMP-PLAIN`: Plain-markdown content slides
- `SLIDES-LOW` / `SLIDES-HIGH`: Slide count outside 8-22
- `R6-PACING`: Consecutive content slides without pacing break
- `IMG-BARE-MD`: Bare markdown image (`![](...)`) not wrapped in `.chart-container`

---

## Post-Checkpoint 4: Deck Export (R11)

After Checkpoint 4 passes, export the deck to PDF and HTML:

```python
from helpers.marp_export import export_both, check_ready

deck_path = "outputs/deck_{{DATASET_NAME}}_{{DATE}}.marp.md"
theme = pipeline_args.get("theme", "analytics")

# Check if Marp CLI is available
status = check_ready()
if not status["marp_cli"]:
    print("WARNING: Marp CLI not available. Skipping PDF/HTML export.")
    print("  Install: npm install -g @marp-team/marp-cli")
    # Record skip in pipeline_state.json
    pipeline_state["export"] = {"status": "skipped", "reason": "marp_cli_unavailable"}
else:
    try:
        exports = export_both(deck_path, theme)
        print(f"PDF:  {exports['pdf']}")
        print(f"HTML: {exports['html']}")
        # Record in pipeline_state.json
        pipeline_state["export"] = {
            "status": "completed",
            "pdf": str(exports["pdf"]),
            "html": str(exports["html"]),
        }
    except Exception as e:
        print(f"WARNING: Export failed: {e}")
        pipeline_state["export"] = {"status": "failed", "error": str(e)}
```

Export is non-blocking — failures are logged as warnings, not pipeline halts. The Marp
markdown deck is always the primary deliverable; PDF/HTML are convenience outputs.

---

## Post-Pipeline: Finalize Run Directory

After export and before metric capture, consolidate the run directory:

1. **Copy artifacts** from `<workspace>/working/` and `<workspace>/outputs/` into `{RUN_DIR}/working/` and `{RUN_DIR}/outputs/`
2. **Update pipeline_state.json** in `{RUN_DIR}/`: set `status: completed`, record `completed_at`
3. **Verify symlink:** Confirm `<workspace>/working/latest` points to this run directory

The run directory is now a self-contained snapshot of the entire analysis.

---

## Post-Pipeline: Metric Capture & Archive

After all checkpoints pass, before reporting completion:

**Metric capture hook:**
1. Scan analysis report for metric references
2. Check `<workspace>/.knowledge/datasets/{active}/metrics/index.yaml` for each metric
3. Note new metrics: "New metric detected: {name}. Use `/metrics` to define it."
4. Update `last_used` on existing entries

**Archive hook:**
1. Apply archive-analysis skill
2. Capture: title, question, level, key findings, metrics used, agents invoked, output files
3. Write to `<workspace>/.knowledge/analyses/index.yaml`

---

## Common Failure Modes

| Failure | Root Cause | Prevention Rule | When Caught |
|---------|-----------|----------------|-------------|
| Dark theme on standard analysis | Deck Creator defaulted to dark | R1 | Checkpoint 4 |
| Chart title = slide headline | Story Architect wrote same text | R2 | Checkpoint 3, 4 |
| Chart on pure white background | `swd_style()` not called | R3 | Checkpoint 3 |
| Recommendations in random order | Listed by topic not confidence | R4 | Checkpoint 4 |
| Sensational language | Dramatic words in headlines | R5 | Checkpoint 3, 4 |
| Wall of charts, no pacing | No breathing slides | R6 | Checkpoint 4 |
| Tiny chart text on slides | Chart rendered at small figsize | R7 | Checkpoint 3 |
| Agent guidance not followed | Didn't read agent file from disk | R8 | All checkpoints |
| Analysis on corrupted data | Data loading error | R9 | Checkpoint 2 |
| Cycle in registry | New agent added with circular dep | Cycle detection | Pre-flight |
| Deadlock in DAG | Tier has no READY agents | Deadlock detection | Phase 2 loop |
| Runaway failures | Multiple agents failing | Circuit breaker | Phase 2 loop |
| No HTML components | Deck uses only plain markdown | R10 | Checkpoint 4 (lint) |
| Missing html:true | Components render as raw HTML text | R10 | Checkpoint 4 (lint) |
| Export fails | Marp CLI not installed or crashes | R11 | Post-Checkpoint 4 |
| Stale pipeline state | Previous run crashed mid-execution | Step 0 cleanup | Pre-flight |
| Chart text overlap | Labels collide at rendered size | R7 | Checkpoint 3 + chart-maker HALT |
| Chart overflows slide | Bare `![](...)` image not in `.chart-container` | R10 | Checkpoint 4 (lint: IMG-BARE-MD) |
