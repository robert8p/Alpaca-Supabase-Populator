# Liquid-security rank books conditioned on prior-day SPY regime — preregistration v1

## Purpose and adaptivity disclosure
The unconditional liquid-security top-versus-bottom books and the long-selected-versus-SPY books both produced zero discovery survivors at 20bp. This campaign tests the remaining low-dimensional explanation: a cross-sectional effect may be conditional on the prior market regime. It does not alter any underlying book definition. Each already-frozen 216-rule market-neutral book is filtered by one of five exhaustive, mutually exclusive SPY prior-day return regimes.

The campaign is adaptive and therefore uses a higher familywise screening threshold. No 2022+ outcome statistic may be queried before discovery screening is complete. 2025-2026 remain locked until a candidate passes all pre-holdout gates and is frozen.

## Base books and chronology
Base definitions and exact daily book returns come from campaign `LIQSEC-RANK-20260813-V1`:
- historical point-in-time eligibility;
- prior close >= $10;
- prior-day dollar-volume tier of $20m, $50m or $100m;
- nine prior-day features;
- K = 1, 3, 5 or 10 per side;
- reversal or continuation;
- enter next market open and exit same-session close;
- 50% gross long and 50% gross short;
- 20bp primary portfolio friction.

The conditioning variable is SPY's completed signal-day `return_pct`, already stored causally in `research.blankcanvas_liquid_security_daily_panel_v1` for the same target date.

## Frozen SPY regimes
Using only 2017-2021 SPY signal-day return values, calibrate and freeze q20, q40, q60 and q80.

Five exhaustive regimes:
1. `SPY_Q1`: value <= q20;
2. `SPY_Q2`: q20 < value <= q40;
3. `SPY_Q3`: q40 < value <= q60;
4. `SPY_Q4`: q60 < value <= q80;
5. `SPY_Q5`: value > q80.

Also freeze q15, q25, q35, q45, q55, q65, q75 and q85 for later threshold-perturbation tests. These may not replace the primary boundaries after validation.

## Candidate universe
- frozen base books: 216;
- exhaustive SPY regimes: 5.

Registered definitions: **216 × 5 = 1,080**.

The conditioned candidate's net return is exactly the base book's 20bp net return on dates belonging to its frozen SPY regime.

## Time splits
- Discovery: 2017-2021.
- Inner validation: 2022-2023.
- Outer pre-holdout: 2024.
- Locked holdout 1: 2025.
- Locked holdout 2: 2026-01-01 through 2026-08-11.

## Discovery gate at 20bp
All conditions are mandatory:
- all five discovery years represented;
- at least 35 books in every year and at least 220 pooled books;
- positive annual average in at least four of five years;
- pooled average net return >= +0.15%;
- pooled median net return > 0;
- pooled profit factor >= 1.35;
- naive pooled t-statistic >= 5.20;
- worst annual average > -0.10%;
- no year contributes more than 25% of books;
- no security appears on either side in more than 35% of conditioned books.

The statistic is screening only and reflects the cumulative search burden.

## Inner-validation gate
Both 2022 and 2023 must independently have at least 35 books and positive average net return. Combined 2022-2023 must have positive average, positive median and profit factor > 1.15 at 20bp.

## Outer-2024 gate
At least 35 books with positive average, positive median and profit factor > 1.05 at 20bp.

## Robustness before freeze
A survivor must additionally satisfy over 2022-2024:
- positive average at 30bp;
- positive average after removing its best five books;
- positive result under both inward and outward 5-percentile regime-boundary perturbations;
- at least one adjacent K value, when available, is positive at 20bp;
- at least one adjacent liquidity tier, when available, is positive at 20bp;
- no quarter contributes more than 35% of books;
- no single security contributes more than 20% of positive P&L;
- shuffled SPY regime labels within calendar quarters fail to reproduce the observed mean;
- missing-path, halt, symbol-event and split-like audits pass.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by minimum annual average across 2017-2024 and then 2022-2024 average at 20bp. Record the base candidate, SPY boundaries, constituent ledger, exclusions, effective/cumulative search counts, data snapshot and code commit before opening 2025.

A candidate advances from 2025 to 2026 YTD only if 2025 has at least 35 books, positive average, positive median and profit factor > 1.05 at 20bp. The same conditions apply to 2026 YTD. No base rule, regime boundary, cost, universe, entry or exit may change after a locked result.
