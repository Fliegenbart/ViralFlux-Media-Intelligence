# H7 Residual Forecast Status Report

Date: 2026-04-13

## Kurzfassung

Der neue H7-Pfad fuer `Influenza A / h7` und `Influenza B / h7` ist jetzt technisch und fachlich durchgelaufen.

Die wichtigsten Punkte:

- Forecast-Kern laeuft jetzt als `residual_baseline_v2`
- Event-Wahrscheinlichkeit kommt produktiv aus `forecast_implied`
- Sommer-Folds ohne Events blockieren den ganzen Lauf nicht mehr
- SurvStat wird wirklich als Wahrheit und als Feature-Familie genutzt
- `Influenza A / h7` und `Influenza B / h7` bestehen beide das neue Quality Gate
- beide Scopes sind in der Registry als Champion eingetragen

## Was wir umgebaut haben

Der Forecast sagt nicht mehr direkt den absoluten Wert in 7 Tagen voraus.
Stattdessen baut er zuerst eine starke Basis und lernt danach nur noch die Abweichung davon.

Zusatzregeln im neuen Stand:

- Persistence-Mischung bleibt aktiv
- Event-Discrimination wird nur auf viable Folds bewertet
- Off-Season-Folds bleiben fuer Forecast- und False-Alarm-Bewertung erhalten
- Shadow-Klassifikator bleibt nur Benchmark, nicht Hauptquelle

## SurvStat-Nutzung

SurvStat ist jetzt nicht nur "mitgeladen", sondern ein echter Teil des Modells.

Bei beiden Scopes:

- `truth_source = survstat_kreis`
- `feature_columns = 169`
- davon `24` direkte oder abgeleitete `survstat_`-Features

Typische SurvStat-Signale:

- `survstat_current_incidence`
- `survstat_lag1w`
- `survstat_lag2w`
- `survstat_lag4w`
- `survstat_lag8w`
- `survstat_baseline_gap`
- `survstat_baseline_zscore`
- `survstat_momentum_2w`
- `survstat_momentum_4w`

Zusaetzliche Modellbeobachtung aus den echten Serverlaeufen:

- `Influenza A`: 8 von 20 Top-Features sind SurvStat-bezogen
- `Influenza B`: 9 von 20 Top-Features sind SurvStat-bezogen

## Serverlaeufe

### Influenza A

- Run: `20260413T090130Z_influenza_a_h7_fast_evalv2`
- Scope: `Influenza A / h7`
- Ergebnis: erfolgreich

### Influenza B

- erster Versuch: `20260413T093317Z_influenza_b_h7_fast_evalv2`
- Status: Training selbst lief, finaler Registry-Schreibschritt scheiterte an einem falschen Zielpfad
- finaler Fix-Lauf: `20260413T112043Z_influenza_b_h7_fast_evalv2_fixreg`
- Ergebnis: erfolgreich

## Operativer Fix fuer den Server

Der Serverfehler war kein Modellproblem, sondern ein Registry-Pfadproblem.

Ursache:

- der Trainer nutzte bisher standardmaessig den lokalen App-Pfad `app/ml_models/forecast_registry`
- im Docker-Lauf war dieser Pfad fuer `appuser` nicht beschreibbar

Fix im Code:

- der Registry-Pfad ist jetzt per `FORECAST_REGISTRY_DIR` oder `ML_FORECAST_REGISTRY_DIR` konfigurierbar
- `RegionalModelTrainer`, `XGBoostTrainer` und `ForecastRegistry` koennen damit denselben beschreibbaren Zielordner verwenden

Fix im Serverlauf:

- der beschreibbare Ordner `/root/viralflux-h7-runs/forecast_registry` wurde nach `/app/backend/app/ml_models/forecast_registry` gemountet
- fuer zukuenftige manuelle Serverlaeufe gibt es jetzt das eingecheckte Startskript `scripts/run-h7-server-eval.sh`
- dieses Skript setzt und mountet den Registry-Pfad automatisch richtig, damit der fruehere Schreibfehler nicht wieder passiert

## Vergleich A vs. B

### Gemeinsamer Stand

Beide Scopes:

- `forecast_core_mode = residual_baseline_v2`
- `event_probability_source = forecast_implied`
- `baseline_component_weights = {current_log: 1.0, seasonal_log: 0.0, pooled_log: 0.0}`
- `persistence_mix_weight = 0.75`
- `fold_viability`: 4 viable Folds, 1 nicht-viabler Sommer-Fold

### Influenza A

- `WIS = 9.197715`
- `CRPS = 2.299429`
- `PR-AUC = 0.697`
- `Brier = 0.068157`
- `ECE = 0.018633`
- `precision_at_top3 = 0.72549`
- `activation_false_positive_rate = 0.006773`

Ablation:

- `A_baseline_only`: `WIS 14.724345`
- `B_residual_quantiles`: `WIS 10.351844`
- `C_mixed_champion`: `WIS 9.197715`

Lesart:

- die Baseline ist brauchbar
- das Residualmodell bringt echten Zusatznutzen
- die Mischung mit Persistence verbessert weiter

### Influenza B

- `WIS = 8.870381`
- `CRPS = 2.217595`
- `PR-AUC = 0.716451`
- `Brier = 0.068163`
- `ECE = 0.02904`
- `precision_at_top3 = 0.742063`
- `activation_false_positive_rate = 0.003098`

Ablation:

- `A_baseline_only`: `WIS 14.647281`
- `B_residual_quantiles`: `WIS 9.958033`
- `C_mixed_champion`: `WIS 8.870381`

Lesart:

- B ist insgesamt etwas staerker als A
- A ist etwas sauberer kalibriert
- beide bestehen den neuen Bewertungsrahmen

## Forecast-implied vs. Shadow-Klassifikator

Der Shadow-Klassifikator ist beim Ranking weiterhin staerker, aber aggressiver.

Beispiel `Influenza B`:

- `forecast_implied`: `PR-AUC 0.716451`, `activation_false_positive_rate 0.003098`
- `shadow_classifier`: `PR-AUC 0.832164`, `activation_false_positive_rate 0.022305`

Lesart:

- Shadow trifft mehr
- Shadow feuert aber auch deutlich mehr Fehlalarme
- der produktive `forecast_implied`-Pfad ist vorsichtiger und semantisch sauberer in den Forecast eingebettet

## Offene Punkte

Der Umbau ist funktional fertig, aber noch nicht maximal stark.

Wichtigste Beobachtung:

- beide Scopes haengen noch stark an der Basis
- `current_log` dominiert die Baseline-Gewichte
- `persistence_mix_weight = 0.75` zeigt weiterhin hohe Naehe zur starken Persistence-Basis

Das ist nicht falsch, aber es bedeutet:

- der Zusatznutzen ist real
- die Modelle sind noch konservativ

## Empfohlene naechste Schritte

1. Ablationsergebnisse A/B/C/D in einen kompakten Dashboard- oder Export-Readout uebernehmen.
2. Server-Start fuer H7-Laeufe dauerhaft auf den konfigurierbaren Registry-Pfad standardisieren.
3. Spaeter gezielt pruefen, ob der Shadow-Klassifikator als zweiter Experte Mehrwert bringt, ohne die False-Positive-Rate zu stark anzuheben.
