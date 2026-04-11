"""Media Cockpit Service: bündelt Bento, Karte, Empfehlungen, Backtest und Datenfrische."""

from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.database import MarketingOpportunity
from app.services.media.cockpit.backtest import build_backtest_summary
from app.services.media.cockpit.bento_section import build_bento_section
from app.services.media.cockpit.freshness import (
    build_data_freshness,
    build_source_freshness_summary,
    build_source_status,
)
from app.services.media.cockpit.map_section import build_map_section
from app.services.media.cockpit import recommendations as cockpit_recommendations
from app.services.media.cockpit.signals import (
    build_campaign_refs_section as cockpit_build_campaign_refs_section,
    build_ranking_signal_fields as cockpit_build_ranking_signal_fields,
    build_signal_snapshot_section as cockpit_build_signal_snapshot_section,
    coerce_float as cockpit_coerce_float,
    normalize_recommendation_ref as cockpit_normalize_recommendation_ref,
    primary_signal_score as cockpit_primary_signal_score,
)
from app.services.media.ranking_signal_service import RankingSignalService

class MediaCockpitService:
    """Aggregierter Read-Service für das map-first Media Cockpit."""

    def __init__(self, db: Session):
        self.db = db

    def get_cockpit_payload(
        self,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
    ) -> dict:
        """Liefert einen einzigen Payload für Dashboard-Tabstruktur."""
        ranking_signal = RankingSignalService(self.db).build(virus_typ=virus_typ)
        data_freshness = self._data_freshness()
        source_status = self._source_status(data_freshness)
        region_refs = self._region_recommendation_refs()

        map_section = self._map_section(
            virus_typ=virus_typ,
            peix_score=ranking_signal,
            region_recommendations=region_refs,
        )
        signal_snapshot = self._signal_snapshot_section(
            virus_typ=virus_typ,
            peix_score=ranking_signal,
            map_section=map_section,
        )

        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "bento": self._bento_section(
                virus_typ=virus_typ,
                map_section=map_section,
                peix_score=ranking_signal,
                source_status=source_status,
            ),
            "ranking_signal": ranking_signal,
            "peix_epi_score": ranking_signal,
            "signal_snapshot": signal_snapshot,
            "source_status": source_status,
            "source_freshness": self._source_freshness_summary(source_status),
            "map": map_section,
            "campaign_refs": self._campaign_refs_section(region_refs),
            "recommendations": self._recommendation_section(),
            "backtest_summary": self._backtest_summary(
                virus_typ=virus_typ,
                target_source=target_source,
            ),
            "data_freshness": data_freshness,
            "timestamp": utc_now().isoformat(),
        }

    @staticmethod
    def _normalize_freshness_timestamp(
        value: datetime | None,
        *,
        now: datetime | None = None,
    ) -> str | None:
        """Return an ISO timestamp that never points into the future."""
        if value is None:
            return None

        effective_now = now or utc_now()
        normalized = value
        if normalized.tzinfo is not None:
            normalized = normalized.replace(tzinfo=None)
        if normalized > effective_now:
            normalized = effective_now
        return normalized.isoformat()

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        return cockpit_coerce_float(value)

    @classmethod
    def _primary_signal_score(cls, item: dict[str, Any] | None) -> float:
        return cockpit_primary_signal_score(item)

    def _ranking_signal_fields(
        self,
        *,
        signal_score: Any,
        source: str,
        legacy_alias: Any = None,
        label: str = "Signal-Score",
    ) -> dict[str, Any]:
        return cockpit_build_ranking_signal_fields(
            signal_score=signal_score,
            source=source,
            legacy_alias=legacy_alias,
            label=label,
        )

    @staticmethod
    def _normalize_recommendation_ref(
        recommendation_ref: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        return cockpit_normalize_recommendation_ref(recommendation_ref)

    def _signal_snapshot_section(
        self,
        *,
        virus_typ: str,
        peix_score: dict[str, Any],
        map_section: dict[str, Any],
    ) -> dict[str, Any]:
        return cockpit_build_signal_snapshot_section(
            virus_typ=virus_typ,
            peix_score=peix_score,
            map_section=map_section,
        )

    def _source_freshness_summary(self, source_status: dict[str, Any]) -> dict[str, Any]:
        return build_source_freshness_summary(source_status)

    def _campaign_refs_section(
        self,
        region_recommendations: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        return cockpit_build_campaign_refs_section(region_recommendations)

    def _map_section(
        self,
        *,
        virus_typ: str,
        peix_score: dict[str, Any],
        region_recommendations: dict[str, dict[str, Any]],
    ) -> dict:
        return build_map_section(
            self.db,
            virus_typ=virus_typ,
            peix_score=peix_score,
            region_recommendations=region_recommendations,
        )

    def _bento_section(
        self,
        *,
        virus_typ: str,
        map_section: dict[str, Any],
        peix_score: dict[str, Any],
        source_status: dict[str, Any],
    ) -> dict[str, Any]:
        return build_bento_section(
            self.db,
            virus_typ=virus_typ,
            map_section=map_section,
            peix_score=peix_score,
            source_status=source_status,
        )

    def _recommendation_section(self) -> dict:
        return cockpit_recommendations.build_recommendation_section(self.db)

    def _region_recommendation_refs(self) -> dict[str, dict[str, Any]]:
        return cockpit_recommendations.build_region_recommendation_refs(self.db)

    def _extract_region_codes_from_row(self, row: MarketingOpportunity) -> list[str]:
        return cockpit_recommendations.extract_region_codes_from_row(row)

    def _backtest_summary(self, virus_typ: str, target_source: str) -> dict:
        return build_backtest_summary(
            self.db,
            virus_typ=virus_typ,
            target_source=target_source,
        )

    def _data_freshness(self) -> dict:
        return build_data_freshness(
            self.db,
            normalize_freshness_timestamp=self._normalize_freshness_timestamp,
        )

    def _source_status(self, data_freshness: dict[str, Any]) -> dict[str, Any]:
        return build_source_status(data_freshness)
