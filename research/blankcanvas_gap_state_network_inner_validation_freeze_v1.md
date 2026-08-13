# Gap-state transmission network — inner-validation freeze v1

Frozen after 2022–2023 validation and before any 2024 candidate performance was queried.

## Identity

- Campaign: `GAP-NET-OVERNIGHT-20260813-V1`
- Candidate: `28435b84e236643912497a40cc8c8f16`
- Preregistration commit: `48ce9496b9e147ef7585cbcd570a06432246914b`
- Discovery-freeze commit: `5fd752ba9ce12ff36db81388be939a41d7e68294`
- Inner-validation ledger MD5: `1accf19cd2298de6bebc81eb747d8a76`
- Inner-validation trade dates: 2022-01-03 through 2023-12-29
- Missing exit dates: 0

The exact implementation remains unchanged: 40 prior same-gap-state occurrences; RISK4 sources DIA/HYG/QQQ/SPY; precision weighting `1/(sd^2+0.0625)`; at least three source experts per target; all seven targets required; K=1; REVERSE; SPAN_ZERO; 50/50 market-neutral; MOC entry and next-session MOO exit; 10bp primary portfolio friction.

## 2022 validation

- Books: 250
- Average net return at 10bp: +0.254714%
- Median net return: +0.213055%
- Win rate: 64.40%
- Profit factor: 4.29996
- t-statistic: 8.96176
- Worst trade: -1.19101%
- Best trade: +2.09402%
- Total net return: +63.6785 percentage points
- Total after removing best trade: +61.5845 percentage points
- Average at 20bp: +0.154714%

## 2023 validation

- Books: 248
- Average net return at 10bp: +0.248683%
- Median net return: +0.248601%
- Win rate: 65.73%
- Profit factor: 4.38523
- t-statistic: 9.20981
- Worst trade: -0.946552%
- Best trade: +2.22888%
- Total net return: +61.6734 percentage points
- Total after removing best trade: +59.4445 percentage points
- Average at 20bp: +0.148683%

## Combined inner validation

- Books: 498
- Average net return at 5bp: +0.301710%
- Average net return at 10bp: +0.251710%
- Average net return at 15bp: +0.201710%
- Average net return at 20bp: +0.151710%
- Median net return at 10bp: +0.232521%
- Win rate: 65.06%
- Profit factor: 4.34191
- t-statistic: 12.8419
- Total net return: +125.352 percentage points
- Total after removing best trade: +123.123 percentage points
- Selected-leg precision weight above 50% on 8.43% of dates

All preregistered inner-validation conditions passed. Status is `INNER_VALIDATION_PASSED_OUTER_2024_UNOPENED`.

The next permitted action is the exact 2024 outer test. No rule component may change.
