-- Oversold Reversion tracking v3: append-only decision episodes.
-- Apply only after application code no longer uses ON CONFLICT(candidate_id).

alter table public.or_decision_tracks
  drop constraint if exists or_decision_tracks_candidate_id_key;

create unique index if not exists idx_or_tracks_one_active_candidate
  on public.or_decision_tracks(candidate_id)
  where active=true;

create index if not exists idx_or_tracks_candidate_history
  on public.or_decision_tracks(candidate_id,selected_at desc);
