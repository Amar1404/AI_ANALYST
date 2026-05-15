---
name: run-analysis
description: "USE THIS SKILL for full end-to-end analytical pipelines, presentation decks, or deep investigations. Triggers when the user says 'run analysis', 'full pipeline', 'end-to-end', 'build me a deck', 'give me the full picture', 'comprehensive analysis', or any request for a polished slide deck with charts. Also use when ask-question classifies a question as L5. This skill orchestrates 18 specialized agents in a DAG pipeline — from framing through charting to a finished Marp deck. Do NOT attempt to build presentations or run multi-agent analysis workflows without this skill."
---

# Run Analysis — Full Pipeline Orchestrator

You are orchestrating a complete analytical pipeline. This is the heavyweight skill — it produces validated findings, SWD-quality charts, and a polished slide deck.

## Step 0: Load Context (Mandatory)

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

Read `agents/registry.yaml` to get the full dependency graph. Execute tier by tier:

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

## Chart Standards (Apply to ALL Charts in Pipeline)

**EVERY chart** must follow SWD (Storytelling with Data) methodology:

```python
import sys
sys.path.insert(0, '<plugin-path>/helpers')
from chart_helpers import swd_style, highlight_bar, highlight_line, action_title, save_chart
```

- **Always call `swd_style()` first**
- Background: `#F7F6F2` (warm off-white, NEVER pure white)
- Highlight color: `#D97706` (Action Amber) for the key finding
- Problem color: `#DC2626` (Accent Red) for negative findings
- Everything else: gray (`#9CA3AF`)
- **Title = takeaway** ("Enterprise grew 3x" not "Revenue by Plan")
- Remove top/right spines, no data markers, direct labels instead of legends
- Standard figsize: `(10, 6)` at 150 DPI

### NON-NEGOTIABLE RULES
- **R2:** Chart title ≠ Slide headline (chart = specific data claim, slide = narrative framing)
- **R3:** Chart background is #F7F6F2 (verified by swd_style())
- **R6:** Breathing slides every 3-4 insight slides
- **R7:** All charts at (10, 6) figsize / 150 DPI
- **R8:** Agent files MUST be read from disk at each phase

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
