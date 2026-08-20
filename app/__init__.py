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
from . import oversold_tracking as _oversold_tracking
from .oversold_scoring_v32_compat import patch_module as _patch_v32
from .oversold_scoring_v33 import patch_module as _patch_v33
from .oversold_scoring_v33_compat import patch_module as _patch_v33_compat
from .oversold_scoring_v33_runtime import patch_module as _patch_v33_runtime
from .oversold_three_session_target import patch_scoring as _patch_three_session_target
from .oversold_tracking_day3 import patch_module as _patch_tracking_day3

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
_patch_tracking_day3(_oversold_tracking)

# Production runtime modules read required settings at import time.  Keep them out
# of pure pytest collection, matching the existing application's isolation model.
if "pytest" not in sys.modules:
    from . import oversold as _oversold_scan
    from .oversold_scan_v33 import patch_module as _patch_scan_v33
    from .oversold_scan_v33_compat import patch_module as _patch_scan_v33_compat

    _patch_scan_v33_compat(_oversold_scan)
    _patch_scan_v33(_oversold_scan)

    # Add explicit three-session path metrics before the target runtime wraps the
    # outcome collector and publishes the public router bindings.
    from . import oversold_outcomes as _oversold_outcomes
    from .oversold_outcomes_v33 import install_patch as _patch_outcomes_v33
    from .oversold_three_session_target import install_runtime_patches as _install_three_session_runtime

    _patch_outcomes_v33(_oversold_outcomes)
    _install_three_session_runtime()

    from .oversold_v2_fundamental_patch import install_patch as _install_oversold_v2_fundamental_patch

    _install_oversold_v2_fundamental_patch()
