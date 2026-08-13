# Cross-sectional ETF basket campaign — preregistration v1

## Purpose
Test a genuinely different intraday family after the frozen TLT–USO pair candidate failed its 2025–2026 holdout. No 2025–2026 cross-sectional basket outcomes may be queried before a candidate is frozen under this protocol.

## Data
`public.blankcanvas_long_intraday_panel_v1`, restricted to 2017-01-01 through 2024-12-31 for search and pre-holdout evaluation. Universe: DIA, HYG, QQQ, SPY, TLT, USO.

## Candidate universe
At each date and decision minute, rank all available ETFs by a causal signal return.

- Signal horizons: 15m, 30m, 60m, open-to-decision.
- Decision minutes ET: 600, 630, 660, 690, 720, 750, 780, 810, 840, 870, 900.
- Basket size per side: K = 1, 2, 3.
- Style: reversal (long bottom K, short top K) or continuation (long top K, short bottom K).
- Exit: 30m, 60m, regular-session close.
- Weights: 50% total long notional and 50% total short notional, equally weighted within each side.
- Primary round-trip cost: 5 basis points of portfolio NAV.
- Registered definitions: 4 × 11 × 3 × 2 × 3 = 792.

Ties use deterministic alphabetical symbol order after signal rank. A book requires all six symbols to have non-null signal and selected exit returns.

## Time splits
- Discovery: 2017–2021.
- Inner validation: 2022–2023.
- Outer pre-holdout: 2024.
- First locked holdout: 2025.
- Final locked holdout: 2026-01-01 through 2026-08-11.

## Discovery gate
A candidate must have all five discovery years, at least 150 trades in every year, positive average net return in at least four of five years, positive aggregate average and median, win rate above 50%, aggregate average net return at least 0.02%, and naive daily t-statistic at least 4.0. The t-statistic is a screening statistic only; a survivor later requires block-bootstrap/HAC analysis.

## Inner-validation gate
Both 2022 and 2023 must be profitable after 5bp, each with at least 150 trades. Aggregate average and median must be positive and win rate must exceed 50%.

## Outer-2024 gate
2024 must have at least 150 trades, positive average and median after 5bp, and win rate above 50%.

## Freeze and holdout
Every candidate passing all gates is frozen before reading 2025. If more than three pass, rank by the minimum annual average across 2017–2024 and freeze no more than three, with ancestry/effective-search-count documented. Evaluate 2025 once. Only candidates passing 2025 on positive average, positive median and win rate above 50% may be evaluated once on 2026 YTD.

No threshold, basket size, signal horizon, decision time, direction, exit or cost assumption may be changed in response to locked-holdout outcomes.
