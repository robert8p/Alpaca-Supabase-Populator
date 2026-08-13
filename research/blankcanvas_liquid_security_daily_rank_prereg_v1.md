# Liquid US-listed security prior-day rank → next-session intraday campaign — preregistration v1

## Purpose and adaptivity disclosure
The fixed-ETF daily and opening families have been exhausted without a discovery survivor under their preregistered gates. This campaign widens breadth to the full SIP/raw daily feature store while remaining low-dimensional and executable. It tests cross-sectional prior-day states across the securities that actually traded on each historical date; it does not use current asset status or a current constituent list.

The screening threshold reflects the cumulative adaptive search across earlier campaigns. No 2022+ outcome statistic may be queried before discovery screening is complete. 2025-2026 remain locked until a candidate passes discovery, 2022-2023 validation, 2024 outer validation and robustness, and is formally frozen.

## Point-in-time universe and chronology
Source table: `public.rd_daily_features` with:
- timeframe = `1Min`;
- feed = `sip`;
- adjustment = `raw`;
- session_label = `regular`.

A security is eligible on signal date D solely from information observable by D's regular-session close:
- symbol matches `^[A-Z]{1,5}$`;
- at least 300 regular-session minute bars;
- prior close >= $10;
- prior-day dollar volume meets the candidate's fixed liquidity tier.

The next market session is defined from the historical SPY trading calendar. A trade is included only when the same security has a complete row on that exact next market date; this prevents a halt, suspension or missing session from being silently treated as a delayed fill.

Execution:
- rank eligible securities after the close on D;
- submit next-session opening orders;
- enter at the target session's exact first regular-session open;
- exit at its exact final regular-session close;
- require at least 300 target-session minute bars;
- hold no overnight exposure.

The universe therefore contains whatever qualifying US-listed securities were genuinely observable on each date. ETFs, ADRs and ordinary shares are not selected by future metadata; deployment later requires instrument-type and borrow checks for every constituent.

## Prior-day predictors
Nine fixed completed-session features:
1. `return_pct`;
2. `first_hour_return_pct`;
3. `last_hour_return_pct`;
4. `range_pct`;
5. `close_location`;
6. `intraday_volatility`;
7. `up_bar_share`;
8. `volume_first_hour_share`;
9. `trade_count_first_hour_share`.

No target-session value enters a predictor.

## Candidate universe
For each predictor:
- prior-day minimum dollar-volume tier: $20m, $50m or $100m;
- K = 1, 3, 5 or 10 securities per side;
- reversal: long bottom K, short top K;
- continuation: long top K, short bottom K.

Weights are 50% total long and 50% total short, equally weighted within each side. Ties are resolved alphabetically by symbol.

Registered definitions: **9 × 3 × 4 × 2 = 216**.

Net return is `style × reversal book return − 0.20%`, where style +1 is reversal and -1 is continuation.

## Execution costs, size and liquidity
- Primary round-trip friction: **20bp of portfolio NAV**.
- Sensitivity: 10bp.
- Adverse stress: 30bp.
- Minimum leg size: £500.
- K=10 uses twenty £500 legs and therefore exactly £10,000 gross notional; larger K values are excluded as incompatible with the capital envelope.
- At the loosest $20m prior-day dollar-volume tier, a £500 leg is immaterial participation; nevertheless, open-auction concentration and realised spread risk remain subject to later stress testing.
- Short constituents require borrow/CFD availability. A candidate is not deployable when constituent borrow or funding cannot be sourced within the 30bp adverse allowance.

## Time splits by target/entry date
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
- no single security appears on either side in more than 25% of discovery books.

The t-statistic is a familywise screening statistic only. Any survivor requires block bootstrap and dependence-aware uncertainty analysis.

## Inner-validation gate
Both 2022 and 2023 must independently have at least 240 books and positive average net return. Combined 2022-2023 must have positive average, positive median and profit factor > 1.15 at 20bp.

## Outer-2024 gate
At least 240 books with positive average, positive median and profit factor > 1.05 at 20bp.

## Robustness before freeze
A survivor must additionally satisfy over 2022-2024:
- positive average at 30bp;
- positive average after removing its best ten books;
- at least one adjacent K value, when available, has positive average at 20bp;
- at least one adjacent liquidity tier, when available, has positive average at 20bp;
- no quarter contributes more than 12% of books;
- no single security contributes more than 20% of total positive P&L;
- one-day delayed-entry placebo does not preserve the edge;
- reversed predictor ranks do not recreate the same directional result;
- missing-path, halt, symbol-event, split-like and early-close audits pass.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked first by minimum annual average across 2017-2024 and then by 2022-2024 average at 20bp. Record exact rule, constituent book ledger, exclusions, effective and cumulative search counts, data snapshot and code commit before opening 2025.

A candidate may advance from 2025 to 2026 YTD only if 2025 has positive average, positive median and profit factor > 1.05 at 20bp. The same conditions apply to 2026 YTD. No predictor, liquidity tier, K, style, cost, universe rule, entry or exit may change after a locked result.
