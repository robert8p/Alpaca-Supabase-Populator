# Oversold Reversion v3.3

## Purpose

**Prioritise liquid US sell-offs where verified price damage appears materially greater than justified economic damage, the business can survive, and a reversion within three trading sessions offers favourable asymmetric risk.**

The scanner is a research-prioritisation system, not a largest-losers list and not an execution signal.

## Purpose gap corrected

Earlier versions began with the right behavioural thesis but could still allow decline magnitude to influence who received full analysis, used incomplete fundamental coverage, and exposed legacy scoring semantics beside the current model. v3.3 changes the objective from **oversoldness** to **short-horizon mispricing quality**.

## Workflow

1. Detect material US-equity sell-offs using SIP prices.
2. Retain a broad, bounded discovery pool rather than truncating immediately by decline.
3. Establish price-session context: pre-market, regular session or after-hours.
4. Retrieve ticker-specific news and classify cause/economic risk.
5. Retrieve point-in-time SEC filing fundamentals when the research cache lacks the symbol.
6. Score opportunity quality and apply hard eligibility gates.
7. Rank by verdict, Opportunity Score, overreaction quality and evidence confidence.
8. Send a candidate or Top 5/10 evidence packet to ChatGPT for independent challenge.
9. Record Investigate / Watch / Pass / Reject and Commentary.
10. Preserve the original signal and measure forward outcomes separately.

## Opportunity Score

The 0–100 Opportunity Score is **not a probability** until a version-matched calibration passes its statistical gates.

The current score uses a weighted geometric mean so a severe weakness cannot be hidden by several strong but less important readings:

| Component | Weight | Meaning |
|---|---:|---|
| Overreaction quality | 28% | Price damage relative to justified economic damage |
| Catalyst reversibility | 22% | Probability the verified cause is temporary, survivable or over-discounted |
| Survivability | 20% | Capacity to remain solvent and operational through the reversion window |
| Three-session fit | 15% | Whether the event can plausibly reprice within three trading sessions |
| Price confirmation | 10% | Evidence of exhausted or stabilising selling |
| Technical exhaustion | 5% | Statistical dislocation; deliberately a small contributor |

Evidence Confidence is separate. It applies a one-way multiplier:

`0.35 + 0.65 × Evidence Confidence`

Weak evidence can only reduce the score. Missing news or fundamentals never become bullish evidence.

Tail risk receives an asymmetric penalty and hard ceilings. Structural impairment, capital distress, failed pivotal events and severe dilution cannot be rescued by RSI, volume or fall magnitude.

## INVESTIGATE gates

All applicable gates must pass:

- Opportunity Score at least 72
- cause VERIFIED, or unusually strong PARTIALLY_VERIFIED evidence
- Evidence Confidence at least 65
- Overreaction Quality at least 60
- Survivability at least 55
- Three-session Fit at least 55
- Damage Risk at most 60
- Tail Risk at most 60
- critical financial evidence available when the event requires it
- previous-day dollar volume at least $2 million
- spread at most 3%
- regular-session confirmation
- no structural hard veto
- no capital distress
- no material dilution
- no dominant post-spike normalisation

A candidate can have a respectable numerical score and remain WATCH when one non-catastrophic gate fails. Catastrophic/structural failures force PASS or a severe score ceiling.

## Point-in-time evidence

The preferred order is:

1. regulatory filing or regulator source
2. company primary release / investor relations
3. major financial media
4. specialist financial media
5. generic movers article

SEC Company Facts and submissions are accepted only when filed strictly before the signal cutoff. Relevant metrics include revenue growth, margins, cash/assets, liabilities/assets, debt/assets, current ratio, operating cash flow, free cash flow, estimated cash runway, diluted-share growth, market capitalisation and price-to-sales where derivable.

Known conclusions are labelled separately from inference:

- VERIFIED
- STRONGLY_INFERRED
- WEAKLY_INFERRED
- UNKNOWN
- CONFLICTING
- UNAVAILABLE

## Immutable research record

Each original signal stores a versioned Evidence Snapshot and original model run. Later models add `rescore` rows against the frozen snapshot; they do not overwrite the original evidence or result.

Forward outcomes are separate and include:

- 1, 3, 5, 10 and 20-session returns
- three-session MFE and MAE
- timestamps/session number for MFE and MAE
- longer research horizons
- corporate-action contamination review
- thesis-invalidation status
- decision-time Day 1/2/3 checkpoints for Investigate and Pass episodes

## Calibration

The target is reversion within three trading sessions. A later rebound remains research information but cannot turn a failed three-session observation into a calibration success.

Auto-calibration remains disabled until the current model/config has at least:

- 300 eligible matured observations
- 60 positive outcomes
- 60 negative outcomes
- 100 observations available for temporal holdout

A calibration must also pass positive-slope, Brier-skill, calibration-error, temporal-stability and sector-stability checks.

## Backlog

### P0 — completed

- stop raw decline from deciding the final analysis pool
- prevent low confidence from raising weak candidates
- add hard structural/capital-risk gates
- version the three-session target
- preserve immutable evidence and append-only rescoring
- harden nested JSONB persistence

### P1 — completed

- point-in-time SEC fundamental fallback
- explicit survivability and tail-risk scores
- session-aware price context
- three-session MFE/MAE path metrics
- evidence-rich independent ChatGPT audit
- current event/sector diagnostics

### P1 — remaining

- systematic company-IR and SEC 8-K event-content ingestion, not merely filing references
- better valuation anchors for businesses where price-to-sales is economically weak
- structured thesis-invalidation capture by the reviewer
- matured three-session samples for component ablation and calibration

### P2

- catalyst-specific model parameters only after sufficient samples exist
- transaction-cost-adjusted portfolio simulations
- analyst revision history as secondary evidence, never as a standalone score
- sector-neutral and liquidity-bucket performance reporting

## Governing rule

Every feature must materially improve the distinction between a genuine, survivable overreaction and a justified decline. Generic terminal functionality and noisy metrics do not belong in the core workflow unless forward evidence demonstrates predictive value.
