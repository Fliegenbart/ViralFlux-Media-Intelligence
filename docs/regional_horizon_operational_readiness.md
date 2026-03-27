# Regional Horizon Operational Readiness

Stand: 2026-03-24

## Ziel

Dieses Dokument beschreibt den operativen Vertrag fuer den regionalen Forecast-Pfad mit echten `3/5/7`-Horizonten.

Seit dem Scope-Entscheid vom 24.03.2026 gilt aber produktseitig klar:

- `h7` ist der einzige aktiv priorisierte Horizon.
- `h5` ist vorerst pausiert.
- `h3` bleibt als Reserve-/Beobachtungspfad erhalten, wird aber nicht aktiv produktisiert.

Wichtig:

- Die kanonische Decision-Hook bleibt in `RegionalForecastService.predict_all_regions(...)`.
- Allocation und Recommendation bleiben downstream auf dem Forecast-/Decision-Output aufgebaut.
- Readiness soll ehrlich zwischen `supported`, `pilot-supported`, `unsupported` und `shadow-only` unterscheiden.

## Canonical Live Path

Der operative Pfad bleibt:

1. horizon-spezifisches Training / Backtest / Artifact-Backfill
2. `RegionalForecastService.predict_all_regions(...)`
3. `RegionalDecisionEngine.evaluate(...)`
4. `RegionalMediaAllocationEngine.allocate(...)`
5. `CampaignRecommendationService`
6. operativer Snapshot in den Audit-Trail
7. `ProductionReadinessService` bewertet Verfuegbarkeit, Recency, Coverage, Quality Gate und Pilotvertrag

## Support Matrix vs Pilot Contract

### Technisch supported

- `Influenza A`: `3/5/7`
- `Influenza B`: `3/5/7`
- `SARS-CoV-2`: `3/5/7`
- `RSV A`: `5/7`

### Explizit unsupported

- `RSV A / h3`
  - Grund: Das regionale h3-Training liefert aktuell nicht genug stabile pooled-panel Reihen fuer einen belastbaren Scope.

### Day-one pilot-supported

Der erste offizielle Pilotvertrag ist absichtlich enger als der technische Support:

- `Influenza A / h7`
- `Influenza B / h7`
- `RSV A / h7`

Technisch supported, aber in diesem Pass **nicht** pilot-supported:

- `Influenza A / h3`
- `Influenza B / h3`
- `SARS-CoV-2 / h3,h5,h7`
- `Influenza A / h5`
- `Influenza B / h5`
- `RSV A / h5`

Interpretation fuer die aktuelle Produktarbeit:

- `h7` ist die aktive Ausbau-, Freigabe- und Kommunikationslinie.
- `h3` ist kein Fehlerfall mehr, sondern ein Reservepfad mit teilweiser Benchmark-Evidenz bei Influenza.
- `h5` bleibt technisch vorhanden, wird aber aktuell nicht mehr aktiv verfolgt.

Readiness spiegelt diese Trennung jetzt explizit pro Scope:

- `pilot_contract_supported`
- `pilot_contract_reason`

## Quality Gate Profiles

Das regionale Quality Gate bleibt binaer: `GO` oder `WATCH`.

Neu ist nur, dass der Gate-Contract jetzt profilbasiert und explizit benannt ist:

### `strict_v1`

Default fuer alle Scopes, die nicht im aktiven `h7`-Pilotvertrag liegen.

- `precision_at_top3 >= 0.70`
- `activation_false_positive_rate <= 0.25`
- `pr_auc >= best_baseline * 1.15`
- `brier_score <= climatology_brier * 0.90`
- `ece <= 0.05`

### `pilot_v1`

Nur fuer den engen Day-one-Pilotvertrag.

- `precision_at_top3 >= 0.60`
- `activation_false_positive_rate <= 0.25`
- `pr_auc >= best_baseline * 1.05`
- `brier_score <= climatology_brier * 0.97`
- `ece <= 0.05`

Wichtig:

- `activation_false_positive_rate` und `ece` bleiben absichtlich unveraendert.
- Nicht-Pilot-Scopes werden **nicht** global weichgerechnet.
- Das gilt bewusst auch fuer `Influenza A / h3` und `Influenza B / h3`: Benchmark-Potenzial allein reicht nicht fuer operative Freigabe.
- Das persistierte `quality_gate` in den Artefakten enthaelt jetzt zusaetzlich:
  - `profile`
  - `failed_checks`
  - `thresholds`

### Metrik-Semantik ab 2026-03-17

Die Schwellen bleiben gleich, aber zwei Metriken sind seit dem
Semantik-Fix explizit anders zu lesen:

- `precision_at_top3`
  - Mittelwert der Top-3-Praezision nur ueber `as_of_date`-Gruppen,
    in denen mindestens ein echtes Event vorkommt.
  - Tage ohne einziges Event werden fuer diese Kennzahl nicht mehr als
    implizite Null-Praezision mitgemittelt.
- `activation_false_positive_rate`
  - Echte False-Positive-Rate ueber Negativfaelle:
    `false_positives / all_negative_cases`.
  - Wenn eine zeilenweise `action_threshold` vorhanden ist, wird genau
    diese dynamische Schwelle fuer die Aktivierungsentscheidung benutzt.

Wichtig:

- Historische Artefakte vor diesem Fix koennen fuer diese beiden
  Kennzahlen nicht direkt mit neu backfilled Artefakten verglichen
  werden, ohne die geaenderte Semantik mitzudenken.
- Nach dieser Vertragsaenderung sind Retrain, Backfill und Recompute
  Pflicht, bevor Readiness- oder Pilot-Entscheidungen neu bewertet
  werden.

## Artifact Contract

Produktive Scoped-Artefakte liegen unter:

`/app/app/ml_models/regional_panel/<virus_slug>/horizon_<h>/`

Pflichtdateien pro Scope:

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
- `legacy_default_window_fallback` fuer `h7` ist kein Normalbetrieb
- nach Gate-/Contract-Aenderungen ist Retrain + Backfill + Recompute Pflicht

## Operational Snapshot Contract

Ein `REGIONAL_OPERATIONAL_SNAPSHOT` schreibt pro `virus_typ x horizon_days` jetzt mindestens:

- `forecast_as_of_date`
- `forecast_status`
- `allocation_status`
- `recommendation_status`
- `artifact_transition_mode`
- `quality_gate`
- `quality_gate_profile`
- `quality_gate_failed_checks`
- `point_in_time_snapshot`
- `source_coverage`
- `source_coverage_scope`
- `artifact_source_coverage`
- `training_source_coverage`
- `live_source_coverage`
- `live_source_freshness`
- `source_criticality`
- `forecast_recency_status`
- `source_coverage_required_status`
- `live_source_coverage_status`
- `live_source_freshness_status`
- `pilot_contract_supported`
- `pilot_contract_reason`
- `rollout_mode`
- `activation_policy`

Diese Metadaten werden fuer Release-Smoke, Readiness und spaetere Policy-Promotion wiederverwendet.

Wichtig:

- `source_coverage` bleibt aus Kompatibilitaetsgruenden im Snapshot, spiegelt aber weiter die Artefakt-/Trainingssicht.
- `source_coverage_scope = artifact` markiert diese Altkompatibilitaet jetzt explizit.
- Die operative Live-Sicht liegt jetzt explizit in `live_source_coverage` und `live_source_freshness`.
- Gute Trainingsartefakte machen einen Scope nicht mehr implizit gruen, wenn eine kritische Live-Quelle fehlt oder stale ist.
- wichtige Snapshot-Consumer wie der `pilot-readout` und der `SARS h7`-Promotionspfad sollen den operativen Zustand ueber `live_source_coverage_status` und `live_source_freshness_status` lesen, nicht ueber `source_coverage`
- neuer Code soll `source_coverage` nur noch als Artefakt-/Trainingssignal behandeln, nicht als Live-Gesundheit

## Required vs Advisory Source Coverage

Readiness behandelt Coverage nicht mehr als blindes Minimum ueber alle Rohsignale.
Sie trennt jetzt explizit:

- Artefakt-/Trainings-Coverage
- aktuelle Live-Coverage
- aktuelle Live-Freshness

### Required

- `Influenza A` / `Influenza B`
  - `grippeweb_are_available`
  - `grippeweb_ili_available`
  - `ifsg_influenza_available`
- `RSV A`
  - `grippeweb_are_available`
  - `grippeweb_ili_available`
  - `ifsg_rsv_available`
- `SARS-CoV-2`
  - `grippeweb_are_available`
  - `grippeweb_ili_available`
  - `sars_are_available`
  - `sars_notaufnahme_available`

### Advisory

- `SARS-CoV-2`
  - `sars_trends_available`

## Live-Coverage Semantik

Die operative Readiness bewertet pro Quelle jetzt fuer das aktuelle `as_of`:

- ob ueberhaupt sichtbare Live-Daten vorhanden sind
- ob diese Quelle kritisch oder nur advisory ist
- wie frisch die letzte sichtbare Lieferung ist

Fuer taegliche Quellen wie `wastewater`, `sars_notaufnahme` und `sars_trends` gilt bewusst:

- ein sichtbarer aktueller Datenpunkt im kleinen Live-Fenster reicht fuer `live_source_coverage = ok`
- ob dieser Punkt operativ noch brauchbar ist, entscheidet dann `live_source_freshness`

Damit gilt:

- `coverage` beantwortet: "Ist die Quelle da?"
- `freshness` beantwortet: "Ist die Quelle noch aktuell genug?"

## SARS-CoV-2 Policy

`SARS-CoV-2` bleibt standardmaessig konservativ:

- `rollout_mode = shadow`
- `activation_policy = watch_only`

Das gilt weiterhin fuer `h3/h5/h7`, solange keine explizite Promotion aktiviert ist.

### Bedingter Promotionspfad fuer `SARS-CoV-2 / h7`

Der Code enthaelt jetzt einen expliziten, aber standardmaessig deaktivierten Promotionspfad.

Die Umschaltung auf:

- `rollout_mode = gated`
- `activation_policy = quality_gate`

ist nur erlaubt, wenn **beides** gilt:

1. die Umgebungsflag `REGIONAL_SARS_H7_PROMOTION_ENABLED=true` ist gesetzt
2. die letzten **zwei** operativen Snapshots fuer `SARS-CoV-2 / h7` zeigen:
   - `quality_gate.overall_passed == true`
   - `source_coverage_required_status == "ok"`
   - `forecast_recency_status == "ok"`
   - kein `artifact_transition_mode`

Ohne Flag bleibt der Scope selbst dann shadow/watch-only.

## Readiness Semantics

`regional_operational` bewertet pro Scope mindestens:

- Support-Status
- Pilotvertrag
- Modellverfuegbarkeit
- Legacy-Fallback aktiv oder nicht
- Quality Gate
- Source Freshness
- Forecast Recency
- Source Coverage
- Model Age
- bei `SARS-CoV-2 / h7`: Promotionseligibility

Interpretation:

- `ok`: Scope ist technisch und operativ belastbar
- `warning`: Scope ist bewusst unsupported, shadow-only oder hat nicht-kritische Einschraenkungen
- `critical`: Scope fehlt, ist stale oder verletzt einen harten Guardrail

Wichtig:

- ein nicht bestandenes Quality Gate bleibt `warning`, nicht heimlich `ok`
- ein nicht pilot-supported Scope kann technisch `ok` sein, bleibt aber vertraglich ausserhalb des Day-one-Pilots

## Live Procedure

### 1. Scoped Artifacts backfillen

```bash
docker exec viralflux_celery_worker python /app/scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7
```

### 2. Operative Views recomputen und snapshotten

```bash
docker exec viralflux_celery_worker python /app/scripts/recompute_operational_views.py --horizon 3 --horizon 5 --horizon 7
```

### 3. Readiness pruefen

```bash
curl -s https://fluxengine.labpulse.ai/health/ready
```

## Realer Live-Stand am 2026-03-17

Nach dem produktionsnahen Backfill und der Recency-Haertung gilt live:

- `health/live = 200`
- `health/ready = 200` mit `status=degraded`
- moderner Release-Smoke = `ready_blocked`
- `missing_models = 0`
- `stale_forecasts = 0`
- `critical = 0`
- `unsupported = 1`
- `quality_gate_failures` bleiben der Hauptgrund fuer `warning`

Das heisst:

- der regionale Produktkern lebt wieder
- die Support-Matrix ist technisch weitgehend sauber
- die eigentliche Pilotfreigabe haengt jetzt vor allem an Quality Gate, Pilotvertrag und dem konservativen SARS-Policy-Layer
