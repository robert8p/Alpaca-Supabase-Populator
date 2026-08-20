from __future__ import annotations

"""Point-in-time and document-selection hardening for primary event evidence."""

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
    original_select_documents = module._select_documents

    # Inline XBRL filing documents may use either .htm/.html or .xhtml. The main
    # filing must not be excluded merely because an issuer chose the latter.
    module.DOCUMENT_EXTENSIONS = tuple(dict.fromkeys((*module.DOCUMENT_EXTENSIONS, ".xhtml")))

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

    def select_documents(
        rows: list[dict[str, Any]],
        *,
        primary_document: str | None,
        form: str,
    ) -> list[dict[str, Any]]:
        available_rows = list(rows)
        normalized_primary = str(primary_document or "").strip()
        exact_form_exists = any(
            module._document_is_textual(row)
            and str(row.get("type") or "").upper().strip() == form.upper().strip()
            for row in available_rows
        )
        if (
            normalized_primary
            and normalized_primary.lower().endswith(module.DOCUMENT_EXTENSIONS)
            and not exact_form_exists
            and not any(
                str(row.get("document") or "").lower() == normalized_primary.lower()
                for row in available_rows
            )
        ):
            # SEC submissions.json explicitly designates the canonical filing
            # body. Some filing-index HTML pages omit that row from the parsed
            # document table while still listing exhibits. Synthesising the row
            # from authoritative submissions metadata is deterministic and avoids
            # treating an agreement/certification as the filing narrative.
            available_rows.insert(
                0,
                {
                    "sequence": "1",
                    "description": f"Canonical Form {form} filing document",
                    "document": normalized_primary,
                    "href": normalized_primary,
                    "type": form.upper().strip(),
                    "size": None,
                    "source": "SEC submissions primaryDocument",
                },
            )

        selected = original_select_documents(
            available_rows,
            primary_document=normalized_primary or None,
            form=form,
        )
        exact_form = next(
            (
                row for row in available_rows
                if module._document_is_textual(row)
                and str(row.get("type") or "").upper().strip() == form.upper().strip()
            ),
            None,
        )
        if exact_form is None:
            return selected
        max_documents = 4 if form.upper().startswith(("8-K", "6-K")) else 2
        return [exact_form, *(row for row in selected if row != exact_form)][:max_documents]

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
    module._select_documents = select_documents
    module._fda_article_from_payload = fda_article_from_payload
    module._point_in_time_compat_installed = True
