# Opening-gap rank → close-to-next-open ETF campaign — preregistration v1

## Purpose and independence

This is a new executable family registered after the earlier TLT–USO holdout failure and after the unconditional intraday basket, SPY-state basket, daily single-state, daily rank and two-state interaction families produced no promoted candidate. It does not tune any failed rule. No 2022+ outcome statistic may be queried until the discovery gate below has been applied exactly as written.

## Data and causal chronology

Source panel: `public.blankcanvas_cross_sectional_states_v1`, restricted to `feature='gap'`.

For every U.S. market session D:

1. At the regular-session open, compute each ETF's opening gap versus its adjusted prior close.
2. Rank the seven-ETF universe by that gap. `r_hi=1` is the largest gap and `r_lo=1` the smallest gap. Ties are resolved by the source panel's deterministic rank ordering.
3. The gap ranks and cross-sectional dispersion are fixed from the open and therefore known well before the closing-auction order cutoff.
4. Submit the selected market-on-close orders no later than 15:45 ET on D.
5. Enter at the official regular-session close on D.
6. Submit market-on-open exits for the next regular session and exit at its official open.

The maximum holding period is one market overnight, including intervening weekends and holidays. No position is retained after the next opening auction.

The panel's `next_overnight_pct` has been verified to equal the target ETF's adjusted close-to-next-open return. A book is eligible only when all seven ETFs, all seven ranks and all seven outcomes are present.

## Instrument universe

DIA, GLD, HYG, QQQ, SPY, TLT and USO.

## Gap-dispersion regimes

The numerical cross-sectional spread is `max(gap) - min(gap)`, in percentage points. Six mutually specified scopes are registered:

- `ALL`: no dispersion filter;
- `S_LT_0_5`: spread < 0.50;
- `S_0_5_1`: 0.50 <= spread < 1.00;
- `S_1_2`: 1.00 <= spread < 2.00;
- `S_2_5`: 2.00 <= spread < 5.00;
- `S_GE_5`: spread >= 5.00.

Discovery-only structural counts before outcome analysis are 1,259 complete sessions: 61, 330, 533, 289 and 46 sessions in the five finite regimes respectively.

## Candidate implementation universe

For each regime and each side size K in {1,2,3}, test exactly six book constructions:

1. `REV_LS`: long the bottom-K gaps and short the top-K gaps; 50% total long notional and 50% total short notional.
2. `CONT_LS`: long the top-K gaps and short the bottom-K gaps; 50% total long and 50% total short.
3. `LONG_TOP`: 100% equally weighted long the top-K gaps.
4. `LONG_BOTTOM`: 100% equally weighted long the bottom-K gaps.
5. `SHORT_TOP`: 100% equally weighted short the top-K gaps.
6. `SHORT_BOTTOM`: 100% equally weighted short the bottom-K gaps.

Registered definitions: **6 regimes × 3 K values × 6 constructions = 108**.

Candidate IDs are the MD5 of `GAP-OVERNIGHT-20260813-V1|regime|K|construction`.

## Costs, sizing and execution assumptions

- Primary round-trip portfolio friction: **10 basis points**.
- Cost sensitivity: 5 basis points.
- Execution/funding stress: 15 and 20 basis points.
- The cost deduction applies once to portfolio NAV, with total gross exposure normalised to 100% for every construction.
- Long/short baskets are equally weighted within each side.
- Minimum leg size assumption: £500.
- K=3 therefore requires at least £3,000 of gross leg capacity and either fractional CFD sizing or sufficiently divisible ETF positions.
- Short constructions require confirmed ETF/CFD availability. A candidate is not deployment-ready if borrow, overnight funding or auction slippage causes realised total friction to exceed the registered stress allowance.
- Any missing auction price, split-like discontinuity not neutralised by adjusted data, unavailable short leg, halt, or missing seven-asset rank invalidates that day's book before entry.

## Time splits by signal/entry-close date

- Discovery: 2017-01-01 through 2021-12-31.
- Inner validation: 2022-01-01 through 2023-12-31.
- Outer pre-holdout: 2024-01-01 through 2024-12-31.
- Locked holdout 1: 2025-01-01 through 2025-12-31.
- Locked holdout 2: 2026-01-01 through 2026-08-10.

The 2025 and 2026 outcomes remain locked until a candidate has passed every preceding gate and has been frozen.

## Discovery gate at 10 basis points

All conditions are mandatory:

- all five discovery years represented;
- for `ALL`, at least 240 eligible books in every year;
- for a dispersion regime, at least 40 pooled books and at least 4 books in every year;
- positive annual average net return in at least four of five years;
- pooled average net return >= +0.12%;
- pooled median net return > 0;
- pooled profit factor >= 1.35;
- naive pooled t-statistic >= 4.50;
- worst annual average net return > -0.10%;
- no single discovery year contributes more than 35% of pooled books.

The t-statistic is a screening statistic only. It is not treated as independent evidence after the cumulative adaptive research programme.

## Inner-validation gate

For both 2022 and 2023 separately:

- the annual average net return at 10bp must be positive;
- `ALL` must contain at least 240 books per year;
- a dispersion-conditioned rule must contain at least 4 books per year.

Across 2022–2023 combined:

- average and median net return must be positive;
- profit factor must exceed 1.10;
- at least 15 books are required for a conditioned rule.

## Outer-2024 gate

At 10bp, 2024 must have positive average, positive median and profit factor above 1.00. `ALL` requires at least 240 books; a conditioned rule requires at least 5.

## Robustness gates before freeze

A candidate must additionally pass all of the following using only 2017–2024 data:

1. 2022–2024 combined average remains positive at 15bp.
2. 2022–2024 combined return remains positive after removing the single best trade.
3. At least one adjacent K value, when available, or one adjacent dispersion regime has positive 2022–2024 average at 10bp with the same construction.
4. No calendar quarter contributes more than 45% of the candidate's 2022–2024 books.
5. A 1,000-run within-date rank-permutation placebo gives an empirical one-sided p-value below 0.01 for the candidate's 2017–2024 mean.
6. Results are reported for 5bp, 10bp, 15bp and 20bp; the rule is not changed in response to cost sensitivity.
7. Exact trade ledger, winner/loser distribution, drawdown, holiday/weekend split, direction exposure and constituent concentration are audited.

## Freeze and locked evaluation

Freeze no more than three candidates, ranked first by minimum annual average across 2017–2024 and then by 2022–2024 average at 10bp. Before reading 2025, record candidate ID, exact implementation, ancestry, registered and effective search count, thresholds, data snapshot, code/SQL commit and full pre-holdout trade ledger.

A candidate may proceed from 2025 to 2026 only when 2025 has:

- the preregistered minimum sample;
- positive average and median net return at 10bp;
- profit factor > 1.00;
- positive total net return after removing its best trade.

The same conditions apply to 2026 YTD. No regime, K, construction, cost, entry, exit, sizing, ranking or constituent rule may be altered after either locked result.
