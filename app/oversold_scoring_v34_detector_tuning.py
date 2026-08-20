from __future__ import annotations

"""Apply source-authority weighting at the contradiction detector boundary."""

from typing import Any

from app.oversold_scoring_v34_tuning import _reweighted_contradiction_severity


def patch_module(module: Any) -> None:
    if getattr(module, "_v34_detector_tuning_installed", False):
        return
    original = module.detect_claim_contradictions

    def detect_claim_contradictions(articles):
        result = original(articles)
        result = dict(result)
        result["severity_before_primary_weighting"] = result.get("severity")
        result["severity"] = _reweighted_contradiction_severity(result)
        return result

    module.detect_claim_contradictions = detect_claim_contradictions
    module._v34_detector_tuning_installed = True
