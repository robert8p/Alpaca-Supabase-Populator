from __future__ import annotations

import math
import re
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.models import JobConfig

NY = ZoneInfo("America/New_York")


def classify_session(ts: datetime) -> str:
    local_time = ts.astimezone(NY).time().replace(tzinfo=None)
    if time(4, 0) <= local_time < time(9, 30):
        return "premarket"
    if time(9, 30) <= local_time < time(16, 0):
        return "regular"
    if time(16, 0) <= local_time < time(20, 0):
        return "postmarket"
    return "overnight"


def in_selected_session(ts: datetime, config: JobConfig) -> bool:
    local = ts.astimezone(NY)
    if config.session.weekdays_only and local.weekday() >= 5:
        return False
    local_time = local.time().replace(tzinfo=None)
    mode = config.session.mode
    if mode == "all":
        return True
    if mode == "regular":
        return time(9, 30) <= local_time < time(16, 0)
    if mode == "extended":
        return time(4, 0) <= local_time < time(20, 0)
    start = config.session.custom_start
    end = config.session.custom_end
    if start < end:
        return start <= local_time < end
    if start > end:
        return local_time >= start or local_time < end
    return True


def filter_assets(assets: list[dict[str, Any]], config: JobConfig) -> list[dict[str, Any]]:
    universe = config.universe
    if universe.mode == "explicit":
        wanted = set(universe.symbols)
        selected = [a for a in assets if str(a.get("symbol", "")).upper() in wanted]
        missing = wanted - {str(a.get("symbol", "")).upper() for a in selected}
        selected.extend({"symbol": symbol, "status": "requested", "class": "us_equity"} for symbol in sorted(missing))
        return sorted(selected, key=lambda a: str(a.get("symbol", "")))

    exchanges = {x.upper() for x in universe.exchanges}
    include_re = re.compile(universe.include_regex) if universe.include_regex else None
    exclude_re = re.compile(universe.exclude_regex) if universe.exclude_regex else None
    selected: list[dict[str, Any]] = []

    for asset in assets:
        symbol = str(asset.get("symbol", "")).upper()
        exchange = str(asset.get("exchange", "")).upper()
        if not symbol:
            continue
        if exchanges and exchange not in exchanges:
            continue
        if universe.tradable_only and asset.get("tradable") is not True:
            continue
        if universe.fractionable_only and asset.get("fractionable") is not True:
            continue
        if universe.marginable_only and asset.get("marginable") is not True:
            continue
        if universe.shortable_only and asset.get("shortable") is not True:
            continue
        if universe.easy_to_borrow_only:
            borrow_status = str(asset.get("borrow_status") or "").lower()
            if asset.get("easy_to_borrow") is not True and borrow_status not in {"easy", "easy_to_borrow", "etb"}:
                continue
        if universe.overnight_tradable_only and "overnight_tradable" not in (asset.get("attributes") or []):
            continue
        if include_re and not include_re.search(symbol):
            continue
        if exclude_re and exclude_re.search(symbol):
            continue
        selected.append(asset)

    selected.sort(key=lambda a: str(a.get("symbol", "")))
    if universe.symbol_limit:
        selected = selected[: universe.symbol_limit]
    return selected


def timeframe_minutes(timeframe: str) -> int:
    if timeframe.endswith("Min"):
        return int(timeframe[:-3])
    if timeframe.endswith("Hour"):
        return int(timeframe[:-4]) * 60
    return 1440


def session_minutes(config: JobConfig) -> int:
    mode = config.session.mode
    if mode == "regular":
        return 390
    if mode == "extended":
        return 960
    if mode == "all":
        return 1440
    start = config.session.custom_start.hour * 60 + config.session.custom_start.minute
    end = config.session.custom_end.hour * 60 + config.session.custom_end.minute
    return (end - start) % 1440 or 1440


def estimate_for(config: JobConfig, symbol_count: int) -> dict[str, Any]:
    days = (config.end_date - config.start_date).days + 1
    weekdays = sum(1 for i in range(days) if (config.start_date + timedelta(days=i)).weekday() < 5)
    active_days = weekdays if config.session.weekdays_only else days
    bars_per_symbol = sum(math.ceil(session_minutes(config) / timeframe_minutes(tf)) for tf in config.timeframes) * active_days
    estimated_rows = symbol_count * bars_per_symbol
    batches = math.ceil(symbol_count / config.performance.symbol_batch_size) if symbol_count else 0
    windows = math.ceil(days / config.performance.date_chunk_days)
    task_count = batches * windows * len(config.timeframes)
    estimated_uncompressed_bytes = estimated_rows * 110
    return {
        "symbol_count": symbol_count,
        "active_days": active_days,
        "estimated_rows": estimated_rows,
        "estimated_uncompressed_gb": round(estimated_uncompressed_bytes / 1_000_000_000, 2),
        "estimated_compressed_staging_gb": round(estimated_uncompressed_bytes * 0.24 / 1_000_000_000, 2),
        "task_count": task_count,
        "note": "Estimate assumes one bar per selected interval during the chosen session; illiquid symbols and holidays reduce actual rows.",
    }
