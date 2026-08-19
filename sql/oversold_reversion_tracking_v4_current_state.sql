-- Oversold Reversion v4: Reject decision + one active tracked episode per symbol.

ALTER TABLE public.or_candidates
  DROP CONSTRAINT IF EXISTS or_candidates_decision_check;
ALTER TABLE public.or_candidates
  ADD CONSTRAINT or_candidates_decision_check
  CHECK (decision = ANY (ARRAY[
    'unreviewed'::text,
    'watch'::text,
    'investigate'::text,
    'pass'::text,
    'reject'::text,
    'traded'::text
  ]));

-- Keep all historical episodes, but only the newest episode for a symbol may be current.
WITH ranked_active AS (
  SELECT id,
         row_number() OVER (PARTITION BY symbol ORDER BY selected_at DESC, id DESC) AS rn
  FROM public.or_decision_tracks
  WHERE active = true
)
UPDATE public.or_decision_tracks t
SET active = false,
    ended_at = COALESCE(t.ended_at, now()),
    updated_at = now()
FROM ranked_active r
WHERE t.id = r.id
  AND r.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_or_tracks_one_active_symbol
  ON public.or_decision_tracks(symbol)
  WHERE active = true;
