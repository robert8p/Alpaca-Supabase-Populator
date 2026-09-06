"""Application package bootstrap.

Oversold Reversion keeps every prior model reproducible. New imports resolve
through the v3.2 economic-risk layer, the three-session target, v3.3 opportunity
quality, v3.4 deterministic downside scenarios, the v3.5 robust ensemble, v3.6
subject-aware classification and v3.7 local-clause causal attribution. Original
Evidence Snapshots and prior model runs remain immutable.
"""

from __future__ import annotations

import sys

from . import oversold_primary_evidence as _oversold_primary_evidence
from . import oversold_regulatory_evidence_v2 as _oversold_regulatory_v2
from . import oversold_scoring_v32 as _oversold_scoring
from . import oversold_scoring_v33 as _oversold_v33_impl
from . import oversold_scoring_v34 as _oversold_v34_impl
from . import oversold_sec_fundamentals as _oversold_sec
from . import oversold_three_session_target as _oversold_target
from . import oversold_tracking as _oversold_tracking
from .oversold_clinicaltrials_search_compat import patch_module as _patch_clinicaltrials_search
from .oversold_primary_evidence_compat import patch_module as _patch_primary_evidence_compat
from .oversold_primary_evidence_scoring import patch_module as _patch_primary_evidence_scoring
from .oversold_regulatory_evidence_v2 import patch_module as _patch_regulatory_evidence_v2
from .oversold_scoring_v32_compat import patch_module as _patch_v32
from .oversold_scoring_v33 import patch_module as _patch_v33
from .oversold_scoring_v33_compat import patch_module as _patch_v33_compat
from .oversold_scoring_v33_contract import patch_module as _patch_v33_contract
from .oversold_scoring_v33_runtime import patch_module as _patch_v33_runtime
from .oversold_scoring_v34 import patch_module as _patch_v34
from .oversold_scoring_v34_detector_tuning import patch_module as _patch_v34_detector
from .oversold_scoring_v34_tuning import patch_module as _patch_v34_tuning
from .oversold_scoring_v35 import patch_module as _patch_v35
from .oversold_scoring_v35_compat import patch_module as _patch_v35_compat
from .oversold_scoring_v36_subject_attribution import patch_module as _patch_v36_subject_attribution
from .oversold_scoring_v37_local_attribution import patch_module as _patch_v37_local_attribution
from .oversold_scoring_v38_evidence_integrity import patch_module as _patch_v38_evidence_integrity
from .oversold_sec_json_compat import patch_module as _patch_sec_json
from .oversold_three_session_reliability import patch_score_store as _patch_three_session_score_store
from .oversold_three_session_target import patch_scoring as _patch_three_session_target
from .oversold_three_session_target_compat import patch_module as _patch_target_marker
from .oversold_tracking_day3 import patch_module as _patch_tracking_day3
from .oversold_v2_session_filter import patch_module as _patch_v2_session_filter

_patch_primary_evidence_compat(_oversold_primary_evidence)
_patch_clinicaltrials_search(_oversold_regulatory_v2)
_patch_regulatory_evidence_v2(_oversold_primary_evidence)
_patch_sec_json(_oversold_sec)
_patch_v32(_oversold_scoring)
sys.modules[f"{__name__}.oversold_scoring"] = _oversold_scoring
_patch_three_session_target(_oversold_scoring)
_patch_v33(_oversold_scoring)
_patch_v33_compat(_oversold_scoring)

# Export the exact v3.3 economic helpers required by later scenario calculations.
# The original implementations remain versioned modules for historical replay.
for _helper_name in (
    "_num",
    "_clamp",
    "_geometric",
    "_three_session_fit",
    "_fundamental_trace",
    "_survivability",
    "_overreaction_quality",
    "_tail_risk",
    "_confidence_state",
    "_price_session_context",
    "_cap_score",
):
    setattr(_oversold_scoring, _helper_name, getattr(_oversold_v33_impl, _helper_name))

_patch_v33_runtime(_oversold_scoring)
_patch_v33_contract(_oversold_scoring)
_patch_primary_evidence_scoring(_oversold_scoring)
_patch_v34_detector(_oversold_v34_impl)
_patch_v34(_oversold_scoring)
_patch_v34_tuning(_oversold_scoring)
_patch_v35(_oversold_scoring)
_patch_v35_compat(_oversold_scoring)
_patch_v36_subject_attribution(_oversold_scoring)
_patch_v37_local_attribution(_oversold_scoring)
_patch_v38_evidence_integrity(_oversold_scoring)

# Install defensive JSON normalization, primary-evidence persistence and the
# explicit three-session target before the scanner imports the store function.
from . import oversold_score_store as _oversold_score_store
from .oversold_primary_evidence_store import patch_module as _patch_primary_evidence_store
from .oversold_score_store_json_compat import patch_module as _patch_score_store_json

_patch_score_store_json(_oversold_score_store)
_patch_primary_evidence_store(_oversold_score_store)
_patch_three_session_score_store(_oversold_score_store)
_patch_tracking_day3(_oversold_tracking)

# Production runtime modules read required settings at import time. Keep them out
# of pure pytest collection, matching the existing application's isolation model.
if "pytest" not in sys.modules:
    from . import oversold as _oversold_scan
    from . import oversold_v2 as _oversold_v2
    from .oversold_primary_evidence_runtime import patch_module as _patch_primary_evidence_runtime
    from .oversold_scan_v33 import patch_module as _patch_scan_v33
    from .oversold_scan_v33_compat import patch_module as _patch_scan_v33_compat

    _patch_scan_v33_compat(_oversold_scan)
    _patch_scan_v33(_oversold_scan)
    _patch_primary_evidence_runtime(_oversold_scan)
    # V2 imports execute_scan by value before the scanner wrappers are installed.
    # Rebind so every entry point uses the broad pool and primary-evidence engine.
    _oversold_v2.execute_canonical_scan = _oversold_scan.execute_scan
    _patch_v2_session_filter(_oversold_v2)

    # Patch evaluation before the scheduler imports its function references.
    from . import oversold_evaluation as _oversold_evaluation
    from .oversold_evaluation_v34 import patch_module as _patch_evaluation_v34

    _patch_evaluation_v34(_oversold_evaluation)

    from . import oversold_calibration as _oversold_calibration
    from . import oversold_calibration_runtime as _oversold_calibration_runtime
    from . import oversold_outcome_scheduler as _oversold_outcome_scheduler
    from . import oversold_outcomes as _oversold_outcomes
    from .oversold_calibration_v35 import patch_module as _patch_calibration_v35
    from .oversold_outcomes_json_compat import patch_module as _patch_outcomes_json
    from .oversold_outcomes_v33 import install_patch as _patch_outcomes_v33
    from .oversold_primary_evidence_diagnostics import patch_module as _patch_primary_evidence_diagnostics
    from .oversold_scan_scheduler_runtime import patch_module as _patch_worker_scan_scheduler
    from .oversold_three_session_reliability import patch_outcome_scheduler as _patch_target_scheduler
    from .oversold_three_session_reliability import patch_outcomes as _patch_target_outcomes
    from .oversold_three_session_target import install_runtime_patches as _install_three_session_runtime
    from .oversold_v33_diagnostics import patch_module as _patch_v33_diagnostics
    from .oversold_v34_diagnostics import patch_module as _patch_v34_diagnostics
    from .oversold_v35_diagnostics import patch_module as _patch_v35_diagnostics

    _patch_outcomes_json(_oversold_outcomes)
    _patch_outcomes_v33(_oversold_outcomes)
    _patch_target_marker(_oversold_target)
    _install_three_session_runtime()
    _patch_target_outcomes(_oversold_outcomes)
    _patch_calibration_v35(_oversold_calibration, _oversold_calibration_runtime)

    # oversold_outcome_scheduler imports this function by value before runtime
    # patches are installed. Rebind it to the fully wrapped collector so worker
    # bootstraps and daily runs include JSON-safe long-horizon updates, explicit
    # three-session MFE/MAE paths and target maturity.
    _oversold_outcome_scheduler.capture_signal_outcomes = _oversold_outcomes.capture_signal_outcomes
    from . import oversold_public as _oversold_public
    _oversold_public.capture_signal_outcomes = _oversold_outcomes.capture_signal_outcomes

    _patch_v33_diagnostics(_oversold_target)
    _patch_primary_evidence_diagnostics(_oversold_target)
    _patch_v34_diagnostics(_oversold_target)
    _patch_v35_diagnostics(_oversold_target)
    _patch_target_scheduler(_oversold_outcome_scheduler)
    _patch_worker_scan_scheduler(_oversold_outcome_scheduler)

    from .oversold_v2_fundamental_patch import install_patch as _install_oversold_v2_fundamental_patch

    _install_oversold_v2_fundamental_patch()
