"""Read-only, bounded public projection of the authenticated replacement report.

Provider configuration, raw evidence, task scopes and arbitrary run metadata
stay on the server. Missing fields remain missing rather than becoming zero.
"""

RUN_FIELDS = "id status cohort_policy cohort_sha256 cohort_manifest_sha256 instruction_sha256 target_start target_end members created_at last_progress_at next_retry_at requests_reserved pages_committed records_committed source_bytes".split()
PLANNER_FIELDS = "planning_complete planner_phase planner_next_selection_order planner_next_breadth_index planner_expected_static_count expected_static_task_count planner_last_progress_at applicable_data_coverage_established coverage_disposition_reason".split()
DEPENDENCY_FIELDS = "provider dependency state code observed_at resolved_at".split()
TASK_FIELDS = "family kind provider status tasks records last_progress_at".split()
DELIVERY_FIELDS = "run_id run_status cohort_policy cohort_sha256 target_start target_end planning_complete last_progress_at required_readbacks_remaining".split()
FAMILY_FIELDS = "family title completion_basis shared_source_family planned_units terminal_units ingested_units no_data_units not_applicable_units provider_limited_units unresolved_units operational_error_units blocked_units retry_wait_units running_units pending_units archived_pages verified_pages committed_records dated_target_records support_records unknown_date_records unclassified_session_records referenced_existing_records referenced_qualifying_records referenced_usable_records usable_minute_records next_retry_at work_completion coverage_basis counts_are_additive_across_families".split()


def _fields(value, names):
    if not isinstance(value, dict):
        raise ValueError("Invalid replacement status object")
    return {name: value[name] for name in names if name in value and
            (value[name] is None or type(value[name]) in (str, int, float, bool))}


def _rows(value, fields, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("Invalid replacement status rows")
    return [_fields(row, fields) for row in value]


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
                row["families"] = _rows(report["families"], FAMILY_FIELDS, 16)
            if "physical_totals" in report:
                row["physical_totals"] = _fields(report["physical_totals"],
                    ("requests_reserved", "physical_pages", "physical_source_and_derived_records", "source_bytes"))
            if "provider_dependencies" in report:
                row["provider_dependencies"] = _rows(report["provider_dependencies"], DEPENDENCY_FIELDS, 2)
            delivery["runs"].append(row)
        result["delivery"] = delivery
    return result
