from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

from app.core.time import utc_now
from app.models.database import (
    BrandProduct,
    MediaOutcomeImportBatch,
    MediaOutcomeImportIssue,
    MediaOutcomeRecord,
    SurvstatWeeklyData,
    WastewaterAggregated,
)
from app.services.media.product_catalog_service import ProductCatalogService
from app.services.media.recommendation_contracts import BUNDESLAND_NAMES, normalize_region_code
from .context import build_truth_validation_context, normalize_brand

METRIC_FIELD_LABELS = {
    "media_spend_eur": "Mediabudget",
    "impressions": "Impressionen",
    "clicks": "Klicks",
    "qualified_visits": "Qualifizierte Besuche",
    "search_lift_index": "Suchanstieg",
    "sales_units": "Verkäufe",
    "order_count": "Bestellungen",
    "revenue_eur": "Umsatz",
}
REQUIRED_OUTCOME_FIELD_NAMES = ("media_spend_eur",)
CONVERSION_OUTCOME_FIELD_NAMES = ("sales_units", "order_count", "revenue_eur")
OPTIONAL_OUTCOME_FIELD_NAMES = ("qualified_visits", "search_lift_index", "impressions", "clicks")
OUTCOME_TEMPLATE_HEADERS = (
    "week_start,product,region_code,media_spend_eur,sales_units,order_count,revenue_eur,"
    "qualified_visits,search_lift_index,impressions,clicks\n"
    "2026-02-02,GeloProsed,SH,12000,140,,,320,18.5,240000,5800\n"
    "2026-02-09,GeloRevoice,Hamburg,9000,,44,18500,210,12.0,120000,2900\n"
)


def build_truth_coverage(
    service: Any,
    *,
    brand: str,
    virus_typ: str | None = None,
) -> dict[str, Any]:
    brand_value = normalize_brand(brand)
    rows = (
        service.db.query(MediaOutcomeRecord)
        .filter(func.lower(MediaOutcomeRecord.brand) == brand_value)
        .order_by(MediaOutcomeRecord.week_start.asc())
        .all()
    )
    latest_import_batch = _latest_import_batch(service, brand=brand_value)
    reference_week = _latest_epi_reference_week(service, virus_typ=virus_typ)
    if not rows:
        return {
            "coverage_weeks": 0,
            "latest_week": None,
            "regions_covered": 0,
            "products_covered": 0,
            "outcome_fields_present": [],
            "required_fields_present": [],
            "conversion_fields_present": [],
            "trust_readiness": "noch_nicht_angeschlossen",
            "truth_freshness_state": "missing",
            "source_labels": [],
            "last_imported_at": latest_import_batch.uploaded_at.isoformat() if latest_import_batch and latest_import_batch.uploaded_at else None,
            "latest_batch_id": latest_import_batch.batch_id if latest_import_batch else None,
            "latest_source_label": latest_import_batch.source_label if latest_import_batch else None,
        }

    week_values = sorted({row.week_start for row in rows if row.week_start})
    weeks = [value.date().isoformat() for value in week_values]
    regions = {row.region_code for row in rows if row.region_code}
    products = {row.product for row in rows if row.product}
    fields_present = [
        label
        for field_name, label in METRIC_FIELD_LABELS.items()
        if any(getattr(row, field_name) is not None for row in rows)
    ]
    required_fields_present = [
        METRIC_FIELD_LABELS[field_name]
        for field_name in REQUIRED_OUTCOME_FIELD_NAMES
        if any(getattr(row, field_name) is not None for row in rows)
    ]
    conversion_fields_present = [
        METRIC_FIELD_LABELS[field_name]
        for field_name in CONVERSION_OUTCOME_FIELD_NAMES
        if any(getattr(row, field_name) is not None for row in rows)
    ]
    coverage_weeks = len(weeks)
    if coverage_weeks >= 52:
        readiness = "belastbar"
    elif coverage_weeks >= 26:
        readiness = "im_aufbau"
    elif coverage_weeks > 0:
        readiness = "erste_signale"
    else:
        readiness = "noch_nicht_angeschlossen"
    latest_week_dt = week_values[-1] if week_values else None
    truth_freshness_state = _truth_freshness_state(
        service,
        latest_truth_week=latest_week_dt,
        reference_week=reference_week,
    )

    return {
        "coverage_weeks": coverage_weeks,
        "latest_week": weeks[-1] if weeks else None,
        "regions_covered": len(regions),
        "products_covered": len(products),
        "outcome_fields_present": fields_present,
        "required_fields_present": required_fields_present,
        "conversion_fields_present": conversion_fields_present,
        "trust_readiness": readiness,
        "truth_freshness_state": truth_freshness_state,
        "source_labels": sorted({row.source_label for row in rows if row.source_label}),
        "last_imported_at": latest_import_batch.uploaded_at.isoformat() if latest_import_batch and latest_import_batch.uploaded_at else None,
        "latest_batch_id": latest_import_batch.batch_id if latest_import_batch else None,
        "latest_source_label": latest_import_batch.source_label if latest_import_batch else None,
    }


def build_truth_evidence(
    service: Any,
    *,
    brand: str,
    virus_typ: str | None = None,
) -> dict[str, Any]:
    brand_value = normalize_brand(brand)
    coverage = build_truth_coverage(service, brand=brand_value, virus_typ=virus_typ)
    truth_context = build_truth_validation_context(
        service,
        brand=brand_value,
        virus_typ=virus_typ,
        truth_coverage=coverage,
    )
    truth_gate = truth_context["truth_gate"]
    outcome_learning = truth_context["learning_bundle"]["summary"]
    business_validation = truth_context["business_validation"]
    recent_batches = list_outcome_import_batches(service, brand=brand_value, limit=8)
    latest_batch = recent_batches[0] if recent_batches else None
    issue_count = int(latest_batch.get("rows_rejected") or 0) if latest_batch else 0
    limits: list[str] = []
    if coverage.get("coverage_weeks", 0) < 26:
        limits.append("Weniger als 26 Wochen Kundendaten reichen noch nicht für belastbare Freigaben.")
    if not coverage.get("required_fields_present"):
        limits.append("Mediabudget fehlt in den Kundendaten oder ist noch nicht breit genug vorhanden.")
    if not coverage.get("conversion_fields_present"):
        limits.append("Mindestens eine echte Wirkungszahl wie Verkäufe, Bestellungen oder Umsatz fehlt noch.")
    if coverage.get("truth_freshness_state") == "stale":
        limits.append("Der letzte Import der Kundendaten liegt zu weit hinter der aktuellen epidemiologischen Woche.")
    return {
        "brand": brand_value,
        "coverage": coverage,
        "truth_gate": truth_gate,
        "business_validation": business_validation,
        "outcome_learning_summary": outcome_learning,
        "recent_batches": recent_batches,
        "latest_batch": latest_batch,
        "latest_batch_issue_count": issue_count,
        "template_url": "/api/v1/media/outcomes/template",
        "official_ingest_url": "/api/v1/media/outcomes/ingest",
        "known_limits": limits,
        "analyst_note": "Die offizielle Kundenschnittstelle ist jetzt die M2M-Ingestion unter /api/v1/media/outcomes/ingest. CSV bleibt nur als Backoffice-Fallback.",
    }


def import_outcomes(
    service: Any,
    *,
    source_label: str,
    records: list[dict[str, Any]] | None = None,
    csv_payload: str | None = None,
    brand: str,
    replace_existing: bool = False,
    validate_only: bool = False,
    file_name: str | None = None,
) -> dict[str, Any]:
    brand_value = normalize_brand(brand)
    source_value = str(source_label or "manual").strip() or "manual"
    batch_id = uuid.uuid4().hex[:12]

    parsed_rows, header_issues = _collect_outcome_rows(
        service,
        records=records or [],
        csv_payload=csv_payload,
        brand=brand_value,
        source_label=source_value,
    )
    batch = MediaOutcomeImportBatch(
        batch_id=batch_id,
        brand=brand_value,
        source_label=source_value,
        ingestion_mode="manual_backoffice",
        file_name=(file_name or "").strip() or None,
        status="validated" if validate_only else "failed",
        rows_total=len(parsed_rows),
        uploaded_at=utc_now(),
    )
    service.db.add(batch)
    service.db.flush()

    issues: list[dict[str, Any]] = list(header_issues)
    normalized_rows: list[dict[str, Any]] = []
    duplicate_count = 0
    seen_keys: set[tuple[str, str, datetime, str, str]] = set()

    for row in parsed_rows:
        normalized = _normalize_outcome_row(
            service,
            row=row,
            brand=brand_value,
            source_label=source_value,
        )
        if normalized.get("issues"):
            issues.extend(normalized["issues"])
            continue

        dedupe_key = (
            brand_value,
            source_value,
            normalized["week_start"],
            normalized["product"],
            normalized["region_code"],
        )
        if dedupe_key in seen_keys:
            duplicate_count += 1
            issues.append(_issue_dict(
                service,
                batch_id=batch_id,
                row_number=row.get("row_number"),
                field_name="row",
                issue_code="duplicate_in_upload",
                message="Diese Kombination aus Woche, Produkt, Region und Source kommt in der Datei mehrfach vor.",
                raw_row=row.get("raw_row"),
            ))
            continue
        seen_keys.add(dedupe_key)

        existing = _find_existing_outcome(
            service,
            brand=brand_value,
            source_label=source_value,
            week_start=normalized["week_start"],
            product=normalized["product"],
            region_code=normalized["region_code"],
        )
        if existing and not replace_existing:
            duplicate_count += 1
            issues.append(_issue_dict(
                service,
                batch_id=batch_id,
                row_number=row.get("row_number"),
                field_name="row",
                issue_code="duplicate_existing",
                message="Für diese Woche, dieses Produkt und diese Region existiert bereits ein Datensatz in den Kundendaten.",
                raw_row=row.get("raw_row"),
            ))
            continue

        normalized["existing_record"] = existing
        normalized_rows.append(normalized)

    imported = 0
    if not validate_only:
        for row in normalized_rows:
            target = row["existing_record"]
            if target is None:
                target = MediaOutcomeRecord(
                    week_start=row["week_start"],
                    brand=brand_value,
                    product=row["product"],
                    region_code=row["region_code"],
                    source_label=source_value,
                )
                service.db.add(target)

            target.media_spend_eur = row["metrics"].get("media_spend_eur")
            target.impressions = row["metrics"].get("impressions")
            target.clicks = row["metrics"].get("clicks")
            target.qualified_visits = row["metrics"].get("qualified_visits")
            target.search_lift_index = row["metrics"].get("search_lift_index")
            target.sales_units = row["metrics"].get("sales_units")
            target.order_count = row["metrics"].get("order_count")
            target.revenue_eur = row["metrics"].get("revenue_eur")
            target.import_batch_id = batch_id
            target.extra_data = row.get("extra_data") or {}
            target.updated_at = utc_now()
            imported += 1

    coverage_after_import = _project_truth_coverage(
        service,
        brand=brand_value,
        normalized_rows=normalized_rows,
        virus_typ=None,
        replace_existing=replace_existing,
        validate_only=validate_only,
    )

    batch.rows_valid = len(normalized_rows)
    batch.rows_imported = imported
    batch.rows_duplicate = duplicate_count
    batch.rows_rejected = len(parsed_rows) - len(normalized_rows)
    batch.week_min = min((row["week_start"] for row in normalized_rows), default=None)
    batch.week_max = max((row["week_start"] for row in normalized_rows), default=None)
    batch.coverage_after_import = coverage_after_import
    if validate_only:
        batch.status = "validated"
    elif imported and issues:
        batch.status = "partial_success"
    elif imported:
        batch.status = "imported"
    else:
        batch.status = "failed"

    if not validate_only and imported:
        coverage_after_import["last_imported_at"] = batch.uploaded_at.isoformat() if batch.uploaded_at else None
        coverage_after_import["latest_batch_id"] = batch_id
        coverage_after_import["latest_source_label"] = source_value

    for issue in issues:
        issue["batch_id"] = batch_id
    for issue in issues:
        service.db.add(MediaOutcomeImportIssue(**issue))

    service.db.commit()
    service.db.refresh(batch)

    return {
        "imported": imported,
        "batch_id": batch_id,
        "batch_summary": _batch_to_dict(service, batch),
        "issues": [_issue_response(service, issue) for issue in issues],
        "preview_only": validate_only,
        "coverage_after_import": coverage_after_import,
        "coverage": coverage_after_import,
        "message": (
            "Upload validiert. Es wurden noch keine Kundendaten gespeichert."
            if validate_only
            else ("Kundendaten importiert." if imported else "Import abgeschlossen, aber keine Zeilen wurden übernommen.")
        ),
    }


def list_outcome_import_batches(
    service: Any,
    *,
    brand: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    brand_value = normalize_brand(brand)
    rows = (
        service.db.query(MediaOutcomeImportBatch)
        .filter(func.lower(MediaOutcomeImportBatch.brand) == brand_value)
        .order_by(MediaOutcomeImportBatch.uploaded_at.desc(), MediaOutcomeImportBatch.id.desc())
        .limit(limit)
        .all()
    )
    return [_batch_to_dict(service, row) for row in rows]


def get_outcome_import_batch_detail(
    service: Any,
    *,
    batch_id: str,
) -> dict[str, Any] | None:
    batch = (
        service.db.query(MediaOutcomeImportBatch)
        .filter(MediaOutcomeImportBatch.batch_id == batch_id)
        .first()
    )
    if not batch:
        return None
    issues = (
        service.db.query(MediaOutcomeImportIssue)
        .filter(MediaOutcomeImportIssue.batch_id == batch_id)
        .order_by(
            MediaOutcomeImportIssue.row_number.is_(None),
            MediaOutcomeImportIssue.row_number.asc(),
            MediaOutcomeImportIssue.id.asc(),
        )
        .all()
    )
    return {
        "batch": _batch_to_dict(service, batch),
        "issues": [_issue_to_dict(service, issue) for issue in issues],
    }


def delete_outcome_import_batch(
    service: Any,
    *,
    batch_id: str,
) -> dict[str, Any] | None:
    """Admin-only: remove all MediaOutcomeRecords attributed to a batch and
    mark the batch itself as deleted.

    Rationale: Data Office users need to clean up a mistaken import (wrong
    week, wrong product, unit mismatch) without having to touch SQL. The
    batch row stays in history with ``status='deleted'`` so the audit trail
    is preserved; the underlying outcome records are actually removed so
    Truth-Coverage (§ IV in the cockpit) reflects the corrected state.

    Returns ``None`` if the batch is unknown, otherwise a small summary
    payload documenting the side effects of the delete.
    """
    batch = (
        service.db.query(MediaOutcomeImportBatch)
        .filter(MediaOutcomeImportBatch.batch_id == batch_id)
        .first()
    )
    if not batch:
        return None

    rows_deleted = (
        service.db.query(MediaOutcomeRecord)
        .filter(MediaOutcomeRecord.import_batch_id == batch_id)
        .delete(synchronize_session=False)
    )

    batch.status = "deleted"
    batch.rows_imported = 0
    batch.rows_valid = 0
    if hasattr(batch, "deleted_at"):
        batch.deleted_at = utc_now()
    service.db.add(batch)
    service.db.commit()

    return {
        "batch_id": batch_id,
        "status": "deleted",
        "rows_deleted": int(rows_deleted or 0),
    }


def outcome_template_csv(service: Any) -> str:
    return OUTCOME_TEMPLATE_HEADERS


def _collect_outcome_rows(
    service: Any,
    *,
    records: list[dict[str, Any]],
    csv_payload: str | None,
    brand: str,
    source_label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        rows.append({
            "row_number": index,
            "raw_row": dict(record),
            "values": {**record, "brand": brand, "source_label": source_label},
        })

    if csv_payload:
        csv_rows, csv_issues = _parse_csv_payload(
            service,
            csv_payload,
            brand=brand,
            source_label=source_label,
        )
        rows.extend(csv_rows)
        issues.extend(csv_issues)

    return rows, issues


def _parse_csv_payload(
    service: Any,
    csv_payload: str,
    *,
    brand: str,
    source_label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sanitized = csv_payload.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(sanitized))
    fieldnames = [str(name or "").strip() for name in (reader.fieldnames or []) if str(name or "").strip()]

    issues: list[dict[str, Any]] = []
    missing_headers = [
        header for header in ("week_start", "product", "region_code", "media_spend_eur")
        if header not in fieldnames
    ]
    if missing_headers:
        issues.append(_issue_dict(
            service,
            batch_id="preview",
            row_number=None,
            field_name="header",
            issue_code="missing_headers",
            message=f"Folgende CSV-Spalten fehlen: {', '.join(missing_headers)}.",
            raw_row={"fieldnames": fieldnames},
        ))

    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(reader, start=2):
        cleaned = {str(key or "").strip(): value for key, value in raw.items() if str(key or "").strip()}
        cleaned.setdefault("brand", brand)
        cleaned.setdefault("source_label", source_label)
        rows.append({
            "row_number": index,
            "raw_row": cleaned,
            "values": cleaned,
        })
    return rows, issues


def _coerce_week_start(service: Any, value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _float_or_none(service: Any, value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truth_gate(service: Any, truth_coverage: dict[str, Any]) -> dict[str, Any]:
    return service.truth_gate_service.evaluate(truth_coverage)


def _latest_import_batch(service: Any, *, brand: str) -> MediaOutcomeImportBatch | None:
    brand_value = normalize_brand(brand)
    return (
        service.db.query(MediaOutcomeImportBatch)
        .filter(
            func.lower(MediaOutcomeImportBatch.brand) == brand_value,
            MediaOutcomeImportBatch.status.in_(("imported", "partial_success")),
        )
        .order_by(MediaOutcomeImportBatch.uploaded_at.desc(), MediaOutcomeImportBatch.id.desc())
        .first()
    )


def _latest_epi_reference_week(service: Any, *, virus_typ: str | None = None) -> datetime | None:
    wastewater_query = service.db.query(func.max(WastewaterAggregated.datum))
    if virus_typ:
        wastewater_query = wastewater_query.filter(WastewaterAggregated.virus_typ == virus_typ)
    wastewater_max = wastewater_query.scalar()
    if wastewater_max:
        return wastewater_max

    survstat_max = service.db.query(func.max(SurvstatWeeklyData.week_start)).scalar()
    return survstat_max


def _truth_freshness_state(
    service: Any,
    *,
    latest_truth_week: datetime | None,
    reference_week: datetime | None,
) -> str:
    if latest_truth_week is None:
        return "missing"
    if reference_week is None:
        return "unknown"
    return "fresh" if (reference_week - latest_truth_week) <= timedelta(days=14) else "stale"


def _normalize_outcome_row(
    service: Any,
    *,
    row: dict[str, Any],
    brand: str,
    source_label: str,
) -> dict[str, Any]:
    values = row.get("values") or {}
    raw_row = row.get("raw_row") or values
    row_number = row.get("row_number")
    issues: list[dict[str, Any]] = []

    week_start = _coerce_week_start(service, values.get("week_start"))
    if week_start is None:
        issues.append(_issue_dict(
            service,
            batch_id="preview",
            row_number=row_number,
            field_name="week_start",
            issue_code="invalid_week_start",
            message="`week_start` fehlt oder ist kein gültiges ISO-Datum.",
            raw_row=raw_row,
        ))

    product, product_issue = _normalize_outcome_product(
        service,
        brand=brand,
        raw_product=values.get("product"),
    )
    if product_issue:
        issues.append(_issue_dict(
            service,
            batch_id="preview",
            row_number=row_number,
            field_name="product",
            issue_code=product_issue["code"],
            message=product_issue["message"],
            raw_row=raw_row,
        ))

    region_code, region_issue = _normalize_outcome_region(service, values.get("region_code"))
    if region_issue:
        issues.append(_issue_dict(
            service,
            batch_id="preview",
            row_number=row_number,
            field_name="region_code",
            issue_code=region_issue["code"],
            message=region_issue["message"],
            raw_row=raw_row,
        ))

    metrics: dict[str, float | None] = {
        "media_spend_eur": _float_or_none(service, values.get("media_spend_eur")),
        "impressions": _float_or_none(service, values.get("impressions")),
        "clicks": _float_or_none(service, values.get("clicks")),
        "qualified_visits": _float_or_none(service, values.get("qualified_visits")),
        "search_lift_index": _float_or_none(service, values.get("search_lift_index")),
        "sales_units": _float_or_none(service, values.get("sales_units")),
        "order_count": _float_or_none(service, values.get("order_count")),
        "revenue_eur": _float_or_none(service, values.get("revenue_eur")),
    }
    if metrics["media_spend_eur"] is None:
        issues.append(_issue_dict(
            service,
            batch_id="preview",
            row_number=row_number,
            field_name="media_spend_eur",
            issue_code="missing_media_spend",
            message="`media_spend_eur` ist Pflicht und muss numerisch befüllt sein.",
            raw_row=raw_row,
        ))
    if not any(metrics[field_name] is not None for field_name in CONVERSION_OUTCOME_FIELD_NAMES):
        issues.append(_issue_dict(
            service,
            batch_id="preview",
            row_number=row_number,
            field_name="conversion",
            issue_code="missing_conversion_metric",
            message="Mindestens eine Wirkungszahl (`sales_units`, `order_count` oder `revenue_eur`) ist erforderlich.",
            raw_row=raw_row,
        ))

    extra_data = values.get("extra_data")
    if extra_data is None:
        extra_data = {}
    elif not isinstance(extra_data, dict):
        extra_data = {"raw_extra_data": extra_data}

    return {
        "issues": issues,
        "week_start": week_start,
        "product": product,
        "region_code": region_code,
        "brand": brand,
        "source_label": source_label,
        "metrics": metrics,
        "extra_data": extra_data,
    }


def _normalize_outcome_product(
    service: Any,
    *,
    brand: str,
    raw_product: Any,
) -> tuple[str | None, dict[str, str] | None]:
    raw_value = str(raw_product or "").strip()
    if not raw_value:
        return None, {"code": "missing_product", "message": "Produktname fehlt."}

    normalized = ProductCatalogService._normalize_name(raw_value)
    compact = "".join(ch for ch in normalized if ch.isalnum())
    products = (
        service.db.query(BrandProduct)
        .filter(
            func.lower(BrandProduct.brand) == normalize_brand(brand),
            BrandProduct.active.is_(True),
        )
        .all()
    )
    if not products:
        return None, {
            "code": "missing_product_catalog",
            "message": f"Für die Marke `{brand}` ist kein aktiver Produktkatalog vorhanden.",
        }

    exact_map: dict[str, str] = {}
    compact_map: dict[str, str] = {}
    for product in products:
        canonical_name = str(product.product_name or "").strip()
        normalized_name = ProductCatalogService._normalize_name(canonical_name)
        if normalized_name:
            exact_map.setdefault(normalized_name, canonical_name)
            compact_map.setdefault("".join(ch for ch in normalized_name if ch.isalnum()), canonical_name)

    if normalized in exact_map:
        return exact_map[normalized], None
    if compact in compact_map:
        return compact_map[compact], None

    fuzzy_matches = [
        canonical
        for norm_name, canonical in exact_map.items()
        if normalized in norm_name or norm_name in normalized
    ]
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0], None

    return None, {
        "code": "unknown_product",
        "message": f"Produkt `{raw_value}` konnte nicht auf den aktiven Produktkatalog gemappt werden.",
    }


def _normalize_outcome_region(service: Any, raw_region: Any) -> tuple[str | None, dict[str, str] | None]:
    raw_value = str(raw_region or "").strip()
    if not raw_value:
        return None, {"code": "missing_region", "message": "Region fehlt."}

    if raw_value.lower() in {"de", "deutschland", "national"}:
        return "DE", None
    normalized = normalize_region_code(raw_value)
    if normalized in BUNDESLAND_NAMES:
        return normalized, None
    return None, {
        "code": "invalid_region",
        "message": f"Region `{raw_value}` ist weder ein Bundesland-Code noch ein bekannter Bundeslandname.",
    }


def _find_existing_outcome(
    service: Any,
    *,
    brand: str,
    source_label: str,
    week_start: datetime,
    product: str,
    region_code: str,
) -> MediaOutcomeRecord | None:
    return (
        service.db.query(MediaOutcomeRecord)
        .filter(
            MediaOutcomeRecord.week_start == week_start,
            func.lower(MediaOutcomeRecord.brand) == brand,
            MediaOutcomeRecord.product == product,
            MediaOutcomeRecord.region_code == region_code,
            MediaOutcomeRecord.source_label == source_label,
        )
        .first()
    )


def _project_truth_coverage(
    service: Any,
    *,
    brand: str,
    normalized_rows: list[dict[str, Any]],
    virus_typ: str | None,
    replace_existing: bool,
    validate_only: bool,
) -> dict[str, Any]:
    brand_value = normalize_brand(brand)
    existing_rows = (
        service.db.query(MediaOutcomeRecord)
        .filter(func.lower(MediaOutcomeRecord.brand) == brand_value)
        .all()
    )
    synthetic_rows = [
        {
            "week_start": row.week_start,
            "brand": row.brand,
            "product": row.product,
            "region_code": row.region_code,
            "source_label": row.source_label,
            "metrics": {
                field_name: getattr(row, field_name)
                for field_name in (
                    *REQUIRED_OUTCOME_FIELD_NAMES,
                    *CONVERSION_OUTCOME_FIELD_NAMES,
                    *OPTIONAL_OUTCOME_FIELD_NAMES,
                )
            },
        }
        for row in existing_rows
    ]
    keyed_rows: dict[tuple[str, str, datetime, str, str], dict[str, Any]] = {}
    for row in synthetic_rows:
        key = (
            str(row["brand"]).lower(),
            str(row["source_label"]),
            row["week_start"],
            str(row["product"]),
            str(row["region_code"]),
        )
        keyed_rows[key] = row

    for row in normalized_rows:
        key = (
            brand_value,
            str(row["source_label"]),
            row["week_start"],
            row["product"],
            row["region_code"],
        )
        if key in keyed_rows and not replace_existing and validate_only:
            continue
        keyed_rows[key] = {
            "week_start": row["week_start"],
            "brand": brand_value,
            "product": row["product"],
            "region_code": row["region_code"],
            "source_label": row["source_label"],
            "metrics": row["metrics"],
        }
    return _coverage_from_rows(service, list(keyed_rows.values()), brand=brand_value, virus_typ=virus_typ)


def _coverage_from_rows(
    service: Any,
    rows: list[dict[str, Any]],
    *,
    brand: str,
    virus_typ: str | None,
) -> dict[str, Any]:
    latest_import_batch = _latest_import_batch(service, brand=brand)
    reference_week = _latest_epi_reference_week(service, virus_typ=virus_typ)
    if not rows:
        return {
            "coverage_weeks": 0,
            "latest_week": None,
            "regions_covered": 0,
            "products_covered": 0,
            "outcome_fields_present": [],
            "required_fields_present": [],
            "conversion_fields_present": [],
            "trust_readiness": "noch_nicht_angeschlossen",
            "truth_freshness_state": "missing",
            "source_labels": [],
            "last_imported_at": latest_import_batch.uploaded_at.isoformat() if latest_import_batch and latest_import_batch.uploaded_at else None,
            "latest_batch_id": latest_import_batch.batch_id if latest_import_batch else None,
            "latest_source_label": latest_import_batch.source_label if latest_import_batch else None,
        }

    week_values = sorted({row["week_start"] for row in rows if row.get("week_start")})
    weeks = [value.date().isoformat() for value in week_values]
    regions = {str(row.get("region_code")) for row in rows if row.get("region_code")}
    products = {str(row.get("product")) for row in rows if row.get("product")}
    source_labels = sorted({str(row.get("source_label")) for row in rows if row.get("source_label")})
    fields_present = [
        label
        for field_name, label in METRIC_FIELD_LABELS.items()
        if any((row.get("metrics") or {}).get(field_name) is not None for row in rows)
    ]
    required_fields_present = [
        METRIC_FIELD_LABELS[field_name]
        for field_name in REQUIRED_OUTCOME_FIELD_NAMES
        if any((row.get("metrics") or {}).get(field_name) is not None for row in rows)
    ]
    conversion_fields_present = [
        METRIC_FIELD_LABELS[field_name]
        for field_name in CONVERSION_OUTCOME_FIELD_NAMES
        if any((row.get("metrics") or {}).get(field_name) is not None for row in rows)
    ]
    coverage_weeks = len(weeks)
    if coverage_weeks >= 52:
        readiness = "belastbar"
    elif coverage_weeks >= 26:
        readiness = "im_aufbau"
    elif coverage_weeks > 0:
        readiness = "erste_signale"
    else:
        readiness = "noch_nicht_angeschlossen"

    latest_week_dt = week_values[-1] if week_values else None
    return {
        "coverage_weeks": coverage_weeks,
        "latest_week": weeks[-1] if weeks else None,
        "regions_covered": len(regions),
        "products_covered": len(products),
        "outcome_fields_present": fields_present,
        "required_fields_present": required_fields_present,
        "conversion_fields_present": conversion_fields_present,
        "trust_readiness": readiness,
        "truth_freshness_state": _truth_freshness_state(
            service,
            latest_truth_week=latest_week_dt,
            reference_week=reference_week,
        ),
        "source_labels": source_labels,
        "last_imported_at": latest_import_batch.uploaded_at.isoformat() if latest_import_batch and latest_import_batch.uploaded_at else None,
        "latest_batch_id": latest_import_batch.batch_id if latest_import_batch else None,
        "latest_source_label": latest_import_batch.source_label if latest_import_batch else None,
    }


def _issue_dict(
    service: Any,
    *,
    batch_id: str,
    row_number: int | None,
    field_name: str | None,
    issue_code: str,
    message: str,
    raw_row: Any,
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "row_number": row_number,
        "field_name": field_name,
        "issue_code": issue_code,
        "message": message,
        "raw_row": raw_row,
    }


def _issue_response(service: Any, issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_number": issue.get("row_number"),
        "field_name": issue.get("field_name"),
        "issue_code": issue.get("issue_code"),
        "message": issue.get("message"),
        "raw_row": issue.get("raw_row"),
    }


def _issue_to_dict(service: Any, issue: MediaOutcomeImportIssue) -> dict[str, Any]:
    return {
        "row_number": issue.row_number,
        "field_name": issue.field_name,
        "issue_code": issue.issue_code,
        "message": issue.message,
        "raw_row": issue.raw_row,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
    }


def _batch_to_dict(service: Any, batch: MediaOutcomeImportBatch) -> dict[str, Any]:
    return {
        "batch_id": getattr(batch, "batch_id", None),
        "brand": getattr(batch, "brand", None),
        "source_label": getattr(batch, "source_label", None),
        "source_system": getattr(batch, "source_system", None),
        "external_batch_id": getattr(batch, "external_batch_id", None),
        "ingestion_mode": getattr(batch, "ingestion_mode", None),
        "file_name": getattr(batch, "file_name", None),
        "status": getattr(batch, "status", None),
        "rows_total": getattr(batch, "rows_total", None),
        "rows_valid": getattr(batch, "rows_valid", None),
        "rows_imported": getattr(batch, "rows_imported", None),
        "rows_rejected": getattr(batch, "rows_rejected", None),
        "rows_duplicate": getattr(batch, "rows_duplicate", None),
        "week_min": batch.week_min.isoformat() if getattr(batch, "week_min", None) else None,
        "week_max": batch.week_max.isoformat() if getattr(batch, "week_max", None) else None,
        "coverage_after_import": getattr(batch, "coverage_after_import", None) or {},
        "uploaded_at": batch.uploaded_at.isoformat() if getattr(batch, "uploaded_at", None) else None,
    }
