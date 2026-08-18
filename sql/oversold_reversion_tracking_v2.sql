-- Oversold Reversion tracking v2: point-in-time decision snapshots.
-- Applied to Supabase project mnmkxjirpwbptdnvjmpw on 2026-08-19.

alter table public.or_decision_tracks add column if not exists ended_at timestamptz;
alter table public.or_decision_tracks add column if not exists decision_notes text not null default '';
alter table public.or_decision_tracks add column if not exists context_snapshot jsonb not null default '{}'::jsonb;

update public.or_decision_tracks t
set decision_notes = coalesce(c.review_notes,''),
    context_snapshot = jsonb_build_object(
      'drop_pct', c.drop_pct,
      'spread_pct', c.spread_pct,
      'prev_dollar_volume', c.prev_dollar_volume,
      'catalyst_class', c.catalyst_class,
      'catalyst_summary', c.catalyst_summary,
      'risk_flags', c.risk_flags,
      'heuristic_score', c.heuristic_score,
      'triage_label', c.triage_label,
      'headline_count', c.headline_count
    )
from public.or_candidates c
where c.id=t.candidate_id
  and (t.context_snapshot='{}'::jsonb or t.context_snapshot is null);
