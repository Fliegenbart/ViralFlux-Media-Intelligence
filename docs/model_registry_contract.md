# Model Registry Contract

## Geltungsbereich

Dieses Dokument beschreibt den finalen Contract für persistierte ML-Artefakte im Regional-Forecast-Pfad.

## Schlüssel

Ein regionales Modell ist eindeutig über diese Dimensionen adressiert:

- `virus_typ`
- `horizon_days`
- `model_family = "regional_pooled_panel"`

Es gibt aktuell kein separates per-State-Modellverzeichnis. Das regionale Modell ist ein gepooltes Panel-Modell pro Virus und Horizon.

## Verzeichnisstruktur

Pfad:

`backend/app/ml_models/regional_panel/<virus_slug>/horizon_<horizon_days>/`

Beispiel:

`backend/app/ml_models/regional_panel/sars_cov_2/horizon_7/`

## Pflichtdateien

Ein lauffähiges regionales Inferenz-Artefakt benötigt:

- `classifier.json`
- `regressor_median.json`
- `regressor_lower.json`
- `regressor_upper.json`
- `calibration.pkl`
- `metadata.json`

Optionale, aber erwartete Sidecars:

- `backtest.json`
- `dataset_manifest.json`
- `point_in_time_snapshot.json`
- `threshold_manifest.json`

Wenn Pflichtdateien fehlen, gilt der Scope als `no_model`.

## Pflichtfelder in metadata.json

Mindestens erforderlich:

- `virus_typ`
- `model_family`
- `trained_at`
- `horizon_days`
- `target_window_days`
- `feature_columns`
- `action_threshold`
- `quality_gate`
- `aggregate_metrics`

Empfohlen bzw. heute ebenfalls geschrieben:

- `supported_horizon_days`
- `forecast_target_semantics`
- `model_version`
- `calibration_version`
- `label_selection`
- `signal_bundle_version`
- `rollout_mode`
- `activation_policy`
- `dataset_manifest`
- `point_in_time_snapshot`

## Horizon-Integrität

Scoped Artefakte unter `horizon_<n>/` müssen in `metadata.json` dasselbe `horizon_days` tragen.

Wenn ein Loader feststellt:

- `metadata.horizon_days` fehlt oder
- `metadata.horizon_days != angefragter_horizon`

darf das Artefakt nicht still verwendet werden.

Der Service markiert diesen Fall als `load_error`, und die öffentliche API antwortet mit `no_model`.

## Versionierung

Die regionale Versionierung ist horizon-spezifisch:

- `model_version = regional_pooled_panel:h<horizon>:<trained_at>`
- `calibration_version = isotonic:h<horizon>:<trained_at>`

Damit bleibt Lineage auch dann eindeutig, wenn mehrere Horizonte parallel für denselben Virus live liegen.

## Backtest- und Manifest-Contract

`backtest.json`, `dataset_manifest.json` und `point_in_time_snapshot.json` sollen denselben Horizon-Kontext tragen:

- `horizon_days`
- `target_window_days`

Der Backtest bezieht sich damit immer auf genau den angefragten Horizon und nicht mehr auf einen impliziten 3-7-Tage-Korridor.

## Übergangsmodus

Der einzige erlaubte Übergangsmodus ist:

- Request `horizon_days = 7`
- neues `horizon_7/`-Verzeichnis fehlt
- Legacy-Root-Artefakte unter `<virus_slug>/` existieren

Dann wird im Loader markiert:

- `artifact_transition_mode = "legacy_default_window_fallback"`
- `requested_horizon_days = 7`

Dieser Modus ist ausdrücklich temporär. Für `3` und `5` gibt es keinen Legacy-Fallback.
