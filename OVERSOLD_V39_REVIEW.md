# Oversold Reversion v3.9 — robustness/stress audit

## Decision
Keep the seven weight sets and existing 72/75 opportunity thresholds. Repair the diagnostics and abstention rules rather than tune the model to make ten rejected stocks pass. Neither the old nor new heuristic has established out-of-sample net profitability.

## Verified defects and changes
- **Mixed percentile bases:** v3.5 reported p10/median before friction and the displayed p25 after friction/caps. v3.9 applies the same transforms to every member before taking every percentile. Historical rows are explicitly labeled mixed-basis, not silently rewritten.
- **Clipped stability:** identical capped/floored scores could earn perfect weight stability. v3.9 measures the pre-cap score range and reports censored/incomplete tests as unavailable. Crossing the research threshold under alternative weights blocks promotion.
- **Component removal:** deleting a component and renormalizing all other weights was not an adverse-input test. The new diagnostic reduces one component by max(10 points,20%) with all weights held fixed, and measures pre-cap loss. This perturbation is an explicit policy assumption, not a fitted shock distribution.
- **False stress pass-rate:** a compatibility alias used median-pass AND component-pass, not a measured rate. The new numerator counts actual cases meeting the score/overreaction/survival/timing/tail policy, with an explicit denominator of 35. The 35 correlated cases are not independent observations or a success probability. The 60% threshold is inherited governance policy, not return calibration.
- **False source-removal assurance:** a cluster-count lookup and count-minus-one did not rerun the model. The new layer removes each declared/similarity cluster and re-scores with frozen price/financial evidence, at most eight cases. It checks frozen-baseline reproduction, invalidates explicitly shared financial roots, records removed articles and score/verdict changes, and blocks incomplete/ambiguous tests. A 48-point retained WATCH floor is a new explicit source-removal research policy.
- **Non-independent counts:** exact duplicate text is collapsed before economic scoring. Declared common roots and similarity chains form deterministic connected components. Undeclared common sourcing remains a limitation; different wording is not proof of independence. One primary source can prove an event without proving a trade.
- **Duplicated failures:** legacy aliases no longer inflate the canonical failed-gate list. Related failures are grouped. The final verdict is computed after all new gates.
- **Execution assumptions:** missing/invalid inputs, crossed quotes, post-cutoff quotes, stale quotes, spread inconsistencies and extreme spreads are exposed. Costs remain volume-tier proxies, not executable quotes. Separate 1x/1.5x/2x cost cases are shown without pretending they are observed trading outcomes.
- **Timing and accounts:** article recency and accounting coverage are no longer presented as verified event alignment or quantified financial damage. Event/onset timestamps and event-specific evidence remain UNKNOWN/NOT_QUANTIFIED when absent; no missing fact is invented.
- **Prompt grounding:** both scanners use one audit-rules file, explicitly retain cutoffs/model versions, require dated as-of analyst consensus, independent verdict and mandatory evidence checks, preserve the three-exchange-session horizon and the exact no-allocation outcome. Compact handoffs explicitly disclose omitted evidence.

## Validation and operating boundary
340 Python tests passed locally, including the new invariants, a genuine positive control, duplicate/source-removal checks, a JavaScript prompt-builder runtime test and production-bootstrap checks. JavaScript syntax was checked. The release workflow re-runs the full suite before committing the update.

No original snapshots, prior model source implementations, saved decisions, calibration activation, database contents, allocation settings or orders were changed. New scans use v3.9; historical rows retain their original version and score. The shared canonical backend and both scanner views are updated; this does not assert that any separately hosted copy is deployed.

## Remaining limits
Scenario magnitudes, seven weight sets, score thresholds and slippage proxies are judgmental. Source deletion remains limited by retained lineage and up to eight clusters. Event-specific damage extraction and real entry/exit quote validation still require independent evidence. Stock-level and portfolio-level profitable out-of-sample performance is not established by passing software tests. Do not allocate merely because the revised model passes a research gate.
