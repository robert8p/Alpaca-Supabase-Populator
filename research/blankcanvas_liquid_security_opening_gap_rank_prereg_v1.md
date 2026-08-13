# Liquid-security cross-sectional opening-gap rank campaign — preregistration v1

## Purpose and adaptivity disclosure
Prior-close rank books, SPY-hedged selected tails and SPY-regime-conditioned variants all produced zero discovery survivors at their preregistered 20bp gates. This campaign moves the observable trigger to the next session's official opening print and models an exact one-minute execution delay. It tests a compact opening-gap cross-section rather than adding more prior-close conditions.

The campaign is adaptive and uses an elevated familywise screening threshold. No 2022+ outcome statistic may be queried before discovery screening is complete. Raw 2025-2026 minute outcomes remain locked until a candidate passes discovery, 2022-2023 validation, 2024 outer validation and robustness, and is formally frozen.

## Point-in-time universe
Use `research.blankcanvas_liquid_security_daily_panel_v1`, whose rows were built from historical SIP/raw regular-session data and exact next-SPY-market-date joins.

A security is eligible from the completed prior session when:
- symbol matches `^[A-Z]{1,5}$`;
- prior session has at least 300 minute bars;
- prior close >= $10;
- prior-day dollar volume meets the candidate's fixed tier;
- the target session has a valid official raw open.

No current asset list or current listing status is used.

## Corporate-action handling
The database contains fully adjusted historical rows, but those are back-adjusted and may incorporate corporate actions that occurred after the historical decision date. They are therefore not used for causal signal construction.

The observable raw opening gap is:
`100 × (target official open / prior raw close − 1)`.

To prevent split-like raw discontinuities from dominating ranks, require:
`-20% <= raw_gap_pct <= +20%`.

This fixed cap is applied before ranking. Events outside it are excluded and audited; they cannot be reinstated after outcomes are viewed.

## Decision and exact execution
At 09:31 ET on target date T:
- rank all eligible securities by the official raw opening gap;
- select bottom K and top K;
- enter every selected leg at its exact 09:31 SIP/raw minute open;
- exit at the 10:00 close, 10:30 close or 15:59 close;
- hold no overnight exposure.

A 09:32-entry return is retained for mandatory robustness. Books require all selected entries and exits; missing or halted paths are excluded and audited.

## Candidate universe
For each prior-day minimum dollar-volume tier:
- $20m, $50m or $100m;
- K = 1, 3, 5 or 10 per side;
- reversal: long bottom K gaps, short top K gaps;
- continuation: long top K gaps, short bottom K gaps;
- exit: 10:00, 10:30 or 15:59.

Weights are 50% total long and 50% total short, equally weighted within each side. Ties are resolved alphabetically.

Registered definitions: **3 × 4 × 2 × 3 = 72**.

## Costs, capital and liquidity
- Primary round-trip friction: **30bp of portfolio NAV**.
- Sensitivity: 20bp.
- Adverse stress: 50bp.
- Minimum leg size: £500.
- K=10 uses twenty £500 legs and exactly £10,000 gross notional.
- Short constituents require borrow/CFD availability; excess borrow/funding cost beyond the 50bp stress allowance invalidates deployment.
- The target open is never treated as executable; all performance starts at the exact next-minute open.

## Time splits by target date
- Discovery: 2017-2021.
- Inner validation: 2022-2023.
- Outer pre-holdout: 2024.
- Locked holdout 1: 2025.
- Locked holdout 2: 2026-01-01 through 2026-08-11.

## Discovery gate at 30bp
All conditions are mandatory:
- all five discovery years represented;
- at least 240 complete books in every year;
- positive annual average in at least four of five years;
- pooled average net return >= +0.10%;
- pooled median net return > 0;
- pooled profit factor >= 1.30;
- naive pooled t-statistic >= 5.00;
- worst annual average > -0.10%;
- no year contributes more than 22% of books;
- no security appears on either side in more than 25% of discovery books.

The t-statistic is screening only and reflects the cumulative search history.

## Inner-validation gate
Both 2022 and 2023 must independently have at least 240 books and positive average net return. Combined 2022-2023 must have positive average, positive median and profit factor > 1.15 at 30bp.

## Outer-2024 gate
At least 240 books with positive average, positive median and profit factor > 1.05 at 30bp.

## Robustness before freeze
A survivor must additionally satisfy over 2022-2024:
- positive average at 50bp;
- positive average after removing its best ten books;
- positive exact 09:32-entry average at 30bp;
- at least one adjacent K value, when available, is positive at 30bp;
- at least one adjacent liquidity tier, when available, is positive at 30bp;
- gap-cap perturbations of ±15% and ±25% do not reverse the result;
- no quarter contributes more than 12% of books;
- no security contributes more than 20% of positive P&L;
- shuffled gap ranks within date and a one-day delayed-gap placebo fail to reproduce the mean;
- missing-path, halt, symbol-event, split-like and early-close audits pass.

## Freeze and locked evaluation
Freeze no more than three candidates, ranked by minimum annual average across 2017-2024 and then 2022-2024 average at 30bp. Record exact rule, selection and trade ledgers, exclusions, effective/cumulative search counts, data snapshot and code commit before opening 2025.

A candidate advances from 2025 to 2026 YTD only if 2025 has positive average, positive median and profit factor > 1.05 at 30bp. The same conditions apply to 2026 YTD. No tier, K, style, exit, gap cap, cost, universe, entry or exit may change after a locked result.
