---
name: export-results
description: "Triggers on \"export\", \"share\", \"send to Slack\", \"make a deck\", \"/export\"."
triggers:
  - /export
  - export this
  - share results
  - send to Slack
  - make a deck
  - email summary
---

# Skill: Export Results

## Purpose
Export analysis results in different formats for different audiences. Converts
pipeline outputs into ready-to-share deliverables.

## When to Use
- User says `/export` or "export this as..." or "send this to..."
- After completing an analysis or pipeline run
- When the user needs results in a specific format

## Invocation
`/export slides` — generate/refresh Marp slide deck from latest analysis
`/export email` — write an executive summary email (markdown)
`/export slack` — write a concise Slack update (markdown)
`/export brief` — write a 1-page decision brief (markdown)
`/export data` — export analysis data tables as CSV
`/export all` — generate all text formats + data

## Instructions

### Step 1: Find Source Material
Check for completed analysis outputs in order of preference:
1. `<workspace>/outputs/slides_*.md` — latest deck
2. `<workspace>/outputs/analysis_*.md` — latest narrative
3. `<workspace>/working/pipeline_summary.md` — pipeline summary
4. `<workspace>/working/storyboard_*.md` — storyboard

If no outputs exist:
- Check `<workspace>/working/` for partial results
- If nothing found: "No analysis results to export. Run an analysis first or use `/run-analysis`."

### Step 2: Generate Requested Format

**Format: slides**
- If deck already exists, ask: "Deck found at {path}. Regenerate or export as-is?"
- If no deck, invoke Deck Creator agent with latest narrative + charts
- Output: `<workspace>/outputs/slides_{DATE}.md`

**Format: email**
- Structure: Subject line + 3-paragraph body (context, key finding, recommendation)
- Tone: Executive-friendly, no jargon, action-oriented
- Include: 1-2 key numbers, the "so what", and a clear ask
- Output: `<workspace>/outputs/email_summary_{DATE}.md`

Example:
```
Subject: Q2 Growth Update — Key Findings

Hi [Recipient],

Over the past quarter, we analyzed user growth patterns across all segments.
Here are the key findings:

**Key Finding:** Our organic segment grew 45% YoY, but our paid acquisition
channel saw a 12% decline due to increased competition. This shift has
reduced our overall CAC efficiency by 8%.

**Our Recommendation:** Shift 30% of paid budget from top-of-funnel ads
to product recommendations. Early testing shows a 3x improvement in
conversion for this channel.

What I need from you: Approval to reallocate the paid budget. I can have
the new strategy live by end of week.

Best,
[Your name]
```

**Format: slack**
- Structure: Bold headline + 3-5 bullet points + thread-friendly
- Keep under 300 words
- Use emoji sparingly (checkmarks, arrows only)
- Include: key metric, direction, and recommended action
- Output: `<workspace>/outputs/slack_update_{DATE}.md`

Example:
```
🎯 **Q2 Growth Analysis: Organic Up, Paid Down**

Key findings:
• Organic segment: +45% YoY (our strongest channel)
• Paid acquisition: -12% YoY (due to increased CPM)
• Overall CAC efficiency: -8% (needs correction)

Recommendation: Reallocate 30% of paid budget to product recommendations.
Early tests show 3x better conversion. We can launch by EOW.

Questions? Let me know in thread.
```

**Format: brief**
- Structure: Title + Executive Summary (3 sentences) + Key Findings (numbered) +
  Recommendation + Next Steps + Appendix (data sources, methodology)
- 1 page target (~500 words)
- Output: `<workspace>/outputs/decision_brief_{DATE}.md`

Example:
```
# Q2 Growth Analysis: Strategic Realignment

## Executive Summary

Our organic segment is thriving (+45% YoY), but our paid acquisition channel
is struggling (-12% YoY) due to increased CPM. To maintain growth while
improving profitability, we recommend reallocating 30% of paid budget to
product recommendations, which show 3x better conversion in early testing.

## Key Findings

1. **Organic Growth is Accelerating**
   - Up 45% YoY across all segments
   - Driven by brand awareness and word-of-mouth
   - Highest margin channel

2. **Paid Acquisition is Under Pressure**
   - Down 12% YoY due to increased CPM
   - CAC increased 25% while conversion remained flat
   - Requires strategic realignment

3. **Product Recommendations Are Underutilized**
   - Early tests show 3x conversion improvement vs paid ads
   - Current spend: $50K/month
   - Potential upside: $150K/month at same CAC

## Recommendation

Reallocate 30% of paid budget ($75K/month) to product recommendations.
Expected outcome: +$150K/month incremental revenue, -20% overall CAC.

## Next Steps

1. Approve budget reallocation (this week)
2. Launch expanded product recommendations (next week)
3. Track performance weekly for 4 weeks
4. Optimize based on results

## Appendix

Data sources: Orders table, user_segments table, marketing_spend table
Methodology: Cohort analysis with 90-day lookback
Confidence: 85% (based on limited test sample)
```

**Format: data**
- Export all DataFrames from `<workspace>/working/` as CSVs to `<workspace>/outputs/data/`
- Include a README listing each file and its contents
- Output: `<workspace>/outputs/data/` directory

**Format: all**
- Run email + slack + brief + data sequentially
- Skip slides if already exists

### Step 3: Post-Export
- List all exported files with paths
- Suggest: "Copy the email to your clipboard?" or "Want to adjust the tone?"

## Rules
1. Never fabricate findings — only use data from actual analysis outputs
2. Always cite the source analysis date and dataset
3. Adapt detail level to format (email = high-level, brief = medium, data = raw)
4. Apply clear, jargon-free language for all text outputs
5. If the analysis had confidence scores, include them in brief format

## Edge Cases
- **Partial analysis:** Export what's available, note gaps: "Note: validation step was not completed."
- **Multiple analyses in outputs/:** Use the most recent by date, or ask user which one
- **Charts missing:** Text formats still work, note: "Charts not available for this export."
- **User requests unknown format:** List available formats and ask to choose

## Export Quality Checklist

Before exporting, ensure:
- [ ] All numbers are cited (with source table)
- [ ] No jargon without explanation
- [ ] Recommendations are actionable (not vague)
- [ ] Tone matches audience (exec vs technical vs team)
- [ ] Time period is clear (what dates does this cover?)
- [ ] Confidence level is noted (if applicable)
- [ ] Next steps are specific (not "keep monitoring")
