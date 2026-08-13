# Daily cross-asset leader/follower network → next-session intraday campaign — preregistration v1

## Purpose and adaptivity disclosure
Same-symbol states, cross-sectional ranks, contemporaneous interactions and two-day sequences all failed their preregistered discovery gates. This campaign tests information transmission across assets: whether the close-time state of one liquid ETF predicts a different ETF's next-session open-to-close return. It is a complete directed network, not a hand-picked macro hypothesis. No 2022+ outcome may be queried before discovery screening is complete.

## Data and causal chronology
Source: `public.blankcanvas_adjusted_daily_features_v1` for DIA, GLD, HYG, QQQ, SPY, TLT and USO.

For source ETF S and target ETF T on signal date D:
- S's feature state is fully observable at the regular-session close on D;
- T is entered at its next regular-session open on `D.next_trade_date`;
- T is exited at that session's regular-session close;
- no overnight position is held;
- S and T must be different ETFs;
- phase assignment uses T's target/entry date.

## Source features and states
Seven source features:
1. `intraday_ret_pct`
2. `day_ret_pct`
3. `gap_pct`
4. `ret5_pct`
5. `ret20_pct`
6. `range_pct`
7. `close_location`

Use the source ETF's frozen discovery-only thresholds from `research.blankcanvas_daily_state_threshold_v1`, campaign `DAILY-STATE-20260813-V1`:
- `LOW20`: source value <= frozen 20th percentile;
- `HIGH80`: source value >= frozen 80th percentile.

## Candidate universe
- directed source-target pairs with source != target: 7 × 6 = 42;
- source features: 7;
- source states: LOW20 or HIGH80;
- target direction: long (+1) or short (-1).

Registered definitions: **42 × 7 × 2 × 2 = 1,176**.

Net return is `direction × target next-session open-to-close return − 0.10%`.

## Costs and constraints
- Primary round-trip friction: 10bp.
- Sensitivity: 5bp.
- Adverse stress: 15bp.
- Minimum target position: £500.
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
- at least 35 trades in every year and at least 220 pooled trades;
- positive annual average in at least four of five years;
- pooled average net return >= +0.15%;
- pooled median net return > 0;
- pooled profit factor >= 1.35;
- naive pooled t-statistic >= 4.60;
- worst annual average > -0.10%;
- no year contributes more than 25% of trades.

## Inner-validation gate
Each of 2022 and 2023 must independently have at least 35 trades and positive average net return. Combined 2022-2023 must have positive average, positive median and profit factor > 1.15.

## Outer-2024 gate
At least 35 trades, positive average, positive median and profit factor > 1.00.

## Robustness, network and placebo requirements before freeze
Over 2022-2024 a survivor must additionally show:
- positive average at 15bp;
- positive average after removing its best trade;
- the stricter same-link neighbour (`LOW10` for LOW20 or `HIGH90` for HIGH80) is positive at 10bp;
- the signal decays rather than strengthens when the same source state is applied to the target's second subsequent session;
- shuffled source dates do not reproduce the observed mean in a block-preserving placebo;
- no calendar quarter contributes more than 35% of trades.

The directed source-target network and reverse link are reported; the reverse link cannot replace or rescue the frozen direction.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by minimum annual average across 2017-2024 and then 2022-2024 average at 10bp. Record exact thresholds, directed link, ancestry, effective and cumulative search counts, data snapshot and code commit before opening 2025.

A candidate may advance from 2025 to 2026 YTD only if 2025 has at least 35 trades, positive average, positive median and profit factor > 1.00 at 10bp. The same conditions apply to 2026 YTD. No source, target, feature, state, threshold, direction, cost, entry or exit rule may change after a locked result.
