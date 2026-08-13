from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

SEED = 20260813
BLOCK_LENGTH = 5
REPLICATIONS = 20_000


def circular_block_indices(n: int, block_length: int, replications: int, seed: int) -> np.ndarray:
    if n <= 0:
        raise ValueError("n must be positive")
    if block_length <= 0:
        raise ValueError("block_length must be positive")
    rng = np.random.Generator(np.random.PCG64(seed))
    blocks_needed = math.ceil(n / block_length)
    starts = rng.integers(0, n, size=(replications, blocks_needed))
    offsets = np.arange(block_length)
    indices = (starts[:, :, None] + offsets[None, None, :]) % n
    return indices.reshape(replications, -1)[:, :n]


def bootstrap_candidate(values: list[float]) -> dict[str, float | int]:
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or x.size < 2 or not np.isfinite(x).all():
        raise ValueError("Each candidate must contain at least two finite ordered returns")

    indices = circular_block_indices(x.size, BLOCK_LENGTH, REPLICATIONS, SEED)
    bootstrap_means = x[indices].mean(axis=1)
    observed_mean = float(x.mean())
    centred = x - observed_mean
    null_means = centred[indices].mean(axis=1)

    ci_low, ci_high = np.quantile(bootstrap_means, [0.025, 0.975], method="linear")
    p_value = (1 + int(np.count_nonzero(null_means >= observed_mean))) / (REPLICATIONS + 1)

    return {
        "n": int(x.size),
        "mean": observed_mean,
        "bootstrap_ci_low": float(ci_low),
        "bootstrap_ci_high": float(ci_high),
        "bootstrap_p_value": float(p_value),
        "bootstrap_mean": float(bootstrap_means.mean()),
        "bootstrap_standard_deviation": float(bootstrap_means.std(ddof=1)),
    }


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    p = np.asarray(p_values, dtype=float)
    if p.ndim != 1 or p.size == 0 or not np.isfinite(p).all():
        raise ValueError("p_values must be a non-empty finite vector")
    order = np.argsort(p)
    sorted_p = p[order]
    raw = sorted_p * p.size / np.arange(1, p.size + 1)
    monotone = np.minimum.accumulate(raw[::-1])[::-1]
    adjusted = np.empty_like(monotone)
    adjusted[order] = np.minimum(monotone, 1.0)
    return [float(v) for v in adjusted]


def analyse(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        raise ValueError("Input mapping is empty")
    ordered_ids = sorted(payload)
    output = {candidate_id: bootstrap_candidate(payload[candidate_id]) for candidate_id in ordered_ids}
    q_values = benjamini_hochberg([output[candidate_id]["bootstrap_p_value"] for candidate_id in ordered_ids])
    for candidate_id, q_value in zip(ordered_ids, q_values, strict=True):
        output[candidate_id]["bh_q_value"] = q_value
    return {
        "method": {
            "generator": "NumPy PCG64",
            "seed": SEED,
            "block_length": BLOCK_LENGTH,
            "replications": REPLICATIONS,
            "interval": "uncentred circular moving-block percentile 95%",
            "p_value": "one-sided centred circular moving-block bootstrap",
            "multiplicity": "Benjamini-Hochberg across all supplied definitions",
        },
        "candidates": output,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", help="JSON file mapping candidate IDs to ordered return arrays; stdin if omitted")
    parser.add_argument("--output", help="Optional output JSON path")
    args = parser.parse_args()

    if args.input:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        payload = json.load(sys.stdin)

    result = analyse(payload)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
