# Intraday Profitability Edge API

This function is deliberately deployed with `verify_jwt = false` because the Render static site is a public, credential-free application rather than a Supabase Auth client.

The browser supplies no username, access key, database key or Alpaca credential. The Edge Function instead protects privileged operations through:

- an exact production-origin allowlist and CORS preflight handling;
- one active scan at a time;
- a global scan cooldown;
- hashed client mutation-rate limits stored in `ip_public_api_requests`;
- strict server-side input bounds;
- unique database constraints for active scans and candidate selections;
- Row Level Security with no `anon` or `authenticated` table access.

`health` and `readiness` expose only operational status. Database access uses Supabase's platform-provided service-role environment variable inside the Edge runtime; it is never sent to the browser.
