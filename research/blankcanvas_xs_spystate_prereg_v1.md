# SPY-state-conditioned cross-sectional ETF basket campaign — preregistration v1

## Rationale and independence
The unconditional cross-sectional basket campaign produced zero discovery survivors under its preregistered gates. This campaign does not relax those gates or inspect 2025–2026 basket outcomes. It tests a distinct economic family: whether cross-sectional continuation or reversal is conditional on the contemporaneously observable SPY state over the same signal horizon.

## Base implementation
Same universe, decision times, signal horizons, basket sizes, styles, exits, weighting and 5bp primary cost as `blankcanvas_xs_basket_prereg_v1.md`.

## Causal SPY contexts
For the same signal horizon used to rank assets, classify SPY at decision time into exactly one state:

- `strong_down`: SPY return < -0.25%
- `down`: -0.25% <= SPY return < -0.10%
- `flat`: -0.10% <= SPY return <= +0.10%
- `up`: +0.10% < SPY return <= +0.25%
- `strong_up`: SPY return > +0.25%

No future price or exit information enters the context.

## Candidate universe and search count
Five contexts are crossed with every executable base definition. Registered upper bound: 792 × 5 = 3,960; the effective executable count will be audited after causal data-availability exclusions.

## Time splits
- Discovery: 2017–2021.
- Inner validation: 2022–2023.
- Outer pre-holdout: 2024.
- Locked holdouts: 2025 and then 2026 YTD.

## Discovery gate
All five years must be present; each year must contain at least 30 trades; at least four of five years must have positive average net return; aggregate weighted average must be at least +0.05% after 5bp; aggregate weighted win rate must exceed 52%; and the pooled naive t-statistic must be at least 4.4. Exact aggregate median must then be positive when the event ledger is reconstructed.

## Inner-validation gate
Both 2022 and 2023 must have at least 20 trades and positive average net return. Across both years, average and median must be positive and win rate must exceed 50%.

## Outer-2024 gate
At least 20 trades, positive average, positive median and win rate above 50%.

## Freeze
Freeze at most three candidates, ranked by minimum annual average across 2017–2024, before reading 2025. Only a 2025 pass may proceed to 2026 YTD. No rule component may be altered after either locked result.
