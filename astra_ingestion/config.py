"""Explicit runtime configuration; importing this module starts no work."""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit, unquote, parse_qs
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    username: str = "rob"
    password: str = field(default="", repr=False)
    service_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8000
    test_mode: bool = False
    worker_poll_seconds: float = 2.0
    lease_seconds: int = 90
    api_key: str = field(default="", repr=False)
    secret_key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls, *, require_web_auth: bool = True) -> "Settings":
        test_mode = os.environ.get("ASTRA_INGESTION_TEST_MODE") == "1"
        url = os.environ.get("ASTRA_INGESTION_DATABASE_URL", "")
        if not url:
            raise ValueError("ASTRA_INGESTION_DATABASE_URL is required")
        if not url.startswith(("postgresql://", "postgres://")) and not (test_mode and url.startswith("sqlite:///")):
            raise ValueError("Production requires PostgreSQL; SQLite is allowed only in explicit test mode")
        if not test_mode:
            ref = os.environ.get("ASTRA_INGESTION_PROJECT_REF", "")
            if not re.fullmatch(r"[a-z]{20}", ref) or ref in {"xdponktobhosycdhbcrr", "syokddbfiecauakwqygv"}:
                raise ValueError("An explicit current production project reference is required")
            parsed = urlsplit(url)
            overrides = set(parse_qs(parsed.query, keep_blank_values=True)) & {"host", "hostaddr", "port", "user", "password", "dbname", "service", "servicefile"}
            if overrides or parsed.fragment or parsed.path != "/postgres":
                raise ValueError("Database URL contains a connection identity override")
            direct = parsed.hostname == "db." + ref + ".supabase.co"
            pooler = bool(parsed.hostname and parsed.hostname.endswith(".pooler.supabase.com") and unquote(parsed.username or "").endswith("." + ref))
            if not (direct or pooler):
                raise ValueError("Database URL does not match the explicit project binding")
        password = os.environ.get("ASTRA_INGESTION_PASSWORD", "")
        if require_web_auth and len(password.encode("utf-8")) < 32 and not test_mode:
            raise ValueError("A dedicated password of at least 32 characters is required")
        port = int(os.environ.get("PORT", os.environ.get("ASTRA_INGESTION_PORT", "8000")))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid port")
        return cls(database_url=url, username=os.environ.get("ASTRA_INGESTION_USERNAME", "rob"),
                   password=password, port=port, test_mode=test_mode,
                   api_key=os.environ.get("APCA_API_KEY_ID", os.environ.get("ALPACA_API_KEY", "")),
                   secret_key=os.environ.get("APCA_API_SECRET_KEY", os.environ.get("ALPACA_SECRET_KEY", "")))
