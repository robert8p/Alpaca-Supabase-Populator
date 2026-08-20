from __future__ import annotations

"""Final conservative tuning discovered by release-gate archetype tests."""

from typing import Any


def _reweighted_contradiction_severity(contradictions: dict[str, Any]) -> float:
    severity = 0.0
    unresolved = contradictions.get("unresolved") if isinstance(contradictions.get("unresolved"), list) else []
    for conflict in unresolved:
        if not isinstance(conflict, dict):
            continue
        minimum = float(conflict.get("minimum_side_authority") or 0.0)
        positive = conflict.get("positive") if isinstance(conflict.get("positive"), list) else []
        negative = conflict.get("negative") if isinstance(conflict.get("negative"), list) else []
        primary_positive = any(bool(item.get("is_primary")) for item in positive if isinstance(item, dict))
        primary_negative = any(bool(item.get("is_primary")) for item in negative if isinstance(item, dict))
        severity += 30.0 + 10.0 * max(0.0, minimum - 1.0)
        if primary_positive or primary_negative:
            severity += 10.0
        if primary_positive and primary_negative:
            severity += 10.0
    if len(unresolved) > 1:
        severity += 10.0
    return max(0.0, min(100.0, round(severity, 1)))


def patch_module(module: Any) -> None:
    if getattr(module, "_v34_tuning_installed", False):
        return
    original = module.score_candidate

    def score_candidate(candidate, articles, catalyst_class, risk_flags):
        result = original(candidate, articles, catalyst_class, risk_flags)
        analysis = result.setdefault("catalyst_analysis", {})
        reliability = analysis.get("reliability_assessment") if isinstance(analysis.get("reliability_assessment"), dict) else {}
        contradictions = reliability.get("contradictions") if isinstance(reliability.get("contradictions"), dict) else {}
        severity = _reweighted_contradiction_severity(contradictions)
        contradictions["severity_before_primary_weighting"] = contradictions.get("severity")
        contradictions["severity"] = severity
        analysis["evidence_contradiction_severity"] = severity

        fundamental_trace = analysis.get("fundamental_trace") if isinstance(analysis.get("fundamental_trace"), dict) else {}
        fundamentals_available = bool(fundamental_trace.get("available"))
        missing_fundamental_haircut = 0.0
        if not fundamentals_available:
            old_confidence = float(result.get("evidence_confidence") or 0.0)
            new_confidence = max(0.0, old_confidence - 12.0)
            result["evidence_confidence"] = round(new_confidence, 1)
            reliability["adjusted_evidence_confidence_before_fundamental_haircut"] = old_confidence
            reliability["adjusted_evidence_confidence"] = round(new_confidence, 1)
            missing_fundamental_haircut = min(6.0, (old_confidence - new_confidence) * 0.25)
            analysis["missing_fundamentals_reliability_haircut"] = round(missing_fundamental_haircut, 2)

        score = max(0.0, float(result.get("final_score") or 0.0) - missing_fundamental_haircut)
        if severity >= 75.0:
            score = min(score, 30.0)
        elif severity >= 50.0:
            score = min(score, 50.0)
        score = round(score, 1)

        gates = dict(analysis.get("eligibility_gates") or {})
        gates["no_material_evidence_contradiction"] = severity < 50.0
        gates["conservative_opportunity_threshold"] = score >= 72.0
        failed = [name for name, passed in gates.items() if not passed]
        severe = (
            bool(result.get("hard_veto"))
            or float(analysis.get("tail_risk_score") or 0.0) >= 90.0
            or float(result.get("damage_risk") or 0.0) >= 80.0
            or severity >= 75.0
        )
        if severe or score < 40.0:
            verdict = "PASS"
        elif all(gates.values()):
            verdict = "INVESTIGATE"
        elif score >= 48.0:
            verdict = "WATCH"
        else:
            verdict = "PASS"

        reliability["contradictions"] = contradictions
        reliability["conservative_score_before_final_tuning"] = reliability.get("conservative_score")
        reliability["missing_fundamental_score_haircut"] = round(missing_fundamental_haircut, 2)
        reliability["conservative_score"] = score
        analysis["reliability_assessment"] = reliability
        analysis["eligibility_gates"] = gates
        analysis["failed_eligibility_gates"] = failed
        trace = result.setdefault("calculation_trace", {})
        trace.setdefault("v3_4_reliability", {}).update(reliability)
        trace["final"] = {
            **(trace.get("final") or {}),
            "conservative_score": score,
            "contradiction_severity": severity,
            "missing_fundamental_score_haircut": round(missing_fundamental_haircut, 2),
            "verdict": verdict,
            "eligibility_gates": gates,
            "failed_eligibility_gates": failed,
        }
        result["final_score"] = score
        result["verdict"] = verdict
        result["explanation"] = (
            f"{result.get('explanation') or ''} Final reliability tuning: contradiction severity "
            f"{severity:.0f}; missing-fundamental haircut {missing_fundamental_haircut:.1f}; "
            f"conservative score {score:.1f}; verdict {verdict}."
        ).strip()
        return result

    module.score_candidate = score_candidate
    module._v34_tuning_installed = True
