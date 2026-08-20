from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

SECTOR_BENCHMARKS: dict[str, str] = {
    "biotechnology": "XBI",
    "financials": "XLF",
    "software": "IGV",
    "industrials": "XLI",
    "consumer": "XLY",
}
MARKET_BENCHMARK = "SPY"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(variance, 0.0))


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _prior_history(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    history = candidate.get("history_bars") or []
    cutoff = _parse_ts(candidate.get("evidence_cutoff"))
    cutoff_date = cutoff.astimezone(NY).date() if cutoff else None
    rows: list[tuple[datetime, dict[str, Any]]] = []
    for bar in history:
        if not isinstance(bar, dict):
            continue
        ts = _parse_ts(bar.get("t"))
        if ts is None:
            continue
        if cutoff_date is not None and ts.astimezone(NY).date() >= cutoff_date:
            continue
        if _number(bar.get("c")) is None:
            continue
        rows.append((ts, bar))
    rows.sort(key=lambda item: item[0])
    return [bar for _, bar in rows][-80:]


def _returns_from_closes(closes: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        if previous > 0:
            returns.append((current / previous) - 1.0)
    return returns


def _rsi14(prior_closes: list[float], current_price: float | None) -> float | None:
    if current_price is None or current_price <= 0 or len(prior_closes) < 14:
        return None
    closes = prior_closes[-14:] + [current_price]
    changes = [current - previous for previous, current in zip(closes, closes[1:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = _mean(gains)
    avg_loss = _mean(losses)
    if avg_gain is None or avg_loss is None:
        return None
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr20(prior_bars: list[dict[str, Any]]) -> float | None:
    if len(prior_bars) < 2:
        return None
    bars = prior_bars[-21:]
    true_ranges: list[float] = []
    previous_close: float | None = None
    for bar in bars:
        high = _number(bar.get("h"))
        low = _number(bar.get("l"))
        close = _number(bar.get("c"))
        if high is None or low is None or close is None:
            previous_close = close
            continue
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        if true_range >= 0:
            true_ranges.append(true_range)
        previous_close = close
    return _mean(true_ranges[-20:])


def _benchmark_return(context: dict[str, Any] | None) -> float | None:
    if not context:
        return None
    snapshot = context.get("snapshot") or {}
    previous = snapshot.get("prevDailyBar") or {}
    latest_trade = snapshot.get("latestTrade") or {}
    daily = snapshot.get("dailyBar") or {}
    prev_close = _number(previous.get("c"))
    last_price = _number(latest_trade.get("p")) or _number(daily.get("c"))
    if prev_close is None or last_price is None or prev_close <= 0:
        return None
    return ((last_price / prev_close) - 1.0) * 100.0


def technical_features(candidate: dict[str, Any], sector_hint: str | None = None) -> dict[str, Any]:
    prior_bars = _prior_history(candidate)
    closes = [_number(bar.get("c")) for bar in prior_bars]
    closes = [value for value in closes if value is not None and value > 0]
    current_price = _number(candidate.get("last_price"))
    prev_close = _number(candidate.get("prev_close"))
    current_return_pct = _number(candidate.get("drop_pct"))
    returns = _returns_from_closes(closes)
    recent_returns = returns[-20:]
    mean20 = _mean(recent_returns)
    std20 = _std(recent_returns)
    shock_z = None
    if current_return_pct is not None and std20 is not None and std20 > 0:
        current_return = current_return_pct / 100.0
        baseline = mean20 or 0.0
        shock_z = max(0.0, -(current_return - baseline) / max(std20, 0.0075))

    sma20 = _mean(closes[-20:]) if len(closes) >= 20 else None
    sma50 = _mean(closes[-50:]) if len(closes) >= 50 else None
    sma20_distance_pct = ((current_price / sma20) - 1.0) * 100.0 if current_price and sma20 else None
    sma50_distance_pct = ((current_price / sma50) - 1.0) * 100.0 if current_price and sma50 else None
    rsi14 = _rsi14(closes, current_price)

    highs = [_number(bar.get("h")) for bar in prior_bars[-60:]]
    highs = [value for value in highs if value is not None and value > 0]
    recent_high = max(highs) if highs else None
    drawdown_from_60d_high_pct = ((current_price / recent_high) - 1.0) * 100.0 if current_price and recent_high else None

    prior_volumes = [_number(bar.get("v")) for bar in prior_bars[-20:]]
    prior_volumes = [value for value in prior_volumes if value is not None and value >= 0]
    snapshot = candidate.get("raw_snapshot") or {}
    daily = snapshot.get("dailyBar") or {}
    current_volume = _number(daily.get("v"))
    volume_mean20 = _mean(prior_volumes)
    volume_std20 = _std(prior_volumes)
    relative_volume20 = current_volume / volume_mean20 if current_volume is not None and volume_mean20 and volume_mean20 > 0 else None
    volume_z20 = (current_volume - volume_mean20) / volume_std20 if current_volume is not None and volume_mean20 is not None and volume_std20 and volume_std20 > 0 else None

    atr20 = _atr20(prior_bars)
    atr_move_multiple = abs((current_price or 0.0) - (prev_close or 0.0)) / atr20 if current_price and prev_close and atr20 and atr20 > 0 else None

    day_open = _number(daily.get("o"))
    day_low = _number(daily.get("l"))
    day_high = _number(daily.get("h"))
    day_vwap = _number(daily.get("vw"))
    gap_pct = ((day_open / prev_close) - 1.0) * 100.0 if day_open and prev_close and prev_close > 0 else None
    range_position = ((current_price - day_low) / (day_high - day_low) * 100.0) if current_price is not None and day_low is not None and day_high is not None and day_high > day_low else None
    return_from_open_pct = ((current_price / day_open) - 1.0) * 100.0 if current_price and day_open and day_open > 0 else None
    gap_reclaim_pct = None
    if current_price is not None and day_open is not None and prev_close is not None and day_open < prev_close:
        gap_size = prev_close - day_open
        if gap_size > 0:
            gap_reclaim_pct = (current_price - day_open) / gap_size * 100.0
    low_reclaim_pct = None
    if current_price is not None and day_low is not None and prev_close is not None and day_low < prev_close:
        denominator = prev_close - day_low
        if denominator > 0:
            low_reclaim_pct = (current_price - day_low) / denominator * 100.0
    vwap_distance_pct = ((current_price / day_vwap) - 1.0) * 100.0 if current_price and day_vwap and day_vwap > 0 else None

    benchmark_context = candidate.get("benchmark_context") or {}
    market_return_pct = _benchmark_return(benchmark_context.get(MARKET_BENCHMARK))
    market_relative_move_pct = current_return_pct - market_return_pct if current_return_pct is not None and market_return_pct is not None else None
    sector_benchmark = SECTOR_BENCHMARKS.get(str(sector_hint or ""))
    sector_return_pct = _benchmark_return(benchmark_context.get(sector_benchmark)) if sector_benchmark else None
    sector_relative_move_pct = current_return_pct - sector_return_pct if current_return_pct is not None and sector_return_pct is not None else None

    available = {
        "history_20": len(closes) >= 20,
        "history_50": len(closes) >= 50,
        "shock_z": shock_z is not None,
        "rsi14": rsi14 is not None,
        "sma20": sma20_distance_pct is not None,
        "sma50": sma50_distance_pct is not None,
        "drawdown_60d": drawdown_from_60d_high_pct is not None,
        "volume_anomaly": relative_volume20 is not None,
        "atr20": atr_move_multiple is not None,
        "market_relative": market_relative_move_pct is not None,
        "sector_relative": sector_relative_move_pct is not None,
        "range_position": range_position is not None,
        "gap_reclaim": gap_reclaim_pct is not None,
        "vwap": vwap_distance_pct is not None,
    }
    completeness = sum(1 for value in available.values() if value) / len(available) * 100.0

    return {
        "history_count": len(closes),
        "current_return_pct": round(current_return_pct, 4) if current_return_pct is not None else None,
        "mean20_return_pct": round((mean20 or 0.0) * 100.0, 4) if mean20 is not None else None,
        "vol20_pct": round((std20 or 0.0) * 100.0, 4) if std20 is not None else None,
        "shock_z": round(shock_z, 3) if shock_z is not None else None,
        "atr20": round(atr20, 4) if atr20 is not None else None,
        "atr_move_multiple": round(atr_move_multiple, 3) if atr_move_multiple is not None else None,
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "sma20": round(sma20, 4) if sma20 is not None else None,
        "sma50": round(sma50, 4) if sma50 is not None else None,
        "sma20_distance_pct": round(sma20_distance_pct, 3) if sma20_distance_pct is not None else None,
        "sma50_distance_pct": round(sma50_distance_pct, 3) if sma50_distance_pct is not None else None,
        "recent_high_60d": round(recent_high, 4) if recent_high is not None else None,
        "drawdown_from_60d_high_pct": round(drawdown_from_60d_high_pct, 3) if drawdown_from_60d_high_pct is not None else None,
        "current_volume": round(current_volume, 2) if current_volume is not None else None,
        "volume_mean20": round(volume_mean20, 2) if volume_mean20 is not None else None,
        "relative_volume20": round(relative_volume20, 3) if relative_volume20 is not None else None,
        "volume_z20": round(volume_z20, 3) if volume_z20 is not None else None,
        "gap_pct": round(gap_pct, 3) if gap_pct is not None else None,
        "session_range_position": round(range_position, 2) if range_position is not None else None,
        "return_from_open_pct": round(return_from_open_pct, 3) if return_from_open_pct is not None else None,
        "gap_reclaim_pct": round(gap_reclaim_pct, 2) if gap_reclaim_pct is not None else None,
        "low_reclaim_pct": round(low_reclaim_pct, 2) if low_reclaim_pct is not None else None,
        "vwap": round(day_vwap, 4) if day_vwap is not None else None,
        "vwap_distance_pct": round(vwap_distance_pct, 3) if vwap_distance_pct is not None else None,
        "market_benchmark": MARKET_BENCHMARK,
        "market_return_pct": round(market_return_pct, 3) if market_return_pct is not None else None,
        "market_relative_move_pct": round(market_relative_move_pct, 3) if market_relative_move_pct is not None else None,
        "sector_benchmark": sector_benchmark,
        "sector_return_pct": round(sector_return_pct, 3) if sector_return_pct is not None else None,
        "sector_relative_move_pct": round(sector_relative_move_pct, 3) if sector_relative_move_pct is not None else None,
        "feature_availability": available,
        "technical_history_completeness": round(completeness, 1),
    }
