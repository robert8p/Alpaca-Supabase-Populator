# Prior-day two-state interaction → next-session intraday campaign — preregistration v1

## Purpose and adaptivity disclosure
Three lower-order daily families have now failed their preregistered discovery gates: 392 single-ETF tail rules, 42 cross-ETF rank books, and the preceding intraday basket programmes. This campaign is an explicitly adaptive but fully preregistered higher-order follow-up. It tests every pair of prior-day states in a fixed symmetric universe rather than selecting combinations around individual near-misses. The elevated screening threshold reflects the cumulative search burden. No 2022+ outcome may be queried until discovery survivors are frozen at the family level.

## Data and executable chronology
Source: `public.blankcanvas_adjusted_daily_features_v1` for DIA, GLD, HYG, QQQ, SPY, TLT and USO.

For each symbol and signal date D:
- all trigger features are observable at the regular-session close on D;
- enter the same ETF at the next regular-session open;
- exit at that session's regular-session close;
- no overnight position is held;
- phase assignment uses the target/entry date.

## Feature states
Seven prior-day features:
1. `intraday_ret_pct`
2. `day_ret_pct`
3. `gap_pct`
4. `ret5_pct`
5. `ret20_pct`
6. `range_pct`
7. `close_location`

Use the already frozen, discovery-only thresholds in `research.blankcanvas_daily_state_threshold_v1`, campaign `DAILY-STATE-20260813-V1`:
- `LOW20`: value <= frozen 20th percentile;
- `HIGH80`: value >= frozen 80th percentile.

Thresholds were frozen at 2026-08-13 02:08:02 UTC from 1,259 discovery observations per symbol-feature and are not recalibrated.

## Candidate universe
For each of seven symbols:
- choose each unordered pair of distinct features: C(7,2) = 21;
- assign each feature either `LOW20` or `HIGH80`: 4 joint states;
- choose direction long (+1) or short (-1): 2.

Registered definitions: **7 × 21 × 4 × 2 = 1,176**.

A trigger requires both states simultaneously. Net return is:
`direction × next-session open-to-close return − 0.10%`.

## Costs and constraints
- Primary round-trip friction: **10bp** of position notional.
- Sensitivity: 5bp.
- Adverse stress: 15bp.
- Minimum assumed position: £500.
- Short rules require an available liquid ETF or CFD borrow route; funding/borrow costs beyond 15bp invalidate deployment.

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
- no single discovery year contributes more than 35% of trades.

The t-statistic is only a familywise screening statistic. Any survivor requires dependence-aware inference and exact trade-ledger review.

## Inner-validation gate
Each of 2022 and 2023 must independently have:
- at least 4 trades;
- positive average net return.

Across 2022-2023 combined:
- at least 15 trades;
- positive average and median net return;
- profit factor > 1.20.

## Outer-2024 gate
At least 5 trades with positive average, positive median and profit factor > 1.00.

## Robustness before freeze
A candidate must additionally satisfy all of the following over 2022-2024:
- positive average at 15bp;
- positive result after removing its best trade;
- at least one stricter neighbouring interaction remains positive at 10bp, obtained by replacing one `LOW20` with frozen `LOW10`, or one `HIGH80` with frozen `HIGH90`, while leaving every other rule component unchanged;
- no calendar quarter contributes more than 45% of trades.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by minimum annual average across 2017-2024, then by 2022-2024 average at 10bp. Record candidate ID, numeric thresholds, exact rule, ancestry, effective and cumulative search counts, data snapshot and code commit before opening 2025.

A candidate may proceed from 2025 to 2026 YTD only if 2025 has at least 5 trades, positive average, positive median and profit factor > 1.00 at 10bp. The same conditions apply to 2026 YTD. No feature, state, threshold, direction, cost, entry or exit rule may change after either locked result.
