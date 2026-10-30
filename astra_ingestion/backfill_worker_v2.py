"""Replacement execution inside the existing continuously running worker."""
from __future__ import annotations

from hashlib import sha256
import json
import os
import uuid

from .backfill_provider_v2 import KINDS, BackfillProvider, ProviderProblem, canonical, parse_response, utc_now
from .store import LeaseLost, RequestDeferred
from .rpc_store import RpcPersistenceError

DERIVED_KINDS = ("derive_daily", "derive_intraday", "derive_breadth")
RUN_ID = "fixed3000-20250901-20260731-v1-20261030"


def fence(claim):
    return {key: claim[key] for key in ("id", "run_id", "owner", "generation", "run_fence", "page_no")}


class BackfillWorker:
    def __init__(self, store, provider, *, worker_id=None, lease_seconds=90,
                 source_revision="local-unversioned", capability_revision=None, after_commit=None,
                 planning_enabled=False, plan_member_limit=1,
                 identity_enabled=False, retained_massive_enabled=False):
        self.store, self.provider = store, provider
        self.worker_id = worker_id or str(uuid.uuid4())
        self.lease_seconds, self.source_revision = lease_seconds, source_revision
        self.supported_kinds = tuple(provider.supported_kinds()) + DERIVED_KINDS + ("retained_reuse",)
        self.identity_enabled = bool(identity_enabled)
        if self.identity_enabled:
            self.supported_kinds += ("retained_identity",)
        if retained_massive_enabled:
            self.supported_kinds += ("retained_massive_archive",)
        self.capability_revision = capability_revision or sha256(canonical({
            "source_revision": source_revision, "supported_kinds": self.supported_kinds,
            "config_revision": os.environ.get("ASTRA_PROVIDER_CONFIG_REVISION", "initial")}).encode()).hexdigest()
        self.after_commit = after_commit
        self.planning_enabled, self.plan_complete, self._plan_cycle = planning_enabled, False, 0
        self.plan_member_limit = max(1, min(int(plan_member_limit), 5))

    def call(self, operation, payload):
        return self.store._call(operation, payload)

    def run_once(self):
        # The fixed, bounded planner lives in the same database and worker. Its
        # committed member cursor survives a process restart. Source acquisition
        # is interleaved with planning, so admission does not delay useful work.
        if self.planning_enabled and not self.plan_complete:
            if self._plan_cycle % 5 == 0:
                plan = self.call("backfill_plan_next", {"run_id": RUN_ID, "member_limit": self.plan_member_limit,
                                  "supported_kinds": list(self.supported_kinds),
                                  "capability_revision": self.capability_revision})
                self.plan_complete = bool(plan.get("plan_complete"))
            self._plan_cycle += 1
        claim = self.call("backfill_claim", {"worker_id": self.worker_id,
                          "lease_seconds": self.lease_seconds,
                          "supported_kinds": list(self.supported_kinds),
                          "source_revision": self.source_revision,
                          "capability_revision": self.capability_revision})
        if claim is None:
            return {"state": "idle"}
        owned = fence(claim)
        try:
            if claim["kind"] == "retained_identity":
                from .backfill_identity_v2 import IdentityMaterialError, prepare_retained_identity_commit
                source = self.call("backfill_identity_source_read", {"claim": owned})
                try:
                    payload = prepare_retained_identity_commit(claim, source)
                except IdentityMaterialError:
                    raise ProviderProblem("RETAINED_IDENTITY_SOURCE_INVALID",
                                          "Retained identity source requires reconciliation",
                                          evidence={"source_id": claim["scope"].get("identity_source_id"),
                                                    "source_state": source.get("state"),
                                                    "reason": source.get("reason")}) from None
                committed = self.call("backfill_identity_source_commit", payload)
                if self.after_commit is not None:
                    self.after_commit(claim)
                readback = self.verify_committed(claim, committed["body_sha256"], committed["record_count"])
                proof = (readback.get("verification") or {}).get("retained_identity_verification")
                if not isinstance(proof, dict) or not proof.get("passed"):
                    raise RpcPersistenceError("Committed historical identity source lacks matching independent verification")
                return {"state": "backfill_identity_source_committed", "run_id": claim["run_id"],
                        "task_id": claim["id"], "family": claim["family"], **committed}
            if claim["kind"] == "retained_massive_archive":
                committed = self.call("backfill_massive_archive_commit", {"claim": owned})
                if self.after_commit is not None:
                    self.after_commit(claim)
                readback = self.verify_committed(claim, committed["body_sha256"], committed["record_count"])
                proof = (readback.get("verification") or {}).get("retained_s02_verification")
                if not isinstance(proof, dict) or not proof.get("passed"):
                    raise RpcPersistenceError("Committed retained Massive page lacks matching independent verification")
                return {"state": "backfill_massive_archive_committed", "run_id": claim["run_id"],
                        "task_id": claim["id"], "family": claim["family"], **committed}
            if claim["kind"] == "retained_reuse":
                committed = self.call("backfill_reuse_commit", {"claim": owned})
                if self.after_commit is not None:
                    self.after_commit(claim)
                readback = self.verify_committed(claim, committed["body_sha256"], committed["record_count"])
                source = (readback.get("verification") or {}).get("retained_source_verification")
                if not isinstance(source, dict):
                    source = self.call("backfill_reuse_verify", {"task_id": claim["id"], "page_no": claim["page_no"]})
                if not source.get("passed"):
                    raise RpcPersistenceError("Committed retained-source reference differs from its source; reconcile without copying or refetching")
                return {"state": "backfill_reuse_committed", "run_id": claim["run_id"],
                        "task_id": claim["id"], "family": claim["family"],
                        "source_readback": source["state"], **committed}
            if claim["kind"] in DERIVED_KINDS:
                return self.derive(claim, owned)
            # Reservation is part of the same authenticated and fenced queue as
            # the legacy worker. A fatal/uncertain database result is not retried.
            self.provider.require_credentials(claim)
            reservation = self.call("backfill_reserve", {"claim": owned})
            if isinstance(reservation, dict) and reservation.get("state") == "request_deferred":
                return {"state": "waiting", "task_id": claim["id"]}
            page = self.provider.fetch(claim)
            payload = {"claim": owned, **page.payload(),
                       "terminal_state": "INGESTED" if page.records else "NO_DATA_RETURNED"}
            committed = self.call("backfill_commit", payload)
            if self.after_commit is not None:
                self.after_commit(claim)
            self.verify_committed(claim, page.body_sha256, len(page.records))
            return {"state": "backfill_page_committed", "run_id": claim["run_id"],
                    "task_id": claim["id"], "family": claim["family"],
                    "page_no": claim["page_no"], **(committed or {})}
        except RequestDeferred:
            return {"state": "waiting", "task_id": claim["id"]}
        except LeaseLost:
            return {"state": "ownership_lost", "task_id": claim["id"]}
        except ProviderProblem as error:
            try:
                result = self.call("backfill_defer", {"claim": owned, "code": error.code,
                                   "message": str(error), "retryable": error.retryable,
                                   "retry_after": error.retry_after, "evidence": error.evidence})
            except LeaseLost:
                return {"state": "ownership_lost", "task_id": claim["id"]}
            return {"state": "backfill_exception_recorded", "task_id": claim["id"],
                    "family": claim["family"], "code": error.code,
                    "disposition": result.get("state") if isinstance(result, dict) else None}

    def verify_committed(self, claim, digest, expected_count):
        actual = self.call("backfill_verify", {"claim": fence(claim), "page_no": claim["page_no"],
                          "body_sha256": digest, "include_raw": False})
        if (not isinstance(actual, dict) or actual.get("state") != "committed"
                or actual.get("body_sha256") != digest or actual.get("readback_sha256") != digest
                or actual.get("record_count") != expected_count):
            # The source page has already committed. Do not overwrite it or
            # dispatch the provider again after an uncertain readback outcome.
            raise RpcPersistenceError("Replacement source-to-database readback differs; reconcile the durable receipt")
        return actual

    def retained_material(self, claim, source_task):
        """Read only qualified source rows in this calculation's input window."""
        rows, after, seen = [], None, set()
        invalid = 0
        for _ in range(24):
            payload = {"claim": fence(claim), "mode": "material", "source_task_id": source_task["id"], "limit": 2000}
            if after is not None:
                payload["after"] = after
            page = self.call("backfill_reuse_read", payload)
            for row in page.get("rows", []):
                if row.get("provenance_qualified") and row.get("valid_ohlcv"):
                    rows.append(row)
                else:
                    invalid += 1
            if not page.get("has_more"):
                return rows, invalid
            after = page.get("next_after")
            if not after or after in seen:
                raise ProviderProblem("INCOMPLETE_MATERIAL_CURSOR", "Retained-source material cursor did not advance")
            seen.add(after)
        raise ProviderProblem("DERIVATION_UNIT_TOO_LARGE", "Retained-source calculation input requires smaller date units")

    def derive(self, claim, owned):
        from .backfill_features_v2 import derive_family
        scope = claim["scope"]
        if claim["kind"] == "derive_intraday" and scope.get("prefer_retained_formula_cache"):
            cached = self.call("backfill_feature_reuse_commit", {"claim": owned})
            if cached.get("state") != "CACHE_NOT_REUSABLE":
                if self.after_commit is not None:
                    self.after_commit(claim)
                proof = self.verify_committed(claim, cached["body_sha256"], cached["record_count"])
                feature_proof = (proof.get("verification") or {}).get("retained_feature_verification")
                if not isinstance(feature_proof, dict) or not feature_proof.get("passed"):
                    raise RpcPersistenceError("Committed retained-feature reference lacks an independent matching source verification")
                return {"state": "backfill_feature_reuse_committed", "run_id": claim["run_id"],
                        "task_id": claim["id"], "family": claim["family"],
                        "source_readback": feature_proof.get("state"), **cached}
        rows, lineage, after = [], [], None
        retained_rows, replacement_days = [], set()
        if claim["kind"] == "derive_breadth":
            seen = set()
            for _ in range(4):
                material = self.call("backfill_breadth_material", {"claim": owned, "after": after, "limit": 1000})
                if not material.get("ready"):
                    raise ProviderProblem("DEPENDENCY_WAIT", "Cohort daily inputs are still acquiring", retryable=True, retry_after=120)
                rows.extend(material.get("rows", []))
                lineage.extend(material.get("input_lineage", []))
                if material.get("complete"):
                    break
                after = material.get("next_after")
                if after is None or after in seen:
                    raise ProviderProblem("INCOMPLETE_MATERIAL_CURSOR", "Cohort input cursor did not advance")
                seen.add(after)
            else:
                raise ProviderProblem("DERIVATION_UNIT_TOO_LARGE", "Cohort reader exceeded the fixed3000 membership")
            material_batches = ()
        else:
            material_batches = range(32)
        for batch in material_batches:
            args = {"claim": owned, "limit": 4}
            if after is not None:
                args["after"] = after
            material = self.call("backfill_material", args)
            if not material.get("ready", True):
                raise ProviderProblem("DEPENDENCY_WAIT", "Required source tasks are still acquiring", retryable=True, retry_after=120)
            for page in material.get("pages", []):
                raw = page["raw_body"]
                if sha256(raw.encode()).hexdigest() != page["body_sha256"]:
                    raise ProviderProblem("SOURCE_READBACK_MISMATCH", "Stored source receipt digest does not match")
                source_task = page["task"]
                if source_task["kind"] == "retained_reuse":
                    values = json.loads(raw)["rows"]
                    source_rows, invalid = self.retained_material(claim, source_task)
                    retained_rows.extend(source_rows)
                    lineage.append({"task_id": source_task["id"], "page_no": page["page_no"],
                                    "body_sha256": page["body_sha256"], "receipt_records": len(values),
                                    "material_records": len(source_rows), "unusable_inputs_excluded": invalid,
                                    "source_digest": values[0].get("source_digest") if values else None})
                    if len(values) != page["record_count"]:
                        raise ProviderProblem("SOURCE_READBACK_MISMATCH", "Retained pointer count differs from receipt")
                    continue
                elif source_task["kind"] in DERIVED_KINDS:
                    values = json.loads(raw)["rows"]
                else:
                    values, source_next_cursor, _ = parse_response(source_task, page["request"], raw)
                    # A successfully exhausted repair query replaces the old
                    # session input, including when it legitimately returned no
                    # rows. Keep the original archive and its provenance intact.
                    if source_task.get("scope", {}).get("reuse_parent") and source_next_cursor is None:
                        replacement_days.update(e["date"] for e in source_task["scope"].get("calendar", []))
                if len(values) != page["record_count"]:
                    raise ProviderProblem("SOURCE_READBACK_MISMATCH", "Reparsed source count does not match receipt")
                lineage.append({"task_id": source_task["id"], "page_no": page["page_no"],
                                "body_sha256": page["body_sha256"], "records": len(values)})
                for row in values:
                    if self.identity_enabled and source_task["kind"] == "alpaca_stock_bars":
                        # Bind symbol-mapping semantics to this actual stored
                        # source receipt. Do not change original parsed source
                        # rows, infer a default asof, or qualify identity here.
                        request = page["request"]
                        requested = str(request.get("params", {}).get("symbols", "")).split(",")
                        row = dict(row)
                        row["provider_symbol_mapping"] = {
                            "provider": request.get("provider"), "host": request.get("host"),
                            "path": request.get("path"), "method": request.get("method"),
                            "asof": request.get("params", {}).get("asof"),
                            "requested_symbol": row.get("symbol") if row.get("symbol") in requested else None,
                            "source_body_sha256": page["body_sha256"],
                            "request_sha256": sha256(canonical(request).encode()).hexdigest(),
                        }
                    if scope.get("symbols") and row.get("symbol") not in scope["symbols"]:
                        continue
                    day = row.get("market_date")
                    if day and (day < scope.get("input_start", "1900-01-01") or day > scope.get("target_end", "2026-07-31")):
                        continue
                    rows.append(row)
            after = material.get("next_after")
            if material.get("complete", not after):
                break
            if after is None:
                raise ProviderProblem("INCOMPLETE_MATERIAL_CURSOR", "Source-material pagination did not advance")
        else:
            if claim["kind"] != "derive_breadth":
                raise ProviderProblem("DERIVATION_UNIT_TOO_LARGE", "Calculation unit needs bounded repartitioning")
        rows.extend(row for row in retained_rows if row.get("market_date") not in replacement_days)
        identity = None
        representative_security = scope.get("representative_security")
        if self.identity_enabled and claim["kind"] in DERIVED_KINDS:
            from .backfill_identity_v2 import IdentityMaterialError, apply_identity_material
            material = self.call("backfill_identity_material", {"claim": owned})
            try:
                identity = apply_identity_material(rows, material, claim)
            except IdentityMaterialError:
                raise ProviderProblem("IDENTITY_MATERIAL_INVALID",
                                      "Current identity material requires scope/hash reconciliation") from None
            rows = identity["rows"]
            representative_security = identity["representative_security"]
        result = derive_family(claim["family"], rows,
                               sessions=scope.get("calendar", []),
                               target_start=scope.get("target_start", "2025-09-01"),
                               target_end=scope.get("target_end", "2026-07-31"),
                               member_id=scope.get("member_ids", [None])[0],
                               representative_security=representative_security)
        output_rows = result["rows"]
        if identity is not None:
            result["limitations"] = result.get("limitations", []) + identity.get("limitations", [])
            if claim["kind"] in ("derive_daily", "derive_intraday"):
                from .backfill_identity_v2 import attach_identity_output
                output_rows = attach_identity_output(output_rows, identity)
        if not output_rows and not result.get("limitations"):
            result["limitations"] = [{"state": "IDENTITY_OR_QUALITY_UNRESOLVED",
                                       "reason": "NO_CALCULABLE_OUTPUT_FROM_RETAINED_INPUTS",
                                       "input_count": len(rows), "family": claim["family"]}]
        # The calculation receipt distinguishes derived output from external
        # source observations, and includes input lineage rather than invented
        # provider response metadata.
        raw = canonical({"formula_version": result["formula_version"], "family": claim["family"],
                         "input_lineage": lineage,
                         "input_sha256": sha256(canonical(rows).encode()).hexdigest(),
                         "rows": output_rows, "limitations": result.get("limitations", []),
                         **({"identity_material_sha256": identity["identity_material_sha256"],
                             "identity_lineage": identity["identity_lineage"]} if identity is not None else {})})
        payload = {"claim": owned, "raw_body": raw, "body_sha256": sha256(raw.encode()).hexdigest(),
                   "http_status": 200, "request_id": None, "fetched_at": utc_now(),
                   "request": {"provider": "DERIVED", "formula_version": result["formula_version"],
                               "input_lineage": lineage},
                   "records": output_rows, "next_cursor": None,
                   "terminal_state": "INGESTED" if output_rows else "IDENTITY_OR_QUALITY_UNRESOLVED",
                   "quality": result.get("limitations", []), "headers": {},
                   "adapter_version": result["formula_version"]}
        committed = self.call("backfill_commit", payload)
        if self.after_commit is not None:
            self.after_commit(claim)
        self.verify_committed(claim, payload["body_sha256"], len(output_rows))
        return {"state": "backfill_calculation_committed", "run_id": claim["run_id"],
                "task_id": claim["id"], "family": claim["family"], **(committed or {})}


def from_settings(store, settings):
    provider = BackfillProvider(settings.api_key, settings.secret_key,
                                os.environ.get("MASSIVE_API_KEY", os.environ.get("POLYGON_API_KEY", "")),
                                paper=os.environ.get("APCA_API_BASE_URL", "https://paper-api.alpaca.markets") != "https://api.alpaca.markets")
    if settings.api_url:
        from .backfill_massive_relay_v2 import MassiveRelay, ProviderWithManagedMassive
        provider = ProviderWithManagedMassive(provider, MassiveRelay(
            settings.api_url, settings.publishable_key, settings.rpc_token))
    return BackfillWorker(store, provider, lease_seconds=settings.lease_seconds,
                          source_revision=os.environ.get("RENDER_GIT_COMMIT", "local-unversioned"),
                          planning_enabled=True, plan_member_limit=5,
                          identity_enabled=True, retained_massive_enabled=True)
