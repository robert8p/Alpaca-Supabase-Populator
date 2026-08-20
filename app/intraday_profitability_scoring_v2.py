from __future__ import annotations

import math
from datetime import UTC, datetime
from statistics import median
from typing import Any, Iterable

SCORING_VERSION = "ip-robust-v2.0"
MIN_BARS = 35
MAX_BAR_GAP_RATIO = 0.18


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _score(value: float) -> float:
    return _clip(value, 0.0, 100.0)


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and value:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _age_seconds(timestamp: Any, cutoff: datetime) -> float | None:
    parsed = _parse_dt(timestamp)
    if parsed is None:
        return None
    return max(0.0, (cutoff.astimezone(UTC) - parsed).total_seconds())


def _pct(current: float, prior: float | None) -> float:
    if prior is None or prior <= 0:
        return 0.0
    return (current / prior - 1.0) * 100.0


def _log_return(current: float, prior: float) -> float:
    if current <= 0 or prior <= 0:
        return 0.0
    return math.log(current / prior)


def _window_return(closes: list[float], minutes: int) -> float:
    if len(closes) <= minutes:
        return 0.0
    return _pct(closes[-1], closes[-minutes - 1])


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(0.0, variance))


def _robust_stdev(values: list[float]) -> float:
    if len(values) < 3:
        return _stdev(values)
    centre = median(values)
    deviations = [abs(value - centre) for value in values]
    mad = median(deviations)
    if mad <= 0:
        return _stdev(values)
    robust = 1.4826 * mad
    winsor = 4.0 * robust
    clipped = [_clip(value, centre - winsor, centre + winsor) for value in values]
    return _stdev(clipped)


def _clean_bars(raw_bars: list[dict[str, Any]], evidence_cutoff: datetime) -> tuple[list[dict[str, Any]], float]:
    by_time: dict[datetime, dict[str, Any]] = {}
    cutoff = evidence_cutoff.astimezone(UTC)
    for raw in raw_bars or []:
        timestamp = _parse_dt(raw.get("t"))
        close = _finite(raw.get("c"))
        if timestamp is None or timestamp > cutoff or close is None or close <= 0:
            continue
        high = _finite(raw.get("h"), close) or close
        low = _finite(raw.get("l"), close) or close
        if high < low or high <= 0 or low <= 0:
            continue
        by_time[timestamp] = {
            "t": timestamp,
            "o": _finite(raw.get("o"), close) or close,
            "h": high,
            "l": low,
            "c": close,
            "v": max(0.0, _finite(raw.get("v"), 0.0) or 0.0),
            "vw": _finite(raw.get("vw"), close) or close,
            "n": max(0.0, _finite(raw.get("n"), 0.0) or 0.0),
        }
    bars = [by_time[key] for key in sorted(by_time)]
    if len(bars) < 2:
        return bars, 1.0
    expected = max(1, int(round((bars[-1]["t"] - bars[0]["t"]).total_seconds() / 60.0)) + 1)
    gap_ratio = _clip(1.0 - len(bars) / expected, 0.0, 1.0)
    return bars, gap_ratio


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
    """Return a validated, executable SIP snapshot or reject it at the hard gate."""
    previous = snapshot.get("prevDailyBar") or {}
    daily = snapshot.get("dailyBar") or {}
    minute = snapshot.get("minuteBar") or {}
    trade = snapshot.get("latestTrade") or {}
    quote = snapshot.get("latestQuote") or {}

    last_price = _finite(trade.get("p"), _finite(minute.get("c"), _finite(daily.get("c"))))
    bid = _finite(quote.get("bp"))
    ask = _finite(quote.get("ap"))
    prev_close = _finite(previous.get("c"))
    previous_volume = _finite(previous.get("v"), 0.0) or 0.0
    current_volume = _finite(daily.get("v"), 0.0) or 0.0

    if not symbol or last_price is None or last_price < min_price or prev_close is None or prev_close <= 0:
        return None
    if bid is None or ask is None or bid <= 0 or ask <= bid:
        return None
    midpoint = (bid + ask) / 2.0
    spread_bps = (ask - bid) / midpoint * 10_000.0
    if not math.isfinite(spread_bps) or spread_bps <= 0 or spread_bps > max_spread_bps:
        return None

    quote_age = _age_seconds(quote.get("t"), evidence_cutoff)
    trade_age = _age_seconds(trade.get("t"), evidence_cutoff)
    if quote_age is None or quote_age > max_quote_age_seconds:
        return None
    if trade_age is None or trade_age > max(max_quote_age_seconds * 1.5, 240.0):
        return None
    if abs(last_price - midpoint) / midpoint > max(0.03, spread_bps / 10_000.0 * 20.0):
        return None

    prev_dollar_volume = previous_volume * prev_close
    current_dollar_volume = current_volume * last_price
    if prev_dollar_volume < min_prev_dollar_volume or current_dollar_volume < min_current_dollar_volume:
        return None

    elapsed = _clip(float(elapsed_minutes or 1.0), 1.0, 390.0)
    expected_volume = previous_volume * elapsed / 390.0
    relative_volume_pace = current_volume / expected_volume if expected_volume > 0 else 0.0

    return {
        "symbol": str(symbol).upper(),
        "name": str(asset.get("name") or symbol),
        "exchange": str(asset.get("exchange") or ""),
        "last_price": last_price,
        "bid": bid,
        "ask": ask,
        "spread_bps": spread_bps,
        "prev_close": prev_close,
        "day_move_pct": _pct(last_price, prev_close),
        "prev_dollar_volume": prev_dollar_volume,
        "current_dollar_volume": current_dollar_volume,
        "relative_volume_pace": relative_volume_pace,
        "quote_age_seconds": quote_age,
        "trade_age_seconds": trade_age,
        "day_high": _finite(daily.get("h"), last_price) or last_price,
        "day_low": _finite(daily.get("l"), last_price) or last_price,
        "day_trade_count": max(0.0, _finite(daily.get("n"), 0.0) or 0.0),
        "evidence_cutoff": evidence_cutoff.astimezone(UTC),
    }


def benchmark_returns(raw_bars: list[dict[str, Any]], *, evidence_cutoff: datetime) -> dict[str, float]:
    bars, gap_ratio = _clean_bars(raw_bars, evidence_cutoff)
    closes = [bar["c"] for bar in bars]
    log_returns = [_log_return(closes[index], closes[index - 1]) for index in range(1, len(closes))]
    return {
        "return_5m_pct": _window_return(closes, 5),
        "return_15m_pct": _window_return(closes, 15),
        "return_30m_pct": _window_return(closes, 30),
        "return_60m_pct": _window_return(closes, 60),
        "realized_vol_1m_pct": _robust_stdev(log_returns[-60:]) * 100.0,
        "gap_ratio": gap_ratio,
    }


def _trend_efficiency(closes: list[float], window: int) -> float:
    if len(closes) <= window:
        return 0.0
    values = closes[-window - 1 :]
    path = sum(abs(values[index] - values[index - 1]) for index in range(1, len(values)))
    return abs(values[-1] - values[0]) / path if path > 0 else 0.0


def _direction_consistency(closes: list[float], window: int) -> float:
    if len(closes) <= 2:
        return 0.5
    values = closes[-min(window + 1, len(closes)) :]
    moves = [values[index] - values[index - 1] for index in range(1, len(values))]
    nonzero = [move for move in moves if move != 0]
    if not nonzero:
        return 0.5
    return sum(move > 0 for move in nonzero) / len(nonzero)


def _ratio_recent_prior(values: list[float], recent: int = 10, prior: int = 20) -> float:
    if len(values) < recent + max(5, prior // 2):
        return 1.0
    recent_mean = _mean(values[-recent:])
    prior_mean = _mean(values[-recent - prior : -recent])
    return recent_mean / prior_mean if prior_mean > 0 else 1.0


def build_market_features(
    *,
    liquidity_record: dict[str, Any],
    raw_bars: list[dict[str, Any]],
    benchmark_returns: dict[str, float],
    evidence_cutoff: datetime,
) -> dict[str, Any] | None:
    bars, gap_ratio = _clean_bars(raw_bars, evidence_cutoff)
    if len(bars) < MIN_BARS or gap_ratio > MAX_BAR_GAP_RATIO:
        return None

    closes = [bar["c"] for bar in bars]
    highs = [bar["h"] for bar in bars]
    lows = [bar["l"] for bar in bars]
    volumes = [bar["v"] for bar in bars]
    trades = [bar["n"] for bar in bars]
    log_returns = [_log_return(closes[index], closes[index - 1]) for index in range(1, len(closes))]
    robust_vol = _robust_stdev(log_returns[-60:])
    realized_vol_1m_pct = robust_vol * 100.0
    vol_capacity = robust_vol * math.sqrt(120.0) * 100.0
    ranges_pct = [(high - low) / close * 100.0 for high, low, close in zip(highs, lows, closes) if close > 0]
    median_range = median(ranges_pct[-30:]) if ranges_pct else 0.0
    move_capacity = _clip(max(0.08, vol_capacity, median_range * math.sqrt(120.0 / 1.8)), 0.08, 12.0)

    total_volume = sum(volumes)
    vwap = sum((bar["vw"] if bar["vw"] > 0 else bar["c"]) * bar["v"] for bar in bars) / total_volume if total_volume > 0 else closes[-1]
    vwap_distance_pct = _pct(closes[-1], vwap)
    return_5 = _window_return(closes, 5)
    return_15 = _window_return(closes, 15)
    return_30 = _window_return(closes, 30)
    return_60 = _window_return(closes, 60)
    relative_5 = return_5 - float(benchmark_returns.get("return_5m_pct", 0.0) or 0.0)
    relative_15 = return_15 - float(benchmark_returns.get("return_15m_pct", 0.0) or 0.0)
    relative_30 = return_30 - float(benchmark_returns.get("return_30m_pct", 0.0) or 0.0)
    relative_60 = return_60 - float(benchmark_returns.get("return_60m_pct", 0.0) or 0.0)

    last_30_high = max(highs[-min(30, len(highs)) :])
    last_30_low = min(lows[-min(30, len(lows)) :])
    range_position = (closes[-1] - last_30_low) / (last_30_high - last_30_low) if last_30_high > last_30_low else 0.5
    data_quality = _score(100.0 - gap_ratio * 180.0 - max(0.0, 60.0 - len(bars)) * 0.35 - (8.0 if total_volume <= 0 else 0.0) - (5.0 if sum(trades) <= 0 else 0.0))

    result = dict(liquidity_record)
    result.update({
        "return_5m_pct": return_5,
        "return_15m_pct": return_15,
        "return_30m_pct": return_30,
        "return_60m_pct": return_60,
        "relative_return_5m_pct": relative_5,
        "relative_return_15m_pct": relative_15,
        "relative_return_30m_pct": relative_30,
        "relative_return_60m_pct": relative_60,
        "vwap": vwap,
        "vwap_distance_pct": vwap_distance_pct,
        "move_capacity_120m_pct": move_capacity,
        "realized_vol_1m_pct": realized_vol_1m_pct,
        "median_range_1m_pct": median_range,
        "trend_efficiency_30": _trend_efficiency(closes, 30),
        "trend_efficiency_60": _trend_efficiency(closes, 60),
        "positive_consistency_30": _direction_consistency(closes, 30),
        "volume_acceleration": _clip(_ratio_recent_prior(volumes), 0.0, 10.0),
        "trade_acceleration": _clip(_ratio_recent_prior(trades), 0.0, 10.0),
        "range_position_30": range_position,
        "bar_gap_ratio": gap_ratio,
        "bars_used": len(bars),
        "data_quality_score": data_quality,
    })
    return result


def _liquidity_score(record: dict[str, Any]) -> float:
    prev_dv = max(1.0, float(record.get("prev_dollar_volume") or 1.0))
    current_dv = max(1.0, float(record.get("current_dollar_volume") or 1.0))
    spread = max(0.0, float(record.get("spread_bps") or 999.0))
    pace = max(0.0, float(record.get("relative_volume_pace") or 0.0))
    scale = _clip((math.log10(prev_dv) - 7.0) / 2.3, 0.0, 1.0)
    current_scale = _clip((math.log10(current_dv) - 6.0) / 2.5, 0.0, 1.0)
    spread_score = _clip(1.0 - spread / 30.0, 0.0, 1.0)
    pace_score = _clip(math.log1p(pace) / math.log(4.0), 0.0, 1.0)
    return _score(100.0 * (0.34 * scale + 0.24 * current_scale + 0.28 * spread_score + 0.14 * pace_score))


def _cost_estimate_bps(record: dict[str, Any]) -> float:
    spread = max(0.1, float(record.get("spread_bps") or 0.1))
    vol = max(0.0, float(record.get("realized_vol_1m_pct") or 0.0))
    pace = max(0.1, float(record.get("relative_volume_pace") or 0.1))
    liquidity_relief = _clip(math.log1p(pace) / 5.0, 0.0, 0.22)
    slippage = max(1.0, spread * (0.22 - liquidity_relief) + vol * 8.0)
    return spread + slippage


def _setup_scores(record: dict[str, Any], direction: int, setup_type: str) -> tuple[float, float, list[str]]:
    ret5 = direction * float(record.get("return_5m_pct") or 0.0)
    ret15 = direction * float(record.get("return_15m_pct") or 0.0)
    ret30 = direction * float(record.get("return_30m_pct") or 0.0)
    ret60 = direction * float(record.get("return_60m_pct") or 0.0)
    rel15 = direction * float(record.get("relative_return_15m_pct") or 0.0)
    vwap = direction * float(record.get("vwap_distance_pct") or 0.0)
    capacity = max(0.1, float(record.get("move_capacity_120m_pct") or 0.1))
    consistency = float(record.get("positive_consistency_30") or 0.5)
    consistency = consistency if direction > 0 else 1.0 - consistency
    trend_eff = 0.6 * float(record.get("trend_efficiency_30") or 0.0) + 0.4 * float(record.get("trend_efficiency_60") or 0.0)
    range_position = float(record.get("range_position_30") or 0.5)
    range_position = range_position if direction > 0 else 1.0 - range_position
    volume_accel = float(record.get("volume_acceleration") or 1.0)
    trade_accel = float(record.get("trade_acceleration") or 1.0)
    reasons: list[str] = []

    if setup_type == "CONTINUATION":
        directional = 50.0 + 18.0 * math.tanh(ret15 / max(0.12, capacity * 0.30)) + 14.0 * math.tanh(ret30 / max(0.18, capacity * 0.50)) + 8.0 * math.tanh(ret60 / max(0.25, capacity * 0.75)) + 7.0 * math.tanh(rel15 / max(0.10, capacity * 0.25))
        confirmation = 28.0 + 30.0 * consistency + 23.0 * trend_eff + 12.0 * range_position + 5.0 * math.tanh(vwap / max(0.08, capacity * 0.20)) + 4.0 * math.tanh((volume_accel - 1.0) / 0.8) + 3.0 * math.tanh((trade_accel - 1.0) / 0.8)
        if ret5 < -0.10:
            confirmation -= 12.0
            reasons.append("five-minute momentum has turned against continuation")
        if ret30 <= 0 or ret15 <= 0:
            confirmation -= 18.0
            reasons.append("multi-horizon directional agreement is incomplete")
    else:
        prior_move = max(-ret30, -ret60 * 0.8)
        turn = ret5
        directional = 34.0 + 29.0 * math.tanh(prior_move / max(0.20, capacity * 0.55)) + 25.0 * math.tanh(turn / max(0.08, capacity * 0.18)) + 8.0 * math.tanh((-vwap) / max(0.10, capacity * 0.30))
        confirmation = 35.0 + 20.0 * (1.0 - trend_eff) + 14.0 * (1.0 - range_position) + 16.0 * math.tanh((volume_accel - 1.0) / 0.9)
        if prior_move <= 0.20 or turn <= 0.0:
            directional -= 35.0
            confirmation -= 30.0
            reasons.append("reversion lacks both a material prior move and a confirmed five-minute turn")
        if ret15 > max(0.35, capacity * 0.35):
            confirmation -= 10.0
            reasons.append("the reversal may already be substantially consumed")

    return _score(directional), _score(confirmation), reasons


def rank_market_records(records: list[dict[str, Any]], *, direction_filter: str = "both") -> list[dict[str, Any]]:
    allowed = {"LONG", "SHORT"}
    if direction_filter == "long":
        allowed = {"LONG"}
    elif direction_filter == "short":
        allowed = {"SHORT"}

    ranked: list[dict[str, Any]] = []
    for record in records:
        if not record:
            continue
        liquidity = _liquidity_score(record)
        cost_bps = _cost_estimate_bps(record)
        capacity = max(0.0, float(record.get("move_capacity_120m_pct") or 0.0))
        cost_pct = cost_bps / 100.0
        edge_to_cost = capacity / cost_pct if cost_pct > 0 else 0.0
        data_quality = float(record.get("data_quality_score") or 0.0)
        volume_pace = max(0.0, float(record.get("relative_volume_pace") or 0.0))
        opportunity = _score(28.0 + 29.0 * math.tanh(capacity / 1.15) + 24.0 * math.tanh((edge_to_cost - 3.0) / 6.0) + 10.0 * math.tanh((volume_pace - 1.0) / 1.5) + 9.0 * (data_quality / 100.0))
        execution = _score(0.48 * liquidity + 0.32 * data_quality + 20.0 * _clip((edge_to_cost - 2.0) / 10.0, 0.0, 1.0))

        candidates: list[dict[str, Any]] = []
        for direction_name, sign in (("LONG", 1), ("SHORT", -1)):
            if direction_name not in allowed:
                continue
            for setup_type in ("CONTINUATION", "REVERSION"):
                directional, confirmation, reasons = _setup_scores(record, sign, setup_type)
                penalties: list[tuple[str, float]] = []
                chase_ratio = abs(float(record.get("return_5m_pct") or 0.0)) / max(0.08, capacity)
                vwap_sigma = abs(float(record.get("vwap_distance_pct") or 0.0)) / max(0.08, capacity / math.sqrt(2.0))
                if edge_to_cost < 4.0:
                    penalties.append(("two-hour move capacity is too small relative to estimated costs", (4.0 - edge_to_cost) * 4.0))
                if data_quality < 88.0:
                    penalties.append(("minute-bar completeness is below the preferred threshold", (88.0 - data_quality) * 0.30))
                if chase_ratio > 0.65:
                    penalties.append(("the latest five-minute move consumes too much of estimated two-hour capacity", (chase_ratio - 0.65) * 26.0))
                if vwap_sigma > 2.4 and setup_type == "CONTINUATION":
                    penalties.append(("price is unusually extended from VWAP", (vwap_sigma - 2.4) * 5.0))
                benchmark_30 = sign * float(record.get("return_30m_pct", 0.0) or 0.0) - sign * float(record.get("relative_return_30m_pct", 0.0) or 0.0)
                if setup_type == "CONTINUATION" and benchmark_30 < -0.20:
                    penalties.append(("the broad-market regime opposes the continuation direction", min(10.0, abs(benchmark_30) * 5.0)))
                penalty_total = sum(value for _, value in penalties)
                raw_score = 0.30 * directional + 0.22 * confirmation + 0.20 * opportunity + 0.16 * liquidity + 0.12 * execution - penalty_total
                candidates.append({"direction": direction_name, "setup_type": setup_type, "directional_score": directional, "confirmation_score": confirmation, "penalties": penalties, "penalty_total": penalty_total, "raw_score": _score(raw_score), "reasons": reasons, "chase_ratio": chase_ratio, "vwap_sigma": vwap_sigma})

        candidates.sort(key=lambda row: row["raw_score"], reverse=True)
        if not candidates:
            continue
        best = candidates[0]
        runner_up = candidates[1]["raw_score"] if len(candidates) > 1 else 0.0
        setup_margin = best["raw_score"] - runner_up
        ambiguity_penalty = max(0.0, 4.0 - setup_margin) * 1.5
        profitability = _score(best["raw_score"] - ambiguity_penalty)
        penalty_labels = [reason for reason, _ in best["penalties"]] + list(best["reasons"])

        if profitability >= 76.0 and data_quality >= 90.0 and edge_to_cost >= 5.0 and setup_margin >= 2.0:
            initial_view = "INVESTIGATE"
        elif profitability >= 62.0:
            initial_view = "WATCH"
        else:
            initial_view = "PASS"

        direction_word = "upward" if best["direction"] == "LONG" else "downward"
        rationale = f"{best['setup_type'].title()} setup with {direction_word} multi-horizon structure; liquidity {liquidity:.0f}/100, data quality {data_quality:.0f}/100, estimated round-trip cost {cost_bps:.1f} bps and capacity/cost {edge_to_cost:.1f}x."
        if penalty_labels:
            rationale += " Cautions: " + "; ".join(dict.fromkeys(penalty_labels[:3])) + "."

        output = dict(record)
        output.update({
            "direction": best["direction"],
            "setup_type": best["setup_type"],
            "cost_estimate_bps": cost_bps,
            "liquidity_score": liquidity,
            "opportunity_score": opportunity,
            "directional_score": best["directional_score"],
            "confirmation_score": best["confirmation_score"],
            "execution_score": execution,
            "profitability_score": profitability,
            "initial_view": initial_view,
            "rationale": rationale,
            "evidence": {
                "scoring_version": SCORING_VERSION,
                "bars_used": int(record.get("bars_used") or 0),
                "bar_gap_ratio": float(record.get("bar_gap_ratio") or 0.0),
                "data_quality_score": data_quality,
                "edge_to_cost_ratio": edge_to_cost,
                "setup_margin": setup_margin,
                "ambiguity_penalty": ambiguity_penalty,
                "penalty_total": best["penalty_total"] + ambiguity_penalty,
                "penalties": penalty_labels,
                "chase_ratio": best["chase_ratio"],
                "vwap_sigma": best["vwap_sigma"],
                "relative_return_5m_pct": float(record.get("relative_return_5m_pct") or 0.0),
                "relative_return_30m_pct": float(record.get("relative_return_30m_pct") or 0.0),
                "relative_return_60m_pct": float(record.get("relative_return_60m_pct") or 0.0),
                "trend_efficiency_30": float(record.get("trend_efficiency_30") or 0.0),
                "positive_consistency_30": float(record.get("positive_consistency_30") or 0.5),
                "volume_acceleration": float(record.get("volume_acceleration") or 1.0),
                "trade_acceleration": float(record.get("trade_acceleration") or 1.0),
            },
        })
        ranked.append(output)

    ranked.sort(key=lambda row: (float(row.get("profitability_score") or 0.0), float(row.get("execution_score") or 0.0), float(row.get("prev_dollar_volume") or 0.0)), reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked
