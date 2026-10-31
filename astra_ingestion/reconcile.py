"""Exact, bounded-report comparison of retained source rows and target rows."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from .source import record_key


def _index(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Every reconciliation record must be an object")
        key = record_key(row)
        if key in indexed:
            duplicates.append(key)
        else:
            indexed[key] = row
    return indexed, duplicates


def _digest(index: dict[str, dict[str, Any]]) -> str:
    text = json.dumps([index[key] for key in sorted(index)], sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compare_records(expected: Iterable[dict[str, Any]], actual: Iterable[dict[str, Any]]) -> dict[str, Any]:
    source, source_duplicates = _index(expected)
    target, target_duplicates = _index(actual)
    missing = sorted(source.keys() - target.keys())
    unexpected = sorted(target.keys() - source.keys())
    changed = sorted(key for key in source.keys() & target.keys() if source[key] != target[key])
    passed = not (missing or unexpected or changed or source_duplicates or target_duplicates)
    return {
        "status": "passed" if passed else "failed",
        "expected_count": len(source), "actual_count": len(target),
        "expected_hash": _digest(source), "actual_hash": _digest(target),
        "missing_count": len(missing), "changed_count": len(changed), "unexpected_count": len(unexpected),
        "expected_duplicate_count": len(source_duplicates), "actual_duplicate_count": len(target_duplicates),
        "missing_keys": missing[:20], "changed_keys": changed[:20], "unexpected_keys": unexpected[:20],
        "expected_duplicate_keys": source_duplicates[:20], "actual_duplicate_keys": target_duplicates[:20],
    }
