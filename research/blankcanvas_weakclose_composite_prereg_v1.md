# Causal weak-close composite campaign — preregistration v1

## Campaign ID
`WEAKCLOSE-COMPOSITE-20260813-V1`

## Why this is a new model-development campaign
The prior one-sided and high-tail-versus-low-tail searches repeatedly surfaced economically positive but statistically insufficient weak-close continuation patterns. Those discovery results are ancestry, not independent evidence. This campaign fixes one simple composite before inspecting any validation return. Discovery is training/descriptive only; the first inferential tests are the two untouched validation blocks.

The related ancestry count is at least 3,748 definitions: 2,496 one-sided extreme-state definitions, 1,248 market-neutral spread definitions, plus the four definitions below. Validation and sequential holdouts, not discovery statistics, provide the stopping protection.

## Look-ahead correction
The earlier protected panels required next-session realised dollar volume and at least 200 completed bars. Those fields are unavailable at entry and therefore contaminate their near-miss economics with look-ahead selection. No rule from those campaigns was promoted, so no accepted result is invalidated. This campaign does not use either field for selection.

The only next-session eligibility information used at entry is the observed opening price. Missing target data is audited after selection; a selected name with missing outcome makes that candidate-day incomplete and is never replaced using future information.

## Fixed universe
- Start from `public.rd_blankcanvas_equity_universe_v2`, frozen from May 2025 pre-discovery liquidity calibration.
- Restrict to the 230 ordinary operating equities in `research.blankcanvas_extreme_asset_eligibility_v1`.
- The current shortable/easy-to-borrow snapshot is a feasibility filter frozen before validation was queried, not proof of historical point-in-time borrow availability. Any surviving short rule still requires a live borrow/CFD availability gate and adverse borrow-fee stress before deployment.
- Require at least 200 universe members with all six signal features on a signal date. This is signal-time data-quality information.

## Signal timing and features
All signal information is from the completed regular session on date D. Entry is at the next regular-session open on D+1; exit is at the same session's regular close.

For every signal date and every fixed-universe name with complete data, calculate a deterministic cross-sectional percentile rank for each feature, with alphabetical symbol order breaking ties:

1. `ret_oc`
2. `close_vs_vwap`
3. `close_location`
4. `max_drawdown_from_open`
5. `last60_ret`
6. `last30_ret`

For feature x on a date with M complete names:
`rank_x = (row_number(order by x ascending, symbol ascending) - 1) / (M - 1)`.

The composite weakness score is the unweighted arithmetic mean of the six ranks. Lower scores are weaker closes; higher scores are stronger closes. No weights, signs, thresholds or transformations are estimated.

At the next-session open, remove names without an observable open or with open price below $5, then take the first N names from the precomputed weak/strong ranking. This price rule is observable before execution and does not use the subsequent outcome.

## Exactly four registered definitions
Target is fixed to next-session regular open-to-close return (`next_ret_oc`). Primary cost is 10 basis points of portfolio NAV; stress cost is 20 basis points.

For N in {1,2}:

1. `SHORT_WEAK_N`: 100% short notional, equally weighted across the N weakest eligible names.
2. `STRONG_MINUS_WEAK_N`: 50% long the N strongest and 50% short the N weakest, equally weighted within each side.

N=1 and N=2 are both executable for a £2,000 account with a £500 minimum position. No N, feature or weighting variation is permitted after validation is opened.

## Time separation
- Descriptive training/discovery: signal dates 2025-06-02 through 2025-09-11, 69 sessions.
- Inner validation: 2025-09-15 through 2025-10-07, 17 sessions.
- Outer preholdout: 2025-10-08 through 2025-10-30, 17 sessions.
- Locked holdout A: 2025-11-03 through 2025-11-28.
- Locked holdout B: 2025-12-01 through 2025-12-30.
- 2026 remains a later independent extension.

All four definitions are frozen before any validation return is queried. Discovery results may be reported descriptively but cannot eliminate, tune or rank the four definitions.

## Validation gates
A definition advances only if all of the following hold without modification:

### Inner validation
- At least 15 complete trades.
- Mean net return after 10 bp > 0.
- Median net return after 10 bp > 0.
- Win rate after 10 bp > 52%.
- Profit factor after 10 bp > 1.20.
- Mean net return after 20 bp > 0.

### Outer preholdout
- At least 15 complete trades.
- Mean net return after 10 bp > 0.
- Median net return after 10 bp > 0.
- Win rate after 10 bp > 50%.
- Profit factor after 10 bp > 1.10.
- Mean net return after 20 bp > 0.

### Combined validation
Across all 34 validation sessions:
- Mean and median after 10 bp > 0.
- Win rate after 10 bp > 52%.
- Profit factor after 10 bp >= 1.30.
- Mean after 20 bp > 0.
- Naive daily t-statistic >= 2.50.
- A moving-block bootstrap 95% lower confidence bound for mean 10 bp return must be above zero.
- Benjamini–Hochberg q-value must be <= 5% across the four composite definitions.

## Freeze and locked testing
- Freeze at most two survivors, preferring one `SHORT_WEAK` and one `STRONG_MINUS_WEAK` ancestry if both qualify; otherwise rank by the lower of the inner and outer 20 bp means, then combined median.
- Holdout A is evaluated exactly once. It requires positive 10 bp mean and median, win rate > 50%, profit factor > 1.10 and positive 20 bp mean.
- Holdout B is evaluated exactly once only for Holdout-A survivors using the same gates.
- No feature, score, side, N, cost, timing, price rule or eligibility rule may change after a locked result.

## Execution caveats
Historical point-in-time borrow availability and borrow fees are unavailable. A survivor is therefore not deployment-ready until each live signal passes borrow/CFD availability, estimated borrow cost, spread and order-size checks. A failure of those checks means no trade, not substitution based on future returns.
