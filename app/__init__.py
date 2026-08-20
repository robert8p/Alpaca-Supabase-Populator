"""Application package bootstrap.

Oversold Reversion keeps prior scorers frozen for reproducibility.  New imports
resolve through the additive v3.2 economic-risk layer, the three-session target,
and the purpose-aligned v3.3 opportunity-quality layer.  Original Evidence
Snapshots and prior model runs remain immutable.
"""

from __future__ import annotations

import sys

from . import oversold_scoring_v32 as _oversold_scoring
from . import oversold_scoring_v33 as _oversold_v33_impl
from . import oversold_sec_fundamentals as _oversold_sec
from . import oversold_three_session_target as _oversold_target
from . import oversold_tracking as _oversold_tracking
from .oversold_primary_evidence_scoring import patch_module as _patch_primary_evidence_scoring
from .oversold_scoring_v32_compat import patch_module as _patch_v32
from .oversold_scoring_v33 import patch_module as _patch_v33
from .oversold_scoring_v33_compat import patch_module as _patch_v33_compat
from .oversold_scoring_v33_contract import patch_module as _patch_v33_contract
from .oversold_scoring_v33_runtime import patch_module as _patch_v33_runtime
from .oversold_sec_json_compat import patch_module as _patch_sec_json
from .oversold_three_session_target import patch_scoring as _patch_three_session_target
from .oversold_tracking_day3 import patch_module as _patch_tracking_day3

_patch_sec_json(_oversold_sec)
_patch_v32(_oversold_scoring)
sys.modules[f"{__name__}.oversold_scoring"] = _oversold_scoring
_patch_three_session_target(_oversold_scoring)
_patch_v33(_oversold_scoring)
_patch_v33_compat(_oversold_scoring)

# The additive v3.3 patch intentionally changes the public scorer but keeps its
# economic helper functions private to the implementation module.  Export the
# exact helpers required by the final runtime pass so the second calculation uses
# one canonical formula rather than duplicating or guessing business logic.
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

# Install one defensive normalization boundary before the scanner imports the
# persistence function. Provider timestamps remain native for database columns,
# while all nested evidence/model JSON is guaranteed serializable.
from . import oversold_score_store as _oversold_score_store
from .oversold_primary_evidence_store import patch_module as _patch_primary_evidence_store
from .oversold_score_store_json_compat import patch_module as _patch_score_store_json

_patch_score_store_json(_oversold_score_store)
_patch_primary_evidence_store(_oversold_score_store)
_patch_tracking_day3(_oversold_tracking)

# Production runtime modules read required settings at import time.  Keep them out
# of pure pytest collection, matching the existing application's isolation model.
if "pytest" not in sys.modules:
    from . import oversold as _oversold_scan
    from .oversold_primary_evidence_runtime import patch_module as _patch_primary_evidence_runtime
    from .oversold_scan_v33 import patch_module as _patch_scan_v33
    from .oversold_scan_v33_compat import patch_module as _patch_scan_v33_compat

    _patch_scan_v33_compat(_oversold_scan)
    _patch_scan_v33(_oversold_scan)
    _patch_primary_evidence_runtime(_oversold_scan)

    # Add explicit three-session path metrics before the target runtime wraps the
    # outcome collector and publishes the public router bindings.
    from . import oversold_outcomes as _oversold_outcomes
    from .oversold_outcomes_v33 import install_patch as _patch_outcomes_v33
    from .oversold_primary_evidence_diagnostics import patch_module as _patch_primary_evidence_diagnostics
    from .oversold_three_session_target import install_runtime_patches as _install_three_session_runtime
    from .oversold_v33_diagnostics import patch_module as _patch_v33_diagnostics

    _patch_outcomes_v33(_oversold_outcomes)
    _install_three_session_runtime()
    _patch_v33_diagnostics(_oversold_target)
    _patch_primary_evidence_diagnostics(_oversold_target)

    from .oversold_v2_fundamental_patch import install_patch as _install_oversold_v2_fundamental_patch

    _install_oversold_v2_fundamental_patch()
