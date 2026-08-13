# Weak-close composite inference specification — v1

This specification is frozen before any validation return from `WEAKCLOSE-COMPOSITE-20260813-V1` is queried.

## Return source
The next-session open-to-close return is reconstructed directly as `next_close / next_open - 1` from `public.rd_blankcanvas_equity_daily_v2`. `public.rd_blankcanvas_equity_targets_v2` is not used because it lacks some fixed-universe names. No next-session volume, bar count, cross-sectional outcome mean or residual is used for selection or replacement.

## Missing-data rule
The signal score is computed only from names with all six signal-date features. A signal date is eligible only when at least 200 fixed-universe names are complete. At the next open, names without an opening print or with price below $5 are skipped using only information observable at entry. The pre-ranked next eligible name may replace them. After selection, a missing next close makes that candidate-day incomplete; it is excluded and explicitly audited, and no replacement based on future information is allowed.

## Moving-block bootstrap
For each definition's combined 34-session validation return series:

- Input: complete net returns after 10 basis points, ordered by signal date.
- Block scheme: circular moving blocks of length 5 sessions.
- Replications: 20,000.
- Pseudorandom generator: NumPy `PCG64` with seed `20260813`.
- Each replicate concatenates independently sampled circular block starts until at least n observations are obtained, then truncates to n.
- Confidence interval: the 2.5th and 97.5th percentiles of uncentred bootstrap sample means. The promotion gate uses the 2.5th percentile as the 95% lower bound.
- One-sided null p-value: subtract the observed sample mean from each return, apply the same block resampling to the centred series, and calculate `(1 + count(bootstrap_mean >= observed_mean)) / (20000 + 1)`.

## Multiple testing
Apply the Benjamini–Hochberg step-up procedure to the four one-sided bootstrap p-values. Report monotone adjusted q-values. A candidate's q-value must be <= 0.05.

## Naive t-statistic
For transparency, also report `mean / (sample_standard_deviation / sqrt(n))`. It remains a preregistered gate at >= 2.50 but is not a replacement for the block bootstrap.
