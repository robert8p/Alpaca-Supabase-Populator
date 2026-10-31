"""Explicit runtime configuration; importing this module starts no work."""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit, unquote
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default="", repr=False)
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
    project_ref: str = "oxzabweahkoimtevbbny"
    api_url: str = ""
    publishable_key: str = field(default="", repr=False)
    rpc_token: str = field(default="", repr=False)

    @classmethod
    def from_env(cls, *, require_web_auth: bool = True) -> "Settings":
        test_mode = os.environ.get("ASTRA_INGESTION_TEST_MODE") == "1"
        url = os.environ.get("ASTRA_INGESTION_DATABASE_URL", "")
        ref = os.environ.get("ASTRA_INGESTION_PROJECT_REF", "")
        api_url = os.environ.get("ASTRA_INGESTION_API_URL", "")
        public_key = os.environ.get("ASTRA_INGESTION_PUBLISHABLE_KEY", "")
        rpc_token = os.environ.get("ASTRA_INGESTION_RPC_TOKEN", "")
        if test_mode and url:
            parsed = urlsplit(url)
            if url.startswith("sqlite:///"):
                pass
            elif (parsed.scheme in ("postgres", "postgresql") and parsed.hostname in ("localhost", "127.0.0.1", "::1")
                  and unquote(parsed.path) == "/astra_ingestion_qualification" and not parsed.query and not parsed.fragment):
                pass
            else:
                raise ValueError("Test databases must be SQLite or the explicitly named loopback qualification database")
        else:
            if url:
                raise ValueError("Production runtime does not accept direct database credentials")
            from .rpc_store import TOKEN_PATTERN, validate_endpoint, validate_public_key
            api_url = validate_endpoint(api_url, ref)
            validate_public_key(public_key)
            if not TOKEN_PATTERN.fullmatch(rpc_token):
                raise ValueError("A dedicated 256-bit ingestion capability token is required")
        password = os.environ.get("ASTRA_INGESTION_PASSWORD", "")
        if require_web_auth and len(password.encode("utf-8")) < 32 and not test_mode:
            raise ValueError("A dedicated password of at least 32 characters is required")
        port = int(os.environ.get("PORT", os.environ.get("ASTRA_INGESTION_PORT", "8000")))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid port")
        return cls(database_url=url, username=os.environ.get("ASTRA_INGESTION_USERNAME", "rob"),
                   password=password, port=port, test_mode=test_mode,
                   project_ref=ref, api_url=api_url, publishable_key=public_key, rpc_token=rpc_token,
                   api_key=os.environ.get("APCA_API_KEY_ID", os.environ.get("ALPACA_API_KEY", "")),
                   secret_key=os.environ.get("APCA_API_SECRET_KEY", os.environ.get("ALPACA_SECRET_KEY", "")))
