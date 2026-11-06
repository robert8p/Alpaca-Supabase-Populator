"""One August D02 archive-reuse pilot. Source records and manifests stay private.

SQL owns admission, uniqueness, fencing, immutable source checks and atomic output.
The CLI never queries external providers, starts a loader or automatically retries
a write. Its verifier runs a distinct, read-only transaction and compares against
a separately obtained private projection of the retained native source records.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = "astra-aug-d02-pilot/v1"
TRADE_DATE = "2026-08-04"
COHORT_SHA = "2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec"
SOURCE_SHA = "81e74427cd1365680d18cdaa31e5950bf601087e3bb0c11a13b2bfd14f4c93ae"
APPROVED_MANIFEST_SHA = "61860ca4d4829f4f33459e9ebc0bad1c220a4552bfd5d9097d3a46af527717e4"
MEMBER_KEYS = {"ordinal", "company_id", "ticker", "composite_figi", "share_class_figi",
               "exchange_mic", "issue_type", "source_row", "raw_record_sha256",
               "identity_source_sha256", "identity_record_sha256"}
MANIFEST_KEYS = {"schema", "date", "cohort_sha256", "source_sha256", "members"}
HEX = re.compile("[a-f0-9]{64}")
ENV_DSN = {"register": "ASTRA_PILOT_REGISTRAR_DSN", "commit": "ASTRA_PILOT_WRITER_DSN",
           "verify": "ASTRA_PILOT_READER_DSN"}
# Original 1..10 membership, ordered (CIK only); symbol or name alone is insufficient.
ORDERED_COMPANIES_SHA = "c80165db996e3a1378115903aa52a0f2519c5c450c9834d78fef601f50817349"
ACCEPTANCE_SHA = "20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9"
VERIFIER_ROLE = "astra_ingestion_verifier_owner_v1"


class PilotError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise PilotError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def parse(raw):
    def invalid(_):
        raise PilotError("Nonfinite number")
    return json.loads(raw, object_pairs_hook=unique_pairs, parse_float=Decimal, parse_constant=invalid)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def prepare_manifest(packet):
    """Build the pilot's ten keys from independently retained membership, dated identity and bar rows."""
    require(packet["asof_date"] == TRADE_DATE and packet["capture"] == "top3000-augsep2026-retained-scope-v1",
            "Wrong capture or date")
    archive = packet["archive"]
    require(archive["source_sha256"] == SOURCE_SHA and archive["session_date"] == TRADE_DATE and
            archive["result_count"] == archive["verified_source_records"] > 0 and
            archive["source_summary"]["source_records_reconciled"] is True, "Unverified source archive")
    out = {"schema": SCHEMA, "date": TRADE_DATE, "source_sha256": SOURCE_SHA, "cohort_sha256": COHORT_SHA,
           "members": []}
    for index, row in enumerate(packet["rows"], 1):
        m, d, x, price = (row[k] for k in ("member", "identity", "identity_crosswalk", "price"))
        point, cross = d["content"], x["content"]
        raw = point["source_record"]
        require(row["rank"] == m["selection_order"] == index and m["membership_accepted"] is True and
                m["anchor_observation_date"] == "2026-08-03", "Unaccepted snapshot member")
        for evidence in (m, point, cross):
            require(evidence["cohort_sha256"] == COHORT_SHA and evidence["membership_acceptance_sha256"] ==
                    ACCEPTANCE_SHA and evidence["company_id"] == m["company_id"], "Cohort receipt mismatch")
        require(d["point_date"] == point["point_date"] == cross["point_date"] == x["point_date"] == TRADE_DATE and
                "CIK:" + raw["cik"] == m["company_id"] == d["company_id"] == x["company_id"],
                "Wrong dated company identity")
        require(raw["ticker"] == x["ticker"] == m["anchor_ticker"] == cross["ticker"] == price["source_ticker"] and
                raw["type"] == m["anchor_security_type"] and raw["primary_exchange"] == m["anchor_exchange"] and
                raw["composite_figi"] == m["anchor_composite_figi"] and
                raw["share_class_figi"] == m["anchor_share_class_figi"] and raw["active"] is True and
                (raw["locale"], raw["market"], raw["currency_name"]) == ("us", "stocks", "usd"), "Instrument mismatch")
        require(point["identity_state"] == d["identity_state"] == cross["identity_state"] ==
                "FROZEN_ANCHOR_TICKER_AND_TWO_FIGI_MATCH" and
                cross["evidence_semantics"] == "STRONG_IDENTIFIER_MATCHED_VENDOR_DATE_POINT_NOT_INTERVAL" and
                cross["source_record_sha256"] == d["record_sha256"] and
                point["source_sha256"] == cross["source_sha256"] and
                point["source_id"] == d["source_id"] == cross["source_id"] and
                point["source_ordinal"] == d["ordinal"] == cross["source_ordinal"], "Identity evidence mismatch")
        require(price["provider_ny_date"] == TRADE_DATE and price["source_day_id"] == archive["source_day_id"] and
                all(type(price[k]) is int and price[k] == 0 for k in ("invalid_mask", "missing_mask", "structure_mask")),
                "Held or wrong-day price")
        out["members"].append(dict(ordinal=index, company_id=m["company_id"], ticker=raw["ticker"],
            composite_figi=raw["composite_figi"], share_class_figi=raw["share_class_figi"], exchange_mic=raw["primary_exchange"],
            issue_type=raw["type"], source_row=price["source_row"], raw_record_sha256=price["raw_record_sha256"],
            identity_source_sha256=point["source_sha256"], identity_record_sha256=d["record_sha256"]))
    manifest_text(out)
    return out


def manifest_text(obj):
    require(isinstance(obj, dict) and set(obj) == MANIFEST_KEYS, "Invalid pilot manifest shape")
    require((obj["schema"], obj["date"], obj["cohort_sha256"], obj["source_sha256"]) ==
            (SCHEMA, TRADE_DATE, COHORT_SHA, SOURCE_SHA), "Wrong pilot, date, cohort or source")
    members = obj["members"]
    require(isinstance(members, list) and len(members) == 10, "Ten frozen members required")
    for ordinal, m in enumerate(members, 1):
        require(isinstance(m, dict) and set(m) == MEMBER_KEYS, "Invalid member fields")
        require(type(m["ordinal"]) is int and m["ordinal"] == ordinal, "Invalid membership order")
        require(type(m["source_row"]) is int and m["source_row"] > 0, "Invalid source ordinal")
        require(isinstance(m["company_id"], str) and re.fullmatch(r"CIK:[0-9]{10}", m["company_id"]),
                "Invalid company key")
        for label in ("raw_record_sha256", "identity_record_sha256", "identity_source_sha256"):
            require(isinstance(m[label], str) and HEX.fullmatch(m[label]), "Missing source digest")
        for label in ("composite_figi", "share_class_figi"):
            require(isinstance(m[label], str) and re.fullmatch("BBG[A-Z0-9]{9}", m[label]), "Invalid FIGI")
        require(isinstance(m["ticker"], str) and re.fullmatch("[A-Z][A-Z0-9.-]{0,14}", m["ticker"])
                and isinstance(m["exchange_mic"], str) and re.fullmatch("[A-Z0-9]{4}", m["exchange_mic"])
                and m["issue_type"] in {"CS", "ADRC"}, "Invalid listing")
    for field in ("company_id", "ticker", "composite_figi", "share_class_figi", "source_row", "raw_record_sha256"):
        require(len({m[field] for m in members}) == len(members), "Duplicate member, price or instrument")
    require(sha(canonical([m["company_id"] for m in members]).encode()) == ORDERED_COMPANIES_SHA,
            "Changed frozen member selection")
    return canonical(obj)


def admission_text(manifest, advertised_sha, attempt):
    text = manifest_text(manifest)
    require(sha(text.encode()) == advertised_sha == APPROVED_MANIFEST_SHA, "Unapproved manifest digest")
    expected = uuid.uuid5(uuid.NAMESPACE_URL, "urn:astra:aug-d02-pilot:" + advertised_sha)
    require(str(attempt) == str(expected), "Unapproved attempt")
    return text


def number(value, label):
    require(type(value) in (int, Decimal) and Decimal(value).is_finite(), "Invalid numeric " + label)
    return Decimal(value)


def prepare_projection(data, manifest):
    """Normalize the separately obtained source readback for the private offline verifier."""
    require(len(data) == 10, "Ten individual source readbacks required")
    expected_uri = "https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/" + TRADE_DATE + "?adjusted=false&include_otc=false"
    rows = []
    for m, r in zip(manifest["members"], data):
        require(r["source_sha256"] == r["actual_sha"] == SOURCE_SHA and
                r["body_status"] == "OK" and r["adjusted"] is False and r["source_uri"] == expected_uri and
                r["response_bytes"] == r["actual_bytes"] > 0 and
                r["actual_count"] == r["result_count"] == r["results_count"] == r["query_count"] and
                0 < r["source_row"] <= r["actual_count"], "Raw source document mismatch")
        require(r["raw_record_sha256"] == r["archive_record_sha256"] == r["actual_record_sha256"] ==
                m["raw_record_sha256"] and r["source_rows"] == 1 and
                r["rank"] == m["ordinal"] and r["source_row"] == m["source_row"] and r["source_ticker"] == m["ticker"] and
                r["provider_ny_date"] == TRADE_DATE and r["source_presence_state"] == "PRESENT_SINGLE" and
                r["point_source_state"] == "VERIFIED_POINT_AND_SOURCE_LINK" and
                r["anchor_identity_record_sha256"] == m["identity_record_sha256"] and
                r["anchor_identity_source_sha256"] == m["identity_source_sha256"], "Record linkage mismatch")
        rows.append({"source_row": r["source_row"], "raw_record_text": r["raw_jsonb_text"]})
    result = {"source_sha256": SOURCE_SHA, "date": TRADE_DATE, "rows": rows}
    source_values(manifest["members"], result)
    return result


def source_values(members, projection):
    """Verify the exact Postgres JSONB source text, without reserializing numeric values."""
    require(isinstance(projection, dict) and projection.get("source_sha256") == SOURCE_SHA
            and projection.get("date") == TRADE_DATE, "Wrong original source")
    items = projection.get("rows")
    require(isinstance(items, list) and len(items) == len(members), "Missing original archive rows")
    by_row = {}
    for r in items:
        require(isinstance(r, dict) and set(r) == {"source_row", "raw_record_text"} and
                type(r["source_row"]) is int and r["source_row"] not in by_row and
                type(r["raw_record_text"]) is str, "Invalid archive projection")
        by_row[r["source_row"]] = r["raw_record_text"]
    result = {}
    for m in members:
        raw = by_row.get(m["source_row"])
        require(raw is not None and sha(raw.encode()) == m["raw_record_sha256"], "Archive row fingerprint mismatch")
        r = parse(raw)
        require(isinstance(r, dict) and r.get("T") == m["ticker"] and type(r.get("t")) is int,
                "Native key mismatch")
        seconds = r["t"] // 1000
        require(0 <= seconds <= 4_102_444_800 and datetime.fromtimestamp(seconds, ZoneInfo("America/New_York"))
                .date().isoformat() == TRADE_DATE, "Native timestamp outside trading day")
        prices = {key: number(r.get(key), key) for key in ("o", "h", "l", "c", "v", "vw")}
        require(0 < prices["l"] <= min(prices["o"], prices["c"]) and
                max(prices["o"], prices["c"]) <= prices["h"] and prices["v"] >= 0 and
                prices["vw"] > 0 and type(r.get("n")) is int and r["n"] >= 0, "Invalid original bar")
        result[m["company_id"]] = (prices["c"], prices["v"])
    return result


def verify_rows(manifest, expected_sha, attempt, projection, rows):
    admission_text(manifest, expected_sha, attempt)
    expected = source_values(manifest["members"], projection)
    require(len(rows) == 10, "Incomplete or ambiguous destination")
    by_company = {r["company_id"]: r for r in rows}
    require(len(by_company) == 10, "Duplicate destination company")
    for m in manifest["members"]:
        r = by_company.get(m["company_id"])
        require(r and r["verified"] is True and r["effective_role"] == VERIFIER_ROLE and
                r["manifest_sha"] == expected_sha and
                str(r["attempt"]) == str(attempt) and str(r["session_date"]) == TRADE_DATE and
                r["source_sha256"] == SOURCE_SHA, "Destination receipt binding mismatch")
        for f in MEMBER_KEYS:
            require(r.get(f) == m[f], "Destination member mismatch: " + f)
        actual = (number(r["raw_close"], "close"), number(r["raw_volume"], "volume"))
        require(actual == expected[m["company_id"]], "Destination values differ from independent source")
    return dict(manifest_sha=expected_sha, attempt=str(attempt), date=TRADE_DATE, expected=10, verified=10,
                company_ids=[m["company_id"] for m in manifest["members"]], discrepancies=[])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "verify-readback", *ENV_DSN))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--sha", required=True, help="Independently reviewed canonical manifest SHA-256")
    parser.add_argument("--attempt", type=uuid.UUID, required=True)
    parser.add_argument("--deadline", help="Required for registration, explicit timezone")
    parser.add_argument("--readback", type=Path, help="Exact JSON rows from a separate read-only verifier transaction")
    args = parser.parse_args(argv)
    manifest = parse(args.manifest.read_bytes())
    projection = parse(args.projection.read_bytes())
    text = admission_text(manifest, args.sha, args.attempt)
    if args.action == "verify-readback":
        require(args.readback is not None, "Independent readback file required")
        return verify_rows(manifest, args.sha, args.attempt, projection, parse(args.readback.read_bytes()))
    source_values(manifest["members"], projection)
    if args.action == "plan":
        return {"expected": 10, "reusable_source_rows": 10, "required_provider_requests": 0,
                "manifest_sha": args.sha, "attempt": str(args.attempt), "destination_verified": False}
    if args.action == "register":
        require(bool(args.deadline), "Registration requires a finite UTC deadline")
        deadline = datetime.fromisoformat(args.deadline)
        require(deadline.tzinfo is not None and deadline > datetime.now(timezone.utc), "Expired or naive deadline")
    dsn = os.environ.get(ENV_DSN[args.action])
    require(bool(dsn), "Missing existing role-bound database connection")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row) as db:
        if args.action == "verify":
            db.execute("SET TRANSACTION READ ONLY")
            rows = db.execute("SELECT * FROM astra_ingestion_v1.aug_d02_pilot_read_v1()").fetchall()
            return verify_rows(manifest, args.sha, args.attempt, projection, rows)
        if args.action == "register":
            row = db.execute("SELECT astra_ingestion_v1.aug_d02_pilot_register_v1(%s,%s,%s,%s) AS pin",
                             (text, args.sha, args.attempt, deadline)).fetchone()
            require(row and row["pin"] == args.sha, "Registration receipt mismatch")
        else:
            row = db.execute("SELECT astra_ingestion_v1.aug_d02_pilot_commit_v1(%s,%s) AS inserted",
                             (args.sha, args.attempt)).fetchone()
            require(row and type(row["inserted"]) is int and 0 <= row["inserted"] <= 10, "Commit receipt mismatch")
    return {"completed_action": args.action, "attempt": str(args.attempt), "manifest_sha": args.sha,
            "inserted": row.get("inserted"), "destination_verified": False}


if __name__ == "__main__":
    try:
        print(json.dumps(main(), sort_keys=True))
    except (PilotError, OSError, TypeError, KeyError, ValueError) as exc:
        # Formats and SQL credentials can be sensitive; report only controlled classes/messages.
        print(str(exc) if isinstance(exc, PilotError) else type(exc).__name__, file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print(type(exc).__name__ + "; reconcile the original attempt before any further operation", file=sys.stderr)
        raise SystemExit(75)
