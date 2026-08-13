# ETF opening gap + completed first-minute confirmation campaign — preregistration v1

## Purpose and adaptivity disclosure
The exact 09:31-entry gap-only family produced zero discovery survivors. This follow-up tests whether the completed 09:30 ET bar contains causal confirmation or rejection information. It is a fully enumerated interaction family, not a rescue of any specific gap near-miss. The multiple-testing threshold is raised for cumulative adaptivity.

No 2022+ outcome may be queried until discovery screening is complete. Raw 2025-2026 bars remain locked until a candidate passes all pre-holdout gates and is frozen.

## Universe, signal and exact execution
ETFs: DIA, GLD, HYG, QQQ, SPY, TLT and USO.

At 09:31 ET on trade date D:
- the adjusted official opening gap is known;
- the entire 09:30 minute bar is complete;
- enter at the exact 09:31 minute open;
- exit at the 10:00 close, 10:30 close or 15:59 close;
- no overnight exposure is held.

Data sources:
- gap: `public.blankcanvas_adjusted_daily_features_v1`;
- exact bars: `research.blankcanvas_etf_opening_point_v1`, sourced from SIP/raw monthly partitions.

## Frozen predictor states
### Gap state
For each symbol, use the already frozen same-day gap thresholds from `research.blankcanvas_etf_gap_threshold_v1`:
- `GAP_LOW20`: gap <= q20;
- `GAP_HIGH80`: gap >= q80.

### Completed 09:30-bar confirmation features
Calibrate symbol-specific discovery-only q20/q80 thresholds from 2017-2021 for four fixed features:
1. `opening_return_pct = 100 × (close_0930 / open_0930 − 1)`;
2. `opening_range_pct = 100 × (high_0930 / low_0930 − 1)`;
3. `opening_close_location = (close_0930 − low_0930) / (high_0930 − low_0930)`;
4. `opening_log_dollar_volume = ln(1 + coalesce(vwap_0930, close_0930) × volume_0930)`.

Each feature state is `LOW20` or `HIGH80`.

## Candidate universe
For each ETF:
- 2 gap states;
- 4 confirmation features;
- 2 confirmation states;
- 2 directions;
- 3 exits.

Registered definitions: **7 × 2 × 4 × 2 × 2 × 3 = 672**.

Net return is `direction × exact 09:31-entry return − 0.10%`.

## Costs and constraints
- Primary round-trip friction: 10bp.
- Sensitivity: 5bp.
- Adverse stress: 15bp.
- Minimum position: £500.
- Short candidates require an available liquid ETF or CFD borrow route; excess borrow/funding cost invalidates deployment.
- GLD definitions remain registered but cannot pass the five-year gate if early raw-minute coverage is absent.

## Time splits
- Discovery: 2017-2021.
- Inner validation: 2022-2023.
- Outer pre-holdout: 2024.
- Locked holdout 1: 2025.
- Locked holdout 2: 2026-01-01 through 2026-08-11.

## Discovery gate at 10bp
All conditions are mandatory:
- all five discovery years represented;
- at least 4 trades in every year and at least 40 pooled trades;
- positive annual average in at least four of five years;
- pooled average net return >= +0.25%;
- pooled median net return > 0;
- pooled profit factor >= 1.50;
- naive pooled t-statistic >= 4.70;
- worst annual average > -0.20%;
- no year contributes more than 35% of trades.

## Inner-validation gate
Each of 2022 and 2023 must independently have at least 4 trades and positive average net return. Combined 2022-2023 must have at least 15 trades, positive average, positive median and profit factor > 1.20.

## Outer-2024 gate
At least 5 trades, positive average, positive median and profit factor > 1.00.

## Robustness before freeze
Over 2022-2024, a survivor must additionally have:
- positive average at 15bp;
- positive average after removing its best trade;
- positive 09:32-entry average at 10bp;
- at least one stricter neighbouring state positive at 10bp, formed by tightening either the gap state to q10/q90 or the confirmation state to q10/q90;
- no calendar quarter contributing more than 45% of trades;
- split, adjustment, missing-bar and same-minute availability audits passing.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by minimum annual average across 2017-2024 and then 2022-2024 average at 10bp. Record exact thresholds, candidate ID, trade ledger, data snapshot, effective/cumulative search count and code commit before opening 2025.

A candidate may advance from 2025 to 2026 YTD only if 2025 has at least 5 trades, positive average, positive median and profit factor > 1.00 at 10bp. The same conditions apply to 2026 YTD. No symbol, gap state, confirmation feature/state, direction, exit, cost or entry timing may change after a locked result.
