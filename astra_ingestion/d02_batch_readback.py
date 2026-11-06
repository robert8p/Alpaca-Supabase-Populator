"""Compare a batch destination read with independently retained August 4 source rows."""
import argparse
import json
from pathlib import Path
from uuid import UUID

from .aug_d02_pilot import (
    COHORT_SHA, MANIFEST_KEYS, MEMBER_KEYS, SOURCE_SHA, TRADE_DATE, VERIFIER_ROLE,
    canonical, number, parse, require, sha, source_values,
)


def verify(manifest_bytes, approved_sha, attempt, first_rank, projection, rows):
    require(sha(manifest_bytes) == approved_sha, "Manifest differs from the approved bytes")
    manifest = parse(manifest_bytes)
    require(isinstance(manifest, dict) and set(manifest) == MANIFEST_KEYS
            and (manifest["schema"], manifest["date"], manifest["cohort_sha256"], manifest["source_sha256"])
            == ("astra-d02-batch/v1", TRADE_DATE, COHORT_SHA, SOURCE_SHA), "Unexpected batch scope")
    require(canonical(manifest).encode() == manifest_bytes, "Noncanonical manifest")
    members = manifest["members"]
    require(11 <= first_rank <= 2991 and first_rank % 10 == 1
            and isinstance(members, list) and len(members) == 10, "Invalid ten-company scope")
    for rank, member in enumerate(members, first_rank):
        require(isinstance(member, dict) and set(member) == MEMBER_KEYS
                and type(member["ordinal"]) is int and member["ordinal"] == rank, "Wrong frozen rank")
    require(len({m["company_id"] for m in members}) == 10, "Duplicate manifest company")
    native = source_values(members, projection)
    require(isinstance(rows, list) and len(rows) == 10, "Wrong destination count")
    by_id = {r["company_id"]: r for r in rows}
    require(set(by_id) == set(native), "Missing, extra or duplicate destination company")
    for member in members:
        row = by_id[member["company_id"]]
        require(row.get("verified") is True and row.get("effective_role") == VERIFIER_ROLE
                and row.get("manifest_sha") == approved_sha and row.get("attempt") == str(attempt)
                and row.get("session_date") == TRADE_DATE and row.get("source_sha256") == SOURCE_SHA,
                "Destination verification role, receipt or source mismatch")
        require(all(row.get(k) == v for k, v in member.items()), "Dated identity or source key mismatch")
        actual = number(row["raw_close"], "close"), number(row["raw_volume"], "volume")
        require(actual == native[member["company_id"]], "Native close or volume mismatch")
    return {"attempt": str(attempt), "manifest_sha": approved_sha, "date": TRADE_DATE,
            "company_ids": [m["company_id"] for m in members], "expected": 10, "verified": 10,
            "discrepancies": []}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "projection", "readback"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--attempt", required=True, type=UUID)
    parser.add_argument("--first-rank", required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(verify(args.manifest.read_bytes(), args.sha, args.attempt, args.first_rank,
                            parse(args.projection.read_bytes()), parse(args.readback.read_bytes()))))
