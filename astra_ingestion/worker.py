"""Bounded ingestion-only worker. Run with python -m astra_ingestion.worker."""
from __future__ import annotations

import hashlib
import json
import signal
import sys
import threading
import uuid

from .config import Settings
from .models import IngestionSpec
from .reconcile import compare_records
from .source import AlpacaSource, SourceError, parse_page, record_key
from .store import LeaseLost, QualityHold, RequestDeferred, Store


def verify_receipts(claim, receipts, actual):
    """Reconstruct expectations from original source evidence in a fresh read."""
    spec = IngestionSpec.from_dict(claim["spec"])
    if not receipts:
        raise QualityHold("No retained source receipts")
    expected = {}
    token = None
    seen_tokens = set()
    for index, receipt in enumerate(receipts):
        if receipt["page_no"] != index or receipt["token_in"] != token:
            raise QualityHold("Source pagination receipt chain is incomplete")
        digest = hashlib.sha256(receipt["raw_body"].encode("utf-8")).hexdigest()
        if digest != receipt["body_sha256"]:
            raise QualityHold("Retained source receipt hash mismatch")
        parsed = parse_page(receipt["raw_body"], symbol=claim["symbol"],
                            start=claim["start"], end=claim["end"], timeframe=spec.timeframe)
        if parsed.next_page_token != receipt["token_out"]:
            raise QualityHold("Stored pagination checkpoint does not match source receipt")
        for row in parsed.records:
            key = record_key(row)
            if key in expected and expected[key] != row:
                raise QualityHold("Source receipts contain conflicting values for one key")
            expected[key] = row
        token = parsed.next_page_token
        if token is not None:
            if token in seen_tokens:
                raise QualityHold("Repeated source pagination token")
            seen_tokens.add(token)
        elif index != len(receipts) - 1:
            raise QualityHold("Unexpected receipt after the final source page")
    if token is not None:
        raise QualityHold("Final source page has not been received")
    if not expected:
        raise QualityHold("Empty source coverage cannot be certified automatically")
    result = compare_records(expected.values(), actual)
    result["scope_hash"] = spec.scope_hash
    result["receipt_count"] = len(receipts)
    result["coverage_certification"] = "NOT_CERTIFIED"
    result["verification_kind"] = "source_to_target_exact"
    return result


class Worker:
    def __init__(self, store, source, *, worker_id=None, lease_seconds=90, after_commit=None):
        self.store = store
        self.source = source
        self.worker_id = worker_id or str(uuid.uuid4())
        self.lease_seconds = lease_seconds
        self.after_commit = after_commit

    def run_once(self):
        claim = self.store.claim_next(self.worker_id, self.lease_seconds)
        if claim is None:
            return {"state": "idle"}
        fetched = None
        try:
            if claim["phase"] == "verify":
                receipts, actual = self.store.verification_material(claim)
                result = verify_receipts(claim, receipts, actual)
                self.store.finish_verification(claim, result)
                return {"state": "verified" if result["status"] == "passed" else "blocked", "partition_id": claim["id"]}
            self.store.reserve_request(claim)
            spec = IngestionSpec.from_dict(claim["spec"])
            fetched = self.source.fetch_page(spec, claim, claim["next_page_token"])
            parsed = parse_page(fetched.raw_text, symbol=claim["symbol"],
                                start=claim["start"], end=claim["end"], timeframe=spec.timeframe)
            result = self.store.commit_page(claim, fetched, parsed)
            # Qualification hook only; a process crash here must not replay effects.
            if self.after_commit is not None:
                self.after_commit(claim)
            return {"state": "page_committed", "partition_id": claim["id"], **result}
        except RequestDeferred:
            return {"state": "waiting", "partition_id": claim["id"]}
        except LeaseLost:
            return {"state": "ownership_lost", "partition_id": claim["id"]}
        except (SourceError, QualityHold) as exc:
            try:
                self.store.fail_claim(
                    claim, code=getattr(exc, "code", "QUALITY_HOLD"), message=str(exc),
                    retryable=getattr(exc, "retryable", False),
                    retry_after=getattr(exc, "retry_after", 0),
                    raw_response=fetched.raw_text if fetched is not None else None,
                )
            except LeaseLost:
                return {"state": "ownership_lost", "partition_id": claim["id"]}
            return {"state": "retry_or_hold", "partition_id": claim["id"]}
        # An unexpected database outcome propagates. Do not replay or overwrite it:
        # a replacement reads the durable receipt/checkpoint after lease expiry.


def _qualification_gateway_probe(settings):
    """One-time anonymous HTTPS boundary check; never emit the public key."""
    from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
    from urllib.error import HTTPError, URLError
    import ssl

    class _NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None

    opener = build_opener(_NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    tests = (
        ("private_verifier_with_publishable", "/rest/v1/rpc/independent_verify_tick_v1",
         b"{}", {"Accept-Profile": "astra_ingestion_v1", "Content-Profile": "astra_ingestion_v1"}),
        ("private_verifier_default_schema", "/rest/v1/rpc/independent_verify_tick_v1",
         b"{}", {}),
        ("public_dispatch_without_capability", "/rest/v1/rpc/astra_ingestion_rpc_v1",
         b'{"operation":"health","payload":{}}', {}),
    )
    results = []
    for name, path, data, extra in tests:
        # The public project key identifies the anonymous gateway actor.
        # No worker RPC capability, service key or user JWT is transmitted.
        req = Request(settings.api_url + path, data=data, method="POST",
                      headers={"apikey": settings.publishable_key,
                               "Content-Type": "application/json", **extra})
        try:
            with opener.open(req, timeout=7) as response:
                status = response.status
        except HTTPError as exc:
            status = exc.code
            exc.close()
        except (URLError, TimeoutError, OSError):
            status = None
        results.append({"test": name, "http_status": status,
                        "denied": status in (400, 401, 403, 404, 405, 406)})
    print(json.dumps({"state": "gateway_qualification_completed",
                      "results": results}, sort_keys=True), flush=True)


def main():
    settings = Settings.from_env(require_web_auth=False)
    if not settings.api_key or not settings.secret_key:
        raise SystemExit("Dedicated provider credentials are required")
    from .rpc_store import create_store
    store = create_store(settings)
    store.health()
    _qualification_gateway_probe(settings)
    worker = Worker(store, AlpacaSource(settings.api_key, settings.secret_key), lease_seconds=settings.lease_seconds)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            outcome = worker.run_once()
            if outcome["state"] not in ("idle", "waiting"):
                print(json.dumps(outcome), flush=True)
        except Exception as exc:
            # Never print driver exceptions: they can contain connection details.
            print(json.dumps({"state": "unresolved_runtime_error", "error_type": type(exc).__name__}), file=sys.stderr, flush=True)
            return 1
        stop.wait(settings.worker_poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
