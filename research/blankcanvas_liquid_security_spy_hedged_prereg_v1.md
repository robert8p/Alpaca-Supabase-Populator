# Liquid-security selection versus SPY next-session intraday campaign — preregistration v1

## Purpose and adaptivity disclosure
The prior-day market-neutral top-versus-bottom security books produced zero discovery survivors at 20bp. This follow-up isolates the selected tail's relative performance against one highly liquid hedge rather than forcing the opposite security tail to carry alpha. It removes multi-name stock-borrow dependence: selected securities are long and SPY is the only short instrument.

The family is preregistered after the earlier failure and uses the same elevated familywise screening threshold. No 2022+ outcome statistic may be queried before discovery screening is complete. 2025-2026 remain locked until a rule passes all pre-holdout gates and is frozen.

## Causal universe and execution
Use the already constructed discovery panel `research.blankcanvas_liquid_security_daily_panel_v1`, sourced only from historical SIP/raw regular-session daily features.

Selection eligibility on signal date D:
- symbol matches `^[A-Z]{1,5}$`;
- symbol is not SPY, because SPY has the fixed hedge role;
- at least 300 signal-session bars;
- prior close >= $10;
- prior-day dollar volume meets the candidate's fixed tier;
- the security and SPY both have complete rows on the exact next SPY market date.

After D's close:
- rank eligible securities by one prior-day feature;
- select the bottom K or top K;
- at the next market open, allocate 50% gross long equally across selected securities and 50% gross short SPY;
- exit every leg at the same session's final regular-session close;
- hold no overnight exposure.

## Predictors
Nine completed prior-session features:
1. `return_pct`;
2. `first_hour_return_pct`;
3. `last_hour_return_pct`;
4. `range_pct`;
5. `close_location`;
6. `intraday_volatility`;
7. `up_bar_share`;
8. `volume_first_hour_share`;
9. `trade_count_first_hour_share`.

## Candidate universe
For each predictor:
- prior-day minimum dollar volume: $20m, $50m or $100m;
- K = 1, 3, 5 or 10 selected securities;
- selected tail: bottom K or top K.

Registered definitions: **9 × 3 × 4 × 2 = 216**.

Gross portfolio return is:
`0.5 × average(selected-security intraday return) − 0.5 × SPY intraday return`.

Net return subtracts 0.20 percentage points.

## Costs, capital and constraints
- Primary round-trip friction: **20bp of portfolio NAV**.
- Sensitivity: 10bp.
- Adverse stress: 30bp.
- Minimum selected-security leg: £500.
- K=10 allocates £500 to each selected security and £5,000 short SPY at £10,000 gross notional, matching the capital envelope.
- Only SPY borrow/CFD availability is required; excess hedge funding cost beyond the 30bp adverse allowance invalidates deployment.

## Time splits by target date
- Discovery: 2017-2021.
- Inner validation: 2022-2023.
- Outer pre-holdout: 2024.
- Locked holdout 1: 2025.
- Locked holdout 2: 2026-01-01 through 2026-08-11.

## Discovery gate at 20bp
All conditions are mandatory:
- all five discovery years represented;
- at least 240 complete books in every year;
- positive annual average in at least four of five years;
- pooled average net return >= +0.08%;
- pooled median net return > 0;
- pooled profit factor >= 1.25;
- naive pooled t-statistic >= 5.00;
- worst annual average > -0.05%;
- no year contributes more than 22% of books;
- no selected security appears in more than 25% of discovery books.

## Inner-validation gate
Both 2022 and 2023 must independently have at least 240 books and positive average net return. Combined 2022-2023 must have positive average, positive median and profit factor > 1.15 at 20bp.

## Outer-2024 gate
At least 240 books with positive average, positive median and profit factor > 1.05 at 20bp.

## Robustness before freeze
A survivor must additionally satisfy over 2022-2024:
- positive average at 30bp;
- positive average after removing its best ten books;
- an adjacent K value, when available, is positive at 20bp;
- an adjacent liquidity tier, when available, is positive at 20bp;
- no quarter contributes more than 12% of books;
- no security contributes more than 20% of positive P&L;
- replacing SPY with an unhedged zero-return placebo does not improve the inferred alpha merely through market beta;
- a one-day delayed-selection placebo does not preserve the edge;
- missing-path, halt, symbol-event and split-like audits pass.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by minimum annual average across 2017-2024 and then 2022-2024 average at 20bp. Record exact rule, constituent ledger, exclusions, effective/cumulative search counts, data snapshot and code commit before opening 2025.

A candidate advances from 2025 to 2026 YTD only if 2025 has positive average, positive median and profit factor > 1.05 at 20bp. The same conditions apply to 2026 YTD. No predictor, tier, K, selected tail, cost, universe rule, hedge, entry or exit may change after a locked result.
