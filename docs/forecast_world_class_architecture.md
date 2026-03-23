# Forecast World-Class Architecture

## Bausteine

- `benchmarking/`: Bewertungslogik, Leaderboards, Artefakte, Registry
- `models/`: wiederverwendbare Challenger-Komponenten
- `forecast_orchestrator.py`: dünne Koordinationsschicht für Registry und Live-Entscheidungen
- `regional_trainer.py`: erster Champion-Kandidat mit probabilistischen Artefakten
- `regional_forecast.py`: stabile API-Ausgabe plus additive Metadaten

## Datenfluss

1. Feature Builder baut point-in-time sichtbare Panels.
2. Trainer erstellt probabilistische Modelle und Event-Kalibrierung.
3. Benchmarking bewertet Kandidaten auf Rolling-Origin-Folds.
4. Registry speichert Champion/Challenger-Entscheidungen.
5. Live-Forecast liest Champion-Metadaten und ergänzt Traceability-Felder.

## Additive Live-Metadaten

- `champion_model_family`
- `ensemble_component_weights`
- `hierarchy_driver_attribution`
- `revision_policy_used`
- `benchmark_evidence_reference`

Diese Felder erweitern die Antwort, ersetzen aber keine bestehenden Felder.
