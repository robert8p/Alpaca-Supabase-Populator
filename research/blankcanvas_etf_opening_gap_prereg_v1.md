# ETF opening-gap → 09:31 entry intraday campaign — preregistration v1

## Purpose and independence
All prior-close daily state families tested so far have failed their preregistered discovery gates. This campaign moves the decision point to the next session's opening print and uses exact minute-bar execution. It does not assume that a trader can observe the official open and fill at that same price.

No 2022+ outcome may be queried until discovery screening is complete. Raw 2025-2026 minute bars remain locked until a candidate passes discovery, 2022-2023 validation and 2024 outer validation and is formally frozen.

## Universe and data
ETFs: DIA, GLD, HYG, QQQ, SPY, TLT and USO.

Signal source:
- same-day adjusted `gap_pct` from `public.blankcanvas_adjusted_daily_features_v1`, observable once the official regular-session opening print occurs;
- symbol-specific predictor thresholds calibrated only from 2017-2021 gap values and frozen before outcomes are examined.

Execution source:
- exact SIP/raw regular-session minute bars from monthly `public.rd_bars_YYYYMM` partitions;
- decision after the 09:30 ET bar/official opening print is observable;
- entry at the **09:31 ET minute open**;
- exits at the **10:00 ET close**, **10:30 ET close**, or **15:59 ET close**.

Every event requires all necessary prices. Early-close dates are eligible for 10:00/10:30 exits but excluded from the close-exit definition when 15:59 is absent.

## Predictor thresholds
For each ETF, calibrate and freeze:
- `LOW10`: gap <= 10th percentile;
- `LOW20`: gap <= 20th percentile;
- `HIGH80`: gap >= 80th percentile;
- `HIGH90`: gap >= 90th percentile.

Calibration uses only signal dates 2017-2021 and does not read future returns.

## Candidate universe
For each of seven ETFs:
- four gap tails;
- direction long (+1) or short (-1);
- three exits: 10:00, 10:30, 15:59.

Registered definitions: **7 × 4 × 2 × 3 = 168**.

Net return is `direction × exact(entry-to-exit return) − 0.10%`.

## Costs and constraints
- Primary round-trip friction: **10bp**.
- Sensitivity: 5bp.
- Adverse stress: 15bp.
- Entry is the next minute's open, never the signal bar's open or close.
- Minimum position: £500.
- Short candidates require a liquid ETF or CFD borrow route; excess borrow/funding cost invalidates deployment.

## Time splits by signal/entry date
- Discovery: 2017-2021.
- Inner validation: 2022-2023.
- Outer pre-holdout: 2024.
- Locked holdout 1: 2025.
- Locked holdout 2: 2026-01-01 through 2026-08-11.

## Discovery gate at 10bp
All conditions are mandatory:
- all five discovery years represented;
- at least 20 trades in every year and at least 100 pooled trades;
- positive annual average in at least four of five years;
- pooled average net return >= +0.15%;
- pooled median net return > 0;
- pooled profit factor >= 1.35;
- naive pooled t-statistic >= 4.60;
- worst annual average > -0.10%;
- no year contributes more than 25% of trades.

## Inner-validation gate
Each of 2022 and 2023 must independently have at least 20 trades and positive average net return. Combined 2022-2023 must have positive average, positive median and profit factor > 1.15.

## Outer-2024 gate
At least 20 trades, positive average, positive median and profit factor > 1.00.

## Robustness before freeze
A survivor must additionally satisfy:
- positive 2022-2024 average at 15bp;
- positive 2022-2024 average after removing its best trade;
- its adjacent tail (`LOW10`↔`LOW20`, `HIGH80`↔`HIGH90`) is positive over 2022-2024 at 10bp;
- entry delayed to 09:32 remains positive over 2022-2024 at 10bp;
- no quarter contributes more than 35% of trades;
- split/adjustment and missing-bar audits pass.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by minimum annual average across 2017-2024 and then 2022-2024 average at 10bp. Record exact thresholds, candidate ID, trade ledger, data snapshot, effective/cumulative search count and code commit before opening 2025.

A candidate may advance from 2025 to 2026 YTD only if 2025 has at least 20 trades, positive average, positive median and profit factor > 1.00 at 10bp. The same conditions apply to 2026 YTD. No symbol, tail, direction, exit, cost or entry timing may change after a locked result.
