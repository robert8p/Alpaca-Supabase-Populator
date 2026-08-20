"""Stable public contract for the robust Intraday Profitability v2 scorer."""
from __future__ import annotations

from . import intraday_profitability_scoring_v2 as _impl

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

TARGET_DEFINITION = (
    "Positive net directional return over the next 120 regular-session minutes "
    "after all signal inputs are complete."
)
