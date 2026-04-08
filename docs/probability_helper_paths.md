# Probability Helper Paths

Diese Notiz beschreibt den kanonischen Helper-Pfad für gelernte Event-Wahrscheinlichkeiten und Kalibrierung.

## Kanonischer Shared Helper

Die gemeinsame Utility-Schicht lebt in
`backend/app/services/ml/forecast_horizon_utils.py`.

Die kanonischen Einstiegspunkte sind:

- `select_probability_calibration(...)`
- `select_probability_calibration_from_raw(...)`
- `apply_probability_calibration(...)`

Diese Helper sind der Standard für:

- den einfachen learned/calibrated event-probability Pfad
- wiederverwendbare Kalibrierung bei Modellen, die nur rohe Probability-Arrays haben

## Simple Path

Der Simple-Pfad in `ForecastService` verwendet:

- `select_probability_calibration(...)` für die Auswahl von `isotonic`, `platt` oder `raw_probability`
- `apply_probability_calibration(...)` für die Anwendung der finalen Kalibrierung

Damit bleibt die Kalibrierungslogik an einer Stelle konzentriert.

## Regional Path

Der regionale Hauptpfad in `RegionalModelTrainer` bleibt bewusst strenger:

- `_select_guarded_calibration(...)` ist weiterhin die kanonische Auswahlregel für den regionalen Promotion- und Backtest-Pfad
- `apply_probability_calibration(...)` bleibt auch dort der gemeinsame Anwendungs-Helper

Der Grund ist fachlich:

- der regionale Hauptpfad guardet nicht nur `brier_score` und `ece`
- er prüft zusätzlich operative Kennzahlen wie `precision_at_top3` und `activation_false_positive_rate`

Deshalb wird die Auswahlregel dort nicht auf den einfacheren Shared Helper reduziert.

## LearnedEventModel

`backend/app/services/ml/models/event_classifier.py` soll keine eigene ad-hoc-Kalibrierungslogik mehr tragen.

Der Modellpfad nutzt jetzt:

- `select_probability_calibration_from_raw(...)`
- `apply_probability_calibration(...)`

Wichtig:

- das Verhalten bleibt konservativ
- für `LearnedEventModel` sind weiterhin nur `isotonic` oder `raw_passthrough` aktiv
- es wird nicht stillschweigend ein neuer Produktmodus eingefuehrt

## Fallback-Verhalten

- Simple Path: `raw_probability`
- Regional Hauptpfad: `raw_passthrough`
- `LearnedEventModel`: `raw_passthrough`

Der Unterschied ist historisch und produktseitig sichtbar, deshalb wird er vorerst beibehalten.
