"""Apply bounded, hash-bound retrospective identity evidence to calculation inputs.

The database builds this material from retained provider records. This helper
does not infer identity from symbols, extend dated observations into intervals,
or claim original historical availability. Source dictionaries are preserved.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import base64
import re
import zlib

from .backfill_provider_v2 import canonical


MATERIAL_VERSION = "fixed3000-retrospective-identity-v2.2"
RESOLVED = "RETROSPECTIVE_DATED_IDENTIFIERS_MATCHED"
COHORT_SHA256 = "2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec"
ASOF_MODE = "ALPACA_EXPLICIT_ASOF_ANCHOR_AND_DATED_IDENTIFIERS"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_FIGI = re.compile(r"[A-Z0-9]{12}\Z")


class IdentityMaterialError(ValueError):
    """A calculation received material outside its immutable claim scope."""


def _qualified_asof_mapping(mapping, entry, symbol):
    """Use only explicit receipt semantics plus the accepted frozen identity.

    Alpaca's historical bars documentation states that an explicit asof selects
    the entity denoted by the requested symbol on that date, and returned bars
    keep the requested label through a past symbol change. The provider policy
    is not itself an identity match: the dated CIK and both FIGIs must agree
    with the accepted asof anchor below. No default or disabled asof is inferred.
    """
    anchor = entry.get("anchor_identity")
    if not isinstance(mapping, dict) or not isinstance(anchor, dict):
        return False
    return bool(
        mapping.get("provider") == "Alpaca" and mapping.get("host") == "data.alpaca.markets"
        and mapping.get("path") == "/v2/stocks/bars" and mapping.get("method") == "GET"
        and mapping.get("requested_symbol") == symbol == entry.get("symbol") == anchor.get("symbol")
        and isinstance(mapping.get("asof"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", mapping["asof"])
        and mapping["asof"] == anchor.get("reference_date")
        and anchor.get("membership_accepted") is True and anchor.get("cohort_sha256") == COHORT_SHA256
        and anchor.get("member_id") == entry.get("member_id") == "CIK:" + str(anchor.get("cik"))
        and all(anchor.get(key) == entry.get(key) for key in ("cik", "composite_figi", "share_class_figi", "security_type"))
        and all(isinstance(value, str) and _HASH.fullmatch(value) for value in
                (anchor.get("anchor_sha256"), mapping.get("source_body_sha256"), mapping.get("request_sha256")))
    )


def _row_attribution(row, entry):
    mapping = row.get("provider_symbol_mapping")
    if mapping is None and isinstance(row.get("identity_input_attribution"), dict):
        prior = row["identity_input_attribution"]
        # A carried derivation proof remains usable only against the current
        # dated evidence. Breadth also binds the independently verified D03 body.
        if (prior.get("state") == RESOLVED and prior.get("all_input_identities_qualified") is True
                and prior.get("identity_anchor") == entry.get("identity_anchor")
                and prior.get("evidence_sha256") == entry.get("evidence_sha256")
                and prior.get("member_id") == entry.get("member_id")
                and prior.get("market_date") == entry.get("market_date")
                and prior.get("symbol") == row.get("symbol")
                and (not entry.get("input_body_sha256") or
                     (row.get("source_lineage") or {}).get("body_sha256") == entry["input_body_sha256"])):
            mapping = prior.get("provider_symbol_mapping")
        else:
            return None, None, "DERIVED_IDENTITY_ATTRIBUTION_NO_LONGER_CURRENT"
    if _qualified_asof_mapping(mapping, entry, row.get("symbol")):
        return ASOF_MODE, mapping, None
    if row.get("symbol") == entry.get("historical_symbol"):
        if mapping is None or (isinstance(mapping, dict) and mapping.get("asof") == "-"
                               and mapping.get("requested_symbol") == row.get("symbol")):
            return "EXACT_DATED_PROVIDER_SYMBOL", None, None
        return None, None, "PROVIDER_ASOF_ANCHOR_UNVERIFIED"
    return None, None, "HISTORICAL_SYMBOL_REQUIRES_ALIAS_ACQUISITION"


def attach_identity_output(rows, overlay):
    """Carry qualified input attribution into immutable derived output rows.

    Numeric values and original formula versions are untouched. The compact
    proof lets a subsequent breadth calculation revalidate an asof alias
    against current dated evidence instead of trusting a legacy anchor string.
    """
    proofs = overlay.get("output_attribution", {})
    result = []
    for source in rows:
        row = dict(source)
        proof = proofs.get((row.get("symbol"), row.get("market_date")))
        if proof is not None:
            row["identity_input_attribution"] = deepcopy(proof)
        result.append(row)
    return result


def prepare_retained_identity_commit(claim, source):
    """Verify one retained gzip source without unbounded decompression.

    The dedicated database commit independently hashes the returned original
    bytes against the retained source receipt and derives the dated mappings.
    No provider dispatch and no new copy of the original source is required.
    """
    if (claim.get("kind") != "retained_identity" or not isinstance(source, dict)
            or source.get("run_id") != claim.get("run_id") or source.get("task_id") != claim.get("id")
            or source.get("source_id") != claim.get("scope", {}).get("identity_source_id")):
        raise IdentityMaterialError("Retained identity source differs from its claim")
    size = source.get("original_bytes")
    if (type(size) is not int or not 1 <= size <= 4 * 1024 * 1024
            or source.get("storage_encoding") != "gzip"):
        raise IdentityMaterialError("Retained identity source has unsupported encoding or size")
    try:
        compressed = base64.b64decode(source["compressed_body_base64"], validate=True)
    except (ValueError, TypeError, KeyError) as error:
        raise IdentityMaterialError("Malformed retained identity source bytes") from error
    if len(compressed) > 2 * 1024 * 1024 or sha256(compressed).hexdigest() != source.get("compressed_sha256"):
        raise IdentityMaterialError("Retained identity compressed source hash differs")
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = inflater.decompress(compressed, size + 1)
        if (len(raw) != size or not inflater.eof or inflater.unconsumed_tail or inflater.unused_data
                or sha256(raw).hexdigest() != source.get("source_sha256")):
            raise IdentityMaterialError("Retained identity original source hash or size differs")
        text = raw.decode("utf-8")
    except (zlib.error, UnicodeDecodeError) as error:
        raise IdentityMaterialError("Retained identity source cannot be decoded") from error
    return {"claim": {key: claim[key] for key in ("id", "run_id", "owner", "generation", "run_fence", "page_no")},
            "raw_body": text, "source_sha256": source["source_sha256"],
            "compressed_sha256": source["compressed_sha256"]}


def apply_identity_material(rows, material, claim):
    """Return copied input rows, representative map, and auditable identity lineage.

    The authenticated RPC returns one exact-date entry per requested member and
    session. Its hash is rechecked before use. Unresolved or changed evidence
    removes any inherited identity anchor; acquisition remains independent.
    """
    if not isinstance(material, dict) or material.get("version") != MATERIAL_VERSION:
        raise IdentityMaterialError("Unsupported identity material version")
    if material.get("run_id") != claim.get("run_id") or material.get("task_id") != claim.get("id"):
        raise IdentityMaterialError("Identity material belongs to another task or run")
    mappings = material.get("mappings")
    digest = material.get("identity_material_sha256")
    if (not isinstance(mappings, list) or len(mappings) > 3000
            or not isinstance(digest, str) or not _HASH.fullmatch(digest)
            or sha256(canonical(mappings).encode()).hexdigest() != digest):
        raise IdentityMaterialError("Identity material hash or bounded shape differs")
    scope = claim.get("scope", {})
    days = {entry["date"] for entry in scope.get("calendar", [])}
    if not days:
        raise IdentityMaterialError("Identity calculations require explicit session dates")
    reps = deepcopy(scope.get("representative_security"))
    members = set(reps) if claim.get("kind") == "derive_breadth" and isinstance(reps, dict) else set(scope.get("member_ids", []))
    if not members or len(members) > 3000:
        raise IdentityMaterialError("Identity calculations require their fixed members")
    symbols = set(scope.get("symbols", []))
    if scope.get("symbol"):
        symbols.add(scope["symbol"])
    indexed, by_member = {}, {}
    for entry in mappings:
        if not isinstance(entry, dict):
            raise IdentityMaterialError("Invalid identity mapping")
        member, day, symbol = entry.get("member_id"), entry.get("market_date"), entry.get("symbol")
        if member not in members or day not in days or not isinstance(symbol, str):
            raise IdentityMaterialError("Identity mapping is outside this member/date scope")
        if claim.get("kind") == "derive_breadth":
            representative = reps.get(member)
            wanted = representative if isinstance(representative, str) else (representative or {}).get("symbol")
            if symbol != wanted:
                raise IdentityMaterialError("Identity mapping changed the frozen representative")
        elif symbol not in symbols:
            raise IdentityMaterialError("Identity mapping changed the requested provider anchor")
        key = (member, day)
        if key in by_member or (claim.get("kind") != "derive_breadth" and (symbol, day) in indexed):
            raise IdentityMaterialError("Ambiguous identity material; duplicate member or symbol/date")
        if entry.get("state") == RESOLVED:
            cik = entry.get("cik")
            composite, share = entry.get("composite_figi"), entry.get("share_class_figi")
            if (not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik) or member != "CIK:"+cik
                    or not isinstance(composite, str) or not _FIGI.fullmatch(composite)
                    or not isinstance(share, str) or not _FIGI.fullmatch(share)
                    or not entry.get("security_type") or not entry.get("primary_exchange")
                    or not isinstance(entry.get("historical_symbol"), str) or not entry["historical_symbol"]
                    or entry.get("identity_anchor") != "CIK:"+cik+"|FIGI:"+composite+"|CLASS:"+share
                    or entry.get("retrospective_only") is not True
                    or entry.get("strict_historical_availability_certified") is not False
                    or not isinstance(entry.get("evidence_sha256"), str)
                    or not _HASH.fullmatch(entry["evidence_sha256"])):
                raise IdentityMaterialError("Resolved mapping lacks stable dated identifiers and evidence")
        indexed[(symbol, day)], by_member[key] = entry, entry
    if set(by_member) != {(member, day) for member in members for day in days}:
        raise IdentityMaterialError("Identity material omitted a requested member/session")
    output, reasons, groups = [], Counter(), {}
    for source in rows:
        row = dict(source)
        entry = (by_member.get((row.get("member_id"), row.get("market_date")))
                 if claim.get("kind") == "derive_breadth"
                 else indexed.get((row.get("symbol"), row.get("market_date"))))
        # Preserve original payload and price semantics, replacing only current
        # attribution metadata. Legacy anchors cannot survive a current hold.
        row["identity_anchor"] = None
        row["identity_status"] = "IDENTITY_OR_QUALITY_UNRESOLVED"
        row.pop("identity_attribution_mode", None)
        if entry is not None:
            row["identity_evidence_sha256"] = entry.get("evidence_sha256")
            row["identity_material_sha256"] = digest
            row["identity_reason"] = entry.get("reason")
            mode, request_mapping, reason = _row_attribution(row, entry) if entry.get("state") == RESOLVED else (None, None, None)
            if mode is not None:
                row["identity_anchor"] = entry["identity_anchor"]
                row["identity_status"] = RESOLVED
                row["historical_provider_symbol"] = entry.get("historical_symbol")
                row["identity_attribution_mode"] = mode
                row["identity_reason"] = None
                if request_mapping is not None:
                    row["provider_symbol_mapping"] = deepcopy(request_mapping)
            else:
                reason = reason or entry.get("reason") or "DATED_IDENTITY_EVIDENCE_UNAVAILABLE"
                row["identity_reason"] = reason
                row["historical_provider_symbol"] = entry.get("historical_symbol")
        else:
            row["identity_reason"] = "ROW_OUTSIDE_REQUESTED_IDENTITY_MATERIAL"
        output.append(row)
        groups.setdefault(((entry or {}).get("member_id", row.get("member_id")), row.get("symbol"), row.get("market_date")), []).append(row)
    # Daily formulas use the raw identity together with split prices. A failed
    # identity check on either variant must hold adjusted attribution for both.
    for group in groups.values():
        daily = [r for r in group if r.get("timeframe") == "1Day" and r.get("adjustment") in ("raw", "split", "all")]
        if daily and any(r.get("identity_anchor") is None for r in daily):
            for row in daily:
                if row.get("identity_anchor") is not None:
                    row["identity_anchor"] = None
                    row["identity_status"] = "IDENTITY_OR_QUALITY_UNRESOLVED"
                    row["identity_reason"] = "DAILY_PRICE_VARIANTS_IDENTITY_DISAGREE"
    for row in output:
        if row.get("identity_anchor") is None:
            reasons[row.get("identity_reason") or "DATED_IDENTITY_EVIDENCE_UNAVAILABLE"] += 1
        if claim.get("kind") == "derive_breadth" and row.get("identity_anchor") is None:
            values = dict(row.get("values", {}))
            nulls = dict(row.get("null_reasons", {}))
            if values.get("adjusted_ret_1d") is not None:
                values["adjusted_ret_1d"] = None
                nulls["adjusted_ret_1d"] = "CURRENT_IDENTITY_EVIDENCE_UNRESOLVED"
            row["values"], row["null_reasons"] = values, nulls
    proofs, qualified, aliases, asof_sessions = {}, set(), set(), set()
    for key, group in groups.items():
        entry = by_member.get((key[0], key[2]))
        if entry is None:
            continue
        complete = all(row.get("identity_anchor") == entry.get("identity_anchor") and row.get("identity_status") == RESOLVED for row in group)
        session_key = (entry["member_id"], entry["market_date"])
        if complete:
            qualified.add(session_key)
        if any(row.get("identity_reason") == "HISTORICAL_SYMBOL_REQUIRES_ALIAS_ACQUISITION" for row in group):
            aliases.add(session_key)
        source_mappings = [row.get("provider_symbol_mapping") for row in group]
        mapping = next((item for item in source_mappings if isinstance(item, dict)), None)
        mapping_keys = ("provider", "host", "path", "method", "asof", "requested_symbol")
        consistent_mapping = bool(mapping is not None and all(isinstance(item, dict) and
                                  all(item.get(key) == mapping.get(key) for key in mapping_keys) for item in source_mappings))
        if complete and any(row.get("identity_attribution_mode") == ASOF_MODE for row in group):
            asof_sessions.add(session_key)
        proofs[(key[1], key[2])] = {
            "state": RESOLVED if complete else "IDENTITY_OR_QUALITY_UNRESOLVED",
            "member_id": entry["member_id"], "market_date": entry["market_date"], "symbol": key[1],
            "identity_anchor": entry.get("identity_anchor") if complete else None,
            "historical_symbol": entry.get("historical_symbol"), "evidence_sha256": entry.get("evidence_sha256"),
            "identity_material_sha256": digest, "all_input_identities_qualified": complete,
            "input_records": len(group), "provider_symbol_mapping": deepcopy(mapping),
            "all_input_provider_symbol_mappings_consistent": consistent_mapping,
            "retrospective_only": True, "strict_historical_availability_certified": False,
        }
    if isinstance(reps, dict):
        for member, original in list(reps.items()):
            item = {"symbol": original} if isinstance(original, str) else dict(original)
            item["eligible"] = None
            item["eligibility_by_date"] = {
                day: (by_member[(member, day)].get("eligible")
                      if by_member[(member, day)].get("state") == RESOLVED else None)
                for day in sorted(days)
            }
            reps[member] = item
    lineage = {
        "version": MATERIAL_VERSION, "identity_material_sha256": digest,
        "resolved_member_sessions": len(qualified),
        "unresolved_member_sessions": len(mappings) - len(qualified),
        "reference_resolved_member_sessions": sum(e.get("state") == RESOLVED for e in mappings),
        "alias_acquisition_required_member_sessions": len(aliases),
        "explicit_asof_attributed_member_sessions": len(asof_sessions),
        "retrospective_only": True, "strict_historical_availability_certified": False,
        "original_page_readback": "HASH_VERIFIED_RETAINED_OR_CURRENT_PROVIDER_RECEIPTS",
        "evidence_revision": material.get("evidence_revision"),
    }
    return {"rows": output, "representative_security": reps, "output_attribution": proofs,
            "identity_material_sha256": digest, "identity_lineage": lineage,
            "limitations": [{"state": "IDENTITY_OR_QUALITY_UNRESOLVED", "reason": reason,
                            "scope": "affected_identity_attribution_only", "affected_input_records": count}
                           for reason, count in sorted(reasons.items())]}
