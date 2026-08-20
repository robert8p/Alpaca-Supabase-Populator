-- Applied to the Rapid Discovery worker database when user credentials were removed.
-- The browser never receives table privileges; the Edge Function uses service_role.

CREATE TABLE IF NOT EXISTS public.ip_public_api_requests (
    id bigserial PRIMARY KEY,
    client_hash text NOT NULL CHECK (client_hash ~ '^[0-9a-f]{64}$'),
    action text NOT NULL CHECK (action IN ('run','select')),
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ip_public_api_requests_lookup_idx
    ON public.ip_public_api_requests (client_hash, action, created_at DESC);
CREATE INDEX IF NOT EXISTS ip_public_api_requests_created_idx
    ON public.ip_public_api_requests (created_at);

ALTER TABLE public.ip_public_api_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.ip_public_api_requests FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.ip_public_api_requests_id_seq FROM anon, authenticated;
GRANT SELECT, INSERT, DELETE ON TABLE public.ip_public_api_requests TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.ip_public_api_requests_id_seq TO service_role;
