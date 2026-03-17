# Forecast Horizon Architecture

## Ziel

`horizon_days` ist im regionalen Forecast-Pfad ein echter Produktparameter. Offiziell unterstützt werden nur:

- `3`
- `5`
- `7`

Alle anderen Werte werden an der API mit `422` abgewiesen und im Service per `ensure_supported_horizon()` hart validiert.

## Kanonischer Pfad

Der regionale Online-Pfad bleibt:

1. `GET /api/v1/forecast/regional/*`
2. `RegionalForecastService.predict_all_regions(virus_typ, horizon_days)`
3. `RegionalDecisionEngine.evaluate(...)`
4. `RegionalMediaAllocationEngine.allocate(...)`

Die Decision-Hook bleibt unverändert in `RegionalForecastService.predict_all_regions()`.

## Wie Horizons technisch aufgelöst werden

### 1. Horizon-spezifische Features

`RegionalFeatureBuilder` erhält `horizon_days` und baut den Kontext für genau diesen Horizont:

- `target_date = as_of_date + horizon_days`
- `target_week_start = Wochenstart des target_date`
- Weather-/Holiday-Kontext wird horizon-spezifisch auf den exakten Zieltag bezogen
- `target_window_days` wird auf `[horizon_days, horizon_days]` gesetzt

Die Feature-Namen bleiben weitgehend stabil, aber ihre Werte sind jetzt horizon-spezifisch.

### 2. Horizon-spezifische Targets im Training

`RegionalModelTrainer` leitet das Regressions-/Event-Target aus dem zukünftigen Punkt-in-Zeit-Panel ab:

- pro Bundesland wird die Zeile mit `as_of_date + horizon_days` gesucht
- deren `current_known_incidence` wird zum Zielwert des früheren As-of-Datums
- dadurch ist das Training exakt horizon-spezifisch und leakage-safe

Die bestehende Event-Definition bleibt erhalten, wird aber jetzt auf das exakte Horizon-Target angewendet.

### 3. Horizon-spezifische Artefakte

Persistierte regionale Modelle liegen unter:

`backend/app/ml_models/regional_panel/<virus_slug>/horizon_<horizon_days>/`

Beispiel:

`backend/app/ml_models/regional_panel/influenza_a/horizon_5/`

Dort liegen getrennt pro Horizon:

- `classifier.json`
- `regressor_median.json`
- `regressor_lower.json`
- `regressor_upper.json`
- `calibration.pkl`
- `metadata.json`
- `backtest.json`
- `dataset_manifest.json`
- `point_in_time_snapshot.json`
- `threshold_manifest.json`

## Response-Semantik

Der Forecast-Response spiegelt den tatsächlichen Horizon wider:

- `horizon_days`
- `supported_horizon_days`
- `target_window_days` als `[h, h]`
- `target_date`

Aus Kompatibilitätsgründen bleibt `expected_next_week_incidence` erhalten. Es ist jetzt ein Legacy-Feldname und bedeutet:

`erwartete Inzidenz am angefragten Horizon`

Additiv wird auch `expected_target_incidence` ausgegeben.

## Empty States und Fallbacks

### Invalid Horizon

- API: `422`
- Service: `ValueError`

### Kein Modell für den angefragten Horizon

`predict_all_regions()` liefert einen stabilen `no_model`-Payload mit:

- `status`
- `message`
- `horizon_days`
- `target_window_days`
- leeren `predictions`

### Fehlende Horizon-Metadaten

Scoped Artefakte ohne `metadata.horizon_days` werden nicht still verwendet. Der Loader markiert das als `load_error`, und der Forecast-Service antwortet mit `no_model`.

## Übergangsmodus

Es gibt genau einen expliziten Übergangsmodus:

- angefragter Horizon `7`
- kein neues `horizon_7/`-Artefakt vorhanden
- aber ein Legacy-Modell im alten Root-Verzeichnis existiert

Dann wird das Legacy-Artefakt noch gelesen und im Payload markiert mit:

- `artifact_transition_mode = "legacy_default_window_fallback"`

Wichtig:

- dieser Fallback gilt nur für `7`
- `3` und `5` fallen nie still auf Legacy zurück
- sobald horizon-spezifisches Retraining erfolgt, verschwindet dieser Modus

## Downstream-Verhalten

- Decision bleibt am bestehenden Hook und bekommt denselben horizon-spezifischen Forecast-Output
- Allocation konsumiert weiterhin den kanonischen Forecast-/Decision-Output
- `predictions`-Ranking, `top_decisions` und Allocation-Ranking bleiben getrennt
