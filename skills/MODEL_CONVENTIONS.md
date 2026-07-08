# Model Conventions — version-aware prompting

This file is the single source of truth for how skills in this plugin adapt their
prompting to the Claude model running them. It exists because Claude Opus 4.8
changed several default behaviors that the analyst's skills depend on. Skills link
here instead of duplicating the guidance.

Grounded in Anthropic's two prompting guides:
- Opus 4.8 specifics: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-4-8
- General best practices: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices

A SKILL.md is static text — it cannot run an `if`. **You, the model, perform the
branch.** You know which model you are. When a skill says "follow MODEL_CONVENTIONS",
read the matching branch below and apply it.

---

## Step 1: Detect your version

Determine which branch applies:

- **Opus 4.8 branch** — you are Claude Opus 4.8 (model id starts `claude-opus-4-8`), or any **newer** model that post-dates it. When unsure whether a newer model behaves like 4.8, default to the 4.8 branch — it is the current baseline.
- **Legacy branch** — you are Opus 4.7 / Sonnet 4.x / Haiku 4.x or older.

You may also surface the active runtime profile with
`python3 -c "from helpers.model_profile import describe; print(describe())"`,
which reports the effort level (`CLAUDE_EFFORT`) and self-reported model id. This is
for display and effort-checks only — the behavioral branch is your call, made from
the model identity above.

---

## Step 2: Apply the branch

### A. Instruction scope (literalism)

> **Opus 4.8:** Interprets instructions literally. It does **not** silently generalize
> an instruction from one item to all items, and does not infer requests you didn't
> make. Wherever a skill step could apply to "more than the obvious one," the scope is
> stated explicitly (e.g. "validate **every** segment, not just the largest"). Treat
> an unscoped instruction as applying **only to the item named** — if a skill seems to
> want broad application but didn't say so, that is a skill bug; follow it literally and
> note it. Do not helpfully expand scope on your own.

> **Legacy:** Reasonable generalization of an instruction across similar items is
> expected and fine. Apply the spirit of a step across the obvious set.

### B. Tool & subagent triggering

> **Opus 4.8:** Favors reasoning over tool calls and spawns **fewer** subagents by
> default. The plugin's analysis depends on actually querying data and (in
> `run-analysis`) fanning out agents — so triggering must be **explicit**:
> - **Query the data** whenever a claim depends on a number you have not already
>   pulled this session. Do not reason your way to a figure you could measure. When a
>   table's schema or value formats are unknown, `sample_table` first.
> - **Fan out subagents** in `run-analysis` per the DAG: spawn the agents a tier
>   declares, in parallel, in one turn. Do not collapse a multi-agent tier into a
>   single inline pass to "save a call" — the pipeline's correctness depends on the
>   independent agents running.
> - **Do not** spawn a subagent for work you can finish directly in one response
>   (e.g. a single query + chart at L1–L2).
> - If tool use still looks too low for the work, the first lever is **raising effort**
>   (see D), not rewording.

> **Legacy:** Default tool/subagent eagerness is adequate. Follow the DAG and query
> guidance as written without extra explicit nudging.

### C. Verbosity & progress scaffolding

> **Opus 4.8:** Self-calibrates response length to task complexity and gives good,
> regular progress updates on long traces on its own. Therefore:
> - **Do not** add or honor scaffolding that forces a fixed cadence of status messages
>   ("summarize after every N tool calls") — it fights the model. Removed from skills.
> - Let length follow the level: L1 answers are one line; L3–L4 are as long as the
>   finding needs. Do not pad an L1 answer to look thorough, and do not compress an
>   L4 finding to look brisk.
> - Keep the explicit *structural* requirements (the Receipt block, Context→Tension→
>   Resolution ordering, confidence note) — those are output **contract**, not verbosity
>   scaffolding, and stay.

> **Legacy:** Keep light progress scaffolding on long pipelines; the model is less
> consistent about interim updates. A periodic status line during `run-analysis` is
> helpful.

### D. Effort calibration

> **Opus 4.8:** Respects the effort level strictly, especially at the low end — at
> `low`/`medium` it scopes work to exactly what was asked and may under-think complex
> analysis. Guidance:
> - **Intelligence-sensitive work** (L3+ analysis, validation, root-cause,
>   experiment design, the full `run-analysis` pipeline): run at **`high` minimum,
>   `xhigh` preferred**. If you observe shallow reasoning, raise effort rather than
>   prompting around it.
> - **Scoped, mechanical work** (L1 single-number lookups, `switch-dataset`,
>   `view-metrics`, `refresh-dataset`): `low`/`medium` is fine and faster.
> - If `CLAUDE_EFFORT` is `low`/`medium` and you are about to start an L3+ analysis,
>   tell the user once: "This is intelligence-sensitive work; consider `/effort high`
>   for better results," then proceed at the current level.

> **Legacy:** Effort affects behavior less. Run as configured; no special calibration
> needed.

### E. Investigate before answering (all current models)

From the general best-practices guide's anti-hallucination guidance, applied to data:
**never report a number you have not measured.** The analyst's analogue of "never
speculate about code you have not opened" is:

> Never state a metric, total, rate, or trend from memory or inference. If an answer
> depends on a figure, query for it first. If the user names a table or metric, read
> its schema / definition before answering. Ground every quantitative claim in a query
> you actually ran this session, and cite it in the Receipt. A grounded "let me query
> that" beats a confident wrong number.

This is not version-branched — it holds on every model and is the backbone of the
Receipt step in `ask-question`.

### F. Calibrated imperative language (all current models)

The general guide warns that current models follow instructions precisely, so the old
habit of shouting (`CRITICAL: You MUST ALWAYS…`, `NEVER…` in caps) now causes
**over-triggering and over-rigidity** rather than reliability. When editing skills:

> Prefer calm, direct phrasing ("Use this tool when…", "Query the data whenever…") over
> all-caps absolutes. Reserve emphatic language for genuine hard rules (PII refusal,
> source-tieout HALT). Explain *why* an instruction matters — the model generalizes
> correctly from a one-line rationale far better than from volume.

Existing genuine hard rules (PII, HALT gates) keep their emphasis; that emphasis is
earned. Routine steps do not need it.

---

## Why this exists

Most of these are not "make Claude better" tweaks — they are **keeping existing skill
behavior intact across a model change**. 4.8's literalism, lower tool/subagent
eagerness, and self-calibrated verbosity would otherwise quietly alter how the analyst
queries, validates, and reports. Stating the branch explicitly is exactly what the 4.8
prompt guide recommends.
