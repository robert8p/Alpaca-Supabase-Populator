# Causal gap-state transmission network → ETF overnight baskets — preregistration v1

## Purpose and independence

The simple opening-gap rank campaign produced zero discovery survivors under its preregistered gate. This campaign is a structurally different online-learning family. It estimates how the current opening-gap state of each source ETF historically transmitted into each target ETF's subsequent close-to-next-open return, using prior observations only. It then combines those source forecasts into a target ranking available well before the closing auction.

No 2022+ candidate outcome is queried until the discovery gate is applied exactly as registered.

## Data and chronology

Source: `public.blankcanvas_cross_sectional_states_v1`, `feature='gap'`, for DIA, GLD, HYG, QQQ, SPY, TLT and USO.

For signal session D:

1. Each source ETF's opening gap is observable at the regular-session open.
2. For every source-target-state mapping, calculate rolling conditional statistics using only earlier sessions; the current outcome is excluded by `ROWS BETWEEN H PRECEDING AND 1 PRECEDING`.
3. The prior session's overnight outcome is already known at D's open, so all rolling inputs are available on D.
4. Aggregate source experts into one forecast per target ETF.
5. Rank the seven target forecasts.
6. Submit market-on-close entries by 15:45 ET on D.
7. Exit all positions with market-on-open orders at the next regular-session open.

Maximum holding period is one market overnight, including intervening weekends and holidays. No position remains after the next opening auction.

## Frozen source gap states

The current source gap is placed into one of six mutually exclusive percentage-point states:

- `G_LT_M1`: gap < -1.00%;
- `G_M1_M0_5`: -1.00% <= gap < -0.50%;
- `G_M0_5_0`: -0.50% <= gap < 0%;
- `G_0_0_5`: 0% <= gap < +0.50%;
- `G_0_5_1`: +0.50% <= gap < +1.00%;
- `G_GE_1`: gap >= +1.00%.

These bins were selected from discovery-period frequency structure only, before any network return was calculated.

## Rolling expert statistics

Occurrence lookbacks H in {10,20,40}. For each source ETF, target ETF and current source state, use the latest H prior occurrences of that same source state to calculate:

- conditional mean target overnight return;
- sample standard deviation;
- observation count.

An expert is eligible only when its count equals H. No partial-window estimate is used.

## Source scopes

Four fixed source pools:

- `ALL7`: all seven sources; require at least four eligible experts;
- `CROSS6`: all sources except the target itself; require at least three eligible experts;
- `RISK4`: DIA, HYG, QQQ and SPY; require at least three eligible experts;
- `MACRO3`: GLD, TLT and USO; require at least two eligible experts.

## Target forecast methods

For the eligible source experts of each target:

1. `AVG_MEAN`: arithmetic mean of conditional-return means.
2. `MEDIAN_MEAN`: median of conditional-return means.
3. `PRECISION_MEAN`: weighted mean with weight `1 / (sd^2 + 0.0625)`, equivalent to a 0.25 percentage-point volatility floor.

## Candidate basket universe

For each H, source scope, forecast method, K in {1,2,3}, style and activation:

- rank all seven target forecasts, breaking ties alphabetically;
- `DIRECT`: long the top-K forecasts and short the bottom-K forecasts;
- `REVERSE`: long the bottom-K and short the top-K;
- use 50% total long and 50% total short notional, equally weighted within each side;
- `ALWAYS`: trade whenever all seven target forecasts are available;
- `SPAN_ZERO`: trade only when the maximum forecast is positive and the minimum forecast is negative.

Registered definitions: **3 lookbacks × 4 scopes × 3 methods × 3 K values × 2 styles × 2 activation modes = 432**.

Candidate ID is the MD5 of `GAP-NET-OVERNIGHT-20260813-V1|H|scope|method|K|style|activation`.

## Execution and cost assumptions

- Primary round-trip portfolio friction: 10 basis points.
- Sensitivity: 5 basis points.
- Adverse execution/funding stresses: 15 and 20 basis points.
- Total gross exposure is normalised to 100%.
- Minimum leg size: £500; K=3 requires at least £3,000 gross leg capacity and fractional CFDs or sufficiently divisible ETF holdings.
- Every short leg requires confirmed ETF/CFD availability. Any unavailable borrow, halt, missing auction price, missing seven-target forecast, or split-like event not neutralised by adjusted data invalidates the book before entry.
- A rule is not deployment-ready when actual commission, spread, slippage, overnight funding or borrow is expected to exceed the 20bp stress allowance.

## Time splits by signal/closing-entry date

- Warm-up history: 2016-01-01 through 2016-12-31, never scored.
- Discovery: 2017-01-01 through 2021-12-31.
- Inner validation: 2022-01-01 through 2023-12-31.
- Outer pre-holdout: 2024-01-01 through 2024-12-31.
- Locked holdout 1: 2025.
- Locked holdout 2: 2026-01-01 through 2026-08-10.

## Discovery gate at 10bp

All conditions are mandatory:

- all five discovery years represented;
- at least 250 pooled books and at least 30 books in every year;
- positive annual average in at least four of five years;
- pooled average net return >= +0.08%;
- pooled median net return > 0;
- pooled profit factor >= 1.30;
- naive pooled t-statistic >= 4.80;
- worst annual average > -0.08%;
- no single year contributes more than 35% of books.

The high screening threshold reflects 432 registered definitions plus the cumulative adaptive search ancestry. It is not treated as independent confirmatory evidence.

## Inner-validation gate

For each of 2022 and 2023 separately:

- at least 30 books;
- positive average net return at 10bp.

Across both years combined:

- at least 100 books;
- positive average and median;
- profit factor > 1.10.

## Outer-2024 gate

At least 30 books, positive average, positive median and profit factor > 1.00 at 10bp.

## Robustness gates before freeze

A candidate must additionally pass all of the following using only 2017–2024:

1. Positive 2022–2024 combined average at 15bp.
2. Positive 2022–2024 total after removing the best trade.
3. At least one adjacent lookback or K value has positive 2022–2024 average at 10bp with all other components fixed.
4. No calendar quarter contributes more than 45% of 2022–2024 books.
5. No single source expert supplies more than 50% of total precision weight on more than 20% of candidate dates.
6. A 1,000-run circular date-shift placebo gives a one-sided empirical p-value below 0.01 for the 2017–2024 mean.
7. Exact ledgers, drawdown, constituent concentration, forecast dispersion, weekend/holiday performance and 5/10/15/20bp cost results are audited.

## Freeze and locked evaluation

Freeze no more than three candidates, ranked by minimum annual average across 2017–2024 and then 2022–2024 average at 10bp. Before opening 2025, record the exact rule, source-state bins, candidate ID, ancestry, registered/effective/cumulative search counts, data snapshot, SQL/code commit, forecast ledger and trade ledger.

A candidate may proceed from 2025 to 2026 only when 2025 has at least 30 books, positive average and median, profit factor > 1.00 and positive total after removing its best trade at 10bp. The same conditions apply to 2026 YTD. No lookback, state bin, scope, method, K, style, activation, cost, entry or exit rule may be changed after a locked result.
