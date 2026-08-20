-- Oversold Reversion tracking performance hardening.
-- Supports track history, completion checks and Day 1-3 checkpoint rendering as
-- the number of review episodes grows.

create index if not exists idx_or_track_checkpoints_track_id
  on public.or_track_checkpoints(track_id);
