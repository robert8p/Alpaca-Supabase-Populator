# Gap-state transmission network — final pre-holdout freeze v1

Frozen before any 2025 or 2026 candidate outcome was queried.

## Identity and immutable lineage

- Campaign: `GAP-NET-OVERNIGHT-20260813-V1`
- Candidate ID: `28435b84e236643912497a40cc8c8f16`
- Preregistration commit: `48ce9496b9e147ef7585cbcd570a06432246914b`
- Discovery-freeze commit: `5fd752ba9ce12ff36db81388be939a41d7e68294`
- Inner-validation-freeze commit: `16fe43031685454e452528213e214d0ae3b1096e`
- Immutable reconstruction SQL commit: `80fabfd2a3225a94ad57b4f07c86f514f3ff60cc`
- Reconstruction function: `research.blankcanvas_gap_network_candidate_events_v1(date,date)`
- Registered family definitions: 432
- Effective family definitions: 432
- Minimum known cumulative registered search ancestry: 6,902 definitions; this is a lower bound.

The immutable function was executed on 2024 and reproduced the frozen 2024 ledger exactly: 252 rows rebuilt, zero missing rows, zero additional rows, zero mismatches and maximum net-return difference of 0.

## Exact executable rule

At the regular-session open on signal day D:

1. Put each of DIA, GLD, HYG, QQQ, SPY, TLT and USO into one of the six frozen opening-gap states: `<-1%`, `[-1,-0.5%)`, `[-0.5,0%)`, `[0,0.5%)`, `[0.5,1%)`, `>=1%`.
2. For each target ETF and each RISK4 source—DIA, HYG, QQQ and SPY—retrieve the 40 latest prior occurrences of that source's current gap state. The current outcome is excluded.
3. For each eligible source→target expert, calculate the prior conditional mean target close-to-next-open return and sample standard deviation.
4. Weight each expert by `1/(sd²+0.0625)`. Require at least three eligible source experts per target.
5. Require forecasts for all seven target ETFs.
6. Trade only when the maximum forecast is positive and the minimum forecast is negative.
7. Long the single ETF with the lowest forecast and short the single ETF with the highest forecast.
8. Allocate 50% gross notional to each leg.
9. Submit market-on-close entry orders no later than 15:45 ET; enter at the official close.
10. Submit market-on-open exits for the next regular session; exit at the official open.

Maximum holding period is one market overnight, including weekends or holidays. No position remains after the next opening auction.

Primary round-trip portfolio friction is 10bp. Recorded stresses are 5bp, 15bp and 20bp. Missing seven-target forecast, unavailable short, halt, missing auction price or unresolved corporate action invalidates the book before entry.

## Frozen data snapshot

- Snapshot ID: `f6bc8a50f10f2911c259fc1cbdd7b8a4`
- Pre-holdout trade-ledger MD5: `440d44316f34b054ea70692c8940cab3`
- Candidate forecast-ledger MD5: `a6027a388490b00fd5df646e09bcbf06`
- Discovery expert-ledger MD5: `306a399d4de607e484f61e28703a47a2`
- Pre-holdout trades: 1,754
- Trade dates: 2017-01-03 through 2024-12-31
- Candidate forecast rows: 14,070 across 2,010 dates
- Discovery expert rows: 73,990
- Missing pre-holdout exits: 0

## Discovery and validation results at 10bp

| Stage | Period | Books | Average | Median | Win rate | Profit factor | t-stat |
|---|---|---:|---:|---:|---:|---:|---:|
| Discovery | 2017–2021 | 1,004 | +0.121125% | +0.106416% | 57.37% | 2.37 | 7.31 |
| Inner validation | 2022 | 250 | +0.254714% | +0.213055% | 64.40% | 4.30 | 8.96 |
| Inner validation | 2023 | 248 | +0.248683% | +0.248601% | 65.73% | 4.39 | 9.21 |
| Outer pre-holdout | 2024 | 252 | +0.292013% | +0.259000% | 68.25% | 5.69 | 11.30 |

2020 was the only negative pre-holdout year, averaging -0.012534%; every other year was positive.

## Full pre-holdout economics

### 2017–2024

- Books: 1,754
- Average at 5bp: +0.226192%
- Average at 10bp: +0.176192%
- Average at 15bp: +0.126192%
- Average at 20bp: +0.076192%
- Median at 10bp: +0.155781%
- Win rate: 60.89%
- Profit factor: 3.26482
- Naive t-statistic: 15.9049
- Newey–West lag-5 t-statistic: 17.201
- Total net return sum: +309.040 percentage points
- Total after removing best trade: +306.178 percentage points
- Maximum compounded drawdown: 2.9868%
- Longest losing streak: 6 trades

### 2022–2024 confirmation period

- Books: 750
- Average at 10bp: +0.265248%
- Average at 15bp: +0.215248%
- Average at 20bp: +0.165248%
- Median at 10bp: +0.241823%
- Win rate: 66.13%
- Profit factor: 4.68726
- Newey–West lag-5 t-statistic: 11.748
- Total after removing best trade: +196.333 percentage points

## Robustness gates

All 15 persisted gates in `research.blankcanvas_gap_network_robustness_gate_v1` passed.

- Cost stress: positive at 15bp and 20bp.
- Best-trade removal: strongly positive.
- Adjacent K perturbation: the unchanged K=2 neighbour produced +0.187690% per trade at 10bp over 2022–2024, +0.173977% median and PF 3.71.
- Quarter concentration: maximum quarter share 4.53%, versus a 45% limit; 21 of 22 confirmation-period quarters were profitable. The only negative quarter averaged -0.003425%.
- Selected-expert concentration: a selected leg exceeded 50% precision weight on 8.27% of confirmation dates, versus the 20% limit.
- Placebo: 1,000 circular date shifts; none matched the observed mean. Empirical one-sided p = 0.000999. The best placebo mean remained negative after costs.
- Corporate-action audit: raw price-only returns were slightly stronger than adjusted returns. Excluding every date with more than 2bp adjustment difference still produced +0.183937% per trade and PF 3.30. The result is not a dividend or split artefact.
- Chronological degradation: every chronological octile was profitable; all 1,505 full rolling 250-trade windows were positive. The latest rolling-250 average was +0.287310%.
- Fixed regime analysis: positive average in every weekday, SPY opening-gap direction, lagged-volatility bucket and prior-SPY-day direction. High volatility was weaker but remained positive.
- Holding periods: both next-calendar-day and weekend/holiday holds were profitable.

## Execution reconstruction and capacity

The exact raw SIP 15:59 close and next-session 09:30 open were reconstructed for all 1,754 pre-holdout books and both legs.

- Missing exact execution prices: 0
- Exact-minute average at 10bp: +0.176185% versus +0.176192% using daily prices
- Exact-minute median at 10bp: +0.155779%
- Exact-minute win rate: 60.89%
- Exact-minute PF: 3.26470
- Average execution-basis difference: less than 0.001bp
- 95th-percentile absolute execution-basis difference: about 0.0053 percentage points at portfolio level
- Maximum isolated minute/daily price difference: 3.60bp

Selected-leg liquidity across the full pre-holdout ledger:

- Minimum observed selected auction-minute dollar volume: approximately $158,773
- Fifth-percentile entry-long minute dollar volume: approximately $2.50m
- Fifth-percentile entry-short minute dollar volume: approximately $2.96m
- Fifth-percentile exit-long minute dollar volume: approximately $8.46m
- Fifth-percentile exit-short minute dollar volume: approximately $8.86m
- All required bars were present.

This is ample for the intended small account, but minute volume is not a substitute for live bid/ask spread, closing/opening-auction imbalance, CFD overnight funding or short availability. Those must be verified before deployment.

## Important economic caveat

The edge is driven primarily by the short leg:

- 2017–2024 average long-leg contribution: -0.01794%
- 2017–2024 average short-leg contribution: +0.29413%
- 2022–2024 long-leg contribution: +0.02613%
- 2022–2024 short-leg contribution: +0.33912%

USO is the most frequent short at 44.81% of books; HYG is the most frequent long at 35.46%. The largest exact pair, long HYG/short USO, accounts for 12.94% of books. Deployment therefore depends on reliable short/CFD access and funding economics, even though the pre-holdout 20bp stress remains strongly positive.

## Locked-holdout protocol

Status: `PREHOLDOUT_ROBUSTNESS_PASSED_2025_UNOPENED`.

The immutable SQL function may now be executed once for 2025. The 2025 gate at 10bp is:

- at least 30 books;
- positive average;
- positive median;
- profit factor > 1.00;
- positive total after removing the best trade.

Only if every 2025 condition passes may the same immutable function be executed for 2026-01-01 through 2026-08-10. No state bin, source set, lookback, weighting formula, minimum-expert count, target universe, activation, ranking, K, direction, sizing, entry, exit or cost assumption may change after this freeze.
