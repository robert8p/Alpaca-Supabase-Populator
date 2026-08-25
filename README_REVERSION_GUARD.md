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
