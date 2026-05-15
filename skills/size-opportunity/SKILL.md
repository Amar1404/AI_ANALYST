---
name: size-opportunity
description: >
  Estimate the business impact and financial value of a given opportunity.
  Invokes the opportunity-sizer agent to break down addressable market, conversion
  potential, and revenue impact. Triggered when users ask "how much is this worth?",
  "size the opportunity", "business impact analysis", or invoke `/size-opportunity`.
---

# Skill: Size Opportunity

## Purpose
Estimate the business impact and financial value of a given opportunity.
Calls the opportunity-sizer agent to analyze addressable market, conversion potential,
and revenue impact with clear assumptions and sensitivity analysis.

## When to Use
- User asks "how much is this opportunity worth?"
- After identifying a potential improvement, quantify its value
- When evaluating which opportunities to prioritize
- When validating the ROI of a proposed project

## Invocation
`/size-opportunity {brief}` — size an opportunity from description
`/size-opportunity --template {template}` — use a sizing template (e.g., "product", "retention", "efficiency")
`/size-opportunity --sensitivity` — run sensitivity analysis on key assumptions

## Instructions

### Step 1: Parse the Opportunity Brief
Extract:
1. **What is the opportunity?** — New feature, performance improvement, retention lever, new market, etc.
2. **Who benefits?** — User segment, customer tier, geography
3. **Current state:** — Baseline metric/revenue (query from data if available)
4. **Proposed improvement:** — What changes with this opportunity?
5. **Timeline:** — When could this launch? How long to maturity?

### Step 2: Invoke Opportunity-Sizer Agent
Hand off to the opportunity-sizer agent with:
- The opportunity brief
- Current business metrics (active dataset context)
- User constraints and timeline
- Instructions to estimate impact and produce a sizing analysis

### Step 3: Generate Sizing Analysis
The opportunity-sizer agent produces:

```markdown
# Opportunity Sizing: {Opportunity Name}

## Executive Summary
**Opportunity:** {brief description}
**Addressable users:** {N} ({pct}% of base)
**Estimated annual impact:** ${X}M / {Y}% uplift
**Payback period:** {months}
**Confidence:** {High / Medium / Low}

---

## Detailed Breakdown

### Market / Addressable Opportunity

| Dimension | Current | Target | Addressable |
|-----------|---------|--------|-------------|
| Total users | {n} | — | — |
| Segment eligible | {n} | {pct}% of total | {n} |
| Will engage | {n} | {pct}% of segment | {n} |
| **Total addressable** | — | — | {n} users |

### Impact Model

**Revenue opportunity:**
```
{Addressable users}
  × {adoption rate}%
  × {ARPU improvement per user}
= ${impact}
```

**Time to value:**
- **Build time:** {weeks}
- **Ramp time:** {weeks} to full adoption
- **Measurement lag:** {weeks} for signal
- **Total time to impact:** {months}

### Assumptions & Drivers

| Assumption | Conservative | Base Case | Optimistic | Source |
|------------|--------------|-----------|-----------|--------|
| {Segment size} | {X} | {Y} | {Z} | {data source} |
| {Adoption rate} | {X%} | {Y%} | {Z%} | {benchmark or estimate} |
| {ARPU lift} | {$X} | {$Y} | {$Z} | {data or projection} |

### Sensitivity Analysis

What if assumptions change?

```
Impact under different scenarios:

Best case (all assumptions favor opportunity):   ${best}M
Base case (reasonable estimates):                 ${base}M
Worst case (conservative assumptions):            ${worst}M

Break-even adoption rate:                         {X%}
Break-even ARPU lift:                             ${X}
```

### Comparison to Other Opportunities

If multiple opportunities evaluated:

| Opportunity | Annual Impact | Payback | Effort | ROI Rank |
|-------------|---------------|---------|--------|----------|
| {this opportunity} | ${impact} | {months} | {effort} | #{rank} |
| {other opp} | ${impact} | {months} | {effort} | #{rank} |

### Success Metrics & KPIs to Track

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| {metric 1} | {value} | {target} | {how measured} |
| {metric 2} | {value} | {target} | {how measured} |
| {revenue impact} | ${value} | ${target} | Monthly P&L |

### Risks & Assumptions to Validate

| Risk | Impact | Mitigation |
|------|--------|-----------|
| {Adoption lower than expected} | ${lost} | Start with cohort 1, measure before full rollout |
| {Implementation delays} | {months late} | Break into phases, start with MVP |
| {Competitive response} | {market share loss} | Focus on defensible improvements first |

### Recommendation

**Proceed if:**
- This opportunity ranks in the top {N} by ROI
- Key assumptions (adoption, ARPU lift) are validated
- Build effort is estimated at {X} story points or less

**Measure:**
- Weekly tracking of adoption rate and impact metrics
- Monthly cohort analysis to validate assumptions
- Quarterly review of payback and overall business impact

**Next steps:**
1. Validate key assumptions (e.g., survey, prototype test)
2. Design experiment if impact claims are material
3. Build implementation roadmap
4. Brief stakeholders on expected impact
```

### Step 4: Validate Assumptions
Review the sizing with the user:
- Are the addressable user segments realistic?
- Is the adoption rate defensible?
- What assumptions are riskiest and need validation?
- Should we run an experiment before full rollout?

### Step 5: Output Sizing Analysis
Save to:
```
working/opportunity-sizing/{name}_{DATE}.md
```

Provide:
- Quick summary (total addressable opportunity, annual impact, payback)
- Link to full analysis
- Next actions: "Validate assumptions with a small pilot" or "Ready to prioritize relative to other opportunities"

## Templates

### Product Feature Template
Addressable = (Total active users) × (will use feature %) × (will upgrade tier %)
Impact = Addressable × (incremental ARPU) × (adoption ramp)

### Retention/Churn Reduction Template
Addressable = (Churn rate) × (Total users)
Impact = Addressable × (save rate %) × (LTV per user)

### Efficiency/Cost Reduction Template
Addressable = (Current opex) × (% improvable)
Impact = Addressable × (efficiency gain %)
Payback = (Implementation cost) / (Annual impact)

### Geographic/Segment Expansion Template
Addressable = (New market size) × (penetration %) × (ARPU)
Impact = Addressable - (overlap with existing segment)

## Edge Cases
- **Highly uncertain:** Flag confidence as LOW, run scenario analysis
- **Long payback period:** Consider strategic value beyond financial ROI
- **Cannibalization risk:** Model as (gross impact) - (lost revenue from existing tiers)
- **Cross-team dependencies:** Note in risks — can we build independently?

## Anti-Patterns
1. **Never use a single point estimate** — always show range with sensitivity
2. **Never ignore adoption ramp** — few features reach full penetration overnight
3. **Never assume immediate impact** — account for measurement lag and ramp time
4. **Never forget cannibalization** — new tier may shift existing revenue, not add
5. **Never confuse addressable with actualized** — segment size ≠ captured value
