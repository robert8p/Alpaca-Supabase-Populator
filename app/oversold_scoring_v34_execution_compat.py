from __future__ import annotations

"""Session-aware execution friction for the nightly Oversold scan.

The app is intentionally scanned after the US close. A quoted after-hours spread
is useful context but is not a reliable estimate of the next regular-session
round trip. Outside regular hours, ranking therefore uses a conservative liquidity
proxy derived from previous-day dollar volume and micro-cap risk, preserves the
observed quote separately, and marks the estimate for live pre-trade recheck.

This changes score semantics, so it advances the v3.4 configuration lineage rather
than silently rewriting v6 history.
"""

from typing import Any

SCORING_CONFIG_VERSION = "or_score_config_2026_08_20_v7"
RELIABILITY_VERSION = "reliability_scenarios_v2"


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _spread_proxy(dollar_volume: float, market_cap: float | None) -> float:
    if dollar_volume >= 100_000_000:
        proxy = 0.10
    elif dollar_volume >= 25_000_000:
        proxy = 0.20
    elif dollar_volume >= 5_000_000:
        proxy = 0.45
    elif dollar_volume >= 2_000_000:
        proxy = 0.75
    elif dollar_volume >= 500_000:
        proxy = 1.25
    else:
        proxy = 2.00
    if market_cap is not None and market_cap < 25_000_000:
        proxy += 0.50
    elif market_cap is not None and market_cap < 75_000_000:
        proxy += 0.25
    return proxy


def patch_module(module: Any) -> None:
    if getattr(module, "_session_aware_execution_friction_installed", False):
        return
    original = module.estimate_execution_friction
    module.SCORING_CONFIG_VERSION = SCORING_CONFIG_VERSION
    module.RELIABILITY_VERSION = RELIABILITY_VERSION

    def estimate_execution_friction(candidate: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        result = dict(original(candidate, analysis))
        context = analysis.get("price_session_context") if isinstance(analysis.get("price_session_context"), dict) else {}
        if not context and isinstance(candidate.get("price_session_context"), dict):
            context = candidate["price_session_context"]
        session = str(context.get("price_session") or "unknown").lower()
        observed_spread = max(0.0, _num(result.get("spread_pct")) or 0.0)
        dollar_volume = max(0.0, _num(result.get("previous_dollar_volume")) or 0.0)
        market_cap = _num(result.get("market_cap"))
        slippage = max(0.0, _num(result.get("one_way_slippage_proxy_pct")) or 0.0)

        if session == "regular":
            effective_spread = observed_spread
            quote_state = "regular_session_live_quote"
            recheck_required = False
            method = "regular-session quoted spread plus two volume/micro-cap slippage proxies"
        else:
            effective_spread = _spread_proxy(dollar_volume, market_cap)
            quote_state = "off_hours_liquidity_proxy"
            recheck_required = True
            method = (
                "off-hours ranking proxy: previous-day dollar-volume/micro-cap spread proxy plus "
                "two slippage proxies; observed off-hours quote retained separately and must be rechecked"
            )

        round_trip = effective_spread + 2.0 * slippage
        result.update(
            {
                "observed_quoted_spread_pct": round(observed_spread, 3),
                "effective_spread_pct": round(effective_spread, 3),
                "estimated_round_trip_friction_pct": round(round_trip, 3),
                "price_session": session,
                "quote_state": quote_state,
                "live_execution_recheck_required": recheck_required,
                "method": method,
            }
        )
        return result

    module.estimate_execution_friction = estimate_execution_friction
    module._session_aware_execution_friction_installed = True
