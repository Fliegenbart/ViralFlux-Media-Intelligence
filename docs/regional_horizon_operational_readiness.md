# Regional Horizon Operational Readiness

## Ziel

Diese Notiz beschreibt den operativen Zielzustand fuer den regionalen Forecast-Pfad fuer `3/5/7` Tage sowie die reale Freigabelogik fuer Produktion.

## Canonical Live Scope

Der operative regionale Pfad bleibt:

1. Training / Artifact-Backfill pro `virus_typ` und `horizon_days`
2. `RegionalForecastService.predict_all_regions(...)`
3. `RegionalDecisionEngine.evaluate(...)`
4. `RegionalMediaAllocationEngine.allocate(...)`
5. `CampaignRecommendationService`
6. operativer Snapshot in den Audit-Trail
7. `ProductionReadinessService` bewertet Artefakte, Gates und Snapshot-Recency

Die Decision-Hook bleibt unveraendert im Forecast-Service.

## Support Matrix

Offiziell unterstuetzte Produkt-Horizonte sind nur:

- `3`
- `5`
- `7`

Der Code fuehrt eine explizite Support-Matrix pro Virus. Nicht unterstuetzte Kombinationen werden als `unsupported` behandelt, nicht als stiller `no_model`-Pfad.

Aktueller Zielzustand fuer den Live-Betrieb:

- `Influenza A`: `3/5/7`
- `Influenza B`: `3/5/7`
- `SARS-CoV-2`: `3/5/7`
- `RSV A`: `5/7`

Explizit unsupported im aktuellen Produktvertrag:

- `RSV A / h3`
  - Grund: Das regionale h3-Training scheitert aktuell reproduzierbar an zu wenig stabilen pooled-panel Reihen und wird deshalb nicht als halb-funktionaler `no_model`-Pfad ausgeliefert.

Falls ein Scope spaeter bewusst deaktiviert werden muss, wird er explizit in der Support-Matrix dokumentiert und Readiness-seitig als `warning` statt als falscher Model-Fehler gefuehrt.

## Artifact Contract

Produktive Artefakte liegen unter:

`/app/app/ml_models/regional_panel/<virus_slug>/horizon_<h>/`

Erwartete Pflichtdateien pro Scope:

- `classifier.json`
- `regressor_median.json`
- `regressor_lower.json`
- `regressor_upper.json`
- `calibration.pkl`
- `metadata.json`
- `dataset_manifest.json`
- `point_in_time_snapshot.json`
- `backtest.json`
- `threshold_manifest.json`

Wichtige Regeln:

- unvollstaendige Scoped-Artefakte werden nicht still akzeptiert
- `h7` faellt nur dann auf Legacy zurueck, wenn kein Scoped-Ordner existiert
- sobald `horizon_7/` existiert, verschwindet `legacy_default_window_fallback` aus dem aktiven Pfad

## Operational Snapshot Contract

Forecast-Recency wird nicht mehr nur aus dem Trainings-Snapshot abgeleitet.

Nach einem operativen Recompute wird pro `virus_typ` x `horizon_days` ein Snapshot in den Audit-Trail geschrieben:

- `action = REGIONAL_OPERATIONAL_SNAPSHOT`
- `entity_type = RegionalOperationalSnapshot`
- `forecast_as_of_date`
- `forecast_status`
- `allocation_status`
- `recommendation_status`
- `artifact_transition_mode`
- `model_version`
- `calibration_version`
- `quality_gate`
- `point_in_time_snapshot`

`ProductionReadinessService` nutzt diesen Snapshot bevorzugt fuer `forecast_recency_status`.

## Live Procedure

### 1. Scoped artifacts backfillen

Im produktionsnahen Compose-Pfad ueber einen laufenden App-Container ausfuehren:

```bash
docker exec viralflux_celery_worker python /app/scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7
```

### 2. Operative Views recomputen und snapshotten

```bash
docker exec viralflux_celery_worker python /app/scripts/recompute_operational_views.py --horizon 3 --horizon 5 --horizon 7
```

Per Default laufen dabei alle unterstuetzten Viren. Die Recompute-Ausgabe schreibt pro Scope einen operativen Snapshot in den Audit-Trail.

### 3. Readiness pruefen

```bash
curl -s https://fluxengine.labpulse.ai/health/ready
```

## Readiness Semantics

`regional_operational` bewertet pro Scope mindestens:

- Support-Status
- Modellverfuegbarkeit
- Legacy-Fallback aktiv oder nicht
- Quality Gate
- Source Freshness
- Forecast Recency
- Source Coverage
- Model Age

Interpretation:

- `ok`: Scope ist operativ belastbar
- `warning`: Scope ist bewusst unsupported oder hat nur nicht-kritische Einschraenkungen
- `critical`: Scope fehlt, ist stale oder verletzt einen harten operativen Guardrail

## Was rot halten darf

Die Readiness bleibt absichtlich rot, wenn:

- ein offiziell unterstuetzter Scope kein Artefakt hat
- nur Legacy-`h7` aktiv ist
- kein operativer Snapshot fuer den Scope existiert und der Trainings-Snapshot stale ist
- Source Coverage unter den Mindestwert faellt
- das Quality Gate nicht auf `GO` steht

## Live Report

Der Live-Stand muss nach jedem Backfill/Recompute neu aus `GET /health/ready` abgelesen werden.

Empfohlene Berichtstruktur:

- `green`: Scope hat `status=ok`
- `yellow`: Scope hat `status=warning`
- `unsupported`: Scope ist explizit unsupported
- `red`: Scope hat `status=critical`

## Erwarteter Erfolg fuer diese Härtung

Nach erfolgreichem Backfill und Recompute sollten sich die roten Punkte sichtbar reduzieren:

- `missing_models` fuer `h3/h5` gegen `0`
- `legacy_default_window_fallback` fuer `h7` gegen `0`
- `forecast_recency_status` aus operativen Snapshots statt aus Trainings-Lag

Live-Stand vom `2026-03-17` nach dem produktionsnahen Backfill:

- `Influenza A`: `h3/h5/h7` als Scoped-Artefakte vorhanden
- `Influenza B`: `h3/h5/h7` als Scoped-Artefakte vorhanden
- `SARS-CoV-2`: `h3/h5/h7` als Scoped-Artefakte vorhanden
- `RSV A`: `h5/h7` als Scoped-Artefakte vorhanden
- `RSV A / h3`: bewusst unsupported
- `legacy_default_window_fallback`: fuer die beobachteten Live-Scope-Artefakte nicht mehr notwendig

Wenn ein Scope trotz Backfill nicht sauber trainierbar ist, wird er nicht weichgerechnet, sondern explizit als unsupported oder kritisch dokumentiert.
