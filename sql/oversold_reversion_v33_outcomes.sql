-- Oversold Reversion v3.3 outcome path metrics.
-- Existing six-week research fields remain intact; these columns make the
-- three-session target and the requested 5/10/20-session aliases explicit.

alter table public.or_signal_outcomes
  add column if not exists return_5d double precision
    generated always as (return_1w) stored,
  add column if not exists return_10d double precision
    generated always as (return_2w) stored,
  add column if not exists return_20d double precision
    generated always as (return_4w) stored,
  add column if not exists mfe_3d double precision,
  add column if not exists mae_3d double precision,
  add column if not exists mfe_3d_ts timestamptz,
  add column if not exists mae_3d_ts timestamptz,
  add column if not exists time_to_mfe_3d_sessions smallint,
  add column if not exists time_to_mae_3d_sessions smallint,
  add column if not exists thesis_invalidation_status text not null default 'not_assessed';

create index if not exists idx_or_signal_outcomes_three_session_path
  on public.or_signal_outcomes(signal_timestamp, mfe_3d, mae_3d);
