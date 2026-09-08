# Oversold Reversion Guard v1.0

## Purpose

Oversold Reversion Guard is a separate FastAPI/Jinja web app layered on the existing Oversold Reversion scanner. It converts a research candidate into a strict execution decision:

> Is the cause verified and economically survivable, has the price stabilised in the regular session, can the position be sized to a defined invalidation, and does it fit the portfolio without creating hidden factor concentration?

It deliberately does **not** treat a large percentage decline, low RSI, a missing headline, or a strong historical quarter as evidence that a stock is mispriced.

## Isolation and architecture

- **Separate Render web service and URL**
- **Separate entry point:** `app.reversion_guard_main:app`
- **Same stack:** FastAPI, Jinja2, vanilla JavaScript and Render
- **Same evidence architecture:** the app consumes the current scanner's public point-in-time API rather than creating a second competing market-data pipeline
- **No duplicated Alpaca requests or secret credentials:** the upstream scanner remains the system of record
- **Decisions and commentary:** saved through the existing candidate review API
- **Position inputs:** stored only in the user's browser and re-reviewed against the latest candidate evidence when available

This design keeps the current app untouched and prevents scoring divergence caused by two independent scans of the same market event.

## New decision layer

Each candidate receives a deterministic Guard assessment with:

1. event bucket;
2. hard and conditional gates;
3. regular-session timing state;
4. confirmation score;
5. execution quality;
6. Guard score and cap reasons;
7. entry eligibility;
8. provisional invalidation;
9. risk-budget and maximum-position sizing;
10. +1R and 4–6% profit zones;
11. two-session time stop;
12. inferred factor/theme.

The Guard score is an explainable prioritisation score, not a probability.

## Event taxonomy

### Potentially eligible

- verified temporary operational disruption;
- analyst or sentiment-driven move, provided no economic damage is found.

### Conditional wait

- guidance or earnings-quality reset: rebuild fair value before considering entry;
- regulatory, legal, export-control or compliance risk: wait for clarity;
- unknown or weakly verified catalyst: missing evidence is uncertainty.

### Reject new entry

- bankruptcy, solvency, fraud, restatement, delisting or structural impairment;
- convertible debt, registered offering, share issuance, warrants or material dilution;
- failed pivotal clinical/regulatory event;
- dominant parabolic or post-spike unwind;
- upstream hard veto or very high damage risk.

## Entry timing

A candidate cannot become `INVESTIGATE_CONFIRMED` unless:

- the signal is being assessed in a regular US session;
- the evidence cutoff is at or after 10:00 ET;
- price confirmation passes;
- evidence confidence, execution quality and opportunity quality pass;
- no economic hard gate applies.

Confirmation looks for a higher-quality close/last trade within the session range, gap or low reclaim, VWAP behaviour and return from the session open. Extended-hours signals are capped and forced to wait.

## Position sizing

The app prohibits equal cash allocations. Position size is the smaller of:

- shares permitted by the GBP risk budget and entry-to-invalidation distance; and
- shares permitted by the maximum GBP position value.

While a candidate is waiting, the app can show a sizing preview, but **recommended shares remain zero**.

## Portfolio controls

- maximum positions per theme, default three;
- configurable maximum total planned open risk as a percentage of account value;
- explicit theme inference for AI/semiconductors, biotechnology, defence, fintech, automotive and other common factors;
- concentration warning in the existing-position review.

## Existing-position review

The position workflow calculates:

- current P/L in USD, GBP and percentage terms;
- the rebound required to return to break even;
- event-specific action: take profit, trim, conditional hold, heavy trim or exit;
- provisional invalidation and time stop;
- break-even anchoring warning;
- anti-thesis-drift and no-averaging rules.

A 25% loss is explicitly shown as requiring a 33.3% rebound. The app makes the user reassess from the current price rather than treating cost basis as fair value.

## ChatGPT handoff

Every candidate and the ranked top ten can be sent to ChatGPT with a pre-populated audit prompt. The prompt requires:

- respect for the stored evidence cutoff;
- no hindsight;
- independent challenge of the app;
- primary-source verification;
- event classification and economic severity;
- survivability, cash conversion, dilution and concentration analysis;
- regular-session confirmation;
- decisive action and falsification conditions.

## Validation

The implementation includes deterministic tests covering:

- temporary verified candidates;
- extended-hours waiting;
- dilution, failed clinical events, solvency and parabolic hard rejection;
- guidance resets;
- asymmetric break-even mathematics;
- existing-position actions;
- risk-based sizing;
- theme concentration;
- API enrichment and position-review contracts.
