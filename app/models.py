from __future__ import annotations

import re
from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TIMEFRAME_RE = re.compile(r"^(?:[1-9]|[1-5][0-9])Min$|^(?:[1-9]|1[0-9]|2[0-3])Hour$|^1Day$")
SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]+$")


class UniverseConfig(BaseModel):
    mode: Literal["all_active", "all_known", "explicit"] = "all_active"
    symbols: list[str] = Field(default_factory=list)
    exchanges: list[str] = Field(default_factory=lambda: ["NYSE", "NASDAQ", "AMEX", "ARCA", "BATS", "NYSEARCA"])
    tradable_only: bool = True
    fractionable_only: bool = False
    marginable_only: bool = False
    shortable_only: bool = False
    easy_to_borrow_only: bool = False
    overnight_tradable_only: bool = False
    include_regex: str | None = None
    exclude_regex: str | None = r"[/]"
    symbol_limit: int | None = Field(default=None, ge=1, le=20000)

    @field_validator("symbols")
    @classmethod
    def normalise_symbols(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for item in value:
            for symbol in re.split(r"[\s,;]+", item.strip().upper()):
                if symbol and SYMBOL_RE.match(symbol) and symbol not in out:
                    out.append(symbol)
        return out

    @model_validator(mode="after")
    def explicit_requires_symbols(self):
        if self.mode == "explicit" and not self.symbols:
            raise ValueError("Explicit universe requires at least one valid symbol")
        for pattern in (self.include_regex, self.exclude_regex):
            if pattern:
                re.compile(pattern)
        return self


class SessionConfig(BaseModel):
    mode: Literal["regular", "extended", "all", "custom"] = "regular"
    custom_start: time = time(9, 30)
    custom_end: time = time(16, 0)
    weekdays_only: bool = True


class PerformanceConfig(BaseModel):
    symbol_batch_size: int = Field(default=20, ge=1, le=100)
    date_chunk_days: int = Field(default=5, ge=1, le=90)
    page_limit: int = Field(default=10000, ge=100, le=10000)
    concurrency: int = Field(default=6, ge=1, le=30)
    target_rpm: int = Field(default=9000, ge=60, le=10000)
    max_retries: int = Field(default=7, ge=1, le=20)
    retry_backoff_seconds: float = Field(default=1.5, ge=0.2, le=30)


class StorageConfig(BaseModel):
    conflict_policy: Literal["skip", "update"] = "skip"
    keep_staging_files: bool = False
    generate_daily_features: bool = True
    feature_session: Literal["regular", "premarket", "postmarket", "overnight", "all"] = "regular"


class JobConfig(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    start_date: date
    end_date: date
    timeframes: list[str] = Field(default_factory=lambda: ["5Min"])
    feed: Literal["sip", "iex", "boats", "otc"] = "sip"
    adjustment: Literal["raw", "split", "dividend", "all"] = "raw"
    asof: date | None = None
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @field_validator("timeframes")
    @classmethod
    def validate_timeframes(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        for timeframe in value:
            tf = timeframe.strip()
            if not TIMEFRAME_RE.match(tf):
                raise ValueError(f"Unsupported timeframe: {tf}")
            if tf not in unique:
                unique.append(tf)
        if not unique:
            raise ValueError("Select at least one timeframe")
        return unique

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        if (self.end_date - self.start_date).days > 3650:
            raise ValueError("A single job is limited to ten years")
        if self.feed == "boats" and self.session.mode == "regular":
            raise ValueError("BOATS is an overnight feed; choose all, custom or an overnight session")
        return self


class EstimateRequest(BaseModel):
    config: JobConfig


class JobCreateRequest(BaseModel):
    config: JobConfig
