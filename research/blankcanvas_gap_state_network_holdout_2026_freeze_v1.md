# Gap-state transmission network — 2026 YTD holdout freeze v1

Frozen immediately after the untouched 2026-01-01 through 2026-08-10 evaluation.

## Identity

- Campaign: `GAP-NET-OVERNIGHT-20260813-V1`
- Candidate: `28435b84e236643912497a40cc8c8f16`
- Final pre-holdout freeze commit: `af3bf41ea576328cba551caa540931569fcd4d0c`
- 2025 holdout freeze commit: `77a128a005a04bd89309be197ea055703c687d3a`
- Immutable reconstruction SQL commit: `80fabfd2a3225a94ad57b4f07c86f514f3ff60cc`
- Function used without modification: `research.blankcanvas_gap_network_candidate_events_v1(date,date)`
- 2026 YTD trade-ledger MD5: `4925c304c92ce9614a4b1156df430209`
- Signal dates: 2026-01-02 through 2026-08-10
- Missing exits: 0

No rule, parameter, cost, direction, sizing, entry or exit component was changed after either prior freeze.

## Untouched 2026 YTD result

- Books: 150
- Average at 5bp: +0.408409%
- Average at 10bp: +0.358409%
- Average at 15bp: +0.308409%
- Average at 20bp: +0.258409%
- Median at 10bp: +0.320147%
- Win rate: 70.6667%
- Profit factor: 7.15920
- Naive t-statistic: 9.82482
- Average winner: +0.565180%
- Average loser: -0.139912%
- Worst trade: -0.757498%
- Best trade: +3.28258%
- Total net-return sum: +53.7614 percentage points
- Total after removing best trade: +50.4788 percentage points
- Selected-leg precision weight above 50% on 3.3333% of dates

## Gate decision

The preregistered 2026 gate required:

- at least 30 books — passed;
- positive average at 10bp — passed;
- positive median at 10bp — passed;
- profit factor above 1.00 — passed;
- positive total after removing the best trade — passed.

Status: `BOTH_LOCKED_HOLDOUTS_PASSED_FINAL_EXECUTION_AUDIT_PENDING`.

The research rule is now statistically eligible for final deployment-readiness review. No additional historical parameter search is permitted. Remaining work is limited to exact holdout execution reconstruction, full-period risk aggregation, live broker spread/commission/overnight-funding/short-availability verification, operational alert implementation and a tightly controlled shadow/pilot launch.
