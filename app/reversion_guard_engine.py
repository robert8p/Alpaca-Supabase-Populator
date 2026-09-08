from __future__ import annotations

"""Public API for the separate Oversold Reversion Guard application.

The implementation is split into policy classification, execution gating and
position/portfolio review modules so each concern stays independently testable.
"""

from app.reversion_guard_execution import (
    assess_candidate,
    confirmation_assessment,
    execution_quality,
    risk_plan,
)
from app.reversion_guard_policy import (
    DEFAULT_SETTINGS,
    EVENT_LABELS,
    GUARD_VERSION,
    candidate_text,
    classify_event,
    infer_theme,
    signal_session,
)
from app.reversion_guard_positions import (
    break_even_recovery_pct,
    compact_candidate_packet,
    portfolio_summary,
    review_position,
)

__all__ = [
    "DEFAULT_SETTINGS",
    "EVENT_LABELS",
    "GUARD_VERSION",
    "assess_candidate",
    "break_even_recovery_pct",
    "candidate_text",
    "classify_event",
    "compact_candidate_packet",
    "confirmation_assessment",
    "execution_quality",
    "infer_theme",
    "portfolio_summary",
    "review_position",
    "risk_plan",
    "signal_session",
]
