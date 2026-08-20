"""Application package bootstrap.

Oversold Reversion keeps the frozen v3.1 scorer in ``oversold_scoring.py`` for
reproducibility. New imports resolve to the additive v3.2 compatibility layer,
which loads v3.1 privately and applies the versioned economic-risk/gating model.
The active calibration contract is then versioned independently so historical
score/evidence rows remain reproducible when the outcome horizon changes.
"""

from __future__ import annotations

import sys

from . import oversold_scoring_v32 as _oversold_scoring_v32
from . import oversold_tracking as _oversold_tracking
from .oversold_scoring_v32_compat import patch_module as _patch_v32
from .oversold_three_session_target import install_runtime_patches as _install_three_session_runtime
from .oversold_three_session_target import patch_scoring as _patch_three_session_target
from .oversold_tracking_day3 import patch_module as _patch_tracking_day3

_patch_v32(_oversold_scoring_v32)
sys.modules[f"{__name__}.oversold_scoring"] = _oversold_scoring_v32
_patch_three_session_target(_oversold_scoring_v32)
_patch_tracking_day3(_oversold_tracking)
_install_three_session_runtime()

from .oversold_v2_fundamental_patch import install_patch as _install_oversold_v2_fundamental_patch

_install_oversold_v2_fundamental_patch()
