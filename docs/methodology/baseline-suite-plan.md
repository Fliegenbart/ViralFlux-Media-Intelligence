# Baseline Suite Plan

**Status:** Diskussionsplan vor Code. Kein Implementation-Go.  
**Ziel:** FluxEngine nicht nur gegen Persistenz testen, sondern gegen vier faire, einfache Baselines mit identischer Zielvariable, identischen Walk-forward-Splits und 95%-Konfidenzintervallen.

## 1. Baseline-Spezifikation

Alle Baselines implementieren das geplante Interface `fit(train_data)`, `predict(horizon_weeks)`, `name()` und `assumptions()`. `predict()` liefert pro `as_of_date × Bundesland × Virus` einen numerischen Forecast und einen daraus abgeleiteten Event-Score.

| Baseline | Exakte v1-Spezifikation | Annahme |
| --- | --- | --- |
| `PersistenceBaseline` | Vorhersage = letzter verfügbarer Wert je Bundesland/Virus zum `as_of_date`. Bestehende Persistenzlogik wird nur auf das gemeinsame Interface gehoben. | Nächste Woche sieht aus wie die letzte bekannte Woche. |
| `SeasonalNaiveBaseline` | Vorhersage = gleiche ISO-Woche im Vorjahr je Bundesland/Virus. Kein gleitendes Fenster in v1. Wenn kein Vorjahreswert existiert, erzeugt die Baseline `missing_prediction`; primäre Vergleichsmetriken laufen auf der gemeinsamen Schnittmenge aller evaluierbaren Modelle. | Saisonmuster wiederholt sich grob jährlich. |
| `MovingAverageBaseline` | Vorhersage = Durchschnitt der letzten 4 verfügbaren Wochen je Bundesland/Virus, strikt vor `as_of_date`. Default: `window=4`, `lag=1`; beide konfigurierbar, aber im Bericht fest dokumentiert. | Kurzfristiges Niveau ist geglättete jüngste Vergangenheit. |
| `SimpleArimaBaseline` | `statsmodels` ARIMA(1,1,1), separat pro Bundesland/Virus auf `log1p` des Zielwerts. Keine SARIMA-Terme und kein saisonales Pre-Processing in v1; Saisonalität wird bewusst durch `SeasonalNaiveBaseline` separat geprüft. Wenn eine Region zu wenig Historie hat oder Fit fehlschlägt: `missing_prediction`, nicht fallback-schöngerechnet. | Lokale Autokorrelation plus Differenzierung reicht als einfache Zeitreihen-Baseline. |

## 2. Zielvariable

Primär vergleichen wir nicht AMELAG-Rohwert und nicht Sales, sondern exakt das aktuelle FluxEngine-Backtest-Ziel: das abgeleitete regionale Wellen-/Anstiegslabel aus dem bestehenden Regional-Harness (`event_label`, aktuell `regional_survstat_v2`) für denselben Virus, dieselbe Region und denselben Horizont. Baselines dürfen numerische Inzidenz-/Signalwerte prognostizieren, aber PR-AUC, Top-3 und Lead-Zeit werden aus derselben Event-Definition und demselben Probability-/Score-Adapter berechnet wie FluxEngine. So vergleichen wir nicht Äpfel mit Birnen.

## 3. Walk-forward-Splits

Die Suite hängt an den bestehenden regionalen Backtest-Panels und nutzt dieselbe Point-in-Time-Semantik wie `regional_trainer_backtest.py`. V1-Scope: H7 für die cockpit-relevanten Viren; H5 erst separat, wenn die H5-Datenlage stabil ist. Warm-up: mindestens 104 Wochen Training, danach rolling-origin Walk-forward über alle verfügbaren Wochen. Jede Baseline wird pro Fold nur auf Vergangenheit gefittet; ARIMA wird pro Fold und Bundesland/Virus neu gefittet. Re-Training-Frequenz: jedes Forecast-Origin im Walk-forward.

## 4. Harness-Schnittstelle

Neue Dateien nach GO: `/backtests/baselines/<baseline_name>.py`, `/backtests/baselines/runner.py`, `/backtests/baselines/test_baselines.py`, Output nach `/backtests/baselines/results/comparison_<run_id>.csv`. Der Runner baut eine gemeinsame OOF-Tabelle mit Spalten wie `model_name`, `as_of_date`, `target_week_start`, `virus_typ`, `bundesland`, `event_label`, `score`, `predicted_value`, `missing_reason`. FluxEngine wird als eigener `model_name` aus dem bestehenden OOF-Frame eingehängt. Metriken: PR-AUC gesamt und per Bundesland, Precision@Top-3, Recall@Top-3, Median Lead-Zeit in Wochen. 95%-CI via Bootstrap `n=1000`, blockweise nach Forecast-Woche/`as_of_date`, Seed fixiert und im CSV dokumentiert.

## 5. Validierung vor Ergebnisbericht

Tests decken die vier kritischen Sanity-Checks ab: konstante Daten müssen Persistenz perfekt machen; Random-Daten dürfen keine künstlich gute PR-AUC erzeugen; identisch konfigurierte FluxEngine-/Baseline-Scores müssen gleiche Metriken liefern; zwei Bootstrap-Läufe mit `n=1000` müssen innerhalb ±0.5 Prozentpunkte stabil sein. Danach folgt `/docs/methodology/baseline-suite-results-v1.md` mit einfacher Sprache: welche Baselines FluxEngine schlägt, welche nicht, und welche Claims wir GELO ehrlich zumuten können.

**Stop-Regel:** Wenn FluxEngine eine Baseline nicht klar schlägt, wird nichts am Modell „passend gemacht“. Ergebnis dokumentieren, an David eskalieren, dann gemeinsam entscheiden.
