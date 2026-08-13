# Exact opening-time ETF leader/follower network — preregistration v1

## Purpose and adaptivity disclosure
The absolute opening-state and market-neutral opening-rank families failed decisively: none of the 90 cross-sectional books even had a positive discovery mean after 10bp. This campaign tests a different mechanism—directed information transmission during the opening minute. A completed opening state in source ETF S predicts the subsequent intraday return of distinct target ETF T. The complete directed network is tested; no source-target story is selected in advance.

No 2022+ outcome may be queried before discovery screening is complete. Raw 2025-2026 outcomes remain locked until a candidate passes discovery, 2022-2023 validation, 2024 outer validation and robustness, and is formally frozen.

## Fixed universe
DIA, HYG, QQQ, SPY, TLT and USO.

GLD is excluded solely for absent raw SIP opening bars in 2017-2019. This availability decision is fixed before candidate returns are calculated.

## Causal decision and exact execution
At 09:31 ET on trade date D:
- source ETF S's official gap and completed 09:30 bar are observable;
- target ETF T is distinct from S;
- enter T at its exact 09:31 minute open;
- exit T at the 10:00 close, 10:30 close or 15:59 close;
- no overnight exposure is held.

A 09:32-entry implementation is retained as a mandatory robustness test.

## Source predictors and frozen states
Five source predictors:
1. `gap_pct`;
2. `opening_return_pct`;
3. `opening_range_pct`;
4. `opening_close_location`;
5. `opening_log_dollar_volume_change` versus the source ETF's immediately preceding trading day.

For each source ETF and predictor, calibrate from 2017-2021 predictor values only and freeze:
- q10, q20, q80 and q90.

Primary states are `LOW20` and `HIGH80`. The stricter q10/q90 states are reserved for robustness and cannot replace the primary definition after validation.

## Candidate universe
- directed source-target pairs with source != target: 6 × 5 = 30;
- source predictors: 5;
- source states: LOW20 or HIGH80;
- target direction: long (+1) or short (-1);
- exits: 10:00, 10:30 or 15:59.

Registered definitions: **30 × 5 × 2 × 2 × 3 = 1,800**.

Net return is `direction × exact target 09:31-entry return − 0.10%`.

## Costs and constraints
- Primary round-trip friction: **10bp** of target notional.
- Sensitivity: 5bp.
- Adverse stress: 15bp.
- Minimum position: £500.
- Short candidates require a liquid ETF or CFD route; excess borrow/funding cost invalidates deployment.

## Time splits
- Discovery: 2017-2021.
- Inner validation: 2022-2023.
- Outer pre-holdout: 2024.
- Locked holdout 1: 2025.
- Locked holdout 2: 2026-01-01 through 2026-08-11.

## Discovery gate at 10bp
All conditions are mandatory:
- all five discovery years represented;
- at least 35 trades in every year and at least 220 pooled trades;
- positive annual average in at least four of five years;
- pooled average net return >= +0.15%;
- pooled median net return > 0;
- pooled profit factor >= 1.35;
- naive pooled t-statistic >= 4.80;
- worst annual average > -0.10%;
- no year contributes more than 25% of trades.

The elevated statistic reflects cumulative adaptivity and is screening only.

## Inner-validation gate
Both 2022 and 2023 must independently have at least 35 trades and positive average net return. Combined 2022-2023 must have positive average, positive median and profit factor > 1.15.

## Outer-2024 gate
At least 35 trades, positive average, positive median and profit factor > 1.00.

## Robustness, lag and placebo requirements before freeze
Over 2022-2024, a survivor must additionally show:
- positive average at 15bp;
- positive average after removing its best five trades;
- positive exact 09:32-entry average at 10bp;
- the stricter same-link q10/q90 state is positive at 10bp;
- a block-preserving shuffled-date placebo does not reproduce the mean;
- the reverse directed link is reported but cannot replace the frozen link;
- no quarter contributes more than 35% of trades;
- missing-bar, adjustment and early-close audits pass.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by minimum annual average across 2017-2024 and then by 2022-2024 average at 10bp. Record exact thresholds, directed link, full trade ledger, effective/cumulative search counts, data snapshot and code commit before opening 2025.

A candidate may advance from 2025 to 2026 YTD only if 2025 has at least 35 trades, positive average, positive median and profit factor > 1.00 at 10bp. The same conditions apply to 2026 YTD. No source, target, predictor, state, threshold, direction, exit, cost or entry timing may change after a locked result.
