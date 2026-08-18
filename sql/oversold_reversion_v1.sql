CREATE TABLE IF NOT EXISTS or_scans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    trigger_source text NOT NULL DEFAULT 'manual' CHECK (trigger_source IN ('manual','scheduled')),
    scan_date date NOT NULL,
    min_drop_pct double precision NOT NULL DEFAULT 15,
    candidate_limit integer NOT NULL DEFAULT 50,
    asset_count integer NOT NULL DEFAULT 0,
    snapshot_count integer NOT NULL DEFAULT 0,
    candidate_count integer NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    error text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS or_scans_started_idx ON or_scans(started_at DESC);
CREATE INDEX IF NOT EXISTS or_scans_date_idx ON or_scans(scan_date DESC, started_at DESC);

CREATE TABLE IF NOT EXISTS or_candidates (
    id bigserial PRIMARY KEY,
    scan_id uuid NOT NULL REFERENCES or_scans(id) ON DELETE CASCADE,
    rank integer NOT NULL,
    symbol text NOT NULL,
    name text,
    exchange text,
    prev_close double precision,
    last_price double precision,
    drop_pct double precision NOT NULL,
    prev_volume bigint,
    prev_dollar_volume double precision,
    bid double precision,
    ask double precision,
    spread_pct double precision,
    latest_trade_ts timestamptz,
    catalyst_class text NOT NULL DEFAULT 'U' CHECK (catalyst_class IN ('A','B','C','D','E','U')),
    catalyst_summary text,
    risk_flags text[] NOT NULL DEFAULT '{}',
    headline_count integer NOT NULL DEFAULT 0,
    headlines jsonb NOT NULL DEFAULT '[]'::jsonb,
    heuristic_score integer NOT NULL DEFAULT 0 CHECK (heuristic_score BETWEEN 0 AND 100),
    triage_label text NOT NULL,
    decision text NOT NULL DEFAULT 'unreviewed' CHECK (decision IN ('unreviewed','watch','investigate','pass','traded')),
    review_notes text,
    reviewed_at timestamptz,
    raw_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(scan_id, symbol)
);
CREATE INDEX IF NOT EXISTS or_candidates_scan_rank_idx ON or_candidates(scan_id, rank);
CREATE INDEX IF NOT EXISTS or_candidates_symbol_created_idx ON or_candidates(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS or_candidates_score_idx ON or_candidates(scan_id, heuristic_score DESC);

ALTER TABLE or_scans ENABLE ROW LEVEL SECURITY;
ALTER TABLE or_candidates ENABLE ROW LEVEL SECURITY;
