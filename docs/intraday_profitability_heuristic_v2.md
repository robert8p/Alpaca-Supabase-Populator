# Intraday Profitability heuristic v2 audit

## Status

This remains an **unvalidated research ranking**, not a calibrated probability of profit. The v2 objective is to remove avoidable false positives and make the ranking economically coherent before enough immutable selected-signal outcomes exist for formal calibration.

## Defects found in v1

1. **Stale-print exposure.** A fresh quote could be paired with an old or dislocated last trade.
2. **Weak bar-quality controls.** A candidate could survive with too few or too many missing one-minute observations.
3. **Late-chase bias.** A sharp final five-minute move could increase momentum scores after consuming much of the estimated two-hour opportunity.
4. **Insufficient setup ambiguity penalty.** Competing long, short, continuation and reversion explanations could receive similar scores without enough penalty.
5. **Under-specified reversion confirmation.** Reversion needed a confirmed short-horizon turn, not merely a large prior move.
6. **Execution capacity was not dominant enough.** Move capacity had to be evaluated relative to estimated spread and slippage rather than in isolation.
7. **Market opposition was underweighted.** Continuation against a materially opposing broad-market move needed an explicit penalty.
8. **Outlier volatility could inflate capacity.** Raw standard deviation was vulnerable to isolated bad prints.
9. **Borrowability was ignored.** A short could rank highly even when the broker asset record said it was not shortable or not easy to borrow.
10. **Opening-regime instability was untreated.** Signals during the first minutes of regular trading received no penalty for auction and price-discovery noise.

## v2 hard gates

- Positive, non-crossed SIP bid and ask.
- SIP quote no more than 60 seconds old, even when the UI allows a looser operational threshold.
- Latest trade no more than 90 seconds old.
- Last trade within the greater of 50 basis points or eight quoted spreads from the contemporaneous midpoint.
- Minimum price, previous-day dollar volume and current-session dollar volume.
- Spread below the configured maximum.
- At least 35 valid one-minute bars.
- No more than 18% missing minutes in the observed bar interval.
- Positive, internally coherent OHLC values.
- Short candidates are eliminated when the broker asset record explicitly marks the stock non-shortable.

## v2 features

- 5-, 15-, 30- and 60-minute returns.
- SPY-relative returns over the same horizons.
- Robust one-minute realised volatility using MAD-based winsorisation.
- Estimated 120-minute move capacity.
- Volume-weighted VWAP distance.
- 30- and 60-minute trend efficiency.
- Directional consistency across recent one-minute moves.
- Recent volume and trade-count acceleration.
- Position within the recent 30-minute range.
- Bar completeness and data-quality score.
- Liquidity, spread, current activity and estimated execution cost.
- Broker shortable and easy-to-borrow flags.
- Minutes elapsed since the regular-session open.

## Four competing setup hypotheses

Every stock is evaluated as:

- long continuation;
- short continuation;
- long reversion;
- short reversion.

Continuation requires multi-horizon directional agreement and is reduced by a five-minute turn against the proposed direction. Reversion requires both a material prior move against the proposed direction and an actual five-minute turn in the proposed direction.

## Penalties

- Estimated capacity below four times round-trip costs.
- Data quality below the preferred threshold.
- Five-minute move consuming more than 65% of estimated two-hour capacity.
- Continuation unusually extended from VWAP.
- Broad-market regime opposing continuation.
- Small score margin between the best and second-best setup.
- Twelve points during the first 15 regular-session minutes; six points during minutes 15–30.
- Twelve points for a short that is explicitly not easy to borrow.
- Smaller penalties when shortable or easy-to-borrow status is unavailable rather than confirmed.

## Score composition

The selected setup combines:

- 30% directional strength;
- 22% confirmation;
- 20% opportunity/capacity;
- 16% liquidity;
- 12% execution quality;
- minus explicit reliability and executability penalties.

`INVESTIGATE` additionally requires high data quality, a minimum capacity-to-cost ratio, enough separation from the runner-up setup and no large unresolved execution penalty. `WATCH` and `PASS` are research triage labels only.

## Outcome tracker integrity

Selection stores the original candidate ID, scan price, scan timestamp, direction, setup, rank and score. Tracking deliberately excludes the partially observed minute containing the scan. Longs retain the highest subsequent SIP one-minute high; shorts retain the lowest subsequent low. Close is the last regular-session one-minute close before the recorded market close.

## Remaining limitations

- No current score is calibrated to a probability.
- The heuristic has not yet passed untouched holdout validation.
- Bar highs and lows show reachability, not guaranteed fills.
- Catalyst interpretation remains external to the quantitative ranker.
- Execution estimates are conservative approximations, not order-level simulations.
- Easy-to-borrow status can change intraday and is not a guarantee that stock will be available at order time.
- Selection is discretionary, so selected-only outcomes cannot by themselves measure the whole ranking universe without selection-bias controls.

## Required next validation

Persist every scan and selected signal unchanged. Once enough matured observations exist, test monotonicity by score decile, setup and direction; compare against time-of-day, liquidity and volatility baselines; use purged walk-forward splits; include spread/slippage and borrowability; and measure whether ChatGPT upgrades or vetoes add incremental information over the v2 ranker.
