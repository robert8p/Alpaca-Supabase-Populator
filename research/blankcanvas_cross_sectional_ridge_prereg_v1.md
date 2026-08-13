# Nested cross-sectional ridge campaign — preregistration v1

## Campaign ID
`XSRIDGE-20260813-V1`

## Independence and objective
The weak-close composite failed its second locked holdout and is rejected. This campaign tests a different family: a broad cross-sectional prediction model fitted to all registered signal-day technical features. It does not tune or condition on the weak-close rule and it preserves 2026-01-02 through 2026-04-29 as a completely untouched final holdout.

The prior 2025 November/December outcomes were opened for only two frozen weak-close definitions. They are not pristine for psychological discovery, so this campaign treats November/December solely as an outer model-selection block. The first decisive untouched evidence is 2026.

## Universe and causality
- Fixed May-2025 pre-discovery 300-name liquidity universe.
- Restrict to the 230 ordinary operating equities in `research.blankcanvas_extreme_asset_eligibility_v1`.
- Do not use next-session realised volume or bar count.
- Signal features are from the fully completed regular session on D.
- At D+1 open, skip names without an observed opening print or with opening price below $5; this is observable before execution.
- Missing D+1 close after a name is selected makes the candidate-day incomplete and is audited; no future-information substitution is allowed.
- Historical borrow availability and fees are unavailable. Short rules remain research candidates requiring a live borrow/CFD gate and adverse borrow-fee stress.

## Registered base features
Use exactly the 26 causal signal-day features below, with no outcome-based feature selection:

`ret_oc`, `range_pct`, `rv_1m`, `close_location`, `close_vs_vwap`, `first30_ret`, `first60_ret`, `midday_ret`, `last60_ret`, `last30_ret`, `first60_range`, `last60_range`, `first60_volume_share`, `last60_volume_share`, `first60_trade_share`, `last60_trade_share`, `pos_minute_fraction`, `max_minute_ret`, `min_minute_ret`, `minute_ret_abs_sum`, `efficiency_ratio`, `minute_ret_lag1_corr`, `high_time_fraction`, `low_time_fraction`, `max_runup_from_open`, `max_drawdown_from_open`.

For each date, names with all 26 features are deterministically ranked ascending by `(feature value, symbol)`. Normalised rank is `(row_number-1)/(M-1)`, where M is the number of complete fixed-universe names. Require M >= 200.

## Prediction target
For model fitting only, target each name's next-session regular open-to-close return minus that next session's cross-sectional mean return among complete fixed-universe names. The future cross-sectional mean is an outcome transformation, never an input. Strategy economics use the selected names' raw next-session open-to-close returns.

## Model maps and ridge fitting
Two fixed feature maps:

1. `LINEAR`: the 26 normalised ranks centred at 0.5.
2. `QUADRATIC`: all 26 centred linear ranks, their 26 squares and all 325 distinct pairwise products, for 377 columns.

Within each fit, mapped columns are standardised using only that fit's training rows. The target is centred using only training rows. Solve the deterministic ridge objective
`mean((y-Xβ)^2) + lambda * ||β||^2`
with an unpenalised intercept represented by the training target mean.

Registered lambda values: `{0.0001, 0.001, 0.01, 0.1, 1.0}`.

## Strategies and registered search count
For each model configuration, rank entry-eligible predictions each day and test:

- `LONG_TOP_N`: 100% long notional, equal-weight top predicted names.
- `SHORT_BOTTOM_N`: 100% short notional, equal-weight bottom predicted names.
- `TOP_MINUS_BOTTOM_N`: 50% long top predicted names and 50% short bottom predicted names.

N is exactly 1 or 2. With a £2,000 account, N=2 market-neutral positions are £500 per leg.

Registered definitions: 2 maps × 5 lambdas × 3 constructions × 2 N = 60. Primary cost is 10 basis points of portfolio NAV; stress cost is 20 basis points. Related research ancestry is reported but no prior definition is counted as an independent success.

## Time separation
- Train A: signal dates 2025-06-02 through 2025-08-29, 63 sessions.
- Inner validation B: 2025-09-02 through 2025-10-31, 44 sessions.
- Outer validation C: 2025-11-03 through 2025-12-30, 40 sessions.
- Locked final holdout: 2026-01-02 through 2026-04-29, 81 sessions; outcomes through 2026-04-30.

For B, each of the 10 model configurations is fitted only on A. B outcomes select configurations. For C, each B survivor is refitted on A+B with its map and lambda unchanged. C outcomes confirm the definition. At most two C survivors are frozen. For the final holdout, each frozen configuration is refitted once on all 2025 A+B+C rows, with every configuration and strategy choice unchanged.

## Bootstrap and multiplicity
- Circular moving-block bootstrap, block length 5 sessions, 20,000 replications, NumPy PCG64 seed 20260813 reset for each definition.
- 95% interval is the 2.5th/97.5th percentile of uncentred bootstrap means.
- One-sided p-value uses the centred return series: `(1 + count(null bootstrap mean >= observed mean))/(20000+1)`.
- Benjamini-Hochberg q-values are calculated across all 60 B definitions.

## B promotion gate
All must hold after 10 basis points unless noted:
- at least 40 complete trades;
- mean >= +0.10%;
- median > 0;
- win rate > 52%;
- profit factor >= 1.30;
- naive daily t-statistic >= 2.50;
- mean after 20 basis points > 0;
- block-bootstrap 95% lower bound > 0;
- BH q-value <= 0.05.

## C confirmation gate
Using the unchanged definition after refitting only on A+B:
- at least 35 complete trades;
- mean and median after 10 basis points > 0;
- win rate > 50%;
- profit factor > 1.10;
- mean after 20 basis points > 0;
- block-bootstrap 95% lower bound > 0.

Freeze at most two survivors, preferring one market-neutral and one directional construction when available. Within construction, rank by the lower of B and C 20-basis-point means, then C median.

## Final 2026 holdout gate
The frozen model map, lambda, construction, N, costs and execution rules are unchanged. After refitting on all 2025 data, a candidate passes only if:
- at least 70 complete trades;
- mean and median after 10 basis points > 0;
- win rate > 50%;
- profit factor > 1.10;
- mean after 20 basis points > 0;
- block-bootstrap 95% lower bound > 0;
- BH q-value <= 0.05 across the frozen candidates.

No element may be altered after the 2026 outcome is opened.
