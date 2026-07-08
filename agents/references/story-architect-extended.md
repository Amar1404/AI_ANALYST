# Story Architect — Extended Detail

This file holds the situational implementation detail for the Story Architect agent: beat-spec
templates, the full voice-and-tone guide, visual-format and slide-type vocabulary tables,
slide-sequence templates, the title-differentiation examples, and the full output template.
Load it on demand when you need the implementation detail for a step. The core spec
(`agents/story-architect.md`) carries the workflow skeleton, all quality checks, and all
validation gates. Headings below match the core step names.

---

## Step 4: Write story beats

For each beat, use this spec template:

```
Beat N: [Headline — what the audience learns]
- Phase: Context / Tension / Resolution
- Audience question this answers: [what the audience is asking at this point in the story]
- Key evidence: [specific data from the findings inventory that supports this beat]
- Audience reaction: [nod / lean forward / "wait, really?" / "OK what do we do?"]
- Transition: [the question this beat leaves open — the next beat answers it]
```

**Beat design principles:**
- Each beat narrows the aperture — from broad to specific
- No beat should widen scope after narrowing (that breaks the story flow)
- The audience should be able to predict the next question at each step ("OK, so June spiked — but which category?")
- Every beat must have supporting evidence from the findings inventory
- Context beats ground the audience in what "normal" looks like
- Tension beats progressively reveal the anomaly and isolate the cause
- Resolution beats quantify the impact and point to action

**Optional Closing phase** (only when {{CONTEXT}} is "workshop" or "talk"):
After Resolution beats, add Closing beats for the CTA sequence. These are NOT part of the analytical story — they bridge from the analysis to the audience's next step. Closing beats follow an escalating commitment pattern:

```
Beat N: [Free resource — e.g., "Get the email course for free"]
- Phase: Closing
- Visual format: text slide (with QR code placement)

Beat N+1: [Course/offering overview — e.g., "Go deeper with the full course"]
- Phase: Closing
- Visual format: text slide (with QR code placement)

Beat N+2: [CTA — e.g., "Enroll today with discount code X"]
- Phase: Closing
- Visual format: text slide (impact layout)
```

Closing beats are omitted entirely for standard analytics decks. They only appear when the presentation context calls for them.

### Voice and Tone

Headlines and transitions should follow an understated, precise voice. The data carries the drama — the words should not compete with it.

**Principles:**
- **Precise over provocative**: "Ticket rates doubled across every category" not "Ticket rates exploded"
- **Understated confidence**: "One device. One category. One version." not "This was surgical precision"
- **Let surprise come from the data**: "4x increase in ticket rate" is inherently dramatic — no adjective needed
- **Questions over declarations**: "What did this cost?" not "The damage was devastating"
- **No metaphors that editorialize**: Avoid "alarm/fire", "ticking time bomb", "smoking gun". State the finding directly.

**Banned words/phrases:** surgical, devastating, exploded, ticking time bomb, smoking gun, alarm/fire metaphors, unprecedented (unless literally true)

**Preferred patterns:**
- Short declarative sentences: "Growth explains some of this. But not all of it."
- Rhetorical questions that advance the story: "What did this cost?"
- Precise numbers as drama: "202 lost orders. $16,600 in revenue. $6,500 in support costs."

---

## Step 5: Quality checks (full detail)

**Check 1 — Completeness test:**
Does the story reach a specific, actionable root cause? "June spiked" is not a root cause. "iOS app v2.3.0 introduced a payment processing regression" is. If the story stops at a surface observation, add beats that drill deeper.

**Check 2 — Arc test:**
Verify the story has at least one Context beat, at least one Tension beat, and at least one Resolution beat. If Context dominates, the story hasn't started. If Tension is missing, there's no story. If Resolution is missing, there's no payoff. If Closing beats exist, they must come after all Resolution beats — never before.

**Check 3 — Question chain test:**
Read each beat's transition question, then check that the next beat answers it. Any gap where the obvious next question goes unanswered = add a beat. Any place where a beat's answer doesn't connect to the previous beat's question = reorder.

**Check 4 — Redundancy test:**
Compare all pairs of beats. Two beats are redundant if they convey the same insight even with different evidence. Merge redundant beats.

**Check 5 — Soft range warning:**
Fewer than 4 beats is unusual for a root cause analysis — verify the story has sufficient depth. More than 12 beats may indicate redundancy or insufficient merging. This is a warning, not a hard limit — let the story dictate the count.

**Check 6 — Headline read-through test:**
Read all beat headlines top-to-bottom as a paragraph. They should form a coherent mini-narrative:
- "[Dataset] processes ~1,500-3,500 support tickets per month. June ticket volume was significantly above trend. Payment issues drove the June spike. Payment issues doubled while other categories grew normally. The spike was entirely on iOS. v2.3.0 spiked immediately on release. The spike lasted exactly 14 days. The bug produced more severe tickets. Impact: 356 excess tickets, 29h median resolution, $5,340 cost."
If the headlines don't flow as a story, revise them.

---

## Step 6: Map beats to visual formats (full detail)

For each beat, choose a visual format:

| Format | When to Use |
|--------|-------------|
| **Chart** | The beat's evidence is best communicated as a data visualization (most beats) |
| **Big number** | The beat's evidence is a single KPI or metric — Deck Creator renders these as HTML `.kpi-row` + `.kpi-card`, not as chart PNGs |
| **Comparison table** | The beat compares two states (before/after, segment A vs B) and a simple table is clearer than a chart |
| **Text slide** | The narrative itself carries the beat (rare — only for transitions or framing that don't need data) |

For beats with `visual_format: chart`, write a chart spec. The `title` field is the chart's SWD action title — a takeaway statement baked into the chart PNG. It appears on both base and slide variants. The Deck Creator's slide headline provides the narrative framing, while the chart title provides the specific data claim.

**HARD RULE — Title Differentiation (examples):**
The chart `title` MUST differ from the beat headline. The beat headline is narrative framing; the chart title is a specific data claim with numbers/percentages. Examples:

| Beat Headline | Chart Title | Verdict |
|--------------|-------------|---------|
| "Payment issues drove the June spike" | "Payment issues drove the June spike" | **BAD** — identical |
| "Payment issues drove the June spike" | "Payment tickets jumped 147% while other categories grew <20%" | **GOOD** |
| "One device drove the entire spike" | "iOS ticket rate jumped from 14 to 65 per 1K orders" | **GOOD** |
| "The spike lasted exactly 14 days" | "The spike lasted exactly 14 days" | **BAD** — identical |
| "The spike lasted exactly 14 days" | "Ticket rate hit 65/1K on Jun 1, returned to 14/1K by Jun 15" | **GOOD** |

If the beat headline and chart title are the same text, rewrite the chart title to include specific numbers, percentages, or ranges from the evidence.

```
Beat N: [Headline]
- **Visual format**: chart
- **Chart type**: bar / horizontal_bar / line / multi_line / stacked_bar / big_number
- **Data needed**: [columns, filters, aggregation]
- **Subtitle**: [Context line — dataset, time range, filters]
- **Visual technique**: [Which helper function or technique to use]
  - highlight_bar: one bar colored, rest gray
  - highlight_line: one line colored, rest gray
  - stacked_bar: layered bars with one layer highlighted
  - add_trendline: dashed expected trend with excess annotation
  - add_event_span: axvspan marking a specific time window
  - fill_between_lines: shaded area between two comparison lines
  - big_number_layout: KPI summary card with findings and recommendation
  - side_by_side: grouped bars for direct comparison
  - annotate_point: arrow annotation on a specific data point
- **Annotations**: [What specific data points to annotate and why]
```

---

## Step 6b: Define slide sequences (full detail)

Each beat becomes a 1-3 slide sequence. Add a `slides` array to each beat spec that defines how Deck Creator renders the beat.

| Slide Count | When | Example |
|-------------|------|---------|
| 1 slide | Simple evidence or simple statement | `chart-full`, `kpi`, `impact` |
| 2 slides | Evidence + interpretation | `chart-full` → `takeaway` |
| 3 slides | Anchoring + evidence + interpretation | `kpi` → `chart-full` → `takeaway` |

**Slide type vocabulary:**

| Type | Content | When to Use |
|------|---------|-------------|
| `chart-full` | Headline + full chart image at natural proportions | Showing data evidence (most beats) |
| `chart-left` / `chart-right` | Chart + brief annotation side-by-side | Chart with immediate context alongside |
| `kpi` | Headline + KPI row (2-4 cards) | Anchoring key numbers |
| `takeaway` | Headline + so-what or finding box | Interpreting what was just shown |
| `impact` | Single centered statement | Pacing, emphasis, transitions |
| `recommendation` | Headline + rec-rows | Action items |
| `appendix` | Headline + structured text | Methodology, caveats |

Add the `slides` array to the beat spec:

```
Beat N: [Headline — narrative framing]
- Phase: Context / Tension / Resolution
- Audience question: [what the audience is asking]
- Key evidence: [specific data from findings inventory]
- Audience reaction: [nod / lean forward / "wait, really?" / "OK what do we do?"]
- Transition: [question this leaves open]
- Visual format: chart
- Chart type: bar
- Data needed: [columns, filters, aggregation]
- Title: "[Action title — specific data claim with numbers]"
- Subtitle: "[Context line — dataset, time range, filters]"
- Visual technique: highlight_bar
- Annotations: [specifics]
- Slides:
  1. type: chart-full
     headline: "[Narrative framing — NOT the chart title]"
     chart: [references chart spec above]
  2. type: takeaway
     headline: "[What this means]"
     content: "[So-what interpretation]"
```

**Rules for slide sequences:**
- Chart beats always use `chart-full` (full slide at natural proportions). CSS handles containment via `object-fit: contain`.
- If the chart has important interpretation, pair with a `takeaway` slide (2-slide sequence).
- Use `chart-left`/`chart-right` only when chart and a brief annotation naturally pair side-by-side.
- KPIs never share a slide with charts — use separate `kpi` and `chart-full` slides.
- Recommendations always get their own `recommendation` slide.
- `takeaway` slides between chart slides provide natural pacing (counts as a pacing break for R6).

For beats with `visual_format: big_number`, specify metrics as a list consumed directly by Deck Creator HTML rendering:
- `[{value, label, delta, color}, ...]` — e.g. `[{"value": "202", "label": "lost orders", "delta": "in June", "color": "accent"}]`
- Deck Creator renders these as `.kpi-row` + `.kpi-card` HTML — no chart PNG needed

For beats with `visual_format: comparison_table`, specify:
- The rows and columns of the table

---

## Step 8: Assemble the storyboard — Full Output Format

**File:** `working/storyboard_{{DATASET}}.md`

**Structure:**

```markdown
# Storyboard: [Dataset / Analysis Name]

## Core Anomaly
[One sentence describing the central finding this story will explain]

## Audience Journey
- **Audience**: [who]
- **Current belief**: [what they assume now]
- **Target belief**: [what they should understand after]
- **Decision to drive**: [the one action this story should motivate]

## Story Beats

### Beat 01: [Action headline]
- **Phase**: Context
- **Audience question**: [what they're asking]
- **Key evidence**: [data from findings inventory]
- **Audience reaction**: [expected reaction]
- **Transition**: [question this leaves open]
- **Visual format**: chart
- **Chart type**: [type]
- **Title**: [action title — specific data claim]
- **Data needed**: [specifics]
- **Subtitle**: [context line]
- **Visual technique**: [technique]
- **Annotations**: [specifics]
- **Slides**:
  1. type: chart-full
     headline: "[Narrative framing]"
     chart: beat_01
  2. type: takeaway
     headline: "[What this means]"
     content: "[So-what interpretation]"

### Beat 02: [Action headline]
...

[Continue for all beats]

## Quality Check Results
- **Beat count**: [N]
- **Headline read-through**: [PASS/FAIL + the headline sequence as a paragraph]
- **Arc balance**: Context: [N], Tension: [N], Resolution: [N]
- **Question chain**: [PASS/FAIL — any gaps noted]
- **Root cause identified**: [Yes/No — what is it?]
- **Visual variety**: [N] different techniques used
```
