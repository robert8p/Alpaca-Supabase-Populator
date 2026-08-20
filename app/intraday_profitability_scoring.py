"""Stable public contract for the robust Intraday Profitability v2 scorer.

The scanner was originally released against the v1 field contract. The v2
implementation deliberately lives in a separate module; this adapter preserves
all scanner-facing names and evidence fields while delegating the actual
liquidity, feature and ranking logic to the hardened implementation.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Iterable

from . import intraday_profitability_scoring_v2 as _impl

SCORING_VERSION = _impl.SCORING_VERSION
TARGET_DEFINITION = (
    "Positive net directional return over the next 120 regular-session minutes "
    "after all signal inputs are complete."
)
MIN_BARS = _impl.MIN_BARS
MAX_BAR_GAP_RATIO = _impl.MAX_BAR_GAP_RATIO
MAX_EFFECTIVE_QUOTE_AGE_SECONDS = 60.0
MAX_EFFECTIVE_TRADE_AGE_SECONDS = 90.0
parse_timestamp = _impl._parse_dt
benchmark_returns = _impl.benchmark_returns


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return _impl._clip(float(value), float(low), float(high))


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
    """Expose the original public bar schema for compatibility and audits."""
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
        max_quote_age_seconds=min(
            float(max_quote_age_seconds),
            MAX_EFFECTIVE_QUOTE_AGE_SECONDS,
        ),
    )
    if record is None:
        return None

    if float(record.get("trade_age_seconds") or math.inf) > MAX_EFFECTIVE_TRADE_AGE_SECONDS:
        return None
    midpoint = (float(record["bid"]) + float(record["ask"])) / 2.0
    trade_midpoint_dislocation_bps = (
        abs(float(record["last_price"]) - midpoint) / midpoint * 10_000.0
        if midpoint > 0
        else math.inf
    )
    dislocation_limit_bps = max(50.0, float(record["spread_bps"]) * 8.0)
    if trade_midpoint_dislocation_bps > dislocation_limit_bps:
        return None

    previous = normalised["prevDailyBar"]
    daily = normalised["dailyBar"]
    trade = normalised["latestTrade"]
    quote = normalised["latestQuote"]
    prev_volume = _impl._finite(previous.get("v"), 0.0) or 0.0
    current_volume = _impl._finite(daily.get("v"), 0.0) or 0.0
    daily_high = _impl._finite(daily.get("h"), record["last_price"]) or record["last_price"]
    daily_low = _impl._finite(daily.get("l"), record["last_price"]) or record["last_price"]
    daily_range_pct = (
        (daily_high - daily_low) / float(record["last_price"]) * 100.0
        if daily_high >= daily_low and float(record["last_price"]) > 0
        else 0.0
    )
    record.update(
        {
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
            scores[f"{direction_name}_{setup_type}"] = round(
                0.58 * directional + 0.42 * confirmation,
                6,
            )
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
    last_price = float(result["last_price"])
    observed_range_pct = (
        (max(highs) - min(lows)) / last_price * 100.0
        if highs and lows and last_price > 0
        else 0.0
    )
    result.update(
        {
            "bar_start": bars[0]["t"] if bars else None,
            "bar_end": bars[-1]["t"] if bars else None,
            "realized_vol_30m_pct": _realized_window_pct(closes, 30),
            "realized_vol_60m_pct": _realized_window_pct(closes, 60),
            "window_vwap": result.get("vwap"),
            "intraday_range_pct": max(
                observed_range_pct,
                float(result.get("daily_range_pct") or 0.0),
            ),
            "trend_efficiency": float(result.get("trend_efficiency_30") or 0.0),
            "benchmark_return_5m_pct": benchmark_returns.get("return_5m_pct"),
            "benchmark_return_15m_pct": benchmark_returns.get("return_15m_pct"),
            "benchmark_return_30m_pct": benchmark_returns.get("return_30m_pct"),
            "benchmark_return_60m_pct": benchmark_returns.get("return_60m_pct"),
        }
    )
    result["setup_scores"] = _compat_setup_scores(result)
    return result


def _additional_execution_penalties(
    record: dict[str, Any],
    row: dict[str, Any],
) -> list[tuple[str, float]]:
    penalties: list[tuple[str, float]] = []
    elapsed = float(record.get("session_elapsed_minutes") or 390.0)
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


def _apply_additional_penalties(
    record: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    row = dict(row)
    evidence = dict(row.get("evidence") or {})
    existing_labels = list(evidence.get("penalties") or [])
    extra = _additional_execution_penalties(record, row)
    extra_total = sum(value for _, value in extra)
    if extra_total:
        row["profitability_score"] = clamp(
            float(row.get("profitability_score") or 0.0) - extra_total
        )
        labels = existing_labels + [label for label, _ in extra]
        evidence["penalties"] = list(dict.fromkeys(labels))
        evidence["penalty_total"] = float(evidence.get("penalty_total") or 0.0) + extra_total
        evidence["execution_reliability_penalty"] = extra_total
        row["rationale"] = (
            str(row.get("rationale") or "").rstrip(".")
            + ". Execution cautions: "
            + "; ".join(label for label, _ in extra)
            + "."
        )

    score = float(row.get("profitability_score") or 0.0)
    data_quality = float(evidence.get("data_quality_score") or record.get("data_quality_score") or 0.0)
    edge_to_cost = float(evidence.get("edge_to_cost_ratio") or 0.0)
    setup_margin = float(evidence.get("setup_margin") or 0.0)
    if score >= 76.0 and data_quality >= 90.0 and edge_to_cost >= 5.0 and setup_margin >= 2.0 and extra_total < 10.0:
        row["initial_view"] = "INVESTIGATE"
    elif score >= 62.0:
        row["initial_view"] = "WATCH"
    else:
        row["initial_view"] = "PASS"
    row["evidence"] = evidence
    return row


def _rank_record_options(
    record: dict[str, Any],
    direction_filter: str,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    if direction_filter in {"both", "long"}:
        options.extend(
            _apply_additional_penalties(record, row)
            for row in _impl.rank_market_records([record], direction_filter="long")
        )
    if direction_filter in {"both", "short"} and record.get("shortable") is not False:
        options.extend(
            _apply_additional_penalties(record, row)
            for row in _impl.rank_market_records([record], direction_filter="short")
        )
    return options


def rank_market_records(
    records: list[dict[str, Any]],
    *,
    direction_filter: str = "both",
) -> list[dict[str, Any]]:
    if direction_filter not in {"both", "long", "short"}:
        raise ValueError("direction_filter must be 'both', 'long', or 'short'")

    ranked: list[dict[str, Any]] = []
    for record in records:
        options = _rank_record_options(record, direction_filter)
        if not options:
            continue
        options.sort(
            key=lambda row: (
                float(row.get("profitability_score") or 0.0),
                float(row.get("execution_score") or 0.0),
            ),
            reverse=True,
        )
        ranked.append(options[0])

    ranked.sort(
        key=lambda row: (
            float(row.get("profitability_score") or 0.0),
            float(row.get("execution_score") or 0.0),
            float(row.get("prev_dollar_volume") or 0.0),
        ),
        reverse=True,
    )

    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
        evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        row.update(
            {
                "edge_to_cost_ratio": round(float(evidence.get("edge_to_cost_ratio") or 0.0), 6),
                "data_quality_score": round(
                    float(evidence.get("data_quality_score") or row.get("data_quality_score") or 0.0),
                    6,
                ),
                "penalties": {
                    "labels": list(evidence.get("penalties") or []),
                    "penalty_total": round(float(evidence.get("penalty_total") or 0.0), 6),
                    "ambiguity_penalty": round(float(evidence.get("ambiguity_penalty") or 0.0), 6),
                    "chase_ratio": round(float(evidence.get("chase_ratio") or 0.0), 6),
                    "vwap_sigma": round(float(evidence.get("vwap_sigma") or 0.0), 6),
                    "execution_reliability_penalty": round(
                        float(evidence.get("execution_reliability_penalty") or 0.0),
                        6,
                    ),
                },
                "scoring_version": SCORING_VERSION,
                "target_definition": TARGET_DEFINITION,
            }
        )
    return ranked
