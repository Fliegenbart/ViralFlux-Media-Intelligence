# RSV A / h7 Persistent Evaluation

Stand: 2026-03-17

## Zweck

Dieser Leitfaden beschreibt den persistenten, auditierbaren Evaluationspfad für den RSV A / h7 Ranking-Track.

Ziel ist nicht ein weiterer lokaler Testlauf, sondern ein Server-Run mit dauerhaft lesbaren Artefakten:

- kein fluechtiger Container-Output
- keine stillen Successes
- keine impliziten Zahlen
- keine Gate-Weichzeichnung

## Autoritativer Run

Der dedizierte Entry-Point ist:

- [backend/scripts/run_rsv_h7_live_evaluation.py](/Users/davidwegener/Desktop/viralflux/backend/scripts/run_rsv_h7_live_evaluation.py)

Empfohlener Server-Run:

```bash
docker exec viralflux_celery_worker python /app/scripts/run_rsv_h7_live_evaluation.py \
  --output-root /app/app/ml_models/regional_panel_h7_live_evaluation
```

Der gleiche Pfad funktioniert lokal mit dem Repo-Root:

```bash
python backend/scripts/run_rsv_h7_live_evaluation.py \
  --output-root backend/app/ml_models/regional_panel_h7_live_evaluation
```

## Persistenter Output Root

Der Run schreibt pro Ausführung einen eigenen Archivbaum:

```text
<output-root>/rsv_a_h7_rsv_ranking/<run_id>/
```

Beispiel lokal:

```text
backend/app/ml_models/regional_panel_h7_live_evaluation/rsv_a_h7_rsv_ranking/<run_id>/
```

Beispiel auf dem Server:

```text
/app/app/ml_models/regional_panel_h7_live_evaluation/rsv_a_h7_rsv_ranking/<run_id>/
```

## Pflichtartefakte

Jeder erfolgreiche oder teil-erfolgreiche Run muss diese Dateien schreiben:

- `summary.json`
- `report.json`
- `report.md`
- `run_manifest.json`

Bei Fehlern können zusätzlich vorhanden sein:

- `error.json`
- `error.md`

## Was Im Manifest Stehen Muss

`run_manifest.json` ist die Audit-Wahrheit für den Run. Mindestens diese Felder sollen vorhanden sein:

- `run_id`
- `started_at`
- `finished_at`
- `virus`
- `horizon`
- `preset`
- `track`
- `output_root`
- `archive_dir`
- `artifact_path`
- `summary_path`
- `report_path`
- `report_md_path`
- `run_manifest_path`
- `git_commit_sha`
- `baseline_artifact_path`
- `baseline_artifact_version`
- `experiment_artifact_path`
- `experiment_artifact_version`
- `calibration_mode`
- `gate_outcome`
- `retained`
- `files_required`
- `files_written`
- `verification_passed`
- `verification_issues`

Die Manifest-Werte duerfen nur aus dem echten Lauf und den echten Artefakten stammen.

## Verifikation

Der Run prüft am Ende aktiv, ob alle Pflichtdateien wirklich auf Platte liegen.

Semantik:

- fehlen Pflichtdateien, endet der Lauf mit Fehlercode `2`
- wenn nur die Report-Validierung scheitert, bleibt das Artefakt trotzdem sichtbar als `partial_error`
- der Lauf gilt erst als promotionsfähig, wenn die Dateien existieren und der Vergleich ehrlich ist

## Vergleichswahrheit

Der Report muss Baseline und Experiment direkt vergleichbar machen und mindestens diese Werte ausgeben:

- `precision_at_top3`
- `activation_false_positive_rate`
- `ece`
- `brier`
- `calibration_mode`
- `gate_outcome`
- `retained`

Zusatzlich werden Baseline- und Experiment-Pfade archiviert, damit spätere Reviews ohne Annahmen auskommen.

## Ergebnisvorlage

Nach einem Serverlauf kann die Bewertung schnell in diese Form gebracht werden:

```text
RSV A / h7 Persistent Evaluation

Run ID:
Archive:
Baseline artifact:
Experiment artifact:

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

## Generischer Ausbau

Dieses Muster ist bewusst nicht nur für RSV A / h7 gedacht.

Es kann für andere h7-Pilot-Scopes wiederverwendet werden, solange diese drei Punkte gleich bleiben:

- fester Scope
- expliziter Output-Root
- verifizierte Pflichtartefakte

## Verwandte Dokumente

- [rsv_h7_live_evaluation_runbook.md](/Users/davidwegener/Desktop/viralflux/docs/rsv_h7_live_evaluation_runbook.md)
- [h7_pilot_only_training_path.md](/Users/davidwegener/Desktop/viralflux/docs/h7_pilot_only_training_path.md)
- [rsv_h7_go_no_go.md](/Users/davidwegener/Desktop/viralflux/docs/rsv_h7_go_no_go.md)
