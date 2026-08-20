from __future__ import annotations

"""Small compatibility and missing-evidence corrections for v3.3."""

from typing import Any


def patch_module(module: Any) -> None:
    if getattr(module, "_v33_compat_installed", False):
        return
    original = module.score_candidate

    def score_candidate(
        candidate: dict[str, Any],
        articles: list[dict[str, Any]],
        catalyst_class: str,
        risk_flags: list[str],
    ) -> dict[str, Any]:
        result = original(candidate, articles, catalyst_class, risk_flags)
        analysis = result.setdefault("catalyst_analysis", {})
        gates = analysis.setdefault("eligibility_gates", {})

        # Preserve the prior gate name for historical regression consumers while
        # keeping the stricter v3.3 economic meaning.
        if "dilution_not_material" in gates:
            gates["dilution_not_severe"] = bool(gates["dilution_not_material"])

        fundamental = analysis.get("fundamental_trace") if isinstance(analysis.get("fundamental_trace"), dict) else {}
        coverage = int(fundamental.get("metric_coverage_count") or 0)
        valid_primary = bool(
            fundamental.get("available")
            and fundamental.get("source")
            and coverage > 0
        )
        critical = bool(analysis.get("critical_fundamentals_required"))
        if critical and not valid_primary:
            fundamental["available"] = False
            analysis["fundamental_evidence_state"] = "UNAVAILABLE"
            gates["critical_fundamentals_available"] = False
            failed = list(analysis.get("failed_eligibility_gates") or [])
            if "critical_fundamentals_available" not in failed:
                failed.append("critical_fundamentals_available")
            analysis["failed_eligibility_gates"] = failed

            # Missing critical financial evidence cannot support a high ranking.
            score = min(float(result.get("final_score") or 0.0), 55.0)
            result["final_score"] = round(score, 1)
            result["damage_cap"] = min(float(result.get("damage_cap") or 100.0), 55.0)
            if result.get("verdict") == "INVESTIGATE":
                result["verdict"] = "WATCH"
            if score < 40.0:
                result["verdict"] = "PASS"
            result["explanation"] = (
                f"{result.get('explanation') or ''} Critical point-in-time financial evidence is unavailable; "
                "the opportunity score is capped and INVESTIGATE is not permitted."
            ).strip()

        trace = result.setdefault("calculation_trace", {})
        v33 = trace.setdefault("v3_3", {})
        v33["eligibility_gates"] = dict(gates)
        v33["failed_eligibility_gates"] = list(analysis.get("failed_eligibility_gates") or [])
        final = trace.setdefault("final", {})
        final["final_score"] = result.get("final_score")
        final["verdict"] = result.get("verdict")
        final["eligibility_gates"] = dict(gates)
        final["failed_eligibility_gates"] = list(analysis.get("failed_eligibility_gates") or [])
        return result

    module.score_candidate = score_candidate
    module._v33_compat_installed = True
