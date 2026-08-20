from __future__ import annotations

"""Final v3.3 runtime recalculation after extended SEC metrics are attached.

The first v3.3 pass deliberately reuses the frozen v3.2 evidence pipeline.  Some
new SEC-derived metrics (runway, current ratio and debt/assets) are attached to
the retained fundamental trace near the end of that pass.  This wrapper performs
one deterministic recalculation so those metrics affect Survivability, Tail Risk
and the final gates rather than being display-only evidence.
"""

from typing import Any


def patch_module(module: Any) -> None:
    if getattr(module, "_v33_runtime_recalculation_installed", False):
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

        setup = module._clamp(float(result.get("setup_score") or 0.0))
        catalyst = module._clamp(float(result.get("catalyst_score") or 0.0))
        resilience = module._clamp(float(result.get("resilience_score") or 0.0))
        confirmation = module._clamp(float(result.get("confirmation_score") or 0.0))
        damage = module._clamp(float(result.get("damage_risk") or 0.0))
        confidence = module._clamp(float(result.get("evidence_confidence") or 0.0))
        cause_status = str(
            analysis.get("cause_verification_status")
            or ("VERIFIED" if analysis.get("cause_verified") else "UNVERIFIED")
        )
        reversibility = module._clamp(
            module._num(analysis.get("reversibility_score")) or catalyst
        )
        timing = module._three_session_fit(analysis, damage)
        overreaction, overreaction_reasons = module._overreaction_quality(
            setup,
            reversibility,
            damage,
            analysis,
        )
        survivability, survivability_reasons, critical_fundamentals = module._survivability(
            resilience,
            analysis,
            damage,
        )
        tail_risk, tail_reasons = module._tail_risk(
            damage,
            analysis,
            survivability,
            bool(result.get("hard_veto")),
        )

        fundamental_trace, _raw = module._fundamental_trace(analysis)
        coverage = int(fundamental_trace.get("metric_coverage_count") or 0)
        fundamentals_available = bool(
            fundamental_trace.get("available")
            and fundamental_trace.get("source")
            and coverage > 0
        )
        if not fundamentals_available:
            fundamental_trace["available"] = False
        critical_fundamentals_missing = critical_fundamentals and not fundamentals_available
        price_context = module._price_session_context(candidate)

        values = {
            "overreaction": overreaction,
            "reversibility": reversibility,
            "survivability": survivability,
            "three_session_fit": timing,
            "confirmation": confirmation,
            "technical_exhaustion": setup,
        }
        weights = module.SCORING_CONFIG["v3_3"]["weights"]
        raw_opportunity = module._geometric(values, weights)
        confidence_multiplier = 0.35 + 0.65 * (confidence / 100.0)
        confidence_adjusted = raw_opportunity * confidence_multiplier
        tail_penalty = min(24.0, max(0.0, tail_risk - 40.0) * 0.35)
        pre_cap = module._clamp(confidence_adjusted - tail_penalty)
        capped, cap, caps = module._cap_score(
            pre_cap,
            cause_status=cause_status,
            damage=damage,
            tail_risk=tail_risk,
            critical_fundamentals_missing=critical_fundamentals_missing,
            hard_veto=bool(result.get("hard_veto")),
            analysis=analysis,
            price_context=price_context,
        )
        score = round(capped, 1)

        dollar_volume = module._num(candidate.get("prev_dollar_volume"))
        spread = module._num(candidate.get("spread_pct"))
        financing = (
            analysis.get("dilution_analysis")
            if isinstance(analysis.get("dilution_analysis"), dict)
            else {}
        )
        spike = (
            analysis.get("spike_adjustment")
            if isinstance(analysis.get("spike_adjustment"), dict)
            else {}
        )
        strong_partial = cause_status == "PARTIALLY_VERIFIED" and confidence >= 75.0
        gates = {
            "opportunity_threshold": score >= 72.0,
            "cause_verified_or_strong_partial": cause_status == "VERIFIED" or strong_partial,
            "evidence_confidence": confidence >= 65.0,
            "overreaction_quality": overreaction >= 60.0,
            "survivability": survivability >= 55.0,
            "three_session_fit": timing >= 55.0,
            "damage_not_high": damage <= 60.0,
            "tail_risk_acceptable": tail_risk <= 60.0,
            "critical_fundamentals_available": not critical_fundamentals_missing,
            "no_structural_veto": not bool(result.get("hard_veto")),
            "no_capital_distress": financing.get("classification") != "capital_distress",
            "dilution_not_material": financing.get("classification") != "material_dilution",
            "dilution_not_severe": financing.get("classification") != "material_dilution",
            "post_spike_not_dominant": not (
                spike.get("post_spike_unwind")
                and float(spike.get("penalty") or 0.0) >= 12.0
            ),
            "liquidity": dollar_volume is not None and dollar_volume >= 2_000_000.0,
            "spread_quality": spread is not None and spread <= 3.0,
            "regular_session_confirmation": not bool(price_context.get("extended_hours_only")),
        }
        failed = [name for name, passed in gates.items() if not passed]

        if (
            bool(result.get("hard_veto"))
            or financing.get("classification") == "capital_distress"
            or damage >= 80.0
            or tail_risk >= 90.0
            or score < 40.0
        ):
            verdict = "PASS"
        elif all(gates.values()):
            verdict = "INVESTIGATE"
        elif score >= 48.0:
            verdict = "WATCH"
        else:
            verdict = "PASS"

        confidence_state = module._confidence_state(
            cause_status,
            confidence,
            fundamentals_available,
        )
        evidence_state = (
            "VERIFIED_PRIMARY"
            if fundamentals_available and coverage >= 6
            else "PARTIAL_PRIMARY"
            if fundamentals_available
            else "UNAVAILABLE"
        )

        analysis.update(
            {
                "three_session_fit_score": round(timing, 1),
                "overreaction_quality_score": round(overreaction, 1),
                "survivability_score": round(survivability, 1),
                "tail_risk_score": round(tail_risk, 1),
                "assessment_confidence_state": confidence_state,
                "fundamental_evidence_state": evidence_state,
                "critical_fundamentals_required": critical_fundamentals,
                "eligibility_gates": gates,
                "failed_eligibility_gates": failed,
                "overreaction_reasons": overreaction_reasons,
                "survivability_reasons": survivability_reasons,
                "tail_risk_reasons": tail_reasons,
                "price_session_context": price_context,
            }
        )

        explanation = (
            f"Opportunity {score:.1f}/100; overreaction {overreaction:.0f}, "
            f"survivability {survivability:.0f}, three-session fit {timing:.0f}, "
            f"tail risk {tail_risk:.0f}, evidence {confidence:.0f}. "
            + (
                "All INVESTIGATE gates passed."
                if verdict == "INVESTIGATE"
                else f"{verdict}: failed gates include "
                f"{', '.join(failed[:5]) or 'opportunity threshold'}."
            )
        )

        trace = result.setdefault("calculation_trace", {})
        v33 = trace.setdefault("v3_3", {})
        v33.update(
            {
                "component_scores": {
                    key: round(value, 2) for key, value in values.items()
                },
                "weights": weights,
                "raw_opportunity_quality": round(raw_opportunity, 2),
                "confidence_multiplier": round(confidence_multiplier, 4),
                "confidence_adjusted_opportunity": round(confidence_adjusted, 2),
                "tail_risk_penalty": round(tail_penalty, 2),
                "pre_cap_score": round(pre_cap, 2),
                "final_cap": round(cap, 1),
                "caps_applied": caps,
                "eligibility_gates": gates,
                "failed_eligibility_gates": failed,
                "price_session_context": price_context,
                "extended_financial_metrics_applied": True,
            }
        )
        trace["final"] = {
            "final_score": score,
            "verdict": verdict,
            "eligibility_gates": gates,
            "failed_eligibility_gates": failed,
            "caps_applied": caps,
        }

        result.update(
            {
                "core_score": round(raw_opportunity, 2),
                "confidence_adjusted_score": round(confidence_adjusted, 2),
                "damage_penalty": round(tail_penalty, 2),
                "damage_cap": round(cap, 1),
                "pre_cap_score": round(pre_cap, 2),
                "final_score": score,
                "verdict": verdict,
                "explanation": explanation,
            }
        )
        return result

    module.score_candidate = score_candidate
    module._v33_runtime_recalculation_installed = True
