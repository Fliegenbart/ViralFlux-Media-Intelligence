# RSV A / h7 Go / No-Go

Stand: 2026-03-17

## Entscheidung

**GO**

## Begründung

Der echte Serverlauf wurde jetzt mit persistentem Output-Root ausgeführt und hat einen auditierbaren Archivbaum erzeugt unter:

- `/app/app/ml_models/regional_panel_h7_live_evaluation/rsv_a_h7_rsv_ranking/20260317T193728Z_1fb29d71/`

Der Run hat die Pflichtdateien geschrieben und `verification_passed = true` gesetzt:

- `summary.json`
- `report.json`
- `report.md`
- `run_manifest.json`

Der ausgewählte Experiment-Track war `rsv_signal_core` und hat die Baseline ehrlich uebertroffen:

| Rolle | precision_at_top3 | activation_false_positive_rate | ece | brier | calibration_mode | gate_outcome | retained |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| Baseline | 0.577778 | 0.005006 | 0.025965 | 0.028113 | raw_passthrough | WATCH (`precision_at_top3_passed`) | true |
| Experiment | 0.600000 | 0.003755 | 0.023418 | 0.026452 | raw_passthrough | GO | true |

Damit sind alle geforderten Kernbedingungen erfuellt:

- `precision_at_top3` ist gestiegen
- `activation_false_positive_rate` ist gesunken
- `ece` ist gesunken
- `brier` ist gesunken
- `calibration_mode` bleibt `raw_passthrough`
- `gate_outcome` ist `GO`
- `retained = true`

Der Run ist ausserdem im Docker-Volume unter

- `/var/lib/docker/volumes/viralflux-media-intelligence-clean_ml_models/_data/regional_panel_h7_live_evaluation/rsv_a_h7_rsv_ranking/20260317T193728Z_1fb29d71/`

persistent gespeichert und damit nach Container-Neustarts weiter verfuegbar.

## Ergebnis

Der Stand ist jetzt **GO** fuer den RSV A / h7 Ranking-Track auf Basis des echten, persistierten Serverlaufs.
