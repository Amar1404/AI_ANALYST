# DAG Execution Engine

## Overview

The pipeline runs on a DAG (directed acyclic graph) derived from `agents/registry.yaml`. Instead of hardcoded steps, the engine resolves execution order from agent dependencies. This enables:
- **Automatic parallelization** — agents with no dependencies can run in parallel
- **Resilience** — failing agents don't block independent agents
- **Flexibility** — execution plans prune the DAG without breaking dependencies

---

## Step 0: Pre-execution Cleanup (Crash Recovery)

Before validation, detect and clean up artifacts from a previous crashed run.

1. **Detect stale runs:** Check if `<workspace>/working/pipeline_state.json` exists with `status: running`.
   - Parse `updated_at` and compute elapsed time. If > 30 minutes ago, treat as stale.
   - Print: `"Found stale pipeline state from {updated_at}. Previous run may have crashed."`
   - Ask: `"Archive stale state and start fresh? (Y/n)"`
   - **If yes:** Rename `<workspace>/working/pipeline_state.json` to `<workspace>/working/crashed_{run_id}_state.json`. Continue to Phase 0.
   - **If no:** Redirect to `/resume-pipeline` to attempt resuming the previous run. Stop here.
   - If `updated_at` is within 30 minutes, assume another run is active. HALT with: `"Pipeline state shows an active run from {updated_at}. Use /resume-pipeline or wait for it to finish."`

2. **Clean temp files:** Delete any `<workspace>/working/*.tmp.json` files (partial atomic writes from a crashed run).

3. **Validate per-run directory:** If prior run left an orphaned `<workspace>/working/latest` symlink:
   - Remove the stale symlink (the new run will create its own in Phase 1).
   - Create `<workspace>/working/runs/{run_id}/` directory structure with `<workspace>/working/` and `outputs/` subdirectories.

4. **Initialize fresh state:** The actual `pipeline_state.json` creation happens in Phase 1 with `schema_version: 2` and all agents set to `pending`. Step 0 only ensures the workspace is clean.

After cleanup completes (or is skipped if no stale state found), proceed to Phase 0.

---

## Phase 0: Pre-flight Validation

Before any execution, validate the registry:

1. **Read registry:** Parse `agents/registry.yaml`. Extract each agent's `name`, `file`, `pipeline_step`, `depends_on`, `depends_on_any`, `critical`, `inputs`, `outputs`, `knowledge_context`.

2. **File existence check:** For each agent, verify the file at `agent.file` exists on disk. If any file is missing, HALT with: `"Agent file not found: {path}"`

3. **Dependency resolution:** For each agent's `depends_on` and `depends_on_any` lists, verify every referenced agent name exists in the registry. If any reference is dangling, HALT with: `"Unknown dependency: {agent} depends on {missing}"`

4. **Cycle detection:** Perform a topological sort on the dependency graph. If a cycle is detected, HALT with: `"Cycle detected: {cycle_path}"`
   - Algorithm: Kahn's algorithm — iteratively remove nodes with in-degree 0. If nodes remain after no more can be removed, those nodes form a cycle.

5. **Compute execution tiers:** Group agents into tiers where all agents in a tier have their dependencies satisfied by agents in earlier tiers.
   ```
   Tier 0: agents with no dependencies (e.g., question-framing, data-explorer)
   Tier 1: agents depending only on Tier 0 agents (e.g., hypothesis, source-tieout)
   Tier 2: agents depending on Tier 0-1 agents (e.g., descriptive-analytics)
   ...
   ```

6. **Apply execution plan:** Load the plan. Filter the DAG to include only agents in the plan's allow-list. Agents not in the plan are marked `skipped`. If a plan agent depends on a skipped agent, warn: `"Agent {name} depends on skipped agent {dep}. Ensure required context exists."`

---

## Phase 1: Initialize Run Directory & Pipeline State

**Per-run directory setup:** Every pipeline run gets an isolated directory under `<workspace>/working/runs/`.

1. **Create run directory:**
   ```
   RUN_DIR = <workspace>/working/runs/{YYYY-MM-DD}_{DATASET_NAME}_{SHORT_TITLE}/
   ```
   Where `SHORT_TITLE` is derived from the business question -- lowercase, hyphens, max 40 chars
   (e.g., `2026-02-23_acme-analytics_why-revenue-dropped-q3`).

2. **Create subdirectories:**
   ```
   {RUN_DIR}/working/       -- intermediate files (tie-outs, storyboards, reviews)
   {RUN_DIR}/outputs/       -- final deliverables (decks, charts, narratives)
   {RUN_DIR}/pipeline_state.json  -- run state (authoritative)
   {RUN_DIR}/pipeline_metrics.json -- execution timing
   ```

3. **Create symlink:** `<workspace>/working/latest` -> `{RUN_DIR}` (remove existing symlink first if present).

4. **Backward-compatible aliases:** Also create/maintain the legacy `<workspace>/working/` and `outputs/` paths.
   All agents continue writing to `<workspace>/working/` and `<workspace>/outputs/` as before. At pipeline end,
   copy final artifacts into `{RUN_DIR}/working/` and `{RUN_DIR}/outputs/` so the run
   directory is self-contained.

**Initialize pipeline_state.json** in `{RUN_DIR}/` per the schema in `pipeline-state-schema.md`:
- Set `pipeline_id` to current ISO timestamp
- Set `run_dir` to the full run directory path
- Set `dataset` from active dataset
- Set `question` from user input
- Initialize all included agents as `pending`, skipped agents as `skipped`
- Set pipeline `status: running`

If **resuming** (pipeline_state.json already exists with `status: paused` or `status: failed`):
- Read existing state (check `<workspace>/working/latest/pipeline_state.json` first, then fall back to `<workspace>/working/pipeline_state.json`)
- Identify agents with `status: completed` -- leave them
- Identify agents with `status: failed` -- reset to `pending` for retry
- Compute the READY set (pending agents whose dependencies are all completed)
- Report: `"Resuming from {N} completed agents. Next: {READY agent names}"`
- Skip to Phase 2

---

## Phase 2: Walk the DAG

Execute agents tier by tier:

```
FOR each tier in execution_tiers:
  1. READY_SET = agents in this tier that satisfy BOTH:
     - ALL `depends_on` agents have completed (AND-gate)
     - At least ONE `depends_on_any` agent has completed, if specified (OR-gate)
     (after plan filtering and skipping)

  2. If READY_SET is empty AND pending agents remain → deadlock → HALT

  3. FOR each agent in READY_SET:
     a. Mark agent status: running in pipeline_state.json
     b. Record started_at timestamp
     c. Assemble dynamic context (see Context Assembly below)
     d. Read agent file from disk (R8)

  4. LAUNCH agents:
     - If Task tool available AND READY_SET has 2+ agents:
       Launch up to 3 parallel Tasks, each with agent file + context
     - Else: Execute sequentially inline

  5. WAIT for completion (with timeout — see Timeout Handling)

  6. FOR each completed agent:
     a. Record completed_at, output_files in pipeline_state.json
     b. Record timing in pipeline_metrics
     c. If FAILED and agent.critical is true (default): increment failure counter
     d. If FAILED and agent.critical is false (warn_on_failure):
        - Log warning: "⚠ Non-critical agent {name} failed: {error}. Continuing."
        - Write stub output to agent's first output path:
          `# {name} — SKIPPED (failure)\nReason: {error}\nTimestamp: {iso_now}`
        - Mark status as `degraded` in pipeline_state.json
        - Queue warning for display at next checkpoint
        - Do NOT increment tier failure counter

  7. CIRCUIT BREAKER: If 3+ critical agents failed in this tier → HALT pipeline
     Report: "Circuit breaker tripped: {N} failures in tier {T}. Failed: {names}"

  8. CHECKPOINT: If a checkpoint fires after this tier, run it (see Checkpoints)

  9. Update <workspace>/working/pipeline_summary.md with phase results

  10. ADVANCE to next tier
```

---

## Dynamic Context Assembly

Before launching each agent, resolve its runtime context:

1. **System variables:**
   - `{{DATE}}` → current date YYYY-MM-DD
   - `{{DATASET_NAME}}` → from `dataset_name` argument or derived from data_path
   - `{{ACTIVE_DATASET}}` → from `<workspace>/.knowledge/active.yaml`
   - `{{BUSINESS_CONTEXT_TITLE}}` → derived from question

2. **Knowledge context:** For each path in the agent's `knowledge_context` from registry:
   - Replace `{active}` with the active dataset name
   - Read the file and include its content as context for the agent

3. **Dependency outputs:** For each completed dependency agent, gather its `output_files` from pipeline_state.json. These become available inputs for the current agent.

4. **Pipeline arguments:** Pass through `context`, `theme`, `audience`, `data_path` as relevant to the agent's `inputs` list.

---

## Timeout Handling

Each agent has a 5-minute execution timeout:

1. When an agent starts, record `started_at`
2. If 5 minutes elapse with no completion:
   - Mark the attempt as timed out
   - **Retry once** with the same context
3. If the retry also times out:
   - Mark agent as `failed` with error: `"Timeout after 2 attempts (5min each)"`
   - Apply degradation policy: if the agent is non-critical (visual-design-critic, narrative-coherence-reviewer), continue pipeline with a warning. If critical (source-tieout, validation), HALT.

**Critical agents** (HALT on timeout): source-tieout, validation, data-explorer
**Non-critical agents** (degrade on timeout): visual-design-critic, narrative-coherence-reviewer, opportunity-sizer

---

## Circuit Breaker

Prevents runaway failures from consuming resources:

- Track failure count per execution tier
- **Threshold: 3 failures in a single tier** → HALT the pipeline
- On HALT, report:
  ```
  Circuit breaker tripped in tier {N}.
  Failed agents: {list with error messages}
  Completed agents: {list}
  Suggestion: Fix the underlying issue and /resume-pipeline
  ```
- The circuit breaker does NOT fire for skipped agents, only for failed agents
