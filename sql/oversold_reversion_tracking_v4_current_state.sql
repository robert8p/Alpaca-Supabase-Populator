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

CREATE OR REPLACE FUNCTION public.or_enforce_single_active_symbol()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  IF NEW.active THEN
    UPDATE public.or_decision_tracks
    SET active = false,
        ended_at = COALESCE(ended_at, NEW.selected_at, now()),
        updated_at = now()
    WHERE symbol = NEW.symbol
      AND active = true
      AND id IS DISTINCT FROM NEW.id;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS or_single_active_symbol ON public.or_decision_tracks;
CREATE TRIGGER or_single_active_symbol
BEFORE INSERT OR UPDATE OF active, symbol
ON public.or_decision_tracks
FOR EACH ROW
EXECUTE FUNCTION public.or_enforce_single_active_symbol();

CREATE UNIQUE INDEX IF NOT EXISTS idx_or_tracks_one_active_symbol
  ON public.or_decision_tracks(symbol)
  WHERE active = true;
