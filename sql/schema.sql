SELECT pg_advisory_xact_lock(hashtext('alpaca_rapid_discovery_schema_v1'));

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS rd_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued','planning','running','pause_requested','paused','cancel_requested',
        'cancelled','finalising','completed','failed'
    )),
    config jsonb NOT NULL,
    symbol_count integer NOT NULL DEFAULT 0,
    total_tasks integer NOT NULL DEFAULT 0,
    completed_tasks integer NOT NULL DEFAULT 0,
    failed_tasks integer NOT NULL DEFAULT 0,
    rows_staged bigint NOT NULL DEFAULT 0,
    rows_loaded bigint NOT NULL DEFAULT 0,
    api_requests bigint NOT NULL DEFAULT 0,
    bytes_staged bigint NOT NULL DEFAULT 0,
    feature_rows bigint NOT NULL DEFAULT 0,
    claimed_by text,
    heartbeat_at timestamptz,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rd_jobs_status_created_idx ON rd_jobs(status, created_at);

CREATE TABLE IF NOT EXISTS rd_job_symbols (
    job_id uuid NOT NULL REFERENCES rd_jobs(id) ON DELETE CASCADE,
    symbol text NOT NULL,
    PRIMARY KEY (job_id, symbol)
);

CREATE TABLE IF NOT EXISTS rd_tasks (
    id bigserial PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES rd_jobs(id) ON DELETE CASCADE,
    timeframe text NOT NULL,
    feed text NOT NULL,
    adjustment text NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    symbols text[] NOT NULL,
    symbols_hash text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending','running','staged','loading','completed','failed','cancelled'
    )),
    page_token text,
    pages_completed integer NOT NULL DEFAULT 0,
    rows_staged bigint NOT NULL DEFAULT 0,
    rows_loaded bigint NOT NULL DEFAULT 0,
    api_requests integer NOT NULL DEFAULT 0,
    bytes_staged bigint NOT NULL DEFAULT 0,
    staging_path text,
    attempts integer NOT NULL DEFAULT 0,
    claimed_by text,
    heartbeat_at timestamptz,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(job_id, timeframe, feed, adjustment, window_start, window_end, symbols_hash)
);

CREATE INDEX IF NOT EXISTS rd_tasks_job_status_idx ON rd_tasks(job_id, status, id);
CREATE INDEX IF NOT EXISTS rd_tasks_running_heartbeat_idx ON rd_tasks(status, heartbeat_at);

CREATE TABLE IF NOT EXISTS rd_job_events (
    id bigserial PRIMARY KEY,
    job_id uuid REFERENCES rd_jobs(id) ON DELETE CASCADE,
    task_id bigint REFERENCES rd_tasks(id) ON DELETE CASCADE,
    level text NOT NULL DEFAULT 'info',
    event_type text NOT NULL,
    message text NOT NULL,
    details jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rd_job_events_job_created_idx ON rd_job_events(job_id, created_at DESC);

CREATE TABLE IF NOT EXISTS rd_workers (
    worker_id text PRIMARY KEY,
    status text NOT NULL,
    current_job_id uuid,
    current_task_ids bigint[] NOT NULL DEFAULT '{}',
    version text NOT NULL,
    details jsonb,
    heartbeat_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rd_assets (
    symbol text PRIMARY KEY,
    asset_id uuid,
    asset_class text,
    exchange text,
    name text,
    status text,
    tradable boolean,
    marginable boolean,
    shortable boolean,
    easy_to_borrow boolean,
    borrow_status text,
    fractionable boolean,
    attributes jsonb,
    raw jsonb NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rd_assets_exchange_idx ON rd_assets(exchange, symbol);

CREATE TABLE IF NOT EXISTS rd_bars (
    symbol text NOT NULL,
    bar_ts timestamptz NOT NULL,
    timeframe text NOT NULL,
    feed text NOT NULL,
    adjustment text NOT NULL,
    session_label text NOT NULL,
    open double precision NOT NULL,
    high double precision NOT NULL,
    low double precision NOT NULL,
    close double precision NOT NULL,
    volume bigint NOT NULL,
    trade_count bigint,
    vwap double precision,
    loaded_by_job_id uuid,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, timeframe, feed, adjustment, bar_ts)
) PARTITION BY RANGE (bar_ts);

CREATE INDEX IF NOT EXISTS rd_bars_symbol_ts_idx ON rd_bars(symbol, bar_ts);
CREATE INDEX IF NOT EXISTS rd_bars_timeframe_ts_idx ON rd_bars(timeframe, bar_ts);
CREATE INDEX IF NOT EXISTS rd_bars_session_ts_idx ON rd_bars(session_label, bar_ts);

CREATE TABLE IF NOT EXISTS rd_daily_features (
    symbol text NOT NULL,
    trade_date date NOT NULL,
    timeframe text NOT NULL,
    feed text NOT NULL,
    adjustment text NOT NULL,
    session_label text NOT NULL DEFAULT 'regular',
    first_bar_ts timestamptz,
    last_bar_ts timestamptz,
    open double precision,
    high double precision,
    low double precision,
    close double precision,
    volume bigint,
    trade_count bigint,
    bar_count integer,
    vwap double precision,
    return_pct double precision,
    range_pct double precision,
    realised_volatility double precision,
    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(symbol, trade_date, timeframe, feed, adjustment, session_label)
);
CREATE INDEX IF NOT EXISTS rd_daily_features_date_idx ON rd_daily_features(trade_date, timeframe);

CREATE TABLE IF NOT EXISTS rd_inventory (
    timeframe text NOT NULL,
    feed text NOT NULL,
    adjustment text NOT NULL,
    min_bar_ts timestamptz,
    max_bar_ts timestamptz,
    rows_loaded bigint NOT NULL DEFAULT 0,
    loads_completed bigint NOT NULL DEFAULT 0,
    last_job_id uuid,
    last_loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(timeframe, feed, adjustment)
);

CREATE OR REPLACE FUNCTION rd_set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS rd_jobs_set_updated_at ON rd_jobs;
CREATE TRIGGER rd_jobs_set_updated_at BEFORE UPDATE ON rd_jobs
FOR EACH ROW EXECUTE FUNCTION rd_set_updated_at();

DROP TRIGGER IF EXISTS rd_tasks_set_updated_at ON rd_tasks;
CREATE TRIGGER rd_tasks_set_updated_at BEFORE UPDATE ON rd_tasks
FOR EACH ROW EXECUTE FUNCTION rd_set_updated_at();
