# Oversold Reversion Guard

Run locally from the repository root:

```bash
uvicorn app.reversion_guard_main:app --reload
```

Optional environment variables:

```text
OVERSOLD_SOURCE_BASE_URL=https://alpaca-rapid-discovery-web.onrender.com
REVERSION_GUARD_CACHE_SECONDS=20
REVERSION_GUARD_REQUEST_TIMEOUT_SECONDS=75
LOG_LEVEL=INFO
```

Tests:

```bash
PYTHONPATH=. pytest -q tests/test_reversion_guard_engine.py tests/test_reversion_guard_app.py
```

The app is intentionally a separate web service that consumes the existing scanner's point-in-time API. It does not duplicate Alpaca scans or require market-data secrets.

Version 1.1 independently checks issuer-linked, timestamped source content before trusting a verified cause. Filing metadata and high upstream confidence alone cannot promote a catalyst. Missing, crossed, future-dated or stale quotes/trades keep entry status waiting. Quote and trade freshness limits are disclosed operational checks (300 and 900 seconds), not calibrated trading parameters.

Research priority is separate from entry readiness. The existing higher-low rule now requires an actual intraday bar sequence; daily range/VWAP summaries do not prove a higher low. If the source packet has no intraday path, the app explicitly waits for that evidence. Historical scans are reviewed at their cutoff and never produce a shares-now recommendation.

Scores remain uncalibrated. Profit probabilities and expected net returns are unavailable; +1R and +4–6% levels are illustrative planning levels. Saved account and sizing settings are retained. None of these repairs establishes a profitable trading edge without independent outcome validation after costs.
