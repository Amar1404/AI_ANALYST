# Validation Framework Reference

Read this when doing L3+ analysis and you need the full 4-layer validation stack.

## Layer 1: Structural Validation
- Schema matches expected (correct columns, types)
- Primary keys unique
- Foreign keys reference existing records
- Null rates below threshold (warn at 5%, fail at 20%)

## Layer 2: Logical Validation
- Aggregation consistency: parts sum to whole (1% tolerance)
- Trend continuity: no gaps in time series
- Segment exhaustiveness: segments cover full population
- Temporal consistency: date ranges across tables overlap

## Layer 3: Business Rules
- Values in plausible ranges (no negative revenue, no conversion > 100%)
- Rates between 0-100%, denominators > 0
- YoY changes plausible (flag anything > 500%)

## Layer 4: Simpson's Paradox Check
- For any aggregate finding, compute the same metric per segment
- If ANY segment shows the OPPOSITE trend → flag as paradox
- Report segment-level findings instead of aggregate
- Check at least 2 dimensions: user type/plan AND geography/channel

## Confidence Scoring
- A (90-100): All 4 layers pass, no warnings
- B (75-89): Minor warnings, no blockers
- C (60-74): Multiple warnings or one soft blocker
- D (40-59): Significant issues, present with heavy caveats
- F (0-39): Blockers present, do not present as reliable

## External Benchmarks for Plausibility
- SaaS monthly churn: 3-8% typical, <1% suspicious, >15% check definition
- Conversion rate: 2-5% typical, >10% needs checking
- Email open rate: 15-30% typical, >50% check pixel tracking
- NPS: 30-50 good, >70 exceptional (check sample bias)
- DAU/MAU: 20-30% healthy, >50% very sticky product
