"""Local-only source/trigger closure against the retained fresh live catalog.

The operation-dependent wrapper edges below are deliberately explicit. Every
other reachable helper body is included conservatively, including its triggers.
This does not infer effective PostgREST server configuration from a SQL session.
"""
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ROOT_CAPTURE = ROOT / "review/recovery-v74/retry_closure_root_definitions_v74.json"
CATALOG_CAPTURE = ROOT / "review/recovery-v74/retry_closure_callees_and_catalog_v74.json"
QUALIFICATION = HERE / "qualification_final.json"
RETAINED = HERE / "retained_exact_function_sources.json"
FEATURE_SOURCES = ROOT / "evidence/retained-feature-reuse-functions.json"
FEATURE_SCHEMA = "astra_shared_equity_features_20260928_v1"
FEATURE_HASH_SIGNATURE = FEATURE_SCHEMA + ".compact_output_hash_remediated_v1(bytea,bytea,smallint[],smallint[],timestamp with time zone[],double precision[],integer,integer,integer,integer)"
FEATURE_HASH_PIN = "3d2af9589f2171964f77ecb2a5739e7417d12775833c0b3c884a61438689dae5"
TABLE_CAPTURE = ROOT / "review/recovery-v74/retry_table_boundary_catalog_v74.json"
READ_CAPTURE = ROOT / "review/recovery-v74/retry_read_relation_boundary_v74.json"
GATEWAY_CAPTURE = ROOT / "review/recovery-v74/retry_gateway_setting_catalog_v74.json"
VIEW_CAPTURE = ROOT / "review/recovery-v74/retry_view_and_rls_boundary_v74.json"
WRITE_POLICY_CAPTURE = ROOT / "review/recovery-v74/retry_write_policy_boundary_v74.json"
INDEX_CAPTURE = ROOT / "review/recovery-v74/retry_write_index_boundary_v74.json"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    roots = json.loads(ROOT_CAPTURE.read_text())[0]
    live = json.loads(CATALOG_CAPTURE.read_text())[0]
    table_boundary = json.loads(TABLE_CAPTURE.read_text())
    read_boundary = json.loads(READ_CAPTURE.read_text())
    view_boundary = json.loads(VIEW_CAPTURE.read_text())
    write_policies = json.loads(WRITE_POLICY_CAPTURE.read_text())
    indexes = json.loads(INDEX_CAPTURE.read_text())
    qualification = json.loads(QUALIFICATION.read_text())
    catalog = {row["signature"]: row for row in live["all_function_catalog"]}
    for row in roots["functions"]:
        catalog.setdefault(row["signature"], {key: row[key] for key in ("oid", "signature", "source_sha256")})
    external = table_boundary["external_function"]
    assert external["signature"] == FEATURE_HASH_SIGNATURE and external["source_sha256"] == FEATURE_HASH_PIN
    assert sha256(external["definition"].encode()).hexdigest() == FEATURE_HASH_PIN
    catalog[FEATURE_HASH_SIGNATURE] = {key: value for key, value in external.items() if key != "definition"}
    catalog[FEATURE_HASH_SIGNATURE].update({"fresh_metadata_status": "CONFIRMED_IN_TABLE_BOUNDARY_CAPTURE",
        "runtime_source_guard": "exact hash checked by feature reuse summary before call"})
    names = {signature.split("(")[0]: signature for signature in catalog}
    assert len(names) == len(catalog), "Overloads require explicit resolution"
    sources = {}
    for signature, row in json.loads(RETAINED.read_text())["sources"].items():
        if signature in catalog and row["sha256"] == catalog[signature]["source_sha256"]:
            sources[signature] = {**row, "provenance": "retained full source matched to fresh live hash"}
    for row in qualification["postgresql_evidence"]["normalized_function_catalog"]:
        signature = names.get(row["name"])
        if signature and row["sha256"] == catalog[signature]["source_sha256"]:
            sources[signature] = {
                "definition": row["definition"], "sha256": row["sha256"],
                "source_path": str(QUALIFICATION.relative_to(ROOT)),
                "provenance": "actual disposable pg_get_functiondef; explicit fixture substitutions reversed; exact fresh live hash match",
            }
    # This established fixture deliberately merges the old feature schema into
    # its disposable schema and substitutes three formula pins. Reverse those
    # exact, documented substitutions separately; do not repin production.
    feature_summary = next(row["definition"] for row in qualification["postgresql_evidence"]["normalized_function_catalog"]
                           if row["name"] == "astra_ingestion_v1.backfill_feature_reuse_summary_v2")
    for name in ("feature_session_cache_remediated_v1", "shared_identity_contract_remediated_v1",
                 "compute_feature_sessions_remediated_v1", "feature_grid_remediated_v1", "compact_output_hash_remediated_v1"):
        feature_summary = feature_summary.replace("astra_ingestion_v1." + name, FEATURE_SCHEMA + "." + name)
    for variable, original in (
        ("v_builder_hash", "019b86197174c682febb88a546a0ff956c058347e99b6dc0dbdd430e090fb552"),
        ("v_grid_hash", "5f45e08dce40aa5cc138fa9b5819b25d049bacea574d50ceb2f943d8ff02b251"),
        ("v_hash_function_hash", FEATURE_HASH_PIN)):
        feature_summary, count = re.subn(variable + r"<>'[0-9a-f]{64}'", variable + "<>'" + original + "'", feature_summary)
        assert count == 1
    summary_signature = "astra_ingestion_v1.backfill_feature_reuse_summary_v2(text)"
    assert sha256(feature_summary.encode()).hexdigest() == catalog[summary_signature]["source_sha256"]
    sources[summary_signature] = {"definition": feature_summary, "sha256": catalog[summary_signature]["source_sha256"],
        "source_path": str(QUALIFICATION.relative_to(ROOT)),
        "provenance": "exact inverse of established feature fixture namespace/formula-pin substitutions; fresh live hash match"}
    feature_hash = next(row["definition"] for row in json.loads(FEATURE_SOURCES.read_text())
                        if row["proname"] == "compact_output_hash_remediated_v1")
    assert sha256(feature_hash.encode()).hexdigest() == FEATURE_HASH_PIN
    sources[FEATURE_HASH_SIGNATURE] = {"definition": feature_hash, "sha256": FEATURE_HASH_PIN,
        "source_path": str(FEATURE_SOURCES.relative_to(ROOT)),
        "provenance": "retained exact immutable SQL hash function; live wrapper checks this exact source hash before execution"}
    for signature, row in sources.items():
        assert sha256(row["definition"].encode()).hexdigest() == catalog[signature]["source_sha256"]
    root_signatures = [row["signature"] for row in roots["functions"]]
    public = "public.astra_ingestion_rpc_v1(text,jsonb)"
    outer = "astra_ingestion_v1.rpc_dispatch(text,jsonb)"
    private = "astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)"
    delivery = "astra_ingestion_v1.backfill_delivery_dispatch_v2(text,jsonb)"
    planner = "astra_ingestion_v1.backfill_plan_next_v2(jsonb)"
    reuse = "astra_ingestion_v1.backfill_reuse_commit_v2(jsonb)"
    operation_routes = {
        "backfill_claim": [public, outer, private],
        "backfill_reserve": [public, outer, private],
        "backfill_commit": [public, outer, private],
        "backfill_reuse_commit": [public, outer, private, reuse, private],
        "backfill_verify": [public, outer, delivery, private,
                            "astra_ingestion_v1.backfill_recheck_page_v2(text,integer)",
                            "astra_ingestion_v1.backfill_try_finalize_v2(text)"],
        "backfill_plan_next": [public, outer, planner],
    }
    seen, missing, tables = set(), set(), set()
    edges, selected_triggers, external_calls, effect_markers = {}, {}, {}, {}
    pending = root_signatures[:]
    while pending:
        signature = pending.pop()
        if signature in seen:
            continue
        seen.add(signature)
        if signature not in sources:
            missing.add(signature)
            continue
        code = sources[signature]["definition"]
        explicit = None
        if signature == outer:
            # Auth and the global transaction gate precede these six branches.
            # The remaining legacy/relay/maintenance routes are not reachable
            # from an allowlisted operation, and are never retry admission.
            for operation in operation_routes:
                assert "'" + operation + "'" in code
            explicit = [private, delivery, planner]
            inspected = code[:code.index("  -- All mutating operations")]
        elif signature == private:
            claim_start = code.index(" ELSIF p_operation='backfill_claim' THEN")
            defer_start = code.index(" ELSIF p_operation='backfill_defer' THEN")
            commit_tail = code.index(" IF t.provider IN ('Alpaca','Massive') AND (t.reserved_generation")
            inspected = code[claim_start:defer_start] + code[commit_tail:]
            explicit = [reuse]
            assert "IF p_operation='backfill_reuse_commit' THEN RETURN" in code
        elif signature == delivery:
            inspected = code[code.index(" ELSIF p_operation='backfill_verify' THEN"):]
        else:
            inspected = code
        calls = re.findall(r"\b([A-Za-z_][A-Za-z_0-9]*\.[A-Za-z_][A-Za-z_0-9]*)\s*\(", inspected)
        children = set(explicit or [])
        children.update(names[name] for name in calls if name in names)
        edges[signature] = sorted(children)
        pending.extend(children)
        writes = set(re.findall(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(astra_ingestion_v1\.[A-Za-z_][A-Za-z_0-9]*)", inspected, re.I))
        tables.update(writes)
        for trigger in live["all_noninternal_triggers"]:
            if trigger["table"] in writes:
                selected_triggers[trigger["table"] + "." + trigger["name"]] = trigger
                pending.append(trigger["function_signature"])
        # Known schema-qualified calls not in the ASTRA function catalog are
        # retained for human review, including row-type/table syntax matches.
        unknown = sorted({name for name in calls if name not in names and not name.startswith("pg_catalog.")})
        if unknown:
            external_calls[signature] = unknown
        markers = []
        for line in inspected.splitlines():
            if re.search(r"\b(EXECUTE|NOTIFY|COPY|nextval|setval|pg_advisory_lock|pg_try_advisory_lock|dblink|http_post|http_get)\b|\bnet\.|response\.(status|headers)", line, re.I):
                markers.append(line.strip())
        if markers:
            effect_markers[signature] = markers
    matched = sorted(seen - missing)
    assert tables == {row["name"] for row in table_boundary["relations"]}
    assert all(row["relkind"] == "r" and row["persistence"] == "p" for row in table_boundary["relations"])
    assert table_boundary["rewrite_rules"] == []
    assert all(row["update_action"] == row["delete_action"] == "a" and not row["deferrable"] for row in table_boundary["foreign_keys"])
    assert view_boundary["relation_count"] == 18 and not any(row["foreign"] for row in view_boundary["relations"])
    assert view_boundary["policy_function_dependencies"] == []
    assert write_policies["scope_relation_count"] == len(tables) and write_policies["function_dependencies"] == []
    assert all(row.get("using") in (None, "true") and row.get("check") in (None, "true") for row in write_policies["policies"])
    assert indexes["scope_relation_count"] == len(tables) and indexes["function_dependencies"] == []
    assert all(row["namespace"] == "pg_catalog" and row["access_method"] in ("btree", "hash") for row in indexes["opclasses"])
    marker_classification = {}
    for name in sorted({name for group in external_calls.values() for name in group}):
        if name in tables:
            marker_classification[name] = "RELATION_TARGET_COLUMN_LIST_SYNTAX_NOT_FUNCTION_INVOCATION"
        elif name in {FEATURE_SCHEMA + ".compute_feature_sessions_remediated_v1", FEATURE_SCHEMA + ".feature_grid_remediated_v1"}:
            marker_classification[name] = "REGPROCEDURE_SOURCE_HASH_CHECK_ONLY_NOT_INVOKED"
        else:
            marker_classification[name] = "REQUIRES_REVIEW"
    source_bundle = HERE / "retry_closure_sources.json"
    source_bundle.write_text(json.dumps({"schema": "astra.confirmed-lock-abort-exact-sources/1",
        "functions": [{"signature": sig, **sources[sig]} for sig in matched]}, indent=2, sort_keys=True) + "\n")
    output = {
        "schema": "astra.confirmed-lock-abort-source-closure/1",
        "status": "SCOPED_DATABASE_EFFECT_CLOSURE_COMPLETE_GATEWAY_BOUNDARY_DISCLOSED" if not missing else "MISSING_SOURCE_DEFINITIONS",
        "roots_observed_at": roots["observed_at"], "catalog_observed_at": live["observed_at"],
        "inputs": [{"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
                   for path in (ROOT_CAPTURE, CATALOG_CAPTURE, QUALIFICATION, RETAINED, FEATURE_SOURCES,
                                TABLE_CAPTURE, READ_CAPTURE, GATEWAY_CAPTURE, VIEW_CAPTURE, WRITE_POLICY_CAPTURE, INDEX_CAPTURE)],
        "exact_source_bundle": {"path": str(source_bundle.relative_to(ROOT)), "sha256": digest(source_bundle)},
        "operation_routes": operation_routes,
        "source_count": len(matched), "functions": [{**catalog[sig],
            "source_path": sources[sig]["source_path"], "provenance": sources[sig]["provenance"]} for sig in matched],
        "missing_definitions": [catalog[sig] for sig in sorted(missing)],
        "write_tables": sorted(tables), "triggers": sorted(selected_triggers.values(), key=lambda row: (row["table"], row["name"])),
        "edges": edges, "qualified_calls_requiring_manual_classification": external_calls,
        "manual_marker_classification": marker_classification,
        "unresolved_qualified_markers": [name for name, state in marker_classification.items() if state == "REQUIRES_REVIEW"],
        "effect_markers_requiring_manual_classification": effect_markers,
        "write_relation_boundary": {
            "observed_at": table_boundary["observed_at"], "ordinary_persistent_tables": len(table_boundary["relations"]),
            "defaults": len(table_boundary["defaults"]), "checks": len(table_boundary["checks"]),
            "nondeferrable_no_action_foreign_keys": len(table_boundary["foreign_keys"]), "rewrite_rules": 0,
            "manual_default_review": "literals, CURRENT_USER, clock_timestamp, and identity generation only",
            "manual_check_review": "built-ins and already closed backfill_page_limit_cap_v2 only",
            "rollback_exception": "identity/sequence allocation is not reclaimed",
            "rls_policies": len(write_policies["policies"]), "rls_function_dependencies": 0,
            "rls_expression_review": "64 policies; USING/WITH CHECK are only literal true or absent",
            "indexes": indexes["index_count"], "expression_or_partial_indexes": len(indexes["expression_or_partial_indexes"]),
            "index_function_dependencies": 0, "index_operator_classes": indexes["opclasses"],
            "index_expression_review": "built-in JSON/text operators, lower/coalesce, literals and boolean comparisons only",
        },
        "external_read_relation_boundary": {
            "top_level_relations": len(read_boundary), "foreign_tables": sum(row["foreign_table"] for row in read_boundary),
            "view_count": sum(row["relkind"] == "v" for row in read_boundary),
            "recursive_relations": view_boundary["relation_count"],
            "recursive_views": sum(row["kind"] == "v" for row in view_boundary["relations"]),
            "scoped_rls_policies": len(view_boundary["policies"]), "policy_function_dependencies": 0,
            "ordinary_bar_partition_children": sum(len(row["children"]) for row in read_boundary),
            "status": "REVIEWED_BUILTIN_HASHES_CASTS_PROJECTIONS_JOINS_AND_LITERAL_PROVIDER_ARRAY_POLICIES_ONLY_NO_FDW",
        },
        "limitations": [
            "Function and noninternal-trigger source closure is not effective gateway configuration proof.",
            "No actual PostgREST server or production-positive retry classification was exercised.",
            "Native SQL errors rolled back application rows in actual local transactions; sequence consumption and logs can survive rollback.",
            "Database effect review is bounded to the73 callable functions,44 write relations,31 triggers and18 retained-read/view relation closure plus12 ordinary bar partitions.",
            "Source pins are observed baseline pins; a selected shared-refresh b18-to-7f538 change requires final current-source reconciliation before deployment.",
        ],
        "deployment_hold": "INDEPENDENT_REVIEW_EFFECTIVE_GATEWAY_BOUNDARY_AND_EXACT_PUBLISHED_HEAD_CI_REQUIRED",
    }
    destination = HERE / "retry_source_closure.json"
    destination.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"], "functions": len(matched), "missing": len(missing),
                      "write_tables": len(tables), "triggers": len(selected_triggers),
                      "external_call_groups": len(external_calls), "effect_marker_groups": len(effect_markers),
                      "sha256": digest(destination)}, indent=2))


if __name__ == "__main__":
    main()
