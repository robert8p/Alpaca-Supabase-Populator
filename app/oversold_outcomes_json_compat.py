from __future__ import annotations

"""Defensive JSON normalization for Oversold outcome metadata and raw bars."""

from typing import Any

from app.oversold_sec_json_compat import json_safe


def patch_module(module: Any) -> None:
    if getattr(module, "_json_safe_outcomes_installed", False):
        return
    original_jsonb = module.Jsonb

    def safe_jsonb(value: Any):
        return original_jsonb(json_safe(value))

    module.Jsonb = safe_jsonb
    module._json_safe_outcomes_installed = True
