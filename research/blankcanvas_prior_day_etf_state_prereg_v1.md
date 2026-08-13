# Prior-day ETF state → next-session intraday campaign — preregistration v1

## Purpose and independence
This campaign begins only after the unconditional and SPY-state-conditioned cross-sectional basket campaigns produced zero discovery survivors under their preregistered gates. It is a structurally different family: observable information at the prior regular-session close is used to predict the same ETF's next-session open-to-close return. No 2025 or 2026 outcome statistic may be queried before a candidate is frozen under this protocol.

## Data and executable chronology
Source: `public.blankcanvas_adjusted_daily_features_v1` for DIA, GLD, HYG, QQQ, SPY, TLT and USO.

For each signal row at date D:
- all trigger features are known by the regular-session close on D;
- the target row is the same symbol on `next_trade_date`;
- entry is the next session's regular-session open;
- exit is that session's regular-session close;
- outcome is the target row's adjusted `intraday_ret_pct`;
- direction is long or short one liquid ETF;
- no overnight exposure is held.

The phase is assigned by the target/entry date, not the signal date, preventing a signal at a split boundary from leaking a later phase's outcome backward.

## Signal features
Seven fixed prior-day features:
1. `intraday_ret_pct`
2. `day_ret_pct`
3. `gap_pct`
4. `ret5_pct`
5. `ret20_pct`
6. `range_pct`
7. `close_location`

## Threshold calibration
For each symbol-feature pair, calibrate four thresholds using discovery signals whose target dates fall in 2017-2021:
- low 10th percentile;
- low 20th percentile;
- high 80th percentile;
- high 90th percentile.

The resulting numeric thresholds are persisted and frozen before any 2022+ outcome evaluation. Ties at a threshold are included.

## Registered candidate universe
For each of seven symbols × seven features × four tails × two directions:
- tail rule: `LOW10`, `LOW20`, `HIGH80`, or `HIGH90`;
- direction: long (+1) or short (-1);
- net return: `direction × next-day intraday return − 0.10%`.

Registered definitions: **392**. Effective definitions and missing-data exclusions will be audited.

## Costs and capacity
- Primary round-trip friction: **10 basis points** of position notional.
- Sensitivity: 5 bp.
- Adverse execution stress: 15 bp.
- Minimum assumed position: £500.
- Universe is restricted to highly liquid ETFs; no borrow constraint is assumed for long exposure. Short candidates require a liquid ETF/CFD borrow route and are rejected at deployment if unavailable or materially more expensive than the stress allowance.

## Time splits by target date
- Discovery: 2017-01-01 through 2021-12-31.
- Inner validation: 2022-01-01 through 2023-12-31.
- Outer pre-holdout: 2024-01-01 through 2024-12-31.
- Locked holdout 1: 2025-01-01 through 2025-12-31.
- Locked holdout 2: 2026-01-01 through 2026-08-11.

## Discovery gate
A candidate must satisfy all of the following at 10 bp:
- all five discovery years represented;
- at least 12 trades in every year;
- positive annual average in at least four of five years;
- pooled average net return ≥ +0.12%;
- pooled median net return > 0;
- pooled profit factor ≥ 1.25;
- naive pooled t-statistic ≥ 4.0.

The t-statistic is a screening statistic only. Any promoted candidate later requires dependence-aware uncertainty analysis.

## Inner-validation gate
Both 2022 and 2023 must independently have:
- at least 10 trades;
- positive average net return.

Across 2022-2023 combined, the candidate must have:
- positive average and median net return;
- profit factor > 1.10.

## Outer-2024 gate
2024 must have:
- at least 10 trades;
- positive average net return;
- positive median net return;
- profit factor > 1.00.

## Parameter-neighbour robustness
Before a candidate may be frozen, at least one adjacent tail definition with the same symbol, feature and direction must also have positive average net return across 2022-2024:
- `LOW10` ↔ `LOW20`;
- `HIGH80` ↔ `HIGH90`.

This is a robustness requirement, not permission to choose the better neighbour after seeing locked outcomes.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by the minimum annual average across 2017-2024 and then pooled 2022-2024 average. Candidate IDs, numeric thresholds, exact rule, ancestry, effective search count, data snapshot and code commit must be recorded before reading 2025.

A candidate may proceed from 2025 to 2026 YTD only when 2025 has:
- at least 10 trades;
- positive average and median net return;
- profit factor > 1.00 at 10 bp.

The 2026 YTD pass uses the same conditions. No symbol, feature, quantile, threshold, direction, entry, exit or cost assumption may be changed in response to either locked result.
