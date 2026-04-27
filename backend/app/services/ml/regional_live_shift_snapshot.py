"""Read-only five-day regional shift snapshot from persisted forecasts.

This module answers the operational media question:
"Where does the visible regional burden rise over the next five days?"

It deliberately separates ranking from budget release. A region can be a
candidate because the curve rises, while still being blocked for real spend
because the model is an inline fallback or the input data is stale.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import MediaOutcomeRecord, MLForecast
from app.services.ml.forecast_horizon_utils import ensure_supported_horizon
from app.services.ml.regional_panel_utils import ALL_BUNDESLAENDER, BUNDESLAND_NAMES


DEFAULT_SHIFT_VIRUSES: tuple[str, ...] = ("Influenza A", "Influenza B", "RSV A")
DEFAULT_MIN_CHANGE_PCT = 10.0
DEFAULT_MAX_FEATURE_GAP_DAYS = 10
DEFAULT_MIN_BUSINESS_WEEKS = 4
DEFAULT_MIN_BUSINESS_REGIONS = 8
INLINE_MODEL_MARKER = "_inline"


def _round_or_none(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _date_from_value(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _feature_freshness(row: MLForecast) -> dict[str, Any]:
    payload = row.features_used or {}
    if not isinstance(payload, dict):
        return {}
    freshness = payload.get("feature_freshness") or {}
    return dict(freshness) if isinstance(freshness, dict) else {}


def _forecast_quality(row: MLForecast) -> dict[str, Any]:
    payload = row.features_used or {}
    if not isinstance(payload, dict):
        return {}
    quality = payload.get("forecast_quality") or payload.get("quality_gate") or {}
    return dict(quality) if isinstance(quality, dict) else {}


def _normalise_virus_types(virus_types: Iterable[str] | None) -> list[str]:
    if virus_types is None:
        return list(DEFAULT_SHIFT_VIRUSES)
    seen: set[str] = set()
    result: list[str] = []
    for item in virus_types:
        virus = str(item or "").strip()
        if not virus or virus in seen:
            continue
        seen.add(virus)
        result.append(virus)
    return result or list(DEFAULT_SHIFT_VIRUSES)


class RegionalLiveShiftSnapshotService:
    """Build budget-gated regional h5 shift candidates from ``ml_forecasts``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def build_snapshot(
        self,
        *,
        virus_types: Iterable[str] | None = None,
        horizon_days: int = 5,
        top_n: int = 5,
        max_feature_gap_days: int = DEFAULT_MAX_FEATURE_GAP_DAYS,
        min_change_pct: float = DEFAULT_MIN_CHANGE_PCT,
        brand: str = "gelo",
        require_business_validation: bool = True,
        min_business_weeks: int = DEFAULT_MIN_BUSINESS_WEEKS,
        min_business_regions: int = DEFAULT_MIN_BUSINESS_REGIONS,
    ) -> dict[str, Any]:
        horizon = ensure_supported_horizon(horizon_days)
        viruses = _normalise_virus_types(virus_types)
        top_limit = max(1, int(top_n or 1))
        max_gap = max(0, int(max_feature_gap_days))
        min_pct = max(0.0, float(min_change_pct))
        business_validation = self._business_validation_status(
            brand=brand,
            required=require_business_validation,
            min_weeks=min_business_weeks,
            min_regions=min_business_regions,
        )

        rows = (
            self.db.query(MLForecast)
            .filter(
                MLForecast.virus_typ.in_(viruses),
                MLForecast.horizon_days == horizon,
                MLForecast.region.in_(ALL_BUNDESLAENDER),
            )
            .order_by(
                MLForecast.virus_typ.asc(),
                MLForecast.region.asc(),
                MLForecast.created_at.desc(),
                MLForecast.forecast_date.asc(),
                MLForecast.id.asc(),
            )
            .all()
        )
        latest_groups = self._latest_groups(rows)

        viruses_payload: dict[str, Any] = {}
        all_regions: list[dict[str, Any]] = []
        missing_by_virus: dict[str, list[str]] = {}
        blocker_counts: Counter[str] = Counter()
        status_counts: Counter[str] = Counter()

        for virus in viruses:
            region_items = [
                self._build_region_item(
                    virus_typ=virus,
                    region=region,
                    rows=latest_groups.get((virus, region), []),
                    horizon_days=horizon,
                    max_feature_gap_days=max_gap,
                    min_change_pct=min_pct,
                    business_validation=business_validation,
                )
                for region in ALL_BUNDESLAENDER
                if latest_groups.get((virus, region))
            ]
            region_items = self._score_and_sort(region_items)
            top_candidates = [
                item
                for item in region_items
                if item["increase_detected"] and item["budget_release_status"] in {"go", "candidate_only"}
            ][:top_limit]
            missing = [region for region in ALL_BUNDESLAENDER if (virus, region) not in latest_groups]
            missing_by_virus[virus] = missing
            for item in region_items:
                all_regions.append(item)
                status_counts[item["budget_release_status"]] += 1
                blocker_counts.update(item.get("blockers") or [])

            viruses_payload[virus] = {
                "regions_with_forecast": len(region_items),
                "expected_regions": len(ALL_BUNDESLAENDER),
                "missing_regions": missing,
                "top_candidates": top_candidates,
                "regions": region_items,
            }

        global_top = sorted(
            [
                item
                for item in all_regions
                if item["increase_detected"] and item["budget_release_status"] in {"go", "candidate_only"}
            ],
            key=lambda item: float(item.get("candidate_score") or 0.0),
            reverse=True,
        )[:top_limit]
        budget_gate_status = self._budget_gate_status(status_counts=status_counts, top_regions=global_top)

        return {
            "horizon_days": horizon,
            "policy": {
                "min_change_pct": min_pct,
                "max_feature_gap_days": max_gap,
                "inline_model_policy": "candidate_only",
                "business_validation_policy": (
                    "required_for_budget_release"
                    if require_business_validation
                    else "not_required"
                ),
                "expected_regions": list(ALL_BUNDESLAENDER),
            },
            "summary": {
                "budget_gate_status": budget_gate_status,
                "business_validation": business_validation,
                "total_forecast_groups": len(all_regions),
                "budget_releasable_regions": status_counts.get("go", 0),
                "candidate_regions": status_counts.get("candidate_only", 0),
                "blocked_regions": status_counts.get("blocked", 0),
                "watch_regions": status_counts.get("watch", 0),
                "missing_regions_by_virus": missing_by_virus,
                "blocker_counts": dict(sorted(blocker_counts.items())),
                "top_regions": global_top,
            },
            "viruses": viruses_payload,
        }

    @staticmethod
    def _latest_groups(rows: list[MLForecast]) -> dict[tuple[str, str], list[MLForecast]]:
        latest_created: dict[str, datetime] = {}
        for row in rows:
            key = str(row.virus_typ)
            created_at = row.created_at or datetime.min
            if key not in latest_created or created_at > latest_created[key]:
                latest_created[key] = created_at

        groups: dict[tuple[str, str], list[MLForecast]] = {}
        for row in rows:
            virus = str(row.virus_typ)
            if (row.created_at or datetime.min) == latest_created.get(virus):
                groups.setdefault((virus, str(row.region).upper()), []).append(row)
        for key, group_rows in groups.items():
            groups[key] = sorted(group_rows, key=lambda item: (item.forecast_date, item.id or 0))
        return groups

    def _build_region_item(
        self,
        *,
        virus_typ: str,
        region: str,
        rows: list[MLForecast],
        horizon_days: int,
        max_feature_gap_days: int,
        min_change_pct: float,
        business_validation: dict[str, Any],
    ) -> dict[str, Any]:
        first = rows[0]
        last = rows[-1]
        start_value = float(first.predicted_value or 0.0)
        end_value = float(last.predicted_value or 0.0)
        absolute_delta = end_value - start_value
        change_pct = ((absolute_delta / start_value) * 100.0) if start_value > 0 else None
        increase_detected = bool(absolute_delta > 0.0 and (change_pct or 0.0) >= min_change_pct)

        freshness = _feature_freshness(last)
        feature_as_of = _date_from_value(freshness.get("feature_as_of"))
        issue_date = _date_from_value(freshness.get("issue_date")) or _date_from_value(last.created_at)
        feature_gap_days = (
            int((issue_date - feature_as_of).days)
            if issue_date is not None and feature_as_of is not None
            else None
        )
        extension_reason = str(freshness.get("extension_reason") or "").strip() or None
        extension_applied = bool(freshness.get("extension_applied"))

        blockers: list[str] = []
        warnings: list[str] = []
        if len(rows) < horizon_days:
            blockers.append("incomplete_horizon")
        if feature_gap_days is None:
            blockers.append("missing_feature_freshness")
        elif feature_gap_days > max_feature_gap_days:
            blockers.append("feature_gap_too_large")
        if extension_reason == "gap_too_large":
            blockers.append("feature_extension_failed")
        if extension_reason == "extended" and not extension_applied:
            blockers.append("feature_extension_inconsistent")

        model_version = str(last.model_version or "")
        inline_model = INLINE_MODEL_MARKER in model_version
        if inline_model:
            blockers.append("model_not_promoted_inline")

        forecast_quality = _forecast_quality(last)
        model_quality_gate_passed = forecast_quality.get("overall_passed")
        if not forecast_quality:
            blockers.append("missing_model_quality_gate")
            quality_allows_budget = False
        else:
            quality_allows_budget = model_quality_gate_passed is True
            if not quality_allows_budget:
                blockers.append("model_quality_gate_not_passed")
        model_forecast_readiness = str(
            forecast_quality.get("forecast_readiness") or ""
        ).strip() or None
        business_allows_budget = bool(
            business_validation.get("validated_for_budget_activation")
        )
        if not business_allows_budget:
            blockers.append("business_validation_missing")

        hard_blockers = {
            "incomplete_horizon",
            "missing_feature_freshness",
            "feature_gap_too_large",
            "feature_extension_failed",
            "feature_extension_inconsistent",
        }
        if any(blocker in hard_blockers for blocker in blockers):
            budget_release_status = "blocked"
        elif not increase_detected:
            budget_release_status = "watch"
        elif inline_model or not quality_allows_budget or not business_allows_budget:
            budget_release_status = "candidate_only"
        else:
            budget_release_status = "go"

        if feature_gap_days is not None and feature_gap_days > 0:
            warnings.append(f"features_are_{feature_gap_days}_days_old")
        if inline_model:
            warnings.append("inline_fallback_model_not_promoted")
        if not quality_allows_budget:
            warnings.append("model_quality_gate_not_passed")
        if not business_allows_budget:
            warnings.append("business_validation_missing")

        return {
            "virus_typ": virus_typ,
            "region": region,
            "region_name": BUNDESLAND_NAMES.get(region, region),
            "horizon_days": horizon_days,
            "forecast_start_date": first.forecast_date.date().isoformat(),
            "forecast_end_date": last.forecast_date.date().isoformat(),
            "created_at": last.created_at.isoformat() if last.created_at else None,
            "model_version": model_version or None,
            "model_quality_gate_passed": (
                bool(model_quality_gate_passed)
                if model_quality_gate_passed is not None
                else None
            ),
            "model_forecast_readiness": model_forecast_readiness,
            "start_value": _round_or_none(start_value, 1),
            "end_value": _round_or_none(end_value, 1),
            "absolute_delta": _round_or_none(absolute_delta, 1),
            "change_pct": _round_or_none(change_pct, 2),
            "increase_detected": increase_detected,
            "outbreak_risk_score": _round_or_none(last.outbreak_risk_score, 3),
            "confidence": _round_or_none(last.confidence, 3),
            "feature_as_of": feature_as_of.isoformat() if feature_as_of else None,
            "issue_date": issue_date.isoformat() if issue_date else None,
            "feature_gap_days": feature_gap_days,
            "feature_extension_reason": extension_reason,
            "budget_release_status": budget_release_status,
            "budget_releasable": budget_release_status == "go",
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "forecast_points": len(rows),
        }

    @staticmethod
    def _score_and_sort(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        max_delta = max((max(float(item.get("absolute_delta") or 0.0), 0.0) for item in items), default=0.0)
        for item in items:
            change_pct = max(float(item.get("change_pct") or 0.0), 0.0)
            delta = max(float(item.get("absolute_delta") or 0.0), 0.0)
            risk = max(0.0, min(float(item.get("outbreak_risk_score") or 0.0), 1.0))
            confidence = max(0.0, min(float(item.get("confidence") or 0.0), 1.0))
            feature_gap = item.get("feature_gap_days")
            freshness = 0.0
            if feature_gap is not None:
                freshness = max(0.0, 1.0 - min(float(feature_gap), 30.0) / 30.0)
            score = (
                min(change_pct, 300.0) / 300.0 * 0.34
                + (delta / max_delta if max_delta > 0 else 0.0) * 0.30
                + risk * 0.18
                + confidence * 0.10
                + freshness * 0.08
            )
            if item["budget_release_status"] == "blocked":
                score *= 0.25
            elif item["budget_release_status"] == "watch":
                score *= 0.10
            item["candidate_score"] = round(score * 100.0, 2)
        return sorted(
            items,
            key=lambda item: (
                item["budget_release_status"] == "go",
                item["budget_release_status"] == "candidate_only",
                float(item.get("candidate_score") or 0.0),
            ),
            reverse=True,
        )

    def _business_validation_status(
        self,
        *,
        brand: str,
        required: bool,
        min_weeks: int,
        min_regions: int,
    ) -> dict[str, Any]:
        brand_key = str(brand or "gelo").strip().lower()
        rows = (
            self.db.query(
                func.count(MediaOutcomeRecord.id).label("rows"),
                func.count(func.distinct(MediaOutcomeRecord.week_start)).label("weeks"),
                func.count(func.distinct(MediaOutcomeRecord.region_code)).label("regions"),
                func.sum(MediaOutcomeRecord.sales_units).label("sales_units"),
                func.sum(MediaOutcomeRecord.media_spend_eur).label("media_spend_eur"),
            )
            .filter(func.lower(MediaOutcomeRecord.brand) == brand_key)
            .one()
        )
        row_count = int(rows.rows or 0)
        weeks = int(rows.weeks or 0)
        regions = int(rows.regions or 0)
        sales_units = float(rows.sales_units or 0.0)
        media_spend_eur = float(rows.media_spend_eur or 0.0)
        has_sales = sales_units > 0.0
        has_spend = media_spend_eur > 0.0
        validated = (
            not required
            or (
                row_count > 0
                and weeks >= max(1, int(min_weeks))
                and regions >= max(1, int(min_regions))
                and has_sales
                and has_spend
            )
        )
        missing: list[str] = []
        if required:
            if weeks < max(1, int(min_weeks)):
                missing.append("insufficient_outcome_weeks")
            if regions < max(1, int(min_regions)):
                missing.append("insufficient_outcome_regions")
            if not has_sales:
                missing.append("missing_sales_units")
            if not has_spend:
                missing.append("missing_media_spend")
        return {
            "brand": brand_key,
            "required_for_budget_release": required,
            "validated_for_budget_activation": validated,
            "rows": row_count,
            "weeks": weeks,
            "regions": regions,
            "sales_units": round(sales_units, 2),
            "media_spend_eur": round(media_spend_eur, 2),
            "min_weeks": max(1, int(min_weeks)),
            "min_regions": max(1, int(min_regions)),
            "missing_requirements": missing,
        }

    @staticmethod
    def _budget_gate_status(*, status_counts: Counter[str], top_regions: list[dict[str, Any]]) -> str:
        if status_counts.get("go", 0) > 0:
            return "go"
        if top_regions:
            return "candidate_only"
        if status_counts.get("blocked", 0) > 0:
            return "blocked"
        return "watch"
