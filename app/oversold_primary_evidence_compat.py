from __future__ import annotations

"""Point-in-time compatibility hardening for primary event evidence."""

import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def patch_module(module: Any) -> None:
    if getattr(module, "_point_in_time_compat_installed", False):
        return

    original_parse_ts = module._parse_ts
    original_fda_article = module._fda_article_from_payload

    def parse_ts(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if re.fullmatch(r"\d{14}", text):
            # Legacy EDGAR acceptance strings without an explicit zone represent
            # Eastern filing time. Interpreting them as UTC could admit a filing
            # several hours before it was actually public.
            try:
                return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=NY).astimezone(UTC)
            except ValueError:
                return None
        return original_parse_ts(value)

    def fda_article_from_payload(
        *,
        symbol: str,
        application: str,
        payload: dict[str, Any],
        cutoff: datetime,
    ) -> dict[str, Any] | None:
        article = original_fda_article(
            symbol=symbol,
            application=application,
            payload=payload,
            cutoff=cutoff,
        )
        if not article:
            return None
        record = article.get("primary_evidence")
        if not isinstance(record, dict):
            return article
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        submissions = metadata.get("eligible_submissions") if isinstance(metadata.get("eligible_submissions"), list) else []
        statuses: list[str] = []
        for item in submissions[:8]:
            if not isinstance(item, dict):
                continue
            statuses.append(
                f"{item.get('submission_status_date') or 'unknown date'}: "
                f"{item.get('submission_type') or ''} {item.get('submission_status') or ''} "
                f"{item.get('submission_public_notes') or ''}".strip()
            )
        summary = (
            f"FDA Drugs@FDA record {application}. "
            f"Cutoff-valid dated submission history: {' | '.join(statuses) or 'none retained'}."
        )
        record["summary"] = summary
        record["content_excerpt"] = summary
        record["content_hash"] = module._sha256(summary)
        metadata.pop("sponsor_name", None)
        metadata.pop("products", None)
        metadata["current_application_metadata_excluded"] = True
        metadata["point_in_time_scope"] = "dated submission history only"
        record["metadata"] = metadata
        article["summary"] = summary
        article["primary_evidence"] = record
        return article

    module._parse_ts = parse_ts
    module._fda_article_from_payload = fda_article_from_payload
    module._point_in_time_compat_installed = True
