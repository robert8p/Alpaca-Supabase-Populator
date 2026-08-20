-- Oversold Reversion tracking v5: add a third market-session checkpoint window.
-- Existing episodes are backfilled against the Alpaca market calendar by application code.

ALTER TABLE public.or_decision_tracks
  ADD COLUMN IF NOT EXISTS session3_date date,
  ADD COLUMN IF NOT EXISTS session3_open timestamptz,
  ADD COLUMN IF NOT EXISTS session3_close timestamptz;

ALTER TABLE public.or_track_checkpoints
  DROP CONSTRAINT IF EXISTS or_track_checkpoints_session_no_check;

ALTER TABLE public.or_track_checkpoints
  ADD CONSTRAINT or_track_checkpoints_session_no_check
  CHECK (session_no IN (1,2,3));
