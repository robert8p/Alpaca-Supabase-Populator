"""Restricted HTTPS port for staged ASTRA provider-free retained bulk work.

Not wired into the production worker. This client cannot create jobs, insert
source rows, verify/attest outputs, recover leases, invoke provider adapters,
execute arbitrary SQL or grant any database privileges. It requires a genuine
short-lived authenticated *user* JWT issued outside the worker. Decoding JWT
claims here is defensive input screening, NOT signature verification: the
Supabase gateway and a separately qualified database principal must enforce
authentication/authorization before deployment. No runtime role is granted.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, Request, build_opener

from .bulk_reuse_dispatch import DispatchRefused
from .rpc_store import (
    PROJECT_REF, PROJECT_URL, _NoRedirect, _invalid_constant,
    _unique_object, validate_public_key,
)

_SCHEMA = "astra_ingestion_v1"
_ALLOWED = frozenset({
    "bulk_runtime_admission_v1",
    "bulk_runtime_claim_v1",
    "bulk_atomic_retained_page_v1",
    "bulk_retained_receipt_readback_v1",
})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_WORK = re.compile(r"astra-bulk-v1-[0-9a-f]{64}\Z")
_OWNER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_MAX_RESPONSE = 262_144
_TIMEOUT = 15


class BulkPortError(DispatchRefused):
    """Ambiguous remote effects: never retry a mutation before readback."""


class BulkPortAuthError(BulkPortError):
    """An explicit authentication or authorization rejection is not retried."""


def _jwt_claims(token: str) -> dict:
    if (not isinstance(token, str) or len(token) > 8192
            or token.count(".") != 2
            or any(not re.fullmatch(r"[A-Za-z0-9_-]+", item)
                   for item in token.split("."))):
        raise BulkPortAuthError("A genuine user access JWT is required")
    try:
        segment = token.split(".")[1]
        payload = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        claims = json.loads(payload.decode("utf-8"),
                            object_pairs_hook=_unique_object,
                            parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise BulkPortAuthError("Malformed user access JWT claims") from None
    if (not isinstance(claims, dict)
            or claims.get("role") != "authenticated"
            or not isinstance(claims.get("sub"), str)
            or not 1 <= len(claims["sub"]) <= 256
            or type(claims.get("exp")) is not int
            or claims["exp"] <= int(datetime.now(timezone.utc).timestamp())):
        raise BulkPortAuthError("Expired or unauthenticated user JWT refused")
    # The gateway, never these unauthenticated claims, establishes identity.
    return claims


def _sha(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


class RestrictedBulkHttpPort:
    """Exact-function, fail-closed POST interface, with no mutation retries."""

    def __init__(self, public_key: str, access_jwt: str, *, opener=None):
        validate_public_key(public_key)
        _jwt_claims(access_jwt)
        self._public_key = public_key
        self._access_jwt = access_jwt
        self._opener = opener if opener is not None else build_opener(
            _NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def _rpc(self, operation: str, arguments: dict):
        if operation not in _ALLOWED:
            raise BulkPortError("Unsupported restricted function")
        # No caller-supplied domain, path, SQL string or role header.
        url = PROJECT_URL + "/rest/v1/rpc/" + operation
        content = json.dumps(arguments, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(content) > 4096:
            raise BulkPortError("Bounded request exceeded")
        request = Request(url, data=content, method="POST", headers={
            "apikey": self._public_key,
            "Authorization": "Bearer " + self._access_jwt,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Content-Profile": _SCHEMA,
            "Accept-Profile": _SCHEMA,
            "Cache-Control": "no-store",
        })
        try:
            with self._opener.open(request, timeout=_TIMEOUT) as response:
                if response.status != 200 or response.geturl() != url:
                    raise BulkPortError("Unexpected restricted RPC response")
                if (response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                        != "application/json"
                        or response.headers.get("Content-Encoding", "identity") != "identity"):
                    raise BulkPortError("Unexpected restricted RPC representation")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdigit() or int(length) > _MAX_RESPONSE):
                    raise BulkPortError("Oversized restricted RPC response")
                raw = response.read(_MAX_RESPONSE + 1)
                if len(raw) > _MAX_RESPONSE or (length is not None and len(raw) != int(length)):
                    raise BulkPortError("Incomplete restricted RPC response")
        except HTTPError as exc:
            status = exc.code
            exc.close()
            if status in (401, 403):
                raise BulkPortAuthError("Restricted user access rejected") from None
            raise BulkPortError("Restricted RPC outcome uncertain; read back before retry") from None
        except (URLError, TimeoutError, OSError):
            raise BulkPortError("Restricted RPC outcome uncertain; read back before retry") from None
        try:
            result = json.loads(raw.decode("utf-8"),
                                object_pairs_hook=_unique_object,
                                parse_constant=_invalid_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise BulkPortError("Invalid restricted RPC response") from None
        if result is not None and not isinstance(result, dict):
            raise BulkPortError("Unexpected restricted RPC result shape")
        return result

    def admission(self, manifest: str):
        if not _sha(manifest):
            raise BulkPortError("Invalid exact manifest")
        return self._rpc("bulk_runtime_admission_v1", {"p_manifest": manifest})

    def claim_retained(self, manifest: str, owner: str, lease_seconds: int):
        if (not _sha(manifest) or not isinstance(owner, str)
                or _OWNER.fullmatch(owner) is None
                or type(lease_seconds) is not int or not 10 <= lease_seconds <= 180):
            raise BulkPortError("Invalid finite claim")
        return self._rpc("bulk_runtime_claim_v1", {
            "p_manifest": manifest, "p_owner": owner, "p_lease_seconds": lease_seconds})

    def commit_retained_page(self, claim: dict, page: int):
        if (not isinstance(claim, dict) or not isinstance(claim.get("work_key"), str)
                or _WORK.fullmatch(claim["work_key"]) is None
                or not isinstance(claim.get("claim_owner"), str)
                or _OWNER.fullmatch(claim["claim_owner"]) is None
                or type(claim.get("claim_fence")) is not int
                or claim["claim_fence"] < 1
                or type(page) is not int or not 0 <= page <= 1_000_000):
            raise BulkPortError("Invalid original-fence materialization")
        return self._rpc("bulk_atomic_retained_page_v1", {
            "p_work": claim["work_key"], "p_owner": claim["claim_owner"],
            "p_fence": claim["claim_fence"], "p_page": page})

    def readback_receipt(self, work_key: str, page: int):
        if (not isinstance(work_key, str) or _WORK.fullmatch(work_key) is None
                or type(page) is not int or not 0 <= page <= 1_000_000):
            raise BulkPortError("Invalid bounded receipt readback")
        receipt = self._rpc("bulk_retained_receipt_readback_v1", {
            "p_work": work_key, "p_page": page})
        if receipt is not None and (
            receipt.get("work_key") != work_key or receipt.get("page_no") != page
            or receipt.get("consistent") is not True
            or type(receipt.get("records_committed")) is not int
            or receipt["records_committed"] < 1
            or receipt.get("requests_committed") != 0
            or not _sha(receipt.get("source_sha256"))
            or not _sha(receipt.get("output_sha256"))
            or receipt.get("actual_output_sha256") != receipt.get("output_sha256")
            or receipt.get("actual_records") != receipt.get("records_committed")
        ):
            raise BulkPortError("Committed receipt mismatched output; preserve hold")
        return receipt
