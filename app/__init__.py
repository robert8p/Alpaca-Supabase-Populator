"""Application package bootstrap.

Oversold Reversion keeps the frozen v3.1 scorer in ``oversold_scoring.py`` for
reproducibility.  New imports resolve to the additive v3.2 compatibility layer,
which loads v3.1 privately and applies the versioned economic-risk/gating model.
This lets historical code remain unchanged while all new scanner/model/calibration
imports share one canonical v3.2 contract.
"""

from __future__ import annotations

import sys

from . import oversold_scoring_v32 as _oversold_scoring_v32

sys.modules[f"{__name__}.oversold_scoring"] = _oversold_scoring_v32
