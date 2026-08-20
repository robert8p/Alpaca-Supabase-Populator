"""Reliability-first public contract for the Intraday Opportunity scanner.

The underlying feature engine remains intentionally transparent.  This adapter
adds execution gates, preserves the established scanner/database contract and,
most importantly, prevents an unvalidated structural score from being presented
as a probability or a demonstrated trading edge.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Iterable

from . import intraday_profitability_scoring_v2 as _impl

SCORING_VERSION = "ip-reliability-v3.0"
MODEL_AUDIT_VERSION = "ip-reliability-v3.0"
TARGET_DEFINITION = (
    "Research-only prioritisation of executable directional hypotheses over the "
    "next 120 regular-session minutes; no calibrated probability or validated "
    "positive net edge is claimed."
)
MIN_BARS = _impl.MIN_BARS
MAX_BAR_GAP_RATIO = _impl.MAX_BAR_GAP_RATIO
MAX_EFFECTIVE_QUOTE_AGE_SECONDS = 60.0
MAX_EFFECTIVE_TRADE_AGE_SECONDS = 90.0
ANALYSIS_PRIORITY_CAP = 74.0
parse_timestamp = _impl._parse_dt
benchmark_returns = _impl.benchmark_returns

# Frozen audit evidence.  These are not fitted return forecasts: they are the
# external-holdout results used to prevent the scanner from overstating itself.
_AUDIT_BY_SETUP: dict[tuple[str, str], dict[str, Any]] = {
    ("LONG", "CONTINUATION"): {
        "holdout_n": 6_311,
        "holdout_days": 40,
        "holdout_hit_rate": 0.4204,
        "holdout_mean_net_pct": -0.1340,
        "empirical_penalty": 16.0,
        "status": "FAILED_EXTERNAL_HOLDOUT",
    },
    ("SHORT", "CONTINUATION"): {
        "holdout_n": 6_885,
        "holdout_days": 40,
        "holdout_hit_rate": 0.4688,
        "holdout_mean_net_pct": -0.0283,
        "empirical_penalty": 11.0,
        "status": "FAILED_EXTERNAL_HOLDOUT",
    },
    ("LONG", "REVERSION"): {
        "holdout_n": 12,
        "holdout_days": 9,
        "holdout_hit_rate": 0.0,
        "holdout_mean_net_pct": -0.6204,
        "empirical_penalty": 24.0,
        "status": "INSUFFICIENT_AND_UNSTABLE",
    },
    ("SHORT", "REVERSION"): {
        "holdout_n": 18,
        "holdout_days": 15,
        "holdout_hit_rate": 0.5556,
        "holdout_mean_net_pct": 0.1632,
        "empirical_penalty": 21.0,
        "status": "INSUFFICIENT_AND_UNSTABLE",
    },
}


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return _impl._clip(float(value), float(low), float(high))


def _finite(value: Any, default: float = 0.0) -> float:
    number = _impl._finite(value, default)
    return float(default if number is None else number)


def _section(snapshot: dict[str, Any], *names: str) -> dict[str, Any]:
    for name in names:
        value = snapshot.get(name)
        if isinstance(value, dict):
            return value
    return {}


def _pick(section: dict[str, Any], short: str, long: str) -> Any:
    return section.get(short) if short in section else section.get(long)


def _asset_bool(asset: dict[str, Any], key: str) -> bool | None:
    value = asset.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in {"true", "1", "yes", "y"}:
            return True
        if normalised in {"false", "0", "no", "n"}:
            return False
    return None


def _normalised_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    previous = _section(snapshot, "prevDailyBar", "prev_daily_bar")
    daily = _section(snapshot, "dailyBar", "daily_bar")
    minute = _section(snapshot, "minuteBar", "minute_bar")
    trade = _section(snapshot, "latestTrade", "latest_trade")
    quote = _section(snapshot, "latestQuote", "latest_quote")
    return {
        "prevDailyBar": {
            "c": _pick(previous, "c", "close"),
            "v": _pick(previous, "v", "volume"),
        },
        "dailyBar": {
            "c": _pick(daily, "c", "close"),
            "h": _pick(daily, "h", "high"),
            "l": _pick(daily, "l", "low"),
            "v": _pick(daily, "v", "volume"),
            "n": _pick(daily, "n", "trade_count"),
        },
        "minuteBar": {"c": _pick(minute, "c", "close")},
        "latestTrade": {
            "p": _pick(trade, "p", "price"),
            "t": _pick(trade, "t", "timestamp"),
        },
        "latestQuote": {
            "bp": _pick(quote, "bp", "bid_price"),
            "ap": _pick(quote, "ap", "ask_price"),
            "t": _pick(quote, "t", "timestamp"),
        },
    }


def normalise_bars(
    raw_bars: Iterable[dict[str, Any]],
    *,
    evidence_cutoff: datetime | None = None,
) -> list[dict[str, Any]]:
    cutoff = evidence_cutoff or datetime.max.replace(tzinfo=UTC)
    compact: list[dict[str, Any]] = []
    for raw in raw_bars:
        compact.append(
            {
                "t": raw.get("t") if "t" in raw else raw.get("timestamp"),
                "o": raw.get("o") if "o" in raw else raw.get("open"),
                "h": raw.get("h") if "h" in raw else raw.get("high"),
                "l": raw.get("l") if "l" in raw else raw.get("low"),
                "c": raw.get("c") if "c" in raw else raw.get("close"),
                "v": raw.get("v") if "v" in raw else raw.get("volume"),
                "vw": raw.get("vw") if "vw" in raw else raw.get("vwap"),
                "n": raw.get("n") if "n" in raw else raw.get("trade_count"),
            }
        )
    bars, _ = _impl._clean_bars(compact, cutoff)
    return [
        {
            "timestamp": bar["t"],
            "open": bar["o"],
            "high": bar["h"],
            "low": bar["l"],
            "close": bar["c"],
            "volume": bar["v"],
            "vwap": bar["vw"],
            "trade_count": int(bar["n"]),
        }
        for bar in bars
    ]


def snapshot_liquidity_record(
    *,
    symbol: str,
    asset: dict[str, Any],
    snapshot: dict[str, Any],
    evidence_cutoff: datetime,
    elapsed_minutes: float,
    min_price: float,
    min_prev_dollar_volume: float,
    min_current_dollar_volume: float,
    max_spread_bps: float,
    max_quote_age_seconds: float,
) -> dict[str, Any] | None:
    normalised = _normalised_snapshot(snapshot)
    record = _impl.snapshot_liquidity_record(
        symbol=symbol,
        asset=asset,
        snapshot=normalised,
        evidence_cutoff=evidence_cutoff,
        elapsed_minutes=elapsed_minutes,
        min_price=min_price,
        min_prev_dollar_volume=min_prev_dollar_volume,
        min_current_dollar_volume=min_current_dollar_volume,
        max_spread_bps=max_spread_bps,
        max_quote_age_seconds=min(float(max_quote_age_seconds), MAX_EFFECTIVE_QUOTE_AGE_SECONDS),
    )
    if record is None:
        return None

    trade_age = _finite(record.get("trade_age_seconds"), math.inf)
    if trade_age > MAX_EFFECTIVE_TRADE_AGE_SECONDS:
        return None
    midpoint = (_finite(record.get("bid")) + _finite(record.get("ask"))) / 2.0
    if midpoint <= 0:
        return None
    trade_midpoint_dislocation_bps = abs(_finite(record.get("last_price")) - midpoint) / midpoint * 10_000.0
    dislocation_limit_bps = max(50.0, _finite(record.get("spread_bps")) * 8.0)
    if trade_midpoint_dislocation_bps > dislocation_limit_bps:
        return None

    previous = normalised["prevDailyBar"]
    daily = normalised["dailyBar"]
    trade = normalised["latestTrade"]
    quote = normalised["latestQuote"]
    prev_volume = _finite(previous.get("v"))
    current_volume = _finite(daily.get("v"))
    daily_high = _finite(daily.get("h"), _finite(record.get("last_price")))
    daily_low = _finite(daily.get("l"), _finite(record.get("last_price")))
    last_price = _finite(record.get("last_price"))
    daily_range_pct = (daily_high - daily_low) / last_price * 100.0 if last_price > 0 and daily_high >= daily_low else 0.0
    record.update(
        {
            "observed_trade_price": last_price,
            "midpoint_price": midpoint,
            "prev_volume": prev_volume,
            "current_volume": current_volume,
            "daily_range_pct": daily_range_pct,
            "daily_trade_count": int(record.get("day_trade_count") or 0),
            "quote_timestamp": parse_timestamp(quote.get("t")),
            "latest_trade_timestamp": parse_timestamp(trade.get("t")),
            "trade_midpoint_dislocation_bps": trade_midpoint_dislocation_bps,
            "session_elapsed_minutes": float(elapsed_minutes),
            "shortable": _asset_bool(asset, "shortable"),
            "easy_to_borrow": _asset_bool(asset, "easy_to_borrow"),
            "fractionable": _asset_bool(asset, "fractionable"),
            "coarse_liquidity_score": round(_impl._liquidity_score(record), 6),
        }
    )
    return record


def _realized_window_pct(closes: list[float], window: int) -> float:
    if len(closes) < 3:
        return 0.0
    values = closes[-min(len(closes), window + 1) :]
    returns = [
        _impl._log_return(values[index], values[index - 1])
        for index in range(1, len(values))
        if values[index - 1] > 0
    ]
    return _impl._robust_stdev(returns) * math.sqrt(max(1, len(returns))) * 100.0


def _compat_setup_scores(features: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for direction_name, sign in (("LONG", 1), ("SHORT", -1)):
        for setup_type in ("CONTINUATION", "REVERSION"):
            directional, confirmation, _ = _impl._setup_scores(features, sign, setup_type)
            scores[f"{direction_name}_{setup_type}"] = round(0.58 * directional + 0.42 * confirmation, 6)
    return scores


def build_market_features(
    *,
    liquidity_record: dict[str, Any],
    raw_bars: Iterable[dict[str, Any]],
    benchmark_returns: dict[str, float | None],
    evidence_cutoff: datetime,
) -> dict[str, Any] | None:
    raw_list = list(raw_bars)
    result = _impl.build_market_features(
        liquidity_record=liquidity_record,
        raw_bars=raw_list,
        benchmark_returns={key: float(value or 0.0) for key, value in benchmark_returns.items()},
        evidence_cutoff=evidence_cutoff,
    )
    if result is None:
        return None

    compact: list[dict[str, Any]] = []
    for raw in raw_list:
        compact.append(
            {
                "t": raw.get("t") if "t" in raw else raw.get("timestamp"),
                "o": raw.get("o") if "o" in raw else raw.get("open"),
                "h": raw.get("h") if "h" in raw else raw.get("high"),
                "l": raw.get("l") if "l" in raw else raw.get("low"),
                "c": raw.get("c") if "c" in raw else raw.get("close"),
                "v": raw.get("v") if "v" in raw else raw.get("volume"),
                "vw": raw.get("vw") if "vw" in raw else raw.get("vwap"),
                "n": raw.get("n") if "n" in raw else raw.get("trade_count"),
            }
        )
    bars, _ = _impl._clean_bars(compact, evidence_cutoff)
    closes = [float(bar["c"]) for bar in bars]
    highs = [float(bar["h"]) for bar in bars]
    lows = [float(bar["l"]) for bar in bars]
    last_price = _finite(result.get("last_price"))
    observed_range_pct = (max(highs) - min(lows)) / last_price * 100.0 if highs and lows and last_price > 0 else 0.0
    result.update(
        {
            "bar_start": bars[0]["t"] if bars else None,
            "bar_end": bars[-1]["t"] if bars else None,
            "realized_vol_30m_pct": _realized_window_pct(closes, 30),
            "realized_vol_60m_pct": _realized_window_pct(closes, 60),
            "window_vwap": result.get("vwap"),
            "intraday_range_pct": max(observed_range_pct, _finite(result.get("daily_range_pct"))),
            "trend_efficiency": _finite(result.get("trend_efficiency_30")),
            "benchmark_return_5m_pct": benchmark_returns.get("return_5m_pct"),
            "benchmark_return_15m_pct": benchmark_returns.get("return_15m_pct"),
            "benchmark_return_30m_pct": benchmark_returns.get("return_30m_pct"),
            "benchmark_return_60m_pct": benchmark_returns.get("return_60m_pct"),
        }
    )
    result["setup_scores"] = _compat_setup_scores(result)
    return result


def _execution_penalties(record: dict[str, Any], row: dict[str, Any]) -> list[tuple[str, float]]:
    penalties: list[tuple[str, float]] = []
    elapsed = _finite(record.get("session_elapsed_minutes"), 390.0)
    if elapsed < 15.0:
        penalties.append(("opening price discovery remains unusually unstable", 12.0))
    elif elapsed < 30.0:
        penalties.append(("opening price discovery is not yet fully settled", 6.0))

    if row.get("direction") == "SHORT":
        shortable = record.get("shortable")
        easy_to_borrow = record.get("easy_to_borrow")
        if shortable is None:
            penalties.append(("shortability is not confirmed by the broker asset record", 8.0))
        if easy_to_borrow is False:
            penalties.append(("the stock is not marked easy to borrow", 12.0))
        elif easy_to_borrow is None:
            penalties.append(("easy-to-borrow status is not confirmed", 4.0))
    return penalties


def _structural_priority(row: dict[str, Any], data_quality: float) -> tuple[float, float, float]:
    directional_floor = min(_finite(row.get("directional_score")), _finite(row.get("confirmation_score")))
    execution_floor = min(_finite(row.get("liquidity_score")), _finite(row.get("execution_score")))
    movement_opportunity = _finite(row.get("opportunity_score"))
    structural = (
        0.42 * directional_floor
        + 0.25 * movement_opportunity
        + 0.23 * execution_floor
        + 0.10 * data_quality
    )
    return clamp(structural), clamp(directional_floor), clamp(execution_floor)


def _apply_reliability_policy(record: dict[str, Any], raw_row: dict[str, Any]) -> dict[str, Any]:
    row = dict(raw_row)
    evidence = dict(row.get("evidence") or {})
    labels = list(evidence.get("penalties") or [])
    data_quality = _finite(evidence.get("data_quality_score"), _finite(record.get("data_quality_score")))
    setup_key = (str(row.get("direction")), str(row.get("setup_type")))
    audit = dict(_AUDIT_BY_SETUP.get(setup_key) or {})
    execution_penalties = _execution_penalties(record, row)
    execution_penalty = sum(value for _, value in execution_penalties)
    empirical_penalty = _finite(audit.get("empirical_penalty"), 25.0)

    structural, directional_evidence, execution_quality = _structural_priority(row, data_quality)
    setup_margin = _finite(evidence.get("setup_margin"))
    ambiguity_penalty = max(0.0, 6.0 - setup_margin) * 1.25
    priority = clamp(
        structural - execution_penalty - empirical_penalty - ambiguity_penalty,
        0.0,
        ANALYSIS_PRIORITY_CAP,
    )

    if row.get("direction") == "LONG":
        executable_reference = _finite(record.get("ask"), _finite(record.get("last_price")))
        reference_definition = "current SIP ask; next-minute open tracked separately"
    else:
        executable_reference = _finite(record.get("bid"), _finite(record.get("last_price")))
        reference_definition = "current SIP bid; next-minute open tracked separately"
    if executable_reference > 0:
        row["last_price"] = executable_reference

    labels.extend(label for label, _ in execution_penalties)
    labels.append("no registered generic rule passed the frozen robustness gate")
    if audit.get("status") == "FAILED_EXTERNAL_HOLDOUT":
        labels.append("the matching generic setup family had negative mean net return in the external holdout")
    else:
        labels.append("the matching reversal family had insufficient and unstable historical support")

    if priority >= 55.0 and data_quality >= 90.0 and execution_quality >= 75.0 and setup_margin >= 4.0:
        initial_view = "ANALYSE ONLY"
    elif priority >= 38.0:
        initial_view = "LOW PRIORITY"
    else:
        initial_view = "PASS"

    evidence.update(
        {
            "scoring_version": SCORING_VERSION,
            "model_audit_version": MODEL_AUDIT_VERSION,
            "score_interpretation": "analysis priority, not probability or expected return",
            "analysis_priority_score": priority,
            "movement_opportunity_score": _finite(row.get("opportunity_score")),
            "directional_evidence_score": directional_evidence,
            "execution_quality_score": execution_quality,
            "data_quality_score": data_quality,
            "empirical_reliability_score": 0.0,
            "reliability_label": "NO VALIDATED EDGE",
            "validation_status": "RESEARCH_ONLY",
            "trade_gate": "BLOCKED",
            "trade_gate_reason": "zero robust registered candidates passed; generic families failed or lacked sufficient external-holdout support",
            "registered_robust_candidates_tested": 23,
            "registered_robust_candidates_passed": 0,
            "historical_holdout_n": int(audit.get("holdout_n") or 0),
            "historical_holdout_days": int(audit.get("holdout_days") or 0),
            "historical_holdout_hit_rate": audit.get("holdout_hit_rate"),
            "historical_holdout_mean_net_pct": audit.get("holdout_mean_net_pct"),
            "historical_setup_status": audit.get("status", "UNSUPPORTED"),
            "empirical_penalty": empirical_penalty,
            "execution_reliability_penalty": execution_penalty,
            "ambiguity_penalty_v3": ambiguity_penalty,
            "reference_price_definition": reference_definition,
            "observed_trade_price": _finite(record.get("observed_trade_price"), _finite(record.get("last_price"))),
            "reference_price": executable_reference,
            "penalties": list(dict.fromkeys(labels)),
            "penalty_total": _finite(evidence.get("penalty_total")) + execution_penalty + empirical_penalty + ambiguity_penalty,
        }
    )
    row["profitability_score"] = priority
    row["initial_view"] = initial_view
    row["evidence"] = evidence
    row["rationale"] = (
        f"Research priority {priority:.1f}/100: directional evidence {directional_evidence:.0f}, "
        f"movement opportunity {_finite(row.get('opportunity_score')):.0f}, execution quality {execution_quality:.0f} "
        f"and data quality {data_quality:.0f}. The {row.get('direction')} {str(row.get('setup_type')).lower()} "
        "is a hypothesis for catalyst review only; the matching generic family has no validated positive net two-hour edge."
    )
    return row


def _rank_direction_options(record: dict[str, Any], direction_filter: str) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    if direction_filter in {"both", "long"}:
        options.extend(_apply_reliability_policy(record, row) for row in _impl.rank_market_records([record], direction_filter="long"))
    if direction_filter in {"both", "short"} and record.get("shortable") is not False:
        options.extend(_apply_reliability_policy(record, row) for row in _impl.rank_market_records([record], direction_filter="short"))
    return options


def rank_market_records(records: list[dict[str, Any]], *, direction_filter: str = "both") -> list[dict[str, Any]]:
    if direction_filter not in {"both", "long", "short"}:
        raise ValueError("direction_filter must be 'both', 'long', or 'short'")

    ranked: list[dict[str, Any]] = []
    for record in records:
        options = _rank_direction_options(record, direction_filter)
        if not options:
            continue
        options.sort(
            key=lambda row: (
                _finite(row.get("profitability_score")),
                _finite((row.get("evidence") or {}).get("directional_evidence_score")),
                _finite(row.get("execution_score")),
            ),
            reverse=True,
        )
        ranked.append(options[0])

    ranked.sort(
        key=lambda row: (
            _finite(row.get("profitability_score")),
            _finite((row.get("evidence") or {}).get("directional_evidence_score")),
            _finite(row.get("execution_score")),
            _finite(row.get("prev_dollar_volume")),
        ),
        reverse=True,
    )

    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
        evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        row.update(
            {
                "edge_to_cost_ratio": round(_finite(evidence.get("edge_to_cost_ratio")), 6),
                "data_quality_score": round(_finite(evidence.get("data_quality_score")), 6),
                "penalties": {
                    "labels": list(evidence.get("penalties") or []),
                    "penalty_total": round(_finite(evidence.get("penalty_total")), 6),
                    "ambiguity_penalty": round(_finite(evidence.get("ambiguity_penalty_v3")), 6),
                    "chase_ratio": round(_finite(evidence.get("chase_ratio")), 6),
                    "vwap_sigma": round(_finite(evidence.get("vwap_sigma")), 6),
                    "execution_reliability_penalty": round(_finite(evidence.get("execution_reliability_penalty")), 6),
                    "empirical_penalty": round(_finite(evidence.get("empirical_penalty")), 6),
                },
                "scoring_version": SCORING_VERSION,
                "target_definition": TARGET_DEFINITION,
            }
        )
    return ranked
