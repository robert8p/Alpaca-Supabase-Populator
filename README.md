# Alpaca Rapid Discovery Loader

A brand-new, deployable application for rapidly populating Supabase PostgreSQL with configurable Alpaca US-equity candles.

It is designed for research ingestion rather than live trading. The application separates a lightweight web dashboard from a persistent background worker, checkpoints every Alpaca response page, stages compressed CSV files, and bulk-loads them through PostgreSQL `COPY`.

## What the dashboard controls

- **Universe:** all active Alpaca US equities or an explicit symbol list.
- **Filters:** exchange, tradable, fractionable, marginable, shortable, easy-to-borrow, overnight-tradable, regex include/exclude, and a symbol cap.
- **Candles:** one or multiple intervals in the same job, including any custom **1–59 minute** interval, hourly and daily bars.
- **Period:** arbitrary start/end dates plus optional Alpaca `asof` symbol mapping.
- **Feed:** SIP, IEX, BOATS overnight, or OTC.
- **Adjustments:** raw, split, dividend, or all.
- **Retained session:** regular, extended, all returned bars, or a custom New York-time window that can cross midnight.
- **Throughput:** symbols per request, calendar days per task, concurrent tasks, target requests/minute, page size, retries and backoff.
- **Storage:** skip or update duplicates, keep/delete compressed staging files, and optional daily research features.

Before a job is launched, the dashboard can resolve the current Alpaca universe and estimate:

- Symbols
- Resumable task count
- Expected rows
- Approximate compressed staging footprint

## Architecture

```text
Browser dashboard
      │
      ▼
FastAPI web service ───────────────► Supabase control tables
                                          │
                                          ▼
                               Resumable task queue in Postgres
                                          │
                                          ▼
Render background worker ──► Alpaca multi-symbol bars API
          │                               │
          │                    page token + heartbeat checkpoint
          ▼                               │
Persistent disk: gzip CSV ◄───────────────┘
          │
          ▼
PostgreSQL COPY → temporary table → deduplicated insert
          │
          ├──► Monthly `rd_bars_YYYYMM` partitions
          └──► Optional `rd_daily_features`
```

The worker disk is private to the worker. The web service remains stateless and reads progress from Supabase.

## Database objects

| Object | Purpose |
|---|---|
| `rd_jobs` | Job configuration, progress, totals and lifecycle state |
| `rd_tasks` | Resumable date-window / timeframe / symbol-batch tasks |
| `rd_job_symbols` | Resolved symbol universe for each job |
| `rd_job_events` | Operational event and error history |
| `rd_workers` | Worker heartbeat and currently claimed tasks |
| `rd_assets` | Latest observed Alpaca asset metadata |
| `rd_bars` | Partitioned raw/adjusted OHLCV bars |
| `rd_bars_YYYYMM` | Automatically created monthly partitions |
| `rd_daily_features` | Optional daily research-ready aggregates |
| `rd_inventory` | Fast ingestion ledger for the dashboard |

The `rd_bars` natural key is:

```text
(symbol, timeframe, feed, adjustment, bar_ts)
```

This makes task restarts and overlapping date chunks safe.

## Recovery behaviour

- Every Alpaca page updates the task's `next_page_token`, rows staged, API request count and disk path.
- A worker restart returns stale downloading tasks to `pending`; a task that had already finished downloading and was interrupted during database loading returns to `staged` and reuses the completed file.
- A pause leaves partial staging and pagination state intact; a fully downloaded staged task resumes directly at `COPY` without calling Alpaca again.
- If Alpaca later rejects an expired page token, that task deletes its partial file and restarts from page one. Destination deduplication prevents duplicate bars.
- If a database transaction succeeds but the final task update does not, retrying the COPY is still safe.
- Failed tasks retry up to the job's selected limit; the whole job fails only when a task exhausts that limit.

## Research feature output

When enabled, the worker incrementally refreshes `rd_daily_features` for each task. Fields include:

- Open, high, low and close
- Volume and trade count
- Bar count and volume-weighted price
- Open-to-close return
- Intraday range as a percentage of open
- Realised log-return volatility

Example:

```sql
select *
from rd_daily_features
where timeframe = '5Min'
  and trade_date >= current_date - 90
order by trade_date desc, symbol;
```

Raw bars remain available for intraday trigger discovery:

```sql
select symbol, bar_ts, open, high, low, close, volume, vwap
from rd_bars
where symbol = 'AAPL'
  and timeframe = '1Min'
  and feed = 'sip'
  and bar_ts >= '2026-01-01'
order by bar_ts;
```

## Local use

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m scripts.init_db
uvicorn app.main:app --reload
```

In a second terminal:

```bash
source .venv/bin/activate
python -m app.worker
```

Open `http://localhost:8000` and use the `APP_USERNAME` / `APP_PASSWORD` values from `.env`.

## Validation

```bash
pip install -r requirements-dev.txt
pytest -q
python -m scripts.check_config
```

## Recommended first job

Do not begin with all equities at one-minute resolution.

Use this deployment validation run first:

- Explicit symbols: `AAPL, MSFT, NVDA`
- Last 10 completed calendar days
- `5Min`
- SIP / raw
- Regular session
- 3 symbols per request
- 5 days per task
- Concurrency 2
- Target 500 RPM
- Skip duplicates
- Daily features enabled

After that succeeds, move to a **Rapid breadth** pass: 5-minute SIP bars over 12 months, then add 1-minute enrichment only around candidate events or a smaller liquid universe.

## Important scale warning

A full-universe, one-minute, multi-year load can create hundreds of millions or billions of rows. The app makes that selectable, but the estimate is intentionally prominent because Supabase storage, WAL, indexes and feature refreshes can become the limiting factors before Alpaca does.

For maximum ingestion speed:

1. Keep `conflict_policy=skip` for first-time loads.
2. Disable daily features during the largest raw backfill, then run feature generation in narrower jobs if database pressure is high.
3. Keep staging files disabled after successful loads.
4. Use a separate Supabase project for research data rather than sharing production application tables.
5. Increase worker concurrency only after observing Supabase CPU, disk I/O and connection utilisation.
