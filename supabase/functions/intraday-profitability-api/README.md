# Intraday Profitability Edge API

This function is deployed with `verify_jwt = false` because the Render static site is not a Supabase Auth client. It implements its own fixed-username, SHA-256 access-key check before any read or write action. The public `health` action returns no database data. Privileged database access uses Supabase's platform-provided service-role environment variable inside the Edge runtime; the browser never receives it.
