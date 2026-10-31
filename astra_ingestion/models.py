"""Immutable and bounded admission contract for the first ingestion path."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping

UTC = timezone.utc
WINDOW_START = datetime(2025, 9, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 1, tzinfo=UTC)
TIMEFRAMES = frozenset({"1Min", "5Min", "15Min", "1Hour"})
SYMBOL_PATTERN = re.compile(r"[A-Z][A-Z0-9.\-]{0,19}\Z")


def parse_timestamp(value: datetime | str) -> datetime:
    if isinstance(value, str):
        # datetime supports microseconds. Reject precision loss instead of
        # silently turning distinct provider timestamps into the same key.
        fraction = re.search(r"[Tt ]\d{2}:\d{2}:\d{2}[.,](\d+)", value)
        if fraction and len(fraction[1]) > 6 and any(c != "0" for c in fraction[1][6:]):
            raise ValueError("Timestamp has unsupported sub-microsecond precision")
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Timestamp must be an ISO 8601 datetime") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include an explicit UTC offset")
    return value.astimezone(UTC)


def canonical_timestamp(value: datetime | str) -> str:
    value = parse_timestamp(value)
    precision = "microseconds" if value.microsecond else "seconds"
    return value.isoformat(timespec=precision).replace("+00:00", "Z")


def _bounded_integer(name: str, value: Any, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")


@dataclass(frozen=True)
class IngestionSpec:
    symbols: tuple[str, ...]
    start: datetime
    end: datetime
    name: str = "ASTRA ingestion"
    timeframe: str = "5Min"
    feed: str = "sip"
    adjustment: str = "raw"
    max_requests: int = 50
    max_records: int = 50_000
    deadline_seconds: int = 1_800

    def __post_init__(self) -> None:
        if not isinstance(self.symbols, (tuple, list)):
            raise ValueError("symbols must be an explicit list")
        symbols = tuple(self.symbols)
        if not 1 <= len(symbols) <= 10:
            raise ValueError("Select between one and ten explicit symbols")
        if any(not isinstance(s, str) or not SYMBOL_PATTERN.fullmatch(s) for s in symbols):
            raise ValueError("Every symbol must be valid uppercase text")
        if len(set(symbols)) != len(symbols):
            raise ValueError("Duplicate symbols are not allowed")
        object.__setattr__(self, "symbols", symbols)
        start, end = parse_timestamp(self.start), parse_timestamp(self.end)
        if not WINDOW_START <= start < end <= WINDOW_END:
            raise ValueError("Scope must be inside 2025-09-01 through 2026-07-31, with an exclusive end")
        if end - start > timedelta(days=7):
            raise ValueError("The first-release workload is limited to seven days")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        if not isinstance(self.name, str) or not 1 <= len(self.name.strip()) <= 120:
            raise ValueError("name must contain between one and 120 characters")
        if any(ord(c) < 32 for c in self.name):
            raise ValueError("name cannot contain control characters")
        if not isinstance(self.timeframe, str) or self.timeframe not in TIMEFRAMES:
            raise ValueError("Supported timeframes are 1Min, 5Min, 15Min and 1Hour")
        if self.feed != "sip" or self.adjustment != "raw":
            raise ValueError("This admitted path requires SIP with raw adjustment")
        _bounded_integer("max_requests", self.max_requests, 1, 200)
        _bounded_integer("max_records", self.max_records, 1, 100_000)
        _bounded_integer("deadline_seconds", self.deadline_seconds, 30, 7_200)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IngestionSpec":
        if not isinstance(value, Mapping):
            raise ValueError("spec must be an object")
        allowed = {field.name for field in fields(cls)}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError("Unknown spec fields: " + ", ".join(sorted(map(str, unknown))))
        missing = {"symbols", "start", "end"} - set(value)
        if missing:
            raise ValueError("Missing spec fields: " + ", ".join(sorted(missing)))
        return cls(**dict(value))

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["symbols"] = list(self.symbols)
        result["start"] = canonical_timestamp(self.start)
        result["end"] = canonical_timestamp(self.end)
        return result

    @property
    def scope_hash(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def plan_partitions(spec: IngestionSpec) -> list[dict[str, str]]:
    """Preserve every admitted symbol and cover the interval without overlap."""
    partitions: list[dict[str, str]] = []
    for symbol in spec.symbols:
        cursor = spec.start
        while cursor < spec.end:
            end = min(cursor + timedelta(days=1), spec.end)
            partitions.append({"symbol": symbol, "start": canonical_timestamp(cursor), "end": canonical_timestamp(end)})
            cursor = end
    return partitions
