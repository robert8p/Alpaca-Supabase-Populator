# Prior-day cross-ETF rank → next-session intraday campaign — preregistration v1

## Purpose and adaptivity disclosure
The prior-day single-ETF tail campaign produced zero discovery survivors at 10bp. This follow-up was registered after observing that some discovery-only near-misses clustered in equity ETFs, so its multiple-testing burden is treated as cumulative rather than independent. It does not reuse any one near-miss threshold. Instead it tests the complete, low-dimensional family of relative ranks across all seven ETFs. No 2022+ outcome may be queried until the discovery gate is applied exactly as written.

## Data and chronology
Source: `public.blankcanvas_adjusted_daily_features_v1` for DIA, GLD, HYG, QQQ, SPY, TLT and USO.

At the regular-session close on signal date D:
- rank all seven ETFs by one fixed feature;
- require all seven feature values and all seven next-session intraday outcomes to be available;
- enter the selected market-neutral basket at each ETF's next regular-session open;
- exit at that same session's regular-session close;
- hold no overnight exposure.

Phase assignment uses the target/entry date.

## Features
Seven fixed prior-day features:
1. `intraday_ret_pct`
2. `day_ret_pct`
3. `gap_pct`
4. `ret5_pct`
5. `ret20_pct`
6. `range_pct`
7. `close_location`

## Candidate universe
For each feature:
- basket size K = 1, 2 or 3 per side;
- reversal: long the bottom K and short the top K;
- continuation: long the top K and short the bottom K.

Weights are 50% total long and 50% total short, equally weighted within each side. Ties are broken alphabetically by symbol. Registered definitions: **7 × 3 × 2 = 42**.

## Costs and constraints
- Primary round-trip friction: **10bp of portfolio NAV**.
- Sensitivity: 5bp.
- Adverse stress: 15bp.
- All legs are highly liquid ETFs, but any short implementation still requires an available ETF/CFD borrow route.
- Minimum assumed position is £500; a K=3 book therefore requires either fractional CFD sizing or sufficient capital for six legs. Deployment readiness will account for the user's capital and minimum position constraints.

## Time splits by target date
- Discovery: 2017-01-01 through 2021-12-31.
- Inner validation: 2022-01-01 through 2023-12-31.
- Outer pre-holdout: 2024-01-01 through 2024-12-31.
- Locked holdout 1: 2025.
- Locked holdout 2: 2026-01-01 through 2026-08-11.

## Discovery gate at 10bp
All conditions are mandatory:
- all five discovery years represented;
- at least 240 complete daily books in every year;
- positive annual average in at least four of five years;
- pooled average net return ≥ +0.05%;
- pooled median net return > 0;
- pooled profit factor ≥ 1.20;
- naive pooled t-statistic ≥ 4.40.

The elevated t threshold reflects cumulative adaptivity across prior campaigns. It is screening only; any survivor requires dependence-aware inference.

## Inner-validation gate
Both 2022 and 2023 must independently have at least 240 books and positive average net return. Across both years combined:
- average and median net return > 0;
- profit factor > 1.10.

## Outer-2024 gate
At least 240 books with positive average, positive median and profit factor > 1.00.

## Robustness before freeze
A candidate must also satisfy:
- positive 2022-2024 combined average at 15bp;
- at least one adjacent K value, when available, has positive 2022-2024 average at 10bp;
- no single ETF appears on either side of more than 60% of books for K=1 or 80% for K=2/3.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked first by minimum annual average across 2017-2024 and then by 2022-2024 average at 10bp. Record exact rule, effective search count, ancestry, data snapshot and code commit before opening 2025.

A candidate may proceed from 2025 to 2026 YTD only if 2025 has positive average, positive median and profit factor > 1.00 at 10bp. The same conditions apply to 2026 YTD. No feature, K, style, cost, entry or exit rule may change after a locked result.
