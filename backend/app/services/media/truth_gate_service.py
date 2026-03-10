from __future__ import annotations

from typing import Any

from app.services.media.semantic_contracts import truth_readiness_contract


class TruthGateService:
    """Interprets truth coverage into a consistent gate and communication contract."""

    def evaluate(self, truth_coverage: dict[str, Any]) -> dict[str, Any]:
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
                message="Es sind noch keine echten Outcome-Daten angeschlossen.",
                guidance="Aktivierungen bleiben explorativ, bis erste Truth-Daten importiert sind.",
            )
        if freshness_state == "stale":
            return self._result(
                passed=False,
                state="stale",
                learning_state="stale",
                message="Die Kundendaten sind aktuell zu alt im Vergleich zur letzten epidemiologischen Woche.",
                guidance="Outcome-Learnings werden angezeigt, aber nicht als harte Freigabegrundlage verwendet.",
            )
        if coverage_weeks < 26:
            return self._result(
                passed=False,
                state="explorative",
                learning_state="explorative",
                message="Die Kundendaten decken noch keine 26 Wochen ab und bleiben deshalb explorativ.",
                guidance="Outcome-Signale dürfen priorisieren helfen, aber keine Freigabe dominieren.",
            )
        if "Media Spend" not in required_fields:
            return self._result(
                passed=False,
                state="incomplete",
                learning_state="im_aufbau",
                message="Die Kundendaten enthalten noch keinen belastbaren Media-Spend-Verlauf.",
                guidance="Ohne Media Spend bleibt die Lernschleife methodisch unvollständig.",
            )
        if not conversion_fields:
            return self._result(
                passed=False,
                state="incomplete",
                learning_state="im_aufbau",
                message="Die Kundendaten enthalten noch keine ausreichenden Sales-, Order- oder Revenue-Signale.",
                guidance="Ohne echte Outcome-Metrik bleibt der Outcome-Layer nur teilweise angeschlossen.",
            )

        learning_state = "belastbar" if truth_state == "belastbar" else "im_aufbau"
        return self._result(
            passed=True,
            state="ready",
            learning_state=learning_state,
            message=None,
            guidance="Outcome-Learnings dürfen die Priorisierung jetzt aktiv mitsteuern.",
        )

    def _result(
        self,
        *,
        passed: bool,
        state: str,
        learning_state: str,
        message: str | None,
        guidance: str,
    ) -> dict[str, Any]:
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
