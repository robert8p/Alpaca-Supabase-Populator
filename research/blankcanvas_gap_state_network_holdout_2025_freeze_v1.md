# Gap-state transmission network — 2025 holdout freeze v1

Frozen after the untouched 2025 evaluation and before any 2026 candidate outcome was queried.

## Identity

- Campaign: `GAP-NET-OVERNIGHT-20260813-V1`
- Candidate: `28435b84e236643912497a40cc8c8f16`
- Final pre-holdout freeze commit: `af3bf41ea576328cba551caa540931569fcd4d0c`
- Immutable reconstruction SQL commit: `80fabfd2a3225a94ad57b4f07c86f514f3ff60cc`
- Function used without modification: `research.blankcanvas_gap_network_candidate_events_v1(date,date)`
- 2025 trade-ledger MD5: `626f7fb41c1a7ece4440072cf8cbf494`
- Trade dates: 2025-01-02 through 2025-12-31
- Missing exits: 0

No state bin, source set, lookback, weighting, minimum-expert count, target universe, activation, ranking, K, direction, sizing, entry, exit or cost was changed after the pre-holdout freeze.

## Untouched 2025 result

- Books: 251
- Average at 5bp: +0.259107%
- Average at 10bp: +0.209107%
- Average at 15bp: +0.159107%
- Average at 20bp: +0.109107%
- Median at 10bp: +0.242764%
- Win rate: 65.7371%
- Profit factor: 3.60407
- Naive t-statistic: 9.04557
- Average winner: +0.417266%
- Average loser: -0.190277%
- Worst trade: -1.02722%
- Best trade: +2.85162%
- Total net-return sum: +52.4860 percentage points
- Total after removing best trade: +49.6343 percentage points
- Selected-leg precision weight above 50% on 13.9442% of dates

## Gate decision

The preregistered 2025 gate required:

- at least 30 books — passed;
- positive average at 10bp — passed;
- positive median at 10bp — passed;
- profit factor above 1.00 — passed;
- positive total after removing the best trade — passed.

Status: `HOLDOUT_2025_PASSED_2026_UNOPENED`.

The immutable function may now be run once for 2026-01-01 through 2026-08-10. The identical gate applies. No further parameter or implementation change is permitted.
