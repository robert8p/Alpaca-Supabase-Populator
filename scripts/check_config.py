from __future__ import annotations

import asyncio

from app.alpaca import AlpacaClient
from app.config import get_settings
from app.db import close_pool, connection


async def main() -> None:
    settings = get_settings()
    print(f"Database host configured: {'@' in settings.database_url}")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, now()")
            print("Supabase:", cur.fetchone())
        conn.rollback()
    async with AlpacaClient(target_rpm=200, max_retries=2) as client:
        health = await client.health()
        print("Alpaca:", health)
    close_pool()


if __name__ == "__main__":
    asyncio.run(main())
