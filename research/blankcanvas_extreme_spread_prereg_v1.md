# Market-neutral extreme-state spread campaign — preregistration v1

## Campaign ID
`EXTREME-SPREAD-20260813-V1`

## Independence from the prior family
The one-sided `EXTREME-COMMON-20260813-V2` campaign produced no discovery survivor because no definition met the preregistered multiple-testing t-statistic. This campaign does not lower that standard and does not inspect validation or holdout outcomes. It tests a different executable construction: a simultaneous long-short spread between the high and low tails of the same causal feature.

## Universe and chronology
- Fixed May-2025 pre-discovery 300-name liquidity universe.
- Restricted to the 230 ordinary operating equities frozen as shortable and easy-to-borrow before validation was queried.
- ETPs and leveraged/inverse instruments are excluded.
- Signal information ends at the signal-session close.
- Positions are entered in the specified following-session segment using the existing causal target definitions.
- Each selected name must have next-session price >= $5, at least 200 regular-session bars and next-day dollar volume >= $10 million.

## Candidate construction
For each of the same 26 registered end-of-session features and each of the six registered following-session targets:
- Select the N most extreme names from the bottom quintile (`q=1`).
- Select the N most extreme names from the top quintile (`q=5`).
- Form one of two orientations:
  - `HIGH_MINUS_LOW`: 50% long the high-tail basket and 50% short the low-tail basket.
  - `LOW_MINUS_HIGH`: 50% long the low-tail basket and 50% short the high-tail basket.
- Equal-weight names within each side.
- N in {1,2,3,5}.
- Low and high baskets must be disjoint and both sides must contain exactly N eligible names.

## Registered search count
- 26 features × 6 targets × 2 orientations × 4 sizes = 1,248 definitions.
- N in {1,2} is promotable for a £2,000 account with a £500 minimum position across 2N legs: 624 promotable definitions.
- N=3 and N=5 are stability diagnostics only.

## Time separation
- Discovery: signal dates 2025-06-02 through 2025-09-11 (69 sessions).
- Inner validation: 2025-09-15 through 2025-10-07 (17 sessions).
- Outer preholdout: 2025-10-08 through 2025-10-30 (17 sessions).
- Locked holdout A: 2025-11-03 through 2025-11-28.
- Locked holdout B: 2025-12-01 through 2025-12-30.

## Costs
- Gross spread return is 0.5 × long-basket return minus 0.5 × short-basket return.
- Primary round-trip cost is 10 basis points of portfolio NAV.
- Stress cost is 20 basis points.
- Historical borrow fees are unavailable and remain an additional deployment stress.

## Discovery gate
A promotable candidate must satisfy all of the following:
1. N in {1,2}; at least 65 sessions; exactly N names per side on every included date; no low/high overlap.
2. Mean net return after 10 bp >= +0.10% per trade.
3. Median net return after 10 bp > 0.
4. Win rate after 10 bp > 55%.
5. Profit factor after 10 bp >= 1.50.
6. Naive daily t-statistic >= 4.25.
7. Mean net return after 20 bp > 0.
8. No single day contributes more than 25% of total positive P&L.

Every survivor must then pass a moving-block bootstrap and Benjamini–Hochberg false-discovery adjustment at q <= 5% across all 1,248 registered definitions.

## Inner-validation gate
- Minimum 15 trades.
- Mean net return after 10 bp >= +0.05%.
- Median net return after 10 bp > 0.
- Win rate after 10 bp > 52%.
- Profit factor after 10 bp > 1.20.
- Mean net return after 20 bp > 0.

## Outer-preholdout gate
- Minimum 15 trades.
- Mean and median after 10 bp > 0.
- Win rate after 10 bp > 50%.
- Mean net return after 20 bp > 0.

## Neighbour stability and freezing
- The same feature, target and orientation must have at least one adjacent N with positive 10 bp mean in discovery, inner validation and outer preholdout. Adjacency: 1↔2 and 2↔{1,3}.
- Rank survivors by their minimum 10 bp mean across the three preholdout blocks, then outer-preholdout median.
- Freeze no more than three ancestry-distinct candidates before reading November.
- Holdout A and B use the unchanged rule and require positive 10 bp mean/median, win rate >50% and positive 20 bp mean.
- No component may be altered after a locked outcome.
