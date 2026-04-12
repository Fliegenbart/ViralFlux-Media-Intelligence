from __future__ import annotations
from app.core.time import utc_now

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.database import (
    MediaOutcomeImportBatch,
    MediaOutcomeImportIssue,
    MediaOutcomeRecord,
)
from app.services.media.truth_layer_contracts import OutcomeObservationInput
from app.services.media.truth_layer_service import (
    SUPPORTED_OUTCOME_METRICS,
    TruthLayerService,
)
from app.services.media.v2_service import MediaV2Service


_OBSERVATION_TO_RECORD_FIELD = {
    "media_spend": "media_spend_eur",
    "impressions": "impressions",
    "clicks": "clicks",
    "qualified_visits": "qualified_visits",
    "search_demand": "search_lift_index",
    "sales": "sales_units",
    "orders": "order_count",
    "revenue": "revenue_eur",
    "campaign_response": "qualified_visits",
}


class OutcomeIngestionService:
    """Official machine-to-machine ingestion path for GELO outcome observations."""

    def __init__(self, db: Session):
        self.db = db
        self.media_service = MediaV2Service(db)
        self.truth_layer_service = TruthLayerService(db)

    @staticmethod
    def _normalize_brand(brand: str) -> str:
        if brand is None:
            raise ValueError("brand must be provided")
        brand_value = str(brand).strip().lower()
        if not brand_value:
            raise ValueError("brand must be a non-empty string")
        return brand_value

    def ingest_outcomes(
        self,
        *,
        brand: str,
        source_system: str,
        external_batch_id: str,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        brand_value = self._normalize_brand(brand)
        source_value = str(source_system or "").strip().lower()
        external_id_value = str(external_batch_id or "").strip()
        existing_batch = self._existing_batch(
            source_system=source_value,
            external_batch_id=external_id_value,
        )
        if existing_batch is not None:
            detail = self.media_service.get_outcome_import_batch_detail(
                batch_id=existing_batch.batch_id,
            ) or {
                "batch": self.media_service._batch_to_dict(existing_batch),
                "issues": [],
            }
            return {
                "imported": existing_batch.rows_imported,
                "inserted": 0,
                "updated": 0,
                "batch_id": existing_batch.batch_id,
                "batch_summary": detail["batch"],
                "issues": detail["issues"],
                "preview_only": False,
                "coverage_after_import": detail["batch"].get("coverage_after_import") or {},
                "coverage": detail["batch"].get("coverage_after_import") or {},
                "idempotent_replay": True,
                "message": "Batch already processed. Returning the archived ingestion result.",
            }

        batch_id = uuid.uuid4().hex[:12]
        batch = MediaOutcomeImportBatch(
            batch_id=batch_id,
            brand=brand_value,
            source_label=source_value,
            source_system=source_value,
            external_batch_id=external_id_value,
            ingestion_mode="api_ingest",
            status="failed",
            rows_total=len(observations),
            uploaded_at=utc_now(),
        )
        self.db.add(batch)
        self.db.flush()

        issues: list[dict[str, Any]] = []
        normalized_rows: list[dict[str, Any]] = []
        duplicate_count = 0
        seen_keys: set[tuple[str, str, str, str, str, str]] = set()

        if not observations:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    row_number=None,
                    field_name="observations",
                    issue_code="empty_batch",
                    message="At least one outcome observation is required.",
                    raw_row={},
                )
            )

        for row_number, row in enumerate(observations, start=1):
            normalized = self._normalize_observation(
                row_number=row_number,
                row=row,
                brand=brand_value,
                source_label=source_value,
                batch_id=batch_id,
                source_system=source_value,
                external_batch_id=external_id_value,
            )
            if normalized["issues"]:
                issues.extend(normalized["issues"])
                continue

            observation = normalized["observation"]
            dedupe_key = (
                observation.brand,
                observation.product,
                observation.region_code,
                observation.metric_name,
                observation.window_start.isoformat(),
                observation.window_end.isoformat(),
            )
            if dedupe_key in seen_keys:
                duplicate_count += 1
                issues.append(
                    self._issue(
                        batch_id=batch_id,
                        row_number=row_number,
                        field_name="observation",
                        issue_code="duplicate_in_batch",
                        message="This observation scope and metric appears multiple times in the same batch.",
                        raw_row=row,
                    )
                )
                continue
            seen_keys.add(dedupe_key)
            normalized_rows.append(normalized)

        inserted = 0
        updated = 0
        imported = 0
        if normalized_rows:
            truth_result = self.truth_layer_service.upsert_observations(
                [item["observation"] for item in normalized_rows],
                commit=False,
            )
            inserted = int(truth_result.get("inserted") or 0)
            updated = int(truth_result.get("updated") or 0)
            imported = int(truth_result.get("total") or 0)
            self._sync_media_outcome_records(
                rows=normalized_rows,
                batch_id=batch_id,
                source_label=source_value,
            )

        for issue in issues:
            self.db.add(MediaOutcomeImportIssue(**issue))

        batch.rows_valid = len(normalized_rows)
        batch.rows_imported = imported
        batch.rows_duplicate = duplicate_count
        batch.rows_rejected = len(observations) - len(normalized_rows)
        batch.week_min = min(
            (item["observation"].window_start for item in normalized_rows),
            default=None,
        )
        batch.week_max = max(
            (item["observation"].window_start for item in normalized_rows),
            default=None,
        )
        if imported and issues:
            batch.status = "partial_success"
        elif imported:
            batch.status = "imported"
        else:
            batch.status = "failed"
        self.db.flush()
        coverage_after_import = self.media_service.get_truth_coverage(
            brand=brand_value,
        )
        batch.coverage_after_import = coverage_after_import

        self.db.commit()
        self.db.refresh(batch)

        return {
            "imported": imported,
            "inserted": inserted,
            "updated": updated,
            "batch_id": batch_id,
            "batch_summary": self.media_service._batch_to_dict(batch),
            "issues": [self.media_service._issue_response(issue) for issue in issues],
            "preview_only": False,
            "coverage_after_import": coverage_after_import,
            "coverage": coverage_after_import,
            "idempotent_replay": False,
            "message": "Outcome observations ingested successfully." if imported else "No valid outcome observations were ingested.",
        }

    def _existing_batch(
        self,
        *,
        source_system: str,
        external_batch_id: str,
    ) -> MediaOutcomeImportBatch | None:
        return (
            self.db.query(MediaOutcomeImportBatch)
            .filter(MediaOutcomeImportBatch.source_system == source_system)
            .filter(MediaOutcomeImportBatch.external_batch_id == external_batch_id)
            .first()
        )

    def _normalize_observation(
        self,
        *,
        row_number: int,
        row: dict[str, Any],
        brand: str,
        source_label: str,
        batch_id: str,
        source_system: str,
        external_batch_id: str,
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        raw_row = dict(row or {})
        product, product_issue = self.media_service._normalize_outcome_product(
            brand=brand,
            raw_product=raw_row.get("product"),
        )
        if product_issue:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    row_number=row_number,
                    field_name="product",
                    issue_code=product_issue["code"],
                    message=product_issue["message"],
                    raw_row=raw_row,
                )
            )

        region_code, region_issue = self.media_service._normalize_outcome_region(
            raw_row.get("region_code"),
        )
        if region_issue:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    row_number=row_number,
                    field_name="region_code",
                    issue_code=region_issue["code"],
                    message=region_issue["message"],
                    raw_row=raw_row,
                )
            )

        window_start = self.media_service._coerce_week_start(raw_row.get("window_start"))
        window_end = self.media_service._coerce_week_start(raw_row.get("window_end"))
        if window_start is None:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    row_number=row_number,
                    field_name="window_start",
                    issue_code="invalid_window_start",
                    message="`window_start` is missing or not a valid ISO datetime.",
                    raw_row=raw_row,
                )
            )
        if window_end is None:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    row_number=row_number,
                    field_name="window_end",
                    issue_code="invalid_window_end",
                    message="`window_end` is missing or not a valid ISO datetime.",
                    raw_row=raw_row,
                )
            )
        if window_start is not None and window_end is not None and window_end < window_start:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    row_number=row_number,
                    field_name="window_end",
                    issue_code="invalid_window_range",
                    message="`window_end` must be on or after `window_start`.",
                    raw_row=raw_row,
                )
            )

        metric_name = self.truth_layer_service._normalize_metric_name(
            str(raw_row.get("metric_name") or ""),
        )
        if metric_name not in SUPPORTED_OUTCOME_METRICS:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    row_number=row_number,
                    field_name="metric_name",
                    issue_code="unsupported_metric_name",
                    message=f"`metric_name` {raw_row.get('metric_name')!r} is not supported.",
                    raw_row=raw_row,
                )
            )

        metric_value = self.media_service._float_or_none(raw_row.get("metric_value"))
        if metric_value is None:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    row_number=row_number,
                    field_name="metric_value",
                    issue_code="invalid_metric_value",
                    message="`metric_value` is required and must be numeric.",
                    raw_row=raw_row,
                )
            )

        confidence_hint = raw_row.get("confidence_hint")
        confidence_value = None
        if confidence_hint not in (None, ""):
            confidence_value = self.media_service._float_or_none(confidence_hint)
            if confidence_value is None or confidence_value < 0.0 or confidence_value > 1.0:
                issues.append(
                    self._issue(
                        batch_id=batch_id,
                        row_number=row_number,
                        field_name="confidence_hint",
                        issue_code="invalid_confidence_hint",
                        message="`confidence_hint` must be between 0.0 and 1.0 when provided.",
                        raw_row=raw_row,
                    )
                )

        metadata = raw_row.get("metadata")
        if metadata is None:
            metadata = {}
        elif not isinstance(metadata, dict):
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    row_number=row_number,
                    field_name="metadata",
                    issue_code="invalid_metadata",
                    message="`metadata` must be a JSON object when provided.",
                    raw_row=raw_row,
                )
            )
            metadata = {}

        if issues:
            return {"issues": issues}

        observation = OutcomeObservationInput(
            brand=brand,
            product=str(product),
            region_code=str(region_code),
            metric_name=metric_name,
            metric_value=float(metric_value),
            window_start=window_start,
            window_end=window_end,
            source_label=source_label,
            metric_unit=str(raw_row.get("metric_unit")).strip() if raw_row.get("metric_unit") else None,
            channel=str(raw_row.get("channel")).strip().lower() if raw_row.get("channel") else None,
            campaign_id=str(raw_row.get("campaign_id")).strip() if raw_row.get("campaign_id") else None,
            holdout_group=str(raw_row.get("holdout_group")).strip().lower() if raw_row.get("holdout_group") else None,
            confidence_hint=confidence_value,
            metadata={
                **metadata,
                "source_system": source_system,
                "external_batch_id": external_batch_id,
                "ingestion_mode": "api_ingest",
            },
        )
        return {
            "issues": [],
            "observation": observation,
            "raw_row": raw_row,
        }

    def _sync_media_outcome_records(
        self,
        *,
        rows: list[dict[str, Any]],
        batch_id: str,
        source_label: str,
    ) -> None:
        grouped: dict[tuple[str, str, datetime, str], dict[str, Any]] = {}
        for item in rows:
            observation: OutcomeObservationInput = item["observation"]
            key = (
                observation.brand,
                observation.product,
                observation.window_start,
                observation.region_code,
            )
            bucket = grouped.setdefault(
                key,
                {
                    "brand": observation.brand,
                    "product": observation.product,
                    "week_start": observation.window_start,
                    "region_code": observation.region_code,
                    "metrics": {},
                    "extra_data": {},
                },
            )
            record_field = _OBSERVATION_TO_RECORD_FIELD.get(observation.metric_name)
            if record_field is not None:
                bucket["metrics"][record_field] = float(observation.metric_value)
            extra_data = bucket["extra_data"]
            if observation.channel:
                extra_data["channel"] = observation.channel
            if observation.campaign_id:
                extra_data["campaign_id"] = observation.campaign_id
            if observation.holdout_group:
                extra_data["holdout_group"] = observation.holdout_group
            if observation.confidence_hint is not None:
                extra_data["confidence_hint"] = float(observation.confidence_hint)
            if observation.metadata:
                extra_data.update(dict(observation.metadata))
            extra_data["outcome_window_end"] = observation.window_end.isoformat()

        for item in grouped.values():
            target = self.media_service._find_existing_outcome(
                brand=item["brand"],
                source_label=source_label,
                week_start=item["week_start"],
                product=item["product"],
                region_code=item["region_code"],
            )
            if target is None:
                target = MediaOutcomeRecord(
                    week_start=item["week_start"],
                    brand=item["brand"],
                    product=item["product"],
                    region_code=item["region_code"],
                    source_label=source_label,
                )
                self.db.add(target)

            for field_name, value in item["metrics"].items():
                setattr(target, field_name, value)
            merged_extra = dict(target.extra_data or {})
            merged_extra.update(item["extra_data"])
            merged_extra["ingestion_mode"] = "api_ingest"
            target.extra_data = merged_extra
            target.import_batch_id = batch_id
            target.updated_at = utc_now()

    def _issue(
        self,
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
            "raw_row": self._json_safe(raw_row),
        }

    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        return str(value)
