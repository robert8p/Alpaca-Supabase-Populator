# Weak-close sequential holdout protocol — v1

This protocol is frozen before any November 2025 outcome for `WEAKCLOSE-COMPOSITE-20260813-V1` is queried.

## Eligible rules
Only candidate IDs present in `research.blankcanvas_weakclose_preholdout_freeze_v1` may enter Holdout A. Only candidates that pass Holdout A may be loaded into Holdout B.

## Windows
- Holdout A signal dates: 2025-11-03 through 2025-11-28 inclusive.
- Holdout B signal dates: 2025-12-01 through 2025-12-30 inclusive.
- The following trading session's regular open and close define the outcome. The date map is derived from the full daily trading calendar before the window is filtered.

## Locked implementation
The six signal features, deterministic percentile ranks, equal-weight composite, fixed universe, $5 opening-price eligibility rule, N=2 selections, constructions, entry, exit and 10/20 basis-point costs are identical to the preholdout implementation. No next-session realised volume or bar count is used.

## Completeness
- At least 200 signal-complete fixed-universe names must exist on each signal date.
- A selected name must have an observed next-session open of at least $5.
- A missing selected next-session close makes that candidate-day incomplete, is audited and is not replaced.
- A holdout stage requires at least 15 complete trades to pass.

## Stage gate
A candidate passes a holdout stage only when all are true after 10 basis points unless noted:
- trades >= 15;
- arithmetic mean > 0;
- median > 0;
- win rate > 50%;
- profit factor > 1.10;
- arithmetic mean after 20 basis points > 0.

No parameter is changed after either result. Holdout B is structurally inaccessible to a Holdout-A failure.

## Interpretation
Passing both holdouts establishes a robust research candidate, not automatic deployment readiness. Historical point-in-time borrow availability, borrow fees, opening auction spreads and the user's actual CFD/short inventory still require live feasibility gates and adverse execution stress.
