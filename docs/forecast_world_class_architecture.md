# Forecast World-Class Architecture

## Bausteine

- `benchmarking/`: Bewertungslogik, Leaderboards, Artefakte, Registry
- `models/`: wiederverwendbare Challenger-Komponenten inklusive MinT-artiger Hierarchiehilfe und optionalem TSFM-Adapter
- `forecast_orchestrator.py`: dünne Koordinationsschicht für Registry und Live-Entscheidungen
- `regional_trainer.py`: erster Champion-Kandidat mit probabilistischen Artefakten
- `regional_forecast.py`: stabile API-Ausgabe plus additive Metadaten

## Datenfluss

1. Feature Builder baut point-in-time sichtbare Panels.
2. Trainer erstellt probabilistische Modelle und Event-Kalibrierung.
3. Benchmarking bewertet Kandidaten auf Rolling-Origin-Folds.
4. Registry speichert Champion/Challenger-Entscheidungen.
5. Live-Forecast liest Champion-Metadaten und ergänzt Traceability-Felder.

## Exogene Guardrails

Der regionale Feature-Builder traegt jetzt einen kleinen Semantik-Vertrag fuer exogene Inputs:

- `observed_as_of_only`: nur bis `as_of` sichtbar
- `issue_time_forecast_allowed`: Zukunft nur mit sauberer Issue-Time-/Forecast-Run-Semantik
- `forbidden_for_training_or_inference`: realisierte Zukunftswerte sind unzulaessig

Die kompakten Regeln werden im Dataset-Manifest als `exogenous_feature_semantics` mitgeschrieben.

Fuer Wetter-Forecasts gibt es als ersten reproduzierbaren Vertical Slice zusaetzlich:

- `weather_forecast_vintage_mode`
- `weather_forecast_issue_time_semantics`
- `weather_forecast_run_identity_present`
- `weather_forecast_run_identity_source`
- `weather_forecast_run_identity_quality`

Damit koennen historische Trainings- und Inferenzlaeufe explizit markieren, ob sie den Weather-Vintage-Pfad genutzt haben oder kontrolliert degradiert wurden.

Neu fuer den Ingest-/Persistenzpfad:

- neue Forecast-Zeilen tragen eine stabile Persistenz-Run-Identitaet ueber `forecast_run_timestamp` und `forecast_run_id`
- diese Identitaet beschreibt den konkreten gespeicherten Forecast-Batch, nicht stillschweigend nur `created_at`
- Alt-Daten ohne diese Felder bleiben kompatibel, werden aber bewusst als `missing` / unvollstaendig markiert

## Weather Vintage Shadow Benchmark

Der Weather-Vintage-Vergleich ist noch kein globaler Rollout.

Er wird nur aktiviert, wenn `RegionalModelTrainer.train_all_regions(...)` oder
`RegionalModelTrainer.train_selected_viruses_all_regions(...)` explizit mit
`weather_vintage_comparison=True` aufgerufen wird.

Fuer eine kleine Entscheidungsgrundlage gibt es zusaetzlich den Runner
`backend/scripts/run_weather_vintage_comparison.py`, der mehrere Scopes
end-to-end gegen denselben Trainings-/Backtest-Pfad vergleicht und JSON plus
Markdown ausgibt.

Dabei bleibt der normale Trainingsmodus standardmaessig `legacy_issue_time_only`.
Der Trainer laesst zusaetzlich einen Shadow-Backtest mit `run_timestamp_v1` laufen und schreibt additiv:

- `weather_vintage_comparison`
- `legacy_vs_vintage_metric_delta`
- `weather_vintage_run_identity_coverage`
- `weather_vintage_backtest_coverage`

Fuer prospektive Evidenz gibt es zusaetzlich den Archiv-Runner
`backend/scripts/run_weather_vintage_prospective_shadow.py` sowie den kleinen
Standard-Wrapper `backend/scripts/run_weather_vintage_pilot_h7_shadow.py`.
Er startet denselben end-to-end Vergleich fuer `Influenza A / h7` und
`SARS-CoV-2 / h7`, schreibt pro Lauf einen kleinen Archivsatz und aktualisiert
einen Sammelreport ueber mehrere Shadow-Laeufe.

Im Regelbetrieb ist der Pilot-Wrapper der bevorzugte Startpunkt. Er markiert
die Laeufe standardmaessig als `run_purpose = scheduled_shadow`. Smoke- oder
manuelle Testlaeufe bleiben moeglich, werden aber bewusst getrennt markiert.
Fuer scheduler-gesteuerte Starts bringt der Wrapper ausserdem einen kleinen
Host-lokalen Lockfile-Schutz und klare Exit-Codes fuer Lock-Konflikt vs.
allgemeinen Laufzeitfehler mit.

Zusaetzlich gibt es einen kleinen Monitoring-Check ueber
`backend/scripts/check_weather_vintage_shadow_health.py`. Er liest die schon
archivierten `scheduled_shadow`-Laeufe und meldet `ok`, `warning` oder
`critical`, wenn der letzte Lauf zu alt ist, komplett fehlgeschlagen ist oder
ueber laengere Zeit keine brauchbaren Vergleichslaeufe mehr entstehen.

Fuer den Regelbetrieb gibt es als kleinsten Ops-Einstiegspunkt ausserdem
`backend/scripts/run_weather_vintage_pilot_h7_ops.py`. Dieser Wrapper startet
erst den geplanten h7-Shadow-Lauf und fuehrt direkt danach den Health-Check
aus, sodass Scheduler und Monitoring nur noch einen klaren Exit-Code
auswerten muessen.

Der prospektive Archivsatz enthaelt mindestens:

- `summary.json`
- `report.json`
- `report.md`
- `run_manifest.json`

Der Sammelreport zaehlt explizit nur `comparison_eligibility = comparable` als
belastbare Vergleichslaeufe. `insufficient_identity` bleibt sichtbar, verzerrt
aber nicht die Delta-Statistik.

Jeder Lauf schreibt im `run_manifest.json` zusaetzlich den Code-/Schema-Kontext
mit, insbesondere `git_commit_sha`, `alembic_revision` und die Scope-Eintraege
mit `comparison_eligibility`, `weather_vintage_run_identity_coverage` und den
Mode-Snapshots fuer Legacy und Vintage.

Der Sammelreport filtert standardmaessig auf `scheduled_shadow`. Dadurch gehen
Smoke- und manuelle Testlaeufe nicht still in die echte Review-Statistik ein.

Interpretation:

- negative `relative_wis`- oder `crps`-Deltas bedeuten, dass `run_timestamp_v1` besser war als Legacy
- `weather_vintage_run_identity_coverage.run_timestamp_v1.run_identity_present = false` bedeutet, dass der Vintage-Pfad zwar getestet wurde, aber keine saubere Run-Identitaet vorlag
- ein Report mit `insufficient_identity` ist deshalb als `inconclusive due to zero run identity coverage` zu lesen, nicht als Signal gegen Weather Vintage
- `weather_vintage_backtest_coverage` zeigt explizit, wie viel des echten Backtest-Fensters ueberhaupt historische Wetter-Run-Identitaet hat
- fuer eine belastbare Bewertung brauchen wir nicht nur aktuelle Forecast-Runs, sondern genug historische Sichtbarkeit im echten Train-/Test-Fenster; intern gilt dafuer mindestens grob `coverage_train >= 0.5` und `coverage_test >= 0.8`
- im prospektiven Shadow-Betrieb bleibt die Scope-Empfehlung auf `keep_legacy_default`, solange zu wenige vergleichbare Shadow-Laeufe vorliegen oder sich Gates verschlechtern
- `review_ready` setzt mindestens ausreichend vergleichbare Laeufe, keine Gate-Verschlechterung und genug Coverage voraus; erst danach lohnt sich ein manueller Rollout-Review
- dieser Vergleich aendert weder Promotion noch Live-Forecast stillschweigend

## Additive Live-Metadaten

- `champion_model_family`
- `component_model_family`
- `ensemble_component_weights`
- `hierarchy_driver_attribution`
- `reconciliation_method`
- `hierarchy_consistency_status`
- `revision_policy_used`
- `benchmark_evidence_reference`
- `benchmark_metrics`
- `tsfm_metadata`

Diese Felder erweitern die Antwort, ersetzen aber keine bestehenden Felder.
