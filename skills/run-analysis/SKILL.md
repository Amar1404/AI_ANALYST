---
name: run-analysis
description: "Use this skill for full end-to-end analytical pipelines, presentation decks, or deep investigations. Triggers when the user says 'run analysis', 'full pipeline', 'end-to-end', 'build me a deck', 'give me the full picture', 'comprehensive analysis', or any request for a polished slide deck with charts. Also use when ask-question classifies a question as L5. This skill orchestrates 18 specialized agents in a DAG pipeline — from framing through charting to a finished Marp deck. Use it to build presentations or run multi-agent analysis workflows rather than assembling them by hand."
---

# Run Analysis — Full Pipeline Orchestrator

You are orchestrating a complete analytical pipeline. This is the heavyweight skill — it produces validated findings, SWD-quality charts, and a polished slide deck.

## Model conventions (read first)

This skill is version-aware — apply `skills/MODEL_CONVENTIONS.md` for the model you are.
The two that matter most for orchestration:
- **Subagent fan-out is explicit** (§B): newer models spawn *fewer* subagents by default.
  The DAG's correctness depends on the declared agents actually running as separate
  subagents. When a tier lists multiple independent agents, spawn them as parallel
  subagents in one turn — don't collapse a tier into a single inline pass to save calls.
  The exception is a tier with one trivial agent you can finish inline.
- **Effort** (§D): the full pipeline is intelligence-sensitive end-to-end. Run at
  `high`/`xhigh`. If effort is `low`/`medium`, tell the user once that deck quality and
  validation depth improve at higher effort, then proceed.

## Step 0: Load Context

Before anything else:

```python
import os, yaml

# Find workspace
workspace = os.environ.get('AI_ANALYST_WORKSPACE', '')
if not workspace or not os.path.isdir(workspace):
    for d in ['.', './data', '../data']:
        if os.path.isdir(d):
            workspace = os.path.abspath(d)
            break
```

Load from `.knowledge/` if available:
1. Active dataset schema
2. User profile (detail level, chart preference, technical level)
3. Corrections log (known data issues)
4. Query archaeology (reusable SQL)

**Query results are file-first.** `query_athena(sql, out_path="")` writes the full result to a
CSV and inlines rows only when ≤ 50. The analytical agents run aggregated queries, so their
results stay inline as before. For any bulk/raw pull, the tool returns a handle and the agent
reads it back in bounded chunks (`nrows=`/`chunksize=`), never full-loading. Deliverables the
user explicitly requests go to the chosen `out_path`; everything else is a self-cleaning
intermediate in `.query-cache/<session_id>/`.

**Agents share data — they don't re-fetch it.** Repeated identical SQL is served from the
session query cache (`"cached": true`) without hitting Athena, but the real rule is upstream:
every agent prompt you dispatch must list the data files earlier agents already produced (the
run's `working/` CSVs, data-explorer's inventory, `timeseries_prepared.csv`, query handles
from `.query-cache/<session_id>/`) and instruct the agent to work from those files first,
querying the source only for data no prior agent has fetched. Parallel Phase-2 agents get the
same base-extract pointer so they don't each re-pull the same base data.

## Step 1: Parse Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `question` | Yes | — | The business question to answer |
| `data_path` | Yes | — | Path to data files or database |
| `plan` | No | `full_presentation` | Execution plan (see below) |
| `theme` | No | `analytics` (light) | Theme for slides |

**Execution plans:**
- `full_presentation` — All 18 agents, produces deck (default)
- `deep_dive` — Analysis + validation, no deck
- `quick_chart` — Just framing + 1-2 charts
- `validate_only` — Run validation on existing findings

If arguments are missing, ask the user.

## Step 2: Create Run Directory

```
{workspace}/working/runs/{YYYY-MM-DD}_{dataset}_{slug}/
├── working/           # intermediate files
├── outputs/           # final deliverables
├── pipeline_state.json
└── pipeline_metrics.json
```

## Step 3: Execute the DAG

Read `agents/registry.yaml` to get the full dependency graph. Execute tier by tier.

**Spawning model (per MODEL_CONVENTIONS §B):** each agent in a tier runs as its own
subagent — read its `.md` from `agents/` and dispatch it. When a tier lists several
agents whose dependencies are satisfied, dispatch them **as parallel subagents in the
same turn** so they run concurrently. The independent perspectives are the point of the
DAG; running them inline as one merged pass defeats source-tieout and validation acting
as independent checks.

> **Lean cores + on-demand extended specs.** Agents now carry a lean core `.md` (purpose,
> inputs/outputs, the full workflow skeleton, and every HALT/validation gate). The larger
> specs keep their situational implementation detail — code snippets, helper signatures,
> full output templates — in a companion `agents/references/<name>-extended.md`, which the
> agent loads on demand when it needs the detail for a step. This does not change dispatch:
> R8 still holds — the core `.md` is read from disk each phase. Only the extended detail is
> deferred, and only the agent itself loads it.

### Phase 1: Framing (Agents: question-framing, hypothesis)
- Read each agent's .md file from `agents/` directory
- question-framing structures the business question
- hypothesis generates testable hypotheses
- **Checkpoint:** Verify we have a clear question + 2-3 hypotheses

### Phase 2: Exploration & Analysis (Agents: data-explorer, source-tieout, descriptive-analytics, root-cause-investigator, validation, opportunity-sizer)
- data-explorer profiles the data
- source-tieout verifies data loading integrity (HALT on mismatch)
- descriptive-analytics does segmentation, funnel, drivers analysis
- root-cause-investigator drills down iteratively
- validation runs 4-layer checks
- opportunity-sizer quantifies business impact
- **Agents in this phase can run in parallel where dependencies allow**
- **Checkpoint:** Verify findings are validated and plausible

### Phase 3: Storytelling & Charts (Agents: story-architect, chart-maker, visual-design-critic, narrative-coherence-reviewer)
- story-architect designs the storyboard: Context → Tension → Resolution
- chart-maker generates SWD-styled charts (see Chart Standards below)
- visual-design-critic reviews each chart against SWD checklist
- narrative-coherence-reviewer ensures story flow
- **Checkpoint:** All charts approved, narrative is coherent

### Phase 4: Deck & Delivery (Agents: storytelling, deck-creator, close-the-loop)
- storytelling writes the narrative prose
- deck-creator assembles the Marp slide deck
- close-the-loop archives findings and defines follow-up plan
- **Checkpoint:** Deck passes marp_linter, PDF/HTML exported

### Execution Rules
- Max 3 parallel agents per tier
- 5-minute timeout per agent, 1 automatic retry
- Critical agents (data-explorer, source-tieout, validation, descriptive-analytics) HALT on failure
- Non-critical agents (visual-design-critic, narrative-coherence-reviewer) continue with warning
- Circuit breaker: 3+ critical failures → HALT pipeline

## Chart Standards (every chart in the pipeline)

Apply SWD (Storytelling with Data) methodology to every chart. Call `swd_style()` first:

```python
import sys
sys.path.insert(0, '<plugin-path>/helpers')
from chart_helpers import swd_style, highlight_bar, highlight_line, action_title, save_chart
```

- **R2 — Chart title is the takeaway, and differs from the slide headline.** The chart title
  is a specific data claim ("Enterprise grew 3x", not "Revenue by Plan"); the slide headline
  is the narrative framing. Keep them distinct.
- **R3 — Background `#F7F6F2`** (warm off-white, not pure white), verified by `swd_style()`.
- **Color only the story.** Highlight the key finding in `#D97706` (Action Amber), negative
  findings in `#DC2626` (Accent Red); everything else stays gray (`#9CA3AF`).
- **R6 — Breathing slides** every 3-4 insight slides.
- **R7 — Standard sizing:** `(10, 6)` figsize at 150 DPI.
- **R8 — Read each agent's `.md` from disk at the start of each phase** (the spec is the
  source of truth; do not run an agent from memory).
- Remove top/right spines, drop data markers, and use direct labels instead of legends.

## Step 4: Progress Reporting

Report at start and end of each phase:
```
[Phase 1/4: Framing] Starting... (2 agents)
[Phase 1/4: Framing] Complete. (2/2 passed) | Overall: 2/18 agents done
```

## Step 5: Pipeline Complete

Report:
1. Output files (deck path, chart paths, narrative)
2. Checkpoint results summary
3. Execution metrics (duration, agents completed/failed/skipped)
4. Export status (PDF/HTML generated)
5. Suggested next actions based on findings

## References

For detailed specs, read from the `references/` directory:
- `dag-execution-engine.md` — Full DAG walker algorithm
- `execution-plans.md` — All 5 plan definitions
- `checkpoint-logic.md` — All 4 checkpoints with gates
- `pipeline-state-schema.md` — State file schema
- `pipeline-summary-template.md` — Progress report template
