from __future__ import annotations

import statistics
from typing import Any

from app.oversold_score_common import SCORING_CONFIG, clamp, _number, _piecewise


def _history_bars(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = candidate.get("raw_snapshot") or {}
    bars = snapshot.get("historicalDailyBars") or candidate.get("historical_daily_bars") or []
    valid = [dict(bar) for bar in bars if isinstance(bar, dict) and (_number(bar.get("c")) or 0) > 0]
    valid.sort(key=lambda bar: str(bar.get("t") or ""))
    return valid[-80:]


def _rsi14(closes: list[float]) -> float | None:
    if len(closes) < 15:
        return None
    changes = [b - a for a, b in zip(closes[-15:-1], closes[-14:], strict=True)]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains) / len(gains)
    avg_loss = sum(losses) / len(losses)
    if avg_loss <= 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def technical_context(candidate: dict[str, Any]) -> dict[str, Any]:
    bars = _history_bars(candidate)
    current = _number(candidate.get("last_price"))
    closes = [_number(bar.get("c")) for bar in bars]
    closes = [value for value in closes if value is not None and value > 0]
    volumes = [_number(bar.get("v")) for bar in bars]
    volumes = [value for value in volumes if value is not None and value >= 0]
    history_count = len(closes)
    context: dict[str, Any] = {"history_count": history_count}
    if current is None or history_count < 2:
        context["history_available"] = False
        return context

    context["history_available"] = history_count >= int(SCORING_CONFIG["setup"]["minimum_history_bars"])
    returns = [(b / a) - 1.0 for a, b in zip(closes[:-1], closes[1:], strict=True) if a > 0]
    day_return = (_number(candidate.get("drop_pct")) or 0.0) / 100.0
    sample = returns[-60:]
    if len(sample) >= 10:
        mean_return = statistics.fmean(sample)
        std_return = statistics.stdev(sample) if len(sample) > 1 else 0.0
        shock_z = (day_return - mean_return) / std_return if std_return > 1e-9 else None
    else:
        mean_return, std_return, shock_z = None, None, None

    prior20 = closes[-20:]
    median20 = statistics.median(prior20) if prior20 else None
    high20 = max(prior20) if prior20 else None
    baseline20_pct = ((current / median20) - 1.0) * 100.0 if median20 else None
    drawdown20_pct = ((current / high20) - 1.0) * 100.0 if high20 else None
    combined_closes = closes + [current]
    rsi = _rsi14(combined_closes)

    current_volume = _number((candidate.get("raw_snapshot") or {}).get("dailyBar", {}).get("v"))
    median_volume20 = statistics.median(volumes[-20:]) if volumes[-20:] else None
    volume_ratio = current_volume / median_volume20 if current_volume is not None and median_volume20 and median_volume20 > 0 else None

    def multi_return(days: int, include_current: bool) -> float | None:
        series = combined_closes if include_current else closes
        if len(series) < days + 1:
            return None
        base = series[-(days + 1)]
        return ((series[-1] / base) - 1.0) * 100.0 if base > 0 else None

    pre5 = multi_return(5, False)
    current5 = multi_return(5, True)
    pre3 = multi_return(3, False)
    current3 = multi_return(3, True)
    post_spike_risk = bool(
        (pre5 is not None and pre5 >= 50.0)
        or (pre3 is not None and pre3 >= 60.0)
        or (baseline20_pct is not None and baseline20_pct >= 50.0)
    )
    context.update({
        "mean_daily_return_pct": mean_return * 100.0 if mean_return is not None else None,
        "daily_return_std_pct": std_return * 100.0 if std_return is not None else None,
        "shock_z": shock_z, "baseline20_pct": baseline20_pct, "drawdown20_pct": drawdown20_pct,
        "rsi14": rsi, "volume_ratio_20d_median": volume_ratio,
        "pre_signal_5d_return_pct": pre5, "current_5d_return_pct": current5,
        "pre_signal_3d_return_pct": pre3, "current_3d_return_pct": current3,
        "post_spike_risk": post_spike_risk,
    })
    return context


def _liquidity_scores(candidate: dict[str, Any]) -> tuple[float, float]:
    dollar_volume = _number(candidate.get("prev_dollar_volume"))
    if dollar_volume is None:
        liquidity = 30.0
    elif dollar_volume >= 50_000_000:
        liquidity = 95.0
    elif dollar_volume >= 10_000_000:
        liquidity = 82.0
    elif dollar_volume >= 2_000_000:
        liquidity = 65.0
    elif dollar_volume >= 500_000:
        liquidity = 45.0
    else:
        liquidity = 15.0
    spread_pct = _number(candidate.get("spread_pct"))
    if spread_pct is None:
        spread = 35.0
    elif spread_pct <= 0.5:
        spread = 95.0
    elif spread_pct <= 1.0:
        spread = 85.0
    elif spread_pct <= 2.0:
        spread = 68.0
    elif spread_pct <= 5.0:
        spread = 38.0
    else:
        spread = 12.0
    return liquidity, spread


def setup_score(candidate: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    snapshot = candidate.get("raw_snapshot") or {}
    daily = snapshot.get("dailyBar") or {}
    context = technical_context(candidate)
    drop = abs(min(_number(candidate.get("drop_pct")) or 0.0, 0.0))
    prev_close = _number(candidate.get("prev_close"))
    day_open = _number(daily.get("o"))
    gap_pct = ((day_open / prev_close) - 1.0) * 100.0 if prev_close and day_open else None
    gap_magnitude = abs(min(gap_pct or 0.0, 0.0)) if gap_pct is not None else None
    gap_score = _piecewise(gap_magnitude, [(0, 30), (5, 50), (10, 70), (20, 90), (30, 100)], 35)
    liquidity, spread = _liquidity_scores(candidate)
    shock_score = _piecewise(context.get("shock_z"), [(-6, 100), (-4, 92), (-3, 82), (-2, 68), (-1, 48), (0, 25), (1, 10)], _piecewise(drop, [(15, 45), (20, 58), (30, 75), (45, 90), (70, 95)], 45))
    baseline_score = _piecewise(context.get("baseline20_pct"), [(-50, 100), (-35, 95), (-25, 88), (-15, 75), (-7, 60), (0, 40), (20, 20), (50, 5)], 35)
    rsi_score = _piecewise(context.get("rsi14"), [(15, 100), (20, 95), (30, 80), (40, 58), (50, 35), (60, 20), (75, 5)], 35)
    drawdown_abs = abs(min(_number(context.get("drawdown20_pct")) or 0.0, 0.0))
    drawdown_score = _piecewise(drawdown_abs, [(0, 20), (10, 45), (20, 65), (35, 85), (50, 95)], 35)
    volume_score = _piecewise(context.get("volume_ratio_20d_median"), [(0.5, 25), (1, 45), (1.5, 60), (2.5, 78), (4, 92), (8, 100)], 35)
    tradability = 0.58 * liquidity + 0.42 * spread
    history_available = bool(context.get("history_available"))
    if history_available:
        raw_score = 0.25 * shock_score + 0.22 * baseline_score + 0.13 * rsi_score + 0.10 * drawdown_score + 0.10 * volume_score + 0.08 * gap_score + 0.12 * tradability
    else:
        decline_fallback = _piecewise(drop, [(15, 45), (20, 58), (30, 72), (45, 84), (70, 88)], 45)
        raw_score = 0.45 * decline_fallback + 0.20 * gap_score + 0.20 * tradability + 0.15 * volume_score
        raw_score = min(raw_score, 68.0)

    caps: list[dict[str, Any]] = []
    cap = 100.0
    baseline = _number(context.get("baseline20_pct"))
    pre5 = _number(context.get("pre_signal_5d_return_pct"))
    current5 = _number(context.get("current_5d_return_pct"))
    setup_caps = SCORING_CONFIG["setup"]["post_spike_caps"]
    if baseline is not None and baseline >= 100:
        cap = min(cap, float(setup_caps["baseline_100pct"]))
        caps.append({"reason": "price_still_over_100pct_above_20d_median", "cap": cap})
    elif baseline is not None and baseline >= 50:
        cap = min(cap, float(setup_caps["baseline_50pct"]))
        caps.append({"reason": "price_still_over_50pct_above_20d_median", "cap": cap})
    if pre5 is not None and current5 is not None and pre5 >= 100 and current5 >= 20:
        cap = min(cap, float(setup_caps["pre5_100_current20"]))
        caps.append({"reason": "large_pre_signal_spike_not_fully_reversed", "cap": cap})
    elif pre5 is not None and current5 is not None and pre5 >= 50 and current5 >= 10:
        cap = min(cap, float(setup_caps["pre5_50_current10"]))
        caps.append({"reason": "recent_spike_unwind_not_true_baseline_oversold", "cap": cap})
    score = round(clamp(min(raw_score, cap)), 1)
    return score, {
        "history": context, "shock_score": round(shock_score, 1), "baseline_dislocation_score": round(baseline_score, 1),
        "rsi_oversold_score": round(rsi_score, 1), "drawdown_score": round(drawdown_score, 1),
        "volume_anomaly_score": round(volume_score, 1), "gap_dislocation_score": round(gap_score, 1),
        "gap_pct": round(gap_pct, 3) if gap_pct is not None else None,
        "liquidity_score": round(liquidity, 1), "spread_quality_score": round(spread, 1),
        "tradability_score": round(tradability, 1), "raw_setup_score": round(raw_score, 2),
        "setup_cap": cap, "caps_applied": caps, "history_available": history_available,
        "weights": {"shock_z": 0.25, "baseline": 0.22, "rsi": 0.13, "drawdown": 0.10, "volume": 0.10, "gap": 0.08, "tradability": 0.12} if history_available else {"decline_fallback": 0.45, "gap": 0.20, "tradability": 0.20, "volume": 0.15},
    }


def confirmation_score(candidate: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    snapshot = candidate.get("raw_snapshot") or {}
    daily = snapshot.get("dailyBar") or {}
    previous = snapshot.get("prevDailyBar") or {}
    last_price = _number(candidate.get("last_price")) or _number(daily.get("c"))
    low, high, day_open = _number(daily.get("l")), _number(daily.get("h")), _number(daily.get("o"))
    range_position = clamp((last_price - low) / (high - low) * 100.0) if last_price is not None and low is not None and high is not None and high > low else 30.0
    if last_price is not None and day_open and day_open > 0:
        from_open_pct = ((last_price / day_open) - 1.0) * 100.0
        intraday_reversal = clamp(50.0 + from_open_pct * 8.0)
    else:
        from_open_pct, intraday_reversal = None, 30.0
    prev_volume = _number(previous.get("v")) or _number(candidate.get("prev_volume"))
    day_volume = _number(daily.get("v"))
    relative_volume = day_volume / prev_volume if prev_volume and day_volume is not None and prev_volume > 0 else None
    if relative_volume is None:
        volume_confirmation = 30.0
    elif relative_volume >= 2.0 and range_position >= 55:
        volume_confirmation = 88.0
    elif relative_volume >= 1.25 and range_position >= 45:
        volume_confirmation = 70.0
    elif range_position < 25:
        volume_confirmation = 18.0
    else:
        volume_confirmation = 45.0
    daily_vwap = _number(daily.get("vw")) or _number(daily.get("vwap"))
    if last_price is not None and daily_vwap and daily_vwap > 0:
        vwap_distance_pct = ((last_price / daily_vwap) - 1.0) * 100.0
        vwap_reclaim = _piecewise(vwap_distance_pct, [(-8, 10), (-3, 25), (0, 50), (1, 65), (3, 82), (8, 95)], 35)
    else:
        vwap_distance_pct, vwap_reclaim = None, 30.0
    _, spread_normalisation = _liquidity_scores(candidate)
    score = 0.35 * range_position + 0.20 * intraday_reversal + 0.15 * volume_confirmation + 0.20 * vwap_reclaim + 0.10 * spread_normalisation
    return round(clamp(score), 1), {
        "session_range_position": round(range_position, 1),
        "return_from_open_pct": round(from_open_pct, 3) if from_open_pct is not None else None,
        "intraday_reversal_score": round(intraday_reversal, 1), "volume_confirmation_score": round(volume_confirmation, 1),
        "vwap_reclaim_score": round(vwap_reclaim, 1), "vwap_distance_pct": round(vwap_distance_pct, 3) if vwap_distance_pct is not None else None,
        "spread_normalisation_score": round(spread_normalisation, 1),
        "relative_volume": round(relative_volume, 3) if relative_volume is not None else None,
        "weights": {"range_position": 0.35, "intraday_reversal": 0.20, "volume": 0.15, "vwap": 0.20, "spread": 0.10},
    }
