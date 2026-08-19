# Oversold Reversion Score v2

## Meaning

The production output remains **Reversion Score** (0–100, no percent sign) while the model is uncalibrated. It is a ranking score, not a probability.

The eventual calibration target is `hit_plus_5pct_within_6_weeks`: whether the security trades at least 5% above the stored signal price during the six-week evaluation window. Historic evidence is point-in-time and immutable.

## Canonical formula

```text
Core Score =
    0.25 * Setup
  + 0.35 * Catalyst
  + 0.15 * Fundamental Resilience
  + 0.25 * Confirmation

Confidence Adjusted Score =
    50 + ((Core Score - 50) * Evidence Confidence / 100)

Damage Penalty =
    min(15, max(0, Damage Risk - 25) * 0.20)

Pre-Cap Score = clamp(Confidence Adjusted Score - Damage Penalty, 0, 100)
```

Damage caps:

| Damage Risk | Maximum score |
|---|---:|
| 0–29 | 100 |
| 30–49 | 85 |
| 50–69 | 65 |
| 70–84 | 40 |
| 85–100 | 20 |

If the principal cause is not verified, Catalyst is capped at 35, the final score at 60, and the verdict cannot exceed WATCH. Verified existential/solvency/core-thesis failure can hard-veto to PASS.

Confidence is **not** an attractiveness component. It shrinks extreme conclusions toward a neutral score of 50.

## Components

- **Setup** — deterministic market dislocation and tradability. Raw decline magnitude saturates rather than increasing indefinitely.
- **Catalyst** — point-in-time evidence that the cause is temporary, survivable, misunderstood or over-discounted within six weeks.
- **Fundamental Resilience** — capacity to absorb the event without destroying equity value.
- **Confirmation** — point-in-time selling exhaustion/stabilisation using session range, reversal, volume and spread information.
- **Damage Risk** — permanent structural impairment, applied asymmetrically as penalty/cap/veto.
- **Evidence Confidence** — completeness and reliability of the evidence.

Analyst consensus is not a standalone score. Analyst material is supporting catalyst evidence only, with post-event actions preferred over stale pre-event consensus.

## Evidence and auditability

`or_evidence_snapshots` and `or_model_runs` are append-only/immutable. A model change never overwrites an original signal result. New research rescoring must be a new model run.

The app records the exact scoring model/config version and calculation trace used for each signal. The ChatGPT audit buttons receive the same evidence cutoff and canonical formula and are explicitly prohibited from judging the original signal with later evidence.

## Calibration guard

The UI remains `Model status: Uncalibrated` until configured quality gates pass. Initial minimums are 300 matured calibration-eligible signals, at least 60 positive and 60 negative outcomes, a 100-observation temporal holdout, and a temporal calibration run that passes quality checks including positive Brier skill.

Six-week outcomes are captured from Alpaca SIP data. Until corporate-action integrity is independently verified, outcome rows are intentionally not calibration-eligible, preventing splits or other corporate actions from creating false labels.

## Catalyst backend

The current repository contains no backend OpenAI integration or configured LLM client. V2 therefore uses explicit structured, conservative point-in-time catalyst rules over retained Alpaca news. Missing/unverified catalyst evidence lowers confidence and triggers caps rather than being treated as neutral-positive evidence. The external ChatGPT buttons remain an audit layer, not ground truth.
