# Intraday Opportunity Scanner — reliability v3 audit

## Decision

The scanner is **research-only**. It ranks liquid, executable market states for independent catalyst analysis; it does not represent a calibrated probability, expected return or validated generic trading rule.

The production trade gate is blocked because:

- 23 registered interaction candidates were tested under the pre-existing frozen robustness gate;
- 0 of 23 passed;
- no large-sample generic long/short continuation or reversal family produced a robust positive net 120-minute edge across discovery, validation, internal test and external holdout periods.

## Point-in-time audit design

The audit used 551,445 point-in-time stock states over 270 US trading days.

| Split | Dates | States |
|---|---|---:|
| Discovery | 1 July 2025 – 30 January 2026 | 296,521 |
| Validation | 2 February 2026 – 30 April 2026 | 129,507 |
| Internal test | 1 May 2026 – 29 May 2026 | 41,822 |
| External holdout | 5 June 2026 – 3 August 2026 | 83,595 |

The external holdout was not used to choose the frozen generic rule definitions.

### Universe and observation times

- Active included US equities from the Rapid Discovery point-in-time universe.
- Price at least $5.
- Previous-day dollar volume at least $50 million.
- Top 300 names by point-in-time previous-day dollar volume at each decision timestamp.
- Fund-, ETF-, ETN-, warrant-, rights-, units- and obvious acquisition-vehicle names excluded by name controls.
- Decision times sampled every 30 minutes from 10:00 to 13:30 New York time, preserving a complete 120-minute regular-session horizon.

### Execution definitions

- Signal inputs complete at the decision minute.
- Entry is the open of the immediately following regular-session minute.
- Exit is the fixed close 120 minutes after the decision timestamp.
- Conservative round-trip costs by historical liquidity tier: 8, 12, 20 or 35 basis points.
- Live production references use the current SIP ask for a long hypothesis and the current SIP bid for a short hypothesis; the prospective tracker separately records next-minute entry.

## Frozen generic families

The audit tested broad, interpretable versions of:

- long continuation;
- short continuation;
- long reversal;
- short reversal.

Continuation required agreement across multiple return horizons, market-relative direction, VWAP side and recent range position. Strict versions added 60-minute agreement, activity confirmation, move-capacity-to-cost and late-chase controls.

Reversal required a material prior move and an actual five-minute turn. Strict versions added 30/60-minute displacement, VWAP/range location, activity and execution-capacity constraints.

## External-holdout results

The large-sample strict families failed after conservative costs:

| Family | Holdout n | Days | Hit rate | Mean net return | Median net return |
|---|---:|---:|---:|---:|---:|
| Long continuation | 6,311 | 40 | 42.04% | -0.1340% | -0.1301% |
| Short continuation | 6,885 | 40 | 46.88% | -0.0283% | -0.0478% |

The strict reversal samples were too small and unstable to promote:

| Family | Holdout n | Days | Hit rate | Mean net return |
|---|---:|---:|---:|---:|
| Long reversal | 12 | 9 | 0.00% | -0.6204% |
| Short reversal | 18 | 15 | 55.56% | +0.1632% |

The positive short-reversal mean is not treated as evidence of an edge: the sample is tiny, the sign was unstable across earlier splits, and it did not satisfy the registered minimum-support or robustness gates.

## Registered research cross-check

The pre-existing `TPR-EQUITY-V1-20260818` research programme registered:

- 2025-07-01 to 2026-02-27 discovery;
- 2026-03-02 to 2026-05-15 validation;
- 2026-05-18 to 2026-08-03 protected holdout;
- first executable next-minute open;
- a primary net +1.00% within 120-minute barrier target;
- 10 basis-point base and 25 basis-point stress round-trip costs;
- minimum support, FDR, lift, positive-net, positive-month and non-overlap robustness requirements.

Twenty-three interaction candidates reached the frozen robustness table. None passed.

## Reliability v3 production policy

The scanner now exposes four separate concepts:

1. **Directional evidence** — coherence of the proposed direction across horizons and relative-market features.
2. **Movement opportunity** — estimated capacity for meaningful price movement, not expected return.
3. **Execution quality** — liquidity, spread, data quality and broker shortability/borrowability.
4. **Analysis priority** — a capped research triage score after execution, ambiguity and empirical-family penalties.

Every row is labelled `NO VALIDATED EDGE`, `RESEARCH_ONLY` and `trade gate BLOCKED` until a later model version passes the registered gates.

The highest analysis-priority score is capped at 74/100. No row may be labelled as a trade, probability or expected return by the quantitative scanner.

## Prospective unbiased calibration

Every ranked candidate—not only user-selected names—is automatically enrolled in outcome tracking. The tracker records:

- executable quote-side reference at the evidence cutoff;
- first complete next-minute SIP open;
- favourable excursion;
- adverse excursion;
- fixed 120-minute close;
- regular-session close;
- data-refresh status and errors.

The Selected tab is only a user review view. It does not define the calibration population.

## Remaining limitations

- The score is not calibrated.
- The historical audit lacks full point-in-time NBBO and borrowability coverage for every historical state; conservative liquidity-tier costs were used instead.
- Minute highs and lows describe reachability, not guaranteed fills.
- Company-specific catalysts are not inferred by the quantitative layer.
- A future catalyst-led strategy must be validated separately from the rejected generic technical families.
- Prospective outcomes require enough independent trading days, not merely many correlated stocks on the same day.

## Promotion requirement

A future model version may unblock the trade gate only after pre-registration and time-separated evidence supports all applicable requirements, including:

- minimum independent days and symbols;
- positive mean and median net returns;
- superiority to matched time-of-day/liquidity/volatility baselines;
- realistic spread, slippage and borrowability;
- stability across months and regimes;
- non-overlap sensitivity;
- multiple-testing correction;
- untouched holdout success;
- prospective reproduction.
