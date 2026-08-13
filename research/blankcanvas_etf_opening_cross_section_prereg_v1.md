# Exact ETF opening cross-section campaign — preregistration v1

## Purpose and adaptivity disclosure
The absolute opening-gap and gap-plus-first-minute-confirmation families produced zero discovery survivors under their preregistered gates. This campaign tests a structurally different and lower-dimensional implementation: relative ranking across a fixed, fully covered ETF universe at 09:31 ET. It is market-neutral and does not select an absolute threshold around any prior near-miss. The screening threshold reflects the cumulative search history.

No 2022+ outcome may be queried before discovery screening is complete. Raw 2025-2026 outcomes remain locked until a candidate passes discovery, 2022-2023 validation, 2024 outer validation and robustness, and is formally frozen.

## Fixed causal universe
DIA, HYG, QQQ, SPY, TLT and USO.

GLD is excluded solely because the raw SIP minute-data audit found no 2017-2019 opening bars; this exclusion is fixed before any candidate outcome is calculated. Every daily book requires all six universe members to have a non-null predictor, 09:31 entry and selected exit.

## Decision and exact execution
At 09:31 ET on trade date D:
- the official opening gap and completed 09:30 minute bar are observable;
- rank all six ETFs by one fixed predictor;
- enter every selected leg at its exact 09:31 minute open;
- exit at the 10:00 close, 10:30 close or 15:59 close;
- hold no overnight exposure.

Data sources:
- gap: `public.blankcanvas_adjusted_daily_features_v1`;
- exact minute prices: `research.blankcanvas_etf_opening_point_v1`, sourced from SIP/raw monthly partitions.

## Predictors
Five fixed causal predictors:
1. `gap_pct` — official same-day opening gap;
2. `opening_return_pct = 100 × (close_0930/open_0930 − 1)`;
3. `opening_range_pct = 100 × (high_0930/low_0930 − 1)`;
4. `opening_close_location = (close_0930 − low_0930)/(high_0930 − low_0930)`;
5. `opening_log_dollar_volume_change` — log first-minute dollar volume minus the same ETF's immediately preceding trading day's log first-minute dollar volume.

## Candidate universe
For each predictor:
- K = 1, 2 or 3 ETFs per side;
- reversal: long bottom K, short top K;
- continuation: long top K, short bottom K;
- exit: 10:00, 10:30 or 15:59.

Weights are 50% total long and 50% total short, equally weighted within each side. Ties are resolved alphabetically by symbol.

Registered definitions: **5 × 3 × 2 × 3 = 90**.

Net return is `style × reversal book return − 0.10%`, where style +1 is reversal and -1 is continuation.

## Costs and capital constraints
- Primary round-trip friction: **10bp of portfolio NAV**.
- Sensitivity: 5bp.
- Adverse stress: 15bp.
- Minimum leg size: £500.
- K=3 therefore requires at least £3,000 gross notional when every leg meets the minimum; this is compatible with the user's £10,000 research envelope.
- Short legs require liquid ETF or CFD availability; excess borrow/funding cost invalidates deployment.

## Time splits
- Discovery: 2017-2021.
- Inner validation: 2022-2023.
- Outer pre-holdout: 2024.
- Locked holdout 1: 2025.
- Locked holdout 2: 2026-01-01 through 2026-08-11.

## Discovery gate at 10bp
All conditions are mandatory:
- all five discovery years represented;
- at least 240 complete books in every year;
- positive annual average in at least four of five years;
- pooled average net return >= +0.05%;
- pooled median net return > 0;
- pooled profit factor >= 1.20;
- naive pooled t-statistic >= 4.70;
- worst annual average > -0.05%;
- no year contributes more than 22% of books.

The t-statistic is a familywise screening statistic only; a survivor requires dependence-aware inference.

## Inner-validation gate
Both 2022 and 2023 must independently have at least 240 books and positive average net return. Combined 2022-2023 must have positive average, positive median and profit factor > 1.10.

## Outer-2024 gate
At least 240 books with positive average, positive median and profit factor > 1.00.

## Robustness before freeze
A survivor must additionally satisfy over 2022-2024:
- positive average at 15bp;
- positive average after removing its best ten books;
- positive exact 09:32-entry average at 10bp;
- at least one adjacent K value, when available, has positive average at 10bp;
- no quarter contributes more than 12% of books;
- no ETF occupies either side on more than 60% of K=1 books or 80% of K=2/3 books;
- missing-bar, adjustment and early-close audits pass.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked first by minimum annual average across 2017-2024 and then by 2022-2024 average at 10bp. Record exact rule, constituent ledgers, effective and cumulative search counts, data snapshot and code commit before opening 2025.

A candidate may advance from 2025 to 2026 YTD only if 2025 has positive average, positive median and profit factor > 1.00 at 10bp. The same conditions apply to 2026 YTD. No predictor, K, style, exit, cost, universe or entry timing may change after a locked result.
