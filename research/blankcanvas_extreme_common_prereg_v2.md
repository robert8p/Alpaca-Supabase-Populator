# Executable stock extreme-state campaign — preregistration v2

## Campaign ID
`EXTREME-COMMON-20260813-V2`

## Objective
Test whether an extreme, fully observed technical state at the close of one US session predicts an executable return in a specified segment of the following regular session. This campaign is registered before inspecting any portfolio-return statistics from `research.blankcanvas_extreme_common_daily_v1` and before reading any November–December 2025 holdout outcome.

## Causal universe and eligibility
- Fixed 300-name universe ranked from May 2025 pre-discovery liquidity calibration.
- Promotional research is restricted to the 230 ordinary operating equities frozen as Alpaca shortable and easy-to-borrow before validation was queried.
- ETPs and leveraged/inverse products are excluded.
- At the next-session entry, each selected name must have price >= $5, at least 200 regular-session bars and next-day dollar volume >= $10 million.
- Selection information ends at the signal-session close. Entry occurs in the following regular session.

## Signal states
The cross-sectional bottom quintile (`q=1`) and top quintile (`q=5`) are tested for exactly 26 end-of-session features:

`close_location`, `close_vs_vwap`, `efficiency_ratio`, `first30_ret`, `first60_range`, `first60_ret`, `first60_trade_share`, `first60_volume_share`, `high_time_fraction`, `last30_ret`, `last60_range`, `last60_ret`, `last60_trade_share`, `last60_volume_share`, `low_time_fraction`, `max_drawdown_from_open`, `max_minute_ret`, `max_runup_from_open`, `midday_ret`, `min_minute_ret`, `minute_ret_abs_sum`, `minute_ret_lag1_corr`, `pos_minute_fraction`, `range_pct`, `ret_oc`, `rv_1m`.

Within the selected tail, names are ranked from most extreme inward. Equal-weight top-N portfolios use N in {1,2,3,5}. Direction is either long (+1) or short (-1).

## Targets
Exactly six following-session targets are tested:
- `next_ret_oc`: following regular-session open to close.
- `next_first30_ret`: following session's precomputed first-30-minute return.
- `next_first60_ret`: following session's precomputed first-60-minute return.
- `next_midday_ret`: following session's precomputed midday return.
- `next_last60_ret`: following session's precomputed final-60-minute return.
- `next_last30_ret`: following session's precomputed final-30-minute return.

The target table stores raw return, same-day cross-sectional mean and residual. Candidate promotion uses executable raw portfolio returns after costs; residual return is a diagnostic, not a substitute for realised economics.

## Registered search count
- 26 features × 2 tails × 6 targets × 2 directions × 4 portfolio sizes = 2,496 registered definitions.
- Only N in {1,2,3} is promotable for a £2,000 account with a £500 minimum position assumption: 1,872 promotable definitions.
- N=5 exists only for parameter-neighbour and diversification diagnostics.
- Effective search count and candidate ancestry must be reported before freezing candidates.

## Time separation
- Discovery: signal dates 2025-06-02 through 2025-09-11 (69 sessions; targets through 2025-09-12).
- Inner validation: signal dates 2025-09-15 through 2025-10-07 (17 sessions).
- Outer preholdout: signal dates 2025-10-08 through 2025-10-30 (17 sessions; targets through 2025-10-31).
- Locked holdout A: signal dates 2025-11-03 through 2025-11-28.
- Locked holdout B: signal dates 2025-12-01 through 2025-12-30.
- 2026 data remains a later independent extension and may not influence the November–December rule.

## Costs and implementation
- Primary cost: 10 basis points of portfolio NAV per completed trade.
- Stress cost: 20 basis points.
- A candidate must remain profitable at 20 basis points in every preholdout evaluation block.
- N=1,2,3 represents one, two or three equal-weight positions. No leverage benefit is assumed.
- Short candidates require the frozen shortable/easy-to-borrow eligibility. Borrow fees remain a deployment-level adverse stress because historical point-in-time borrow fees are unavailable.

## Discovery screen
A promotable candidate must satisfy all of the following in discovery:
1. N in {1,2,3} and at least 65 observed sessions.
2. Mean net return after 10 bp >= +0.15% per trade.
3. Median net return after 10 bp > 0.
4. Win rate after 10 bp > 55%.
5. Profit factor after 10 bp >= 1.50.
6. Naive daily t-statistic >= 4.25.
7. Mean net return after 20 bp > 0.
8. Mean residual return has the same sign as the gross candidate return.
9. No single day contributes more than 25% of total positive P&L.

The t-statistic is a screen only. Every survivor must subsequently pass a moving-block bootstrap and Benjamini–Hochberg false-discovery adjustment at q <= 5% across the full registered discovery universe.

## Inner-validation gate
Using the frozen definition without modification:
1. All 17 sessions must be represented unless an eligibility exclusion is explicitly audited; minimum 15 trades.
2. Mean net return after 10 bp >= +0.08%.
3. Median net return after 10 bp > 0.
4. Win rate after 10 bp > 52%.
5. Profit factor after 10 bp > 1.20.
6. Mean net return after 20 bp > 0.

## Outer-preholdout gate
Using the unchanged definition:
1. Minimum 15 trades.
2. Mean net return after 10 bp > 0.
3. Median net return after 10 bp > 0.
4. Win rate after 10 bp > 50%.
5. Mean net return after 20 bp > 0.

## Parameter-neighbour stability
The same feature, tail, target and direction must have at least one adjacent portfolio size with positive mean net return after 10 bp in discovery, inner validation and outer preholdout. Adjacent sizes are 1↔2, 2↔{1,3}, and 3↔{2,5}.

## Freeze and locked testing
- Rank final preholdout survivors by the minimum 10 bp mean across discovery, inner validation and outer preholdout, then by outer-preholdout median.
- Freeze at most three ancestry-distinct candidates before loading any November outcome.
- Holdout A is evaluated exactly once. A candidate must have positive 10 bp mean and median, win rate > 50%, and positive 20 bp mean to advance.
- Holdout B is evaluated exactly once only for Holdout-A survivors and uses the same gates.
- No feature, tail, direction, target, portfolio size, eligibility rule or cost assumption may be altered after a locked result.
