from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import MediaOutcomeRecord
from app.services.media.semantic_contracts import (
    outcome_confidence_contract,
    outcome_signal_contract,
    truth_readiness_contract,
)


class OutcomeSignalService:
    """Builds lightweight observed-response signals from imported outcome rows."""

    def __init__(self, db: Session):
        self.db = db

    def build_learning_bundle(
        self,
        *,
        brand: str = "gelo",
        truth_coverage: dict[str, Any] | None = None,
        truth_gate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rows = (
            self.db.query(MediaOutcomeRecord)
            .filter(func.lower(MediaOutcomeRecord.brand) == str(brand or "gelo").strip().lower())
            .order_by(MediaOutcomeRecord.week_start.asc(), MediaOutcomeRecord.id.asc())
            .all()
        )
        coverage = truth_coverage or {}
        gate = truth_gate or {}

        if not rows:
            return {
                "summary": self._empty_summary(coverage=coverage, gate=gate),
                "by_product_region": {},
                "by_product": {},
                "by_region": {},
            }

        by_pair: dict[tuple[str, str], dict[str, Any]] = defaultdict(self._bucket)
        by_product: dict[str, dict[str, Any]] = defaultdict(self._bucket)
        by_region: dict[str, dict[str, Any]] = defaultdict(self._bucket)

        for row in rows:
            product_key = str(row.product or "").strip().lower()
            region_key = str(row.region_code or "").strip().upper()
            response_value = self._response_value(row)
            self._add_row(by_pair[(product_key, region_key)], row=row, response_value=response_value)
            self._add_row(by_product[product_key], row=row, response_value=response_value)
            self._add_row(by_region[region_key], row=row, response_value=response_value)

        pair_candidates = [
            self._candidate_from_bucket(
                key={"product": product, "region_code": region},
                bucket=bucket,
                truth_coverage=coverage,
            )
            for (product, region), bucket in by_pair.items()
        ]
        product_candidates = [
            self._candidate_from_bucket(
                key={"product": product},
                bucket=bucket,
                truth_coverage=coverage,
            )
            for product, bucket in by_product.items()
        ]
        region_candidates = [
            self._candidate_from_bucket(
                key={"region_code": region},
                bucket=bucket,
                truth_coverage=coverage,
            )
            for region, bucket in by_region.items()
        ]

        pair_lookup = {
            (candidate["product_key"], candidate["region_code"]): candidate
            for candidate in pair_candidates
        }
        product_lookup = {
            candidate["product_key"]: candidate
            for candidate in product_candidates
        }
        region_lookup = {
            candidate["region_code"]: candidate
            for candidate in region_candidates
        }

        summary = self._summary_from_candidates(
            pair_candidates=pair_candidates,
            product_candidates=product_candidates,
            region_candidates=region_candidates,
            truth_coverage=coverage,
            truth_gate=gate,
        )
        return {
            "summary": summary,
            "by_product_region": pair_lookup,
            "by_product": product_lookup,
            "by_region": region_lookup,
        }

    def signal_for_card(
        self,
        *,
        card: dict[str, Any],
        bundle: dict[str, Any],
    ) -> dict[str, Any]:
        region_codes = [str(code).strip().upper() for code in (card.get("region_codes") or []) if str(code).strip()]
        product_key = str(card.get("recommended_product") or card.get("product") or "").strip().lower()
        pair_lookup = bundle.get("by_product_region") or {}
        product_lookup = bundle.get("by_product") or {}
        region_lookup = bundle.get("by_region") or {}
        summary = bundle.get("summary") or {}

        matches = []
        for region_code in region_codes:
            pair_candidate = pair_lookup.get((product_key, region_code))
            if pair_candidate:
                matches.append(("pair", pair_candidate))
        if not matches and product_key and product_lookup.get(product_key):
            matches.append(("product", product_lookup[product_key]))
        if not matches:
            for region_code in region_codes:
                region_candidate = region_lookup.get(region_code)
                if region_candidate:
                    matches.append(("region", region_candidate))

        if matches:
            match_type, best = max(
                matches,
                key=lambda item: (
                    float(item[1].get("outcome_signal_score") or 0.0),
                    float(item[1].get("outcome_confidence_pct") or 0.0),
                    int(item[1].get("coverage_weeks") or 0),
                ),
            )
            learning_state = best.get("learning_state") or summary.get("learning_state") or "explorative"
            explanation = self._explanation_for_match(match_type=match_type, best=best)
            return {
                "outcome_signal_score": best.get("outcome_signal_score"),
                "outcome_confidence_pct": best.get("outcome_confidence_pct"),
                "learning_state": learning_state,
                "outcome_learning_scope": match_type,
                "outcome_learning_explanation": explanation,
                "observed_response": best.get("observed_response"),
                "learned_lifts": best.get("learned_lifts"),
            }

        return {
            "outcome_signal_score": None,
            "outcome_confidence_pct": None,
            "learning_state": summary.get("learning_state") or "missing",
            "outcome_learning_scope": "none",
            "outcome_learning_explanation": "Noch keine belastbaren Outcome-Learnings fuer Produkt oder Region vorhanden.",
            "observed_response": None,
            "learned_lifts": [],
        }

    def _summary_from_candidates(
        self,
        *,
        pair_candidates: list[dict[str, Any]],
        product_candidates: list[dict[str, Any]],
        region_candidates: list[dict[str, Any]],
        truth_coverage: dict[str, Any],
        truth_gate: dict[str, Any],
    ) -> dict[str, Any]:
        ranked_pairs = sorted(
            pair_candidates,
            key=lambda item: (
                float(item.get("outcome_signal_score") or 0.0),
                float(item.get("outcome_confidence_pct") or 0.0),
            ),
            reverse=True,
        )
        ranked_products = sorted(
            product_candidates,
            key=lambda item: (
                float(item.get("outcome_signal_score") or 0.0),
                float(item.get("outcome_confidence_pct") or 0.0),
            ),
            reverse=True,
        )
        ranked_regions = sorted(
            region_candidates,
            key=lambda item: (
                float(item.get("outcome_signal_score") or 0.0),
                float(item.get("outcome_confidence_pct") or 0.0),
            ),
            reverse=True,
        )

        top_pairs = ranked_pairs[:5]
        top_pair_score = (
            round(sum(float(item.get("outcome_signal_score") or 0.0) for item in top_pairs) / len(top_pairs), 1)
            if top_pairs else None
        )
        top_pair_confidence = (
            round(sum(float(item.get("outcome_confidence_pct") or 0.0) for item in top_pairs) / len(top_pairs), 1)
            if top_pairs else None
        )
        readiness = str(truth_coverage.get("trust_readiness") or "noch_nicht_angeschlossen")
        learning_state = str((truth_gate or {}).get("learning_state") or readiness or "missing")

        return {
            "learning_state": learning_state,
            "coverage_weeks": int(truth_coverage.get("coverage_weeks") or 0),
            "outcome_signal_score": top_pair_score,
            "outcome_confidence_pct": top_pair_confidence,
            "top_product_learnings": ranked_products[:3],
            "top_region_learnings": ranked_regions[:3],
            "top_pair_learnings": top_pairs,
            "field_contracts": {
                "truth_readiness": truth_readiness_contract(),
                "outcome_signal_score": outcome_signal_contract(),
                "outcome_confidence_pct": outcome_confidence_contract(),
            },
        }

    def _empty_summary(
        self,
        *,
        coverage: dict[str, Any],
        gate: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "learning_state": str((gate or {}).get("learning_state") or "missing"),
            "coverage_weeks": int(coverage.get("coverage_weeks") or 0),
            "outcome_signal_score": None,
            "outcome_confidence_pct": None,
            "top_product_learnings": [],
            "top_region_learnings": [],
            "top_pair_learnings": [],
            "field_contracts": {
                "truth_readiness": truth_readiness_contract(),
                "outcome_signal_score": outcome_signal_contract(),
                "outcome_confidence_pct": outcome_confidence_contract(),
            },
        }

    @staticmethod
    def _bucket() -> dict[str, Any]:
        return {
            "weeks": set(),
            "spend": 0.0,
            "response": 0.0,
            "qualified_visits": 0.0,
            "search_lift_total": 0.0,
            "search_lift_rows": 0,
            "rows": 0,
            "conversion_rows": 0,
        }

    def _add_row(self, bucket: dict[str, Any], *, row: MediaOutcomeRecord, response_value: float) -> None:
        if row.week_start:
            bucket["weeks"].add(row.week_start.date().isoformat())
        bucket["spend"] += float(row.media_spend_eur or 0.0)
        bucket["response"] += response_value
        bucket["qualified_visits"] += float(row.qualified_visits or 0.0)
        bucket["rows"] += 1
        if response_value > 0:
            bucket["conversion_rows"] += 1
        if row.search_lift_index is not None:
            bucket["search_lift_total"] += float(row.search_lift_index or 0.0)
            bucket["search_lift_rows"] += 1

    def _candidate_from_bucket(
        self,
        *,
        key: dict[str, str],
        bucket: dict[str, Any],
        truth_coverage: dict[str, Any],
    ) -> dict[str, Any]:
        weeks = len(bucket["weeks"])
        spend = float(bucket["spend"] or 0.0)
        response = float(bucket["response"] or 0.0)
        search_avg = (
            float(bucket["search_lift_total"]) / float(bucket["search_lift_rows"])
            if bucket["search_lift_rows"] else 0.0
        )
        response_per_1000 = response / max(spend / 1000.0, 1.0) if spend > 0 else 0.0
        response_component = min(100.0, response_per_1000 * 8.0)
        search_component = min(100.0, max(0.0, search_avg))
        coverage_component = min(100.0, (weeks / 26.0) * 100.0)
        freshness_penalty = 15.0 if str(truth_coverage.get("truth_freshness_state") or "").lower() == "stale" else 0.0

        score = max(
            0.0,
            min(
                100.0,
                response_component * 0.65
                + coverage_component * 0.25
                + search_component * 0.10
                - freshness_penalty,
            ),
        )
        confidence = max(
            0.0,
            min(
                100.0,
                min(1.0, weeks / 26.0) * 55.0
                + min(1.0, spend / 50000.0) * 25.0
                + min(1.0, float(bucket["conversion_rows"]) / 8.0) * 20.0
                - freshness_penalty,
            ),
        )

        learning_state = "belastbar" if weeks >= 52 else "im_aufbau" if weeks >= 26 else "explorative"
        return {
            **key,
            "product_key": key.get("product"),
            "coverage_weeks": weeks,
            "rows": int(bucket["rows"]),
            "media_spend_eur": round(spend, 1),
            "observed_response": {
                "response_units": round(response, 1),
                "response_per_1000_eur": round(response_per_1000, 2),
                "qualified_visits": round(float(bucket["qualified_visits"] or 0.0), 1),
                "avg_search_lift_index": round(search_avg, 1) if bucket["search_lift_rows"] else None,
            },
            "learned_lifts": [
                {
                    "label": "Response je 1.000 EUR",
                    "value": round(response_per_1000, 2),
                },
                {
                    "label": "Search Lift",
                    "value": round(search_avg, 1) if bucket["search_lift_rows"] else None,
                },
            ],
            "outcome_signal_score": round(score, 1),
            "outcome_confidence_pct": round(confidence, 1),
            "learning_state": learning_state,
        }

    @staticmethod
    def _response_value(row: MediaOutcomeRecord) -> float:
        if row.sales_units is not None:
            return float(row.sales_units or 0.0)
        if row.order_count is not None:
            return float(row.order_count or 0.0) * 2.0
        if row.revenue_eur is not None:
            return float(row.revenue_eur or 0.0) / 100.0
        if row.qualified_visits is not None:
            return float(row.qualified_visits or 0.0) / 4.0
        return 0.0

    @staticmethod
    def _explanation_for_match(*, match_type: str, best: dict[str, Any]) -> str:
        product = str(best.get("product_key") or "").strip()
        region = str(best.get("region_code") or "").strip()
        weeks = int(best.get("coverage_weeks") or 0)
        score = round(float(best.get("outcome_signal_score") or 0.0))
        if match_type == "pair" and product and region:
            return f"Beobachtetes Learning fuer {product} in {region}: {weeks} Wochen Outcome-Daten stuetzen einen Outcome-Score von {score}/100."
        if match_type == "product" and product:
            return f"Produkt-Learning fuer {product}: {weeks} Wochen Outcome-Daten tragen die Priorisierung mit."
        if match_type == "region" and region:
            return f"Region-Learning fuer {region}: beobachtete Outcomes bleiben in der Priorisierung sichtbar."
        return "Outcome-Learning ist angeschlossen, aber noch nicht fein granular genug fuer eine konkrete Zuordnung."
