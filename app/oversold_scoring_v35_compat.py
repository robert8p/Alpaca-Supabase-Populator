from __future__ import annotations

"""Backward-compatible gate names for clients and historical regression tests."""

from typing import Any


def patch_module(module: Any) -> None:
    if getattr(module, "_v35_compat_installed", False):
        return
    original = module.score_candidate

    def score_candidate(candidate, articles, catalyst_class, risk_flags):
        result = original(candidate, articles, catalyst_class, risk_flags)
        analysis = result.setdefault("catalyst_analysis", {})
        gates = dict(analysis.get("eligibility_gates") or {})
        aliases = {
            "causal_evidence_independence": gates.get("causal_provenance_independence", False),
            "conservative_opportunity_threshold": gates.get("robust_opportunity_threshold", False),
            "score_stability": gates.get("weight_stability", False),
            "stress_gate_pass_rate": (
                gates.get("ensemble_median", False)
                and gates.get("component_independence", False)
            ),
            "not_extreme_microcap": bool(
                (analysis.get("reliability_assessment") or {}).get("eligibility_gates", {}).get(
                    "not_extreme_microcap",
                    True,
                )
            ),
        }
        gates.update(aliases)
        analysis["eligibility_gates"] = gates
        analysis["failed_eligibility_gates"] = [name for name, passed in gates.items() if not passed]
        robustness = analysis.get("robustness_assessment")
        if isinstance(robustness, dict):
            robustness["compatibility_gate_aliases"] = aliases
        trace = result.get("calculation_trace")
        if isinstance(trace, dict) and isinstance(trace.get("final"), dict):
            trace["final"]["eligibility_gates"] = gates
            trace["final"]["failed_eligibility_gates"] = analysis["failed_eligibility_gates"]
        return result

    module.score_candidate = score_candidate
    module._v35_compat_installed = True
