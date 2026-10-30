"""Read-only, bounded public projection of the authenticated replacement report.

Provider configuration, raw evidence, task scopes and arbitrary run metadata
stay on the server. Missing fields remain missing rather than becoming zero.
"""
import re

RUN_FIELDS = "id status cohort_policy cohort_sha256 cohort_manifest_sha256 instruction_sha256 target_start target_end members created_at last_progress_at next_retry_at requests_reserved pages_committed records_committed source_bytes identity_discovery_pending_count identity_refresh_pending_count identity_refresh_next_retry_at identity_recalculation_pending_tasks identity_sources_verified identity_sources_invalidated identity_source_last_verified_at".split()
PLANNER_FIELDS = "planning_complete planner_phase planner_next_selection_order planner_next_breadth_index planner_expected_static_count expected_static_task_count planner_last_progress_at applicable_data_coverage_established coverage_disposition_reason".split()
DEPENDENCY_FIELDS = "provider dependency state code observed_at resolved_at".split()
TASK_FIELDS = "family kind provider status tasks records last_progress_at".split()
DELIVERY_FIELDS = "run_id run_status cohort_policy cohort_sha256 target_start target_end planning_complete last_progress_at required_readbacks_remaining".split()
FAMILY_FIELDS = "family title completion_basis shared_source_family planned_units terminal_units ingested_units no_data_units not_applicable_units provider_limited_units unresolved_units operational_error_units blocked_units retry_wait_units running_units pending_units archived_pages verified_pages committed_records dated_target_records support_records unknown_date_records unclassified_session_records referenced_existing_records referenced_qualifying_records referenced_usable_records usable_minute_records next_retry_at work_completion coverage_basis counts_are_additive_across_families".split()
COVERAGE_FIELDS = "version projected_verified_pages projection_pending_verified_pages physical_receipt_records source_observation_records raw_daily_source_records split_daily_source_records physical_pointer_records all_derived_version_records selected_derived_records superseded_or_incomplete_revision_records identity_invalidated_output_records logical_output_records target_records support_records after_target_records unknown_date_records expected_applicable_records coverage_fraction denominator_state source_count_basis variant_count_basis derived_count_basis counts_additive_across_roles field_validation_basis referenced_source_observations verified_source_occurrences conflicting_source_records historically_attributed_records historical_attribution full_replacement_query_satisfied".split()
VARIANT_FIELDS = "observation_role source_variant projected_pages physical_records selected_records target_records support_records after_target_records unknown_date_records target_first_date target_last_date support_first_date support_last_date after_target_first_date after_target_last_date pages_with_quality_findings pages_of_incomplete_queries".split()
FIELD_COVERAGE_FIELDS = "observation_role source_variant record_type period field datatype field_role observed_field_slots nonnull_values usable_values missing_values unusable_present_values expected_applicable_field_slots coverage_fraction usability_basis".split()
SHARED_RECORD_FIELDS = "unique_provider_record_keys unique_articles unique_contract_references unique_contract_session_bars non_session_option_bar_records primary_records target_records support_records after_target_records unknown_date_records verified_source_occurrences source_versions conflicting_records fallback_content_keys article_security_links cohort_candidate_article_links historically_attributed_article_links boundary_crossing_events boundary_support_events projection_pending_verified_pages cross_provider_matching expected_applicable_records coverage_fraction counts_additive_across_record_types all_original_versions_retained".split()
SHARED_ACTION_FIELDS = "planned_units open_units operational_error_units blocked_units documented_gap_units".split()
CONTRACT_WORK_FIELDS = "registered_contract_windows registered_child_contract_links parent_contract_links new_children_created enumeration_pages_processed unlinked_source_contracts pending_enumeration_pages unverified_pending_enumeration_pages unreconciled_verified_enumeration_pages existing_overlap_contract_links registry_seed_complete preexisting_children_preserved existing_overlaps_remain_executable historical_enumeration_completeness_certified parent_link_count_basis expected_contract_population coverage_fraction".split()


def _fields(value, names):
    if not isinstance(value, dict):
        raise ValueError("Invalid replacement status object")
    return {name: value[name] for name in names if name in value and
            (value[name] is None or type(value[name]) in (str, int, float, bool))}


def _rows(value, fields, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("Invalid replacement status rows")
    return [_fields(row, fields) for row in value]


def _field_coverage_rows(items):
    result = _rows(items, FIELD_COVERAGE_FIELDS, 512)
    for source, target in zip(items, result):
        if "null_or_unusable_reasons" not in source:
            continue
        reasons = source["null_or_unusable_reasons"]
        if not isinstance(reasons, dict) or len(reasons) > 64:
            raise ValueError("Invalid bounded field-coverage reasons")
        target["null_or_unusable_reasons"] = {
            key: count for key, count in reasons.items()
            if isinstance(key, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,119}", key)
            and type(count) is int and count >= 0
        }
    return result


def _coverage(value):
    """Expose counts and controlled reason codes, never raw source/evidence."""
    result = _fields(value, COVERAGE_FIELDS)
    if "variants" in value:
        result["variants"] = _rows(value["variants"], VARIANT_FIELDS, 32)
    for key in ("fields", "source_occurrence_fields"):
        if key in value:
            result[key] = None if value[key] is None else _field_coverage_rows(value[key])
    if "shared_records" in value:
        shared = value["shared_records"]
        result["shared_records"] = None if shared is None else _fields(shared, SHARED_RECORD_FIELDS)
        if shared is not None:
            target = result["shared_records"]
            if "date_axes" in shared:
                target["date_axes"] = _rows(shared["date_axes"],
                                            ("record_type", "date_axis", "period", "records"), 256)
            if "shared_action_workflows" in shared:
                actions = shared["shared_action_workflows"]
                target["shared_action_workflows"] = (None if actions is None
                                                       else _fields(actions, SHARED_ACTION_FIELDS))
            if "contract_work" in shared:
                work = shared["contract_work"]
                target["contract_work"] = None if work is None else _fields(work, CONTRACT_WORK_FIELDS)
    return result


def _families(values):
    result = _rows(values, FAMILY_FIELDS, 16)
    for source, target in zip(values, result):
        if "nonminute_coverage" in source:
            target["nonminute_coverage"] = (None if source["nonminute_coverage"] is None
                                             else _coverage(source["nonminute_coverage"]))
    return result


def public_backfill_status(snapshot):
    """Keep the established status shape while explicitly selecting safe fields."""
    result = _fields(snapshot, ("observed_at",))
    runs = snapshot.get("runs")
    if not isinstance(runs, list) or len(runs) > 20:
        raise ValueError("Invalid replacement run list")
    result["runs"] = []
    for source in runs:
        run = _fields(source, RUN_FIELDS)
        run["metadata"] = _fields(source.get("metadata", {}), PLANNER_FIELDS)
        if "provider_dependencies" in source:
            run["provider_dependencies"] = _rows(source["provider_dependencies"], DEPENDENCY_FIELDS, 2)
        if "tasks" in source:
            run["tasks"] = _rows(source["tasks"], TASK_FIELDS, 4096)
        if "unsupported_pending_kinds" in source:
            kinds = source["unsupported_pending_kinds"]
            if not isinstance(kinds, list) or len(kinds) > 32 or any(not isinstance(kind, str) for kind in kinds):
                raise ValueError("Invalid replacement capability list")
            run["unsupported_pending_kinds"] = kinds
        result["runs"].append(run)
    if "delivery" in snapshot:
        source = snapshot["delivery"]
        delivery = _fields(source, ("observed_at",))
        reports = source.get("runs")
        if not isinstance(reports, list) or len(reports) > 20:
            raise ValueError("Invalid replacement delivery list")
        delivery["runs"] = []
        for report in reports:
            row = _fields(report, DELIVERY_FIELDS)
            if "families" in report and report["families"] is not None:
                row["families"] = _families(report["families"])
            if "physical_totals" in report:
                row["physical_totals"] = _fields(report["physical_totals"],
                    ("requests_reserved", "physical_pages", "physical_source_and_derived_records", "source_bytes"))
            if "provider_dependencies" in report:
                row["provider_dependencies"] = _rows(report["provider_dependencies"], DEPENDENCY_FIELDS, 2)
            delivery["runs"].append(row)
        result["delivery"] = delivery
    return result
