# Step-by-step deployment: GitHub + Supabase + Render

## 1. Create a dedicated Supabase project

A separate project is strongly recommended because intraday bars can dominate storage, write-ahead logging and index activity.

In Supabase:

1. Create the project.
2. Open **Connect**.
3. Select the **Session pooler** connection string on port **5432**.
4. Replace the password placeholder and keep `sslmode=require`.
5. Save the complete URI as `DATABASE_URL`.

Example shape:

```text
postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

URL-encode special characters in the database password.

The app creates its schema automatically. You can also run `sql/schema.sql` manually in the Supabase SQL editor.

## 2. Create a new GitHub repository

1. Extract the zip.
2. Create an empty GitHub repository, for example `alpaca-rapid-discovery-loader`.
3. Upload all extracted files to the repository root, including `render.yaml`.
4. Commit the files.

## 3. Create the Render Blueprint

1. In Render, select **New → Blueprint**.
2. Connect the new GitHub repository.
3. Render detects `render.yaml`.
4. Confirm the two services:
   - `alpaca-rapid-discovery-web`
   - `alpaca-rapid-discovery-worker`
5. Confirm the worker has a 20 GB persistent disk mounted at `/var/data`.

The supplied Blueprint uses:

- Web: Starter
- Worker: Standard
- Region: Frankfurt

The worker is the service to upgrade first if decompression, feature calculation or database-copy preparation becomes CPU constrained. Database speed may still be the bottleneck.

## 4. Enter secrets

Render prompts for unsynchronised variables. Enter the same values for both services where applicable:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Supabase Session pooler URI |
| `ALPACA_API_KEY` | Alpaca key ID |
| `ALPACA_SECRET_KEY` | Alpaca secret |
| `APP_PASSWORD` | Web service only; choose a long unique password |

`APP_USERNAME` defaults to `admin` on the web service. Change it in Render if desired.

Do not use the Supabase anon key or service-role key as `DATABASE_URL`. The application needs a PostgreSQL connection string for `COPY` and partition DDL.

## 5. Deploy

Apply the Blueprint. Both services may attempt schema initialisation; the SQL uses a transaction-scoped PostgreSQL advisory lock so one completes before the other.

Wait for:

- Web health: `/health` returns `status: ok`
- Worker logs: `Worker ... started`
- Dashboard footer: a recent green worker heartbeat

## 6. Open and validate the dashboard

1. Open the web service URL.
2. Sign in with `APP_USERNAME` and `APP_PASSWORD`.
3. Open **System**.
4. Select **Run tests**.
5. Confirm:
   - Supabase Postgres: connected
   - Alpaca APIs: active assets returned

## 7. Run the small validation job

Choose **New load → Event precision**, then change it to:

- Symbols: `AAPL, MSFT, NVDA`
- Date range: last 10 completed days
- Candle interval: `5Min`
- Feed: SIP
- Session: Regular
- Symbols/request: 3
- Days/task: 5
- Concurrent tasks: 2
- Target RPM: 500

Select **Estimate load**, review the result, then queue the job.

A successful job should show:

- All tasks completed
- Non-zero rows loaded
- Worker heartbeat current
- `rd_inventory` containing a 5Min/SIP/raw row
- `rd_daily_features` populated when feature generation is enabled

## 8. Scale deliberately

Recommended next sequence:

1. 5-minute, 12-month, 250-symbol sample.
2. 5-minute, 12-month, full filtered exchange universe.
3. Evaluate data size and discovery usefulness.
4. Add 1-minute data for liquid symbols or candidate event windows.
5. Extend backwards only after a candidate rule survives recent-period testing.

Suggested initial production throughput:

- 20 symbols/request
- 5–10 days/task
- 6 concurrent tasks
- 9,000 target RPM
- 10,000 rows/page

The target RPM is a ceiling, not a guaranteed rate. Network latency, pagination distribution, staging compression and Supabase writes determine actual throughput.

## 9. Monitoring and troubleshooting

### Dashboard says no worker

Check the worker service logs and verify its `DATABASE_URL`. A persistent disk is not sufficient by itself; the worker must connect to the same Supabase project as the web service.

### Job remains in planning

The worker is resolving and filtering assets. If its heartbeat is stale, restart the worker. A stale planning job with no tasks is automatically returned to `queued`.

### HTTP 403 from Alpaca

The selected feed or historical entitlement is unavailable to the API key. Use IEX or verify the Algo Trader Plus/SIP entitlement.

### HTTP 429

Reduce target RPM and/or concurrency. The worker respects 429 responses and rate-limit headers, but several unrelated applications using the same Alpaca key share the effective allowance.

### Supabase connection or COPY timeout

- Confirm Session pooler port 5432.
- Reduce concurrent tasks.
- Temporarily disable daily features.
- Check Supabase database CPU, I/O, disk and active connections.
- Upgrade Supabase compute before increasing the Render worker again.

### Worker restarts during a task

No manual intervention is normally required. After `WORKER_STALE_SECONDS`, a partially downloaded task returns to pending and continues from its saved staging file/page token. A fully downloaded task interrupted during `COPY` returns to staged and reuses the completed file. If Alpaca rejects an old token, the task safely restarts from page one.

### Disk fills

Disable **Keep compressed staging files**, increase the Render disk, or remove completed job folders from the worker shell under `/var/data/staging`. Disk size can be increased later but not reduced.
