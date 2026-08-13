# Gap-state transmission network — discovery freeze v1

Frozen before any 2022+ candidate performance was queried.

## Campaign and candidate

- Campaign: `GAP-NET-OVERNIGHT-20260813-V1`
- Candidate ID: `28435b84e236643912497a40cc8c8f16`
- Preregistration commit: `48ce9496b9e147ef7585cbcd570a06432246914b`
- Registered definitions in this family: 432
- Effective definitions with discovery events: 432
- Minimum known cumulative registered ancestry in the immediately preceding blank-canvas branches: 6,902 definitions; this is a lower bound and excludes older campaigns.
- Discovery trade-ledger MD5: `d71b10e16397027b6f01c21dedc0ae8b`

## Exact observable and implementation

At the regular-session open, place every source ETF's opening gap into one of the six preregistered states. For each target ETF and each of the RISK4 sources—DIA, HYG, QQQ and SPY—retrieve the latest 40 prior occurrences of that source's current gap state. Current outcomes are excluded.

For each eligible source→target expert, calculate the historical mean target close-to-next-open return and sample standard deviation. Weight the mean by `1/(sd^2+0.0625)`. At least three eligible RISK4 source experts are required for each target. Compute a precision-weighted forecast for all seven target ETFs.

Trade only when all seven target forecasts are available and the forecast cross-section spans zero.

- K: 1
- Style: REVERSE
- Long: the ETF with the lowest forecast
- Short: the ETF with the highest forecast
- Sizing: 50% gross long and 50% gross short
- Decision information: gap states and all rolling statistics are available from the open; rankings are fixed before the closing-auction cutoff
- Entry: submit MOC orders by 15:45 ET; official close fill
- Exit: MOO at the next regular-session open
- Maximum holding period: one market overnight, including weekends/holidays
- Primary round-trip portfolio friction: 10bp
- Stress costs: 15bp and 20bp
- Missing seven-target forecast, unavailable short, halt, missing auction price or unresolved split-like event invalidates the book before entry

## Discovery data snapshot

- Expert rows: 73,990
- Expert date range: 2016-01-05 through 2021-12-31
- Forecast rows: 312,816
- Forecast date range: 2017-01-03 through 2021-12-31
- All-family event rows: 500,736
- Frozen-candidate trade rows: 1,004
- Candidate trade range: 2017-01-03 through 2021-12-31

## Discovery result at 10bp

- Trades: 1,004
- Average net return: +0.121125%
- Median net return: +0.106416%
- Win rate: 57.3705%
- Profit factor: 2.36995
- Naive t-statistic: 7.31372
- Average winner: +0.371884%
- Average loser: -0.215215%
- Worst trade: -1.89260%
- Best trade: +2.66191%
- Positive years: 4 of 5
- Worst annual average: -0.0125336%
- Maximum annual sample share: 25.0996%

### Annual results

| Year | Trades | Avg net | Median | Win rate | Profit factor | t-stat |
|---|---:|---:|---:|---:|---:|---:|
| 2017 | 187 | +0.166756% | +0.179528% | 61.50% | 2.93 | 4.02 |
| 2018 | 195 | +0.170221% | +0.134740% | 59.49% | 2.94 | 3.64 |
| 2019 | 251 | +0.134055% | +0.104440% | 59.36% | 2.63 | 4.26 |
| 2020 | 192 | -0.0125336% | +0.023444% | 52.08% | 0.92 | -0.20 |
| 2021 | 179 | +0.157027% | +0.091152% | 53.63% | 2.34 | 3.77 |

## Status and next locked gates

Status: `DISCOVERY_PASSED_VALIDATION_UNOPENED`.

The exact candidate above must now face:

1. 2022 and 2023 inner validation, with each annual average positive and the combined preregistered sample/economic gates passed;
2. 2024 outer pre-holdout;
3. 2017–2024 robustness, cost, selected-leg precision concentration, best-trade removal, adjacent-lookback/K and placebo gates;
4. only after a second freeze, the untouched 2025 holdout;
5. only if 2025 passes, 2026 YTD.

No state bin, source pool, weighting formula, K, style, activation, entry, exit or cost assumption may be changed after this freeze.
