# Two-day ETF state sequence → next-session intraday campaign — preregistration v1

## Purpose and adaptivity disclosure
The single-state, cross-sectional-rank and same-day two-state interaction families all failed their preregistered discovery gates. This campaign tests temporal ordering rather than additional contemporaneous conditioning. It is registered after those failures and therefore uses an elevated screening threshold. No 2022+ outcome may be queried before discovery screening is complete.

## Data and chronology
Source: `public.blankcanvas_adjusted_daily_features_v1` for DIA, GLD, HYG, QQQ, SPY, TLT and USO.

For a current signal date D and the immediately preceding trading date P:
- P is identified causally by `P.next_trade_date = D.signal_date`;
- the same feature's state is observed on P and D;
- both states are fully known by the regular-session close on D;
- enter the same ETF at the next regular-session open (`D.next_trade_date`);
- exit at that session's regular-session close;
- hold no overnight exposure;
- phase assignment uses the target/entry date.

## Features and frozen thresholds
Seven features:
1. `intraday_ret_pct`
2. `day_ret_pct`
3. `gap_pct`
4. `ret5_pct`
5. `ret20_pct`
6. `range_pct`
7. `close_location`

Use the frozen discovery-only symbol-feature thresholds from `research.blankcanvas_daily_state_threshold_v1`, campaign `DAILY-STATE-20260813-V1`:
- `LOW20`: value <= frozen 20th percentile;
- `HIGH80`: value >= frozen 80th percentile.

## Candidate universe
For each of seven symbols and seven features:
- prior-day state: `LOW20` or `HIGH80`;
- current-day state: `LOW20` or `HIGH80`;
- direction: long (+1) or short (-1).

Registered definitions: **7 × 7 × 2 × 2 × 2 = 392**.

Examples include LOW→LOW exhaustion, LOW→HIGH reversal, HIGH→LOW reversal and HIGH→HIGH continuation. No sequence is privileged before discovery.

Net return is `direction × next-session open-to-close return − 0.10%`.

## Costs and constraints
- Primary round-trip friction: 10bp.
- Sensitivity: 5bp.
- Adverse stress: 15bp.
- Minimum position: £500.
- Short candidates require an available liquid ETF or CFD borrow route; excess borrow/funding cost invalidates deployment.

## Time splits by target date
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
- naive pooled t-statistic >= 4.60;
- worst annual average > -0.20%;
- no year contributes more than 35% of trades.

## Inner-validation gate
Each of 2022 and 2023 must independently have at least 4 trades and positive average net return. Combined 2022-2023 must have at least 15 trades, positive average, positive median and profit factor > 1.20.

## Outer-2024 gate
At least 5 trades, positive average, positive median and profit factor > 1.00.

## Robustness before freeze
Over 2022-2024, every survivor must have:
- positive average at 15bp;
- positive average after removing its best trade;
- at least one stricter neighbour positive at 10bp, formed by tightening either sequence state from LOW20 to frozen LOW10 or HIGH80 to frozen HIGH90;
- no quarter contributing more than 45% of trades.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by minimum annual average across 2017-2024 and then 2022-2024 average at 10bp. Record exact thresholds, candidate ancestry, effective and cumulative search counts, data snapshot and code commit before opening 2025.

A candidate may advance from 2025 to 2026 YTD only if 2025 has at least 5 trades, positive average, positive median and profit factor > 1.00 at 10bp. The same conditions apply to 2026 YTD. No feature, sequence, threshold, direction, cost, entry or exit rule may change after a locked result.
