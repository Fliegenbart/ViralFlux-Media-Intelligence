# Forecast Benchmarking

## Implementierter Rahmen

Der Code enthält jetzt einen Benchmarking-Rahmen für:

- WIS und relative WIS
- approximiertes CRPS auf Quantil-Gittern
- Winkler Score für 80% und 95% Intervalle
- Coverage 50/80/95
- Pinball Loss
- MAE, RMSE, MAPE als Diagnostik
- Brier, ECE, PR-AUC
- Recall und Utility am Aktions-Schwellenwert

## Artefakte

Ein Benchmark-Lauf kann schreiben:

- `summary.json`
- `leaderboard.json`
- `fold_diagnostics.json`
- `report.md`

## Aktueller Status

Die Infrastruktur ist implementiert. Ein echter produktionsnaher Benchmark gegen die Datenbank wurde in dieser Session nicht ausgeführt, weil dafür laufende Vintage-Daten und die operative Datenbasis benötigt werden.

## Verifizierter Smoke-Status

Die neue Test-Suite prüft bereits:

- Berechnung probabilistischer Metriken
- schärfere, gut zentrierte Forecasts schlagen breite Forecasts bei WIS/CRPS/Winkler
- Schreiben von Benchmark-Artefakten
- Registry-Promotion bei besserem `relative_wis`
- Registry-Blockade bei schlechterem `CRPS`

## Lokaler Ablauf

1. Modelle trainieren
2. Benchmark-Runner mit echten Issue-Dates und Vintage-Panels ausführen
3. Registry und erzeugte Reports prüfen
4. Champion erst nach bestandenen Gates promoten

## Hierarchie-Backtest

Für den regionalen Champion mit MinT-artiger Reconciliation gibt es jetzt ein eigenes Skript:

```bash
./.venv/bin/python backend/scripts/run_regional_hierarchy_backtest.py --virus "Influenza A" --horizon 7
```

Voraussetzung ist eine laufende App-Datenbank mit gesetzten Backend-Umgebungsvariablen.
