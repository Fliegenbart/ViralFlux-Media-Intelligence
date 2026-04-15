from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from app.services.media.semantic_contracts import MetricContract, truth_readiness_contract


class TruthCoverageInput(TypedDict, total=False):
    coverage_weeks: int | float | str | None
    required_fields_present: Sequence[str] | None
    conversion_fields_present: Sequence[str] | None
    truth_freshness_state: str | None
    trust_readiness: str | None


class TruthGateResult(TypedDict):
    passed: bool
    state: str
    learning_state: str
    message: str | None
    guidance: str
    field_contracts: dict[str, MetricContract]


class TruthGateService:
    """Interprets truth coverage into a consistent gate and communication contract."""

    def evaluate(self, truth_coverage: TruthCoverageInput) -> TruthGateResult:
        coverage_weeks = int(truth_coverage.get("coverage_weeks") or 0)
        required_fields = set(truth_coverage.get("required_fields_present") or [])
        conversion_fields = set(truth_coverage.get("conversion_fields_present") or [])
        freshness_state = str(truth_coverage.get("truth_freshness_state") or "missing").strip().lower()
        truth_state = str(truth_coverage.get("trust_readiness") or "noch_nicht_angeschlossen").strip().lower()

        if coverage_weeks <= 0:
            return self._result(
                passed=False,
                state="missing",
                learning_state="missing",
                message="Es sind noch keine echten Kundendaten angeschlossen.",
                guidance="Aktivierungen bleiben vorerst im Prüfmodus, bis erste Kundendaten importiert sind.",
            )
        if freshness_state == "stale":
            return self._result(
                passed=False,
                state="stale",
                learning_state="stale",
                message="Die Kundendaten sind aktuell zu alt im Vergleich zur letzten epidemiologischen Woche.",
                guidance="Erkenntnisse aus Kundendaten bleiben sichtbar, zählen aber noch nicht als sichere Freigabegrundlage.",
            )
        if coverage_weeks < 26:
            return self._result(
                passed=False,
                state="explorative",
                learning_state="explorative",
                message="Die Kundendaten decken noch keine 26 Wochen ab und bleiben deshalb explorativ.",
                guidance="Die Kundendaten dürfen bei der Priorisierung helfen, sollen die Freigabe aber noch nicht bestimmen.",
            )
        if not ({"Media Spend", "Mediabudget"} & required_fields):
            return self._result(
                passed=False,
                state="incomplete",
                learning_state="im_aufbau",
                message="Die Kundendaten enthalten noch keinen belastbaren Verlauf des Mediabudgets.",
                guidance="Ohne Mediabudget bleibt die Lernschleife unvollständig.",
            )
        if not conversion_fields:
            return self._result(
                passed=False,
                state="incomplete",
                learning_state="im_aufbau",
                message="Die Kundendaten enthalten noch keine ausreichenden Signale zu Verkäufen, Bestellungen oder Umsatz.",
                guidance="Ohne echte Wirkungszahl bleibt die Kundendatenbasis nur teilweise angeschlossen.",
            )

        learning_state = "belastbar" if truth_state == "belastbar" else "im_aufbau"
        return self._result(
            passed=True,
            state="ready",
            learning_state=learning_state,
            message=None,
            guidance="Erkenntnisse aus Kundendaten dürfen die Priorisierung jetzt sichtbar mitsteuern.",
        )

    def _result(
        self,
        *,
        passed: bool,
        state: str,
        learning_state: str,
        message: str | None,
        guidance: str,
    ) -> TruthGateResult:
        return {
            "passed": passed,
            "state": state,
            "learning_state": learning_state,
            "message": message,
            "guidance": guidance,
            "field_contracts": {
                "truth_readiness": truth_readiness_contract(),
            },
        }
