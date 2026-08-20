# Intraday Profitability static frontend

A dependency-free HTML/JavaScript frontend for Render Static Sites. It stores the dedicated app credential in `sessionStorage`, calls the authenticated Supabase Edge Function, polls the worker-backed request queue, renders the ranked candidates, and opens ChatGPT with a frozen point-in-time prompt. It contains no Alpaca, database or OpenAI API secret.
