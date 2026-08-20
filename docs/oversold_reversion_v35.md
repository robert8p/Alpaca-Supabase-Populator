# Oversold Reversion v3.5 — Robust Opportunity Score

## Governing purpose

Prioritise liquid US sell-offs where verified price damage appears materially greater than justified economic damage, the business can survive, and a reversion within three trading sessions offers favourable asymmetric risk.

The score is a research-ranking metric. It is not a recovery probability until a version-matched calibration passes all statistical and robustness gates.

## Why v3.5 exists

v3.4 added deterministic evidence, financial and timing downside scenarios. That materially improved downside control, but ranking on the mean of the two worst scenario scores could become universally pessimistic and did not test dependence on:

- one source repeated through syndication;
- stale evidence near—but not causal to—the signal;
- a particular set of hand-selected component weights;
- one unusually influential model component;
- superficially broad but event-irrelevant financial coverage.

v3.5 retains all structural-risk, liquidity, spread, survivability, dilution, post-spike and regular-session gates. It adds robustness analysis rather than weakening those protections.

## Primary and regulator evidence

The active primary evidence contract is `primary_event_evidence_v2`.

It includes:

- SEC EDGAR filings and canonical filing documents;
- selected filing exhibits, including issuer press releases;
- exact-identifier ClinicalTrials.gov records;
- exact-identifier Drugs@FDA history;
- exact issuer-name FDA drug enforcement records;
- exact issuer-name FDA device enforcement records;
- exact issuer-name ClinicalTrials.gov sponsor records.

Issuer matching is conservative. SEC current and former issuer names are corporate-suffix normalised and must match the regulator record exactly after normalisation. Date-only regulator records must strictly predate the signal date. No fuzzy issuer/product association is used.

## Evidence provenance clusters

Raw article count is not source independence.

v3.5 groups causal evidence into provenance clusters when records:

- share the same SEC accession or primary evidence root;
- have substantially overlapping causal text; or
- have near-identical headlines indicating syndication.

One SEC filing and its EX-99 press-release exhibit therefore count as one provenance root. A company press release copied to multiple news sites does not become several independent confirmations.

INVESTIGATE requires at least two causal provenance clusters and either:

- at least one primary causal cluster; or
- at least two high-quality independent secondary clusters.

A single cluster caps the score at 60 and cannot qualify for INVESTIGATE.

## Event-to-signal alignment

Causal evidence is scored by its proximity to the evidence cutoff:

- 0–6 hours: strongest alignment;
- 6–18 hours: very strong;
- 18–36 hours: strong;
- 36–72 hours: acceptable but weaker;
- 72–96 hours: weak;
- over 96 hours: context rather than a persuasive explanation for the current sell-off.

Primary evidence receives a small alignment benefit, but age cannot be ignored. A recent unrelated filing is not automatically causal.

## Event-specific fundamental-data quality

The model no longer treats a high count of financial fields as sufficient evidence quality. Required metrics depend on the event family.

Examples:

- financing and solvency events require cash, liabilities, equity, debt, current ratio, runway and dilution evidence;
- clinical/regulatory events prioritise runway, leverage, liquidity and dilution capacity;
- earnings events prioritise revenue growth, margins, cash and operating cash flow;
- operational disruptions prioritise liquidity and runway.

Quality combines:

- source authority;
- filing freshness;
- coverage of event-relevant metrics;
- overall metric breadth; and
- balance-sheet accounting consistency where assets, liabilities and equity are available.

Critical events require a financial-data quality score of at least 60 for INVESTIGATE.

## Robust weight ensemble

v3.5 evaluates seven economically plausible weight sets:

1. balanced;
2. economic-damage focused;
3. survivability focused;
4. reversibility focused;
5. three-session timing focused;
6. price-confirmation focused; and
7. technical-light.

Each weight set is evaluated across five deterministic v3.4 scenarios:

- base reliable;
- evidence downside;
- financial downside;
- timing downside; and
- joint downside.

This produces up to 35 ensemble members.

The ranking score is:

1. the lower quartile of the ensemble;
2. less estimated execution-friction penalty;
3. subject to structural, contradiction, provenance, timing, financial-quality and prior economic caps.

The UI retains the ensemble median, p10, minimum, maximum and range. The minimum remains visible but no longer alone defines the score.

## Weight and component stability

The system records:

- score range across base-scenario weight sets;
- a Weight Stability score;
- leave-one-component-out score reductions; and
- maximum single-component dependency.

INVESTIGATE requires:

- Weight Stability at least 70; and
- maximum component dependency no greater than 15 points.

A candidate whose conclusion depends mainly on one hand-selected weight or one component is not robust enough for INVESTIGATE.

## INVESTIGATE requirements

All inherited economic gates and all v3.5 robustness gates must pass:

- Robust Opportunity Score at least 72;
- ensemble median at least 75;
- Weight Stability at least 70;
- maximum component dependency at most 15;
- verified or exceptionally strong partial cause;
- at least two independent causal provenance clusters;
- event alignment at least 60;
- critical event-specific fundamental quality at least 60;
- no material unresolved evidence contradiction;
- estimated round-trip friction at most 1.5%;
- acceptable survivability, damage and tail risk;
- sufficient liquidity and spread quality;
- regular-session confirmation;
- no capital distress, material dilution, structural veto or dominant post-spike normalisation.

The system may legitimately produce no INVESTIGATE candidate.

## Calibration safeguards

The three-session target and existing sample thresholds remain unchanged. In addition, a calibration mapping cannot become active unless it passes:

- deterministic bootstrap direction stability;
- top-quartile versus bottom-quartile hit-rate separation;
- at least three expanding-window temporal folds;
- stable temporal Brier skill; and
- median temporal AUC of at least 0.55.

A newer failed robustness run demotes any older active calibration for the current model/configuration.

## Model selectivity guard

Diagnostics report a model-selectivity warning when at least 100 current-model observations exist but none are WATCH or INVESTIGATE.

This is not permission to lower thresholds. It is a prompt to investigate false negatives using matured outcomes and positive controls. Threshold changes require empirical evidence, not a desire to generate more trades.

## Versioning and auditability

- Model: `oversold_reversion_score_v3_5`
- Config: `or_score_config_2026_08_20_v7`
- Catalyst schema: `catalyst_schema_v3_5`
- Robustness: `robust_weight_evidence_ensemble_v1`
- Target: reversion within three trading sessions

Original Evidence Snapshots remain immutable. Historical v3.5 results are append-only rescoring rows against frozen evidence. New evidence is never inserted into an old signal.
