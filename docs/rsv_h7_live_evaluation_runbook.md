# RSV A / h7 Live Evaluation Runbook

Stand: 2026-03-17

## Zweck

Dieses Runbook beschreibt den produktionsnahen, reproduzierbaren Evaluationspfad fuer den RSV A / h7 Ranking-Track.

Wichtig:

- der Run laeuft gegen die echte ViralFlux-Datenbasis
- keine lokalen Fake-Daten
- keine Gate-Weichzeichnung
- keine impliziten Zahlen
- baseline und experiment werden direkt vergleichbar archiviert

## Was Der Run Macht

Der dedizierte Live-Entrypoint:

- fixiert `virus_typ = RSV A`
- fixiert `horizon_days = 7`
- fixiert `preset = rsv_ranking`
- vergleicht den aktuellen h7-Live-Baseline-Pfad gegen die RSV-spezifischen Ranking-Experimente
- schreibt rohe und kuratierte Ergebnisse in ein timestamped Archive
- legt die Vergleichsergebnisse als JSON und Markdown ab
- kann zusaetzlich einen Audit-Trail-Eintrag schreiben

Der Entry-Point ist:

- [backend/scripts/run_rsv_h7_live_evaluation.py](/Users/davidwegener/Desktop/viralflux/backend/scripts/run_rsv_h7_live_evaluation.py)

## Server Voraussetzungen

Vor dem Lauf sollten diese Bedingungen erfuellt sein:

- der Backend-Container hat Zugriff auf die echte ViralFlux-Postgres-Instanz
- die kanonischen Baseline-Artefakte fuer RSV A / h7 sind verfuegbar
- der aktuelle Code-Stand enthaelt den RSV Ranking-Track
- der Lauf erfolgt in einer Umgebung, in der die Modellartefakte persistent geschrieben werden koennen

## Kanonischer Server-Run

Die autoritative Ausfuehrung ist im Worker- oder Backend-Container:

```bash
docker exec viralflux_celery_worker python /app/scripts/run_rsv_h7_live_evaluation.py --output-root /app/app/ml_models/regional_panel_h7_live_evaluation
```

Wenn der Lauf in einer anderen produktionsnahen Server-Umgebung ausgefuehrt wird, muss der gleiche Script-Pfad mit Zugriff auf die echte DB verwendet werden.

## Archivierung

Der Lauf schreibt pro Ausfuehrung einen eigenen Archivordner:

```text
backend/app/ml_models/regional_panel_h7_live_evaluation/rsv_a_h7_rsv_ranking/<run_id>/
```

Auf dem Server ist derselbe Pfad typischerweise als:

```text
/app/app/ml_models/regional_panel_h7_live_evaluation/rsv_a_h7_rsv_ranking/<run_id>/
```

Erwartete Dateien:

- `summary.json`
- `report.json`
- `report.md`
- `run_manifest.json`
- `artifacts/`

Bei Fehlern zusaetzlich:

- `error.json`
- `error.md`

## Vergleichswerte

Im Report muessen mindestens diese Werte direkt sichtbar sein:

- `precision_at_top3`
- `activation_false_positive_rate`
- `ece`
- `brier`
- `calibration_mode`
- `gate_outcome`
- `retained`

Die Tabelle ist bewusst baseline-vs-experiment aufgebaut. Fuer jede Zeile werden zusaetzlich Delta-Werte gegen die Baseline ausgegeben.

## Entscheidungslogik

### GO

Nur dann, wenn alle Punkte gleichzeitig gelten:

- das gewaehlte Experiment ist `retained = true`
- der Gate-Status ist `GO`
- `precision_at_top3` steigt ehrlich gegenueber der Baseline
- `activation_false_positive_rate` verschlechtert sich nicht
- `ece` verschlechtert sich nicht
- `brier` verschlechtert sich nicht

### WATCH

Wenn der RSV-Track ehrlich besser wird, aber das Gate weiterhin `WATCH` bleibt.

### NO_GO

Wenn mindestens eines davon zutrifft:

- `precision_at_top3` verbessert sich nicht
- `activation_false_positive_rate` steigt unvertretbar
- `ece` verschlechtert sich
- `brier` verschlechtert sich
- der Lauf produziert keine vernuenftige Baseline-vs-Experiment-Zeile

## Kurzvorlage Fuer Das Ergebnis

Nach dem Serverlauf kann diese Vorlage direkt befuellt werden:

```text
RSV A / h7 Live Evaluation

Run ID:
Archive:
Baseline:
Best experiment:
Best retained experiment:

precision_at_top3:
activation_false_positive_rate:
ece:
brier:
calibration_mode:
gate_outcome:
retained:

Decision: GO / WATCH / NO_GO
Reason:
Next step:
```

## Schnellinterpretation

- `GO`: nur, wenn der Track die Gates ehrlich uebertrifft und nicht nur statistisch "anders" ist
- `WATCH`: wenn die Ranking-Separation besser wird, aber der Scope noch nicht freigegeben werden sollte
- `NO_GO`: wenn die vermeintliche Verbesserung durch FP- oder Calibration-Regression erkauft ist

## Reproduzierbarkeit

Der Lauf ist reproduzierbar, weil

- der Scope fest ist
- die Vergleichsdateien archiviert werden
- das Model-Artifact-Verzeichnis pro Run getrennt ist
- die JSON-Ausgabe maschinenlesbar bleibt
- die Markdown-Ausgabe einen direkt lesbaren Readout liefert

## Verwandte Dokumente

- [h7_rsv_ranking_experiments.md](/Users/davidwegener/Desktop/viralflux/docs/h7_rsv_ranking_experiments.md)
- [rsv_h7_persistent_evaluation.md](/Users/davidwegener/Desktop/viralflux/docs/rsv_h7_persistent_evaluation.md)
- [h7_pilot_only_training_path.md](/Users/davidwegener/Desktop/viralflux/docs/h7_pilot_only_training_path.md)
- [model_release_process.md](/Users/davidwegener/Desktop/viralflux/docs/model_release_process.md)
