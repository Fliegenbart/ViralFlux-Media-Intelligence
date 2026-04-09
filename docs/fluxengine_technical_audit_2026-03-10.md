# FluxEngine Technical Audit

Datum: 2026-03-10

## Kurzfazit

FluxEngine hat zwei sehr unterschiedliche mathematische Qualitaetsniveaus:

- Der Forecast-/Backtest-Kern ist formal am stärksten. Dort gibt es echte Zeitreihenmodelle, Leakage-Guards, Walk-forward-Logik und Baseline-Vergleiche.
- Die Score- und Decision-Layer sind deutlich heuristischer. Dort sind mehrere Größen sauber als Ranking- oder Priorisierungssignale nutzbar, aber nicht als empirisch kalibrierte Wahrscheinlichkeiten oder Konfidenzen.

Das wichtigste Gesamturteil lautet:

| Subsystem | Urteil | Begründung |
| --- | --- | --- |
| `forecast_service` | mathematisch konsistent | Reale Modellpipeline mit Leakage-Schutz, OOF-Training und Quantil-Ausgabe. Aber Promotion-Backtest spiegelt die Live-Inferenz nicht vollstaendig. |
| `backtester` Walk-forward | mathematisch konsistent | As-of-/Vintage-Logik, Baseline-Vergleich, Lead-/Lag-Metriken und Quality Gate sind formal plausibel. |
| `backtester` Gewichtskalibrierung -> Business-Gewichte | nicht belastbar | Feature-Importances eines autoregressiven SURVSTAT-Modells werden heuristisch auf `bio/market/psycho/context` gemappt und dann produktiv weiterverwendet. |
| ehemalige Legacy-Risk-Engine (Auditstand 2026-03) | nicht belastbar | Mehrere Einheiten wurden unzulässig gemischt; die Baseline-Korrektur verglich einen Fusionsscore mit Positivraten. |
| `peix_score_service` | heuristisch konsistent aber nicht statistisch validiert | Die 6D-Fusion ist intern konsistent und sauber begrenzt, aber die Wahrscheinlichkeits-Semantik und Gewichtskalibrierung sind nicht empirisch belegt. |
| `opportunity_engine` / Detektoren | heuristisch konsistent aber nicht statistisch validiert | `urgency_score` ist als Priorisierung brauchbar, aber nicht als abgesicherte Wirkungs- oder Eintrittswahrscheinlichkeit. |

## Scope und Evidenz

Analysierte Kernpfade:

- `backend/app/services/ml/forecast_service.py`
- `backend/app/services/ml/backtester.py`
- historische Legacy-Risk-Engine (zum Auditzeitpunkt im Repo, inzwischen entfernt)
- `backend/app/services/media/peix_score_service.py`
- `backend/app/services/marketing_engine/opportunity_engine.py`
- relevante API-/Cockpit- und Detector-Pfade

Durchgefuehrte reproduzierbare Checks:

```bash
source /tmp/viralflux-audit-venv311/bin/activate
pytest -q app/tests/test_backtester_math.py \
         app/tests/test_opportunity_engine_math.py \
         app/tests/test_forecast_service_guards.py \
         app/tests/test_ml_tasks_accuracy.py

pytest -q app/tests/test_model_trainer_guards.py \
         app/tests/test_ml_training_task_contract.py \
         app/tests/test_admin_ml_api.py
```

Ergebnis:

- `27 passed` in den Math-/Guard-/Accuracy-Tests
- `12 passed` in den Trainer-/API-Guard-Tests
- Gesamt: `39 passed`

Wichtige Einschraenkungen:

- Die lokale Default-Runtime war Python 3.9; der Repo-Code benötigt faktisch Python 3.11+ wegen `| None`-Typannotation in `config.py`.
- Es gibt im Repo keine produktiven Rohdaten und keine `.env`-Datei. `data/raw/` und `data/processed/` enthalten nur `.gitkeep`.
- Deshalb konnte keine echte produktive OOS-Evaluierung auf befüllter Datenbank gefahren werden. Die empirische Evidenz in diesem Audit stammt aus Code, Tests und reproduzierbarer statischer Laufzeitprüfung.

## Claim-Inventar

Die wichtigste Trennung für dieses System ist:

| Output | Typ | Aktuelle Semantik im Code | Audit-Urteil |
| --- | --- | --- | --- |
| `forecast` median/lower/upper | statistische Prognose | Vorhersage mit Quantilen | mathematisch konsistent |
| `forecast.confidence` | Konfigurationswert | aktuell effektiv nur `settings.CONFIDENCE_LEVEL` | nicht belastbar als Modellkonfidenz |
| `outbreak_risk_score` | Sigmoid-Ranking | z-Score -> Sigmoid | heuristisch konsistent |
| `final_risk_score` im Legacy-RiskEngine | Fusionsscore | heuristischer 0-100 Score | nicht belastbar |
| `PeixEpiScore.score_0_100` | Composite-Ranking | 6D-Fusion, 0-100 | heuristisch konsistent |
| `impact_probability` im Peix | Pseudo-Probability | Sigmoid auf Score | nicht belastbar als Probability |
| `confidence_numeric` / `confidence_label` | Agreement-Proxy | Streuung der Teilsignale | heuristisch konsistent |
| `urgency_score` | Priorisierung | Detector-spezifische Heuristik | heuristisch konsistent |
| `confidence_pct` in Opportunity-Briefs | Mix aus Confidence und Urgency | faellt auf `urgency_score` zurück | nicht belastbar |
| `quality_gate` | Entscheidungs-Gate | Schwellen auf Hit Rate / Lead / Fehler | mathematisch konsistent als Policy-Gate |

## Detaillierte Analyse

Hinweis zur Einordnung:

- Dieses Dokument beschreibt den Auditstand vom 10.03.2026.
- Einige damals geprüfte Legacy-Dateien wurden inzwischen aus dem aktiven Repo entfernt.
- Wo dieses Audit von der "Legacy-Risk-Engine" spricht, ist damit die damalige, inzwischen entfernte Implementierung gemeint.

### 1. `forecast_service`: stärkster mathematischer Baustein

Positive Punkte:

- OOF-Struktur und Leakage-Schutz sind bewusst eingebaut. `prophet_pred` wird im Meta-Learner-Training als verschobener Rolling-Proxy aufgebaut, nicht als in-sample Truth-Leak (`forecast_service.py:795-803`).
- Warmup-Zeilen werden entfernt und Quellen nur vorwaerts gefuellt, nicht rueckwaerts in die Vergangenheit geblendet. Das wird durch Tests abgesichert (`test_forecast_service_guards.py`).
- Quantil-Crossing wird in der Inferenz aktiv korrigiert (`forecast_service.py:1107-1109`).
- Der Forecast wird gegen Ridge, Holt-Winters und Prophet kombiniert, nicht nur gegen ein einzelnes starres Modell.

Hauptschwaechen:

1. Promotion-Backtest und Live-Inferenz sind nicht isomorph.
   - Im Promotion-Pfad wird Prophet nicht echt verwendet, sondern als konstanter `prophet_proxy` aus dem letzten Mittelwert approximiert (`forecast_service.py:899-902`).
   - In der Live-Inferenz wird dagegen `_fit_prophet()` wirklich aufgerufen (`forecast_service.py:1052-1059`).
   - Damit wird nicht exakt das evaluiert, was später deployed wird.

2. Horizon-Features werden waehrend der Validierung nicht rekursiv aktualisiert.
   - In `evaluate_training_candidate()` wird für alle Validierungsschritte dieselbe `last_row` verwendet (`forecast_service.py:908-920`).
   - Die Basis-Forecasts ändern sich pro Schritt, exogene Meta-Features wie Momentum, AMELAG-Lags oder Trends bleiben aber eingefroren.
   - Das macht die Validierung für laengere Horizonte optimistischer oder zumindest anders als die reale Zeitentwicklung.

3. `confidence` ist keine empirische Modellkonfidenz.
   - Der Rueckgabewert ist einfach `settings.CONFIDENCE_LEVEL` (`forecast_service.py:1131-1140`).
   - Das ist ein Intervall-Level-Parameter, keine ausgeschaetzte Zuverlässigkeit des konkreten Forecasts.

4. `outbreak_risk_score` ist ein Ranking-Signal, keine Wahrscheinlichkeit.
   - Der Wert entsteht aus einem z-Score gegen die juengste Historie und wird durch eine Sigmoid-Funktion gejagt (`forecast_service.py:975-988`).
   - Das ist als Monotonie-/Priorisierungsfunktion sinnvoll, aber ohne Kalibrierung keine Probability.

Urteil:

- Forecast-Median/Intervalle: `mathematisch konsistent`
- `confidence`: `nicht belastbar`
- `outbreak_risk_score`: `heuristisch konsistent aber nicht statistisch validiert`

### 2. `backtester`: gute OOS-Basis, aber problematische Gewichts-Ableitung

Positive Punkte:

- Strikte Vintage-/As-of-Logik ist vorhanden und zentral in die Zeitreise-Queries eingebaut.
- Walk-forward-Backtest trainiert nur auf bis zum Forecast-Zeitpunkt verfügbaren Zielwerten (`backtester.py:1948-1955`).
- Es gibt Baseline-Vergleiche gegen Persistence und Seasonal-Naive (`backtester.py:1991-2035`).
- Lead-/Lag-, TTD-, False-Alarm- und Quality-Gate-Metriken sind explizit implementiert und durch Tests abgesichert.

Hauptschwaechen:

1. Das produktive "Gewicht-Lernen" ist semantisch nicht identifiziert.
   - `optimized_weights` stammen im Walk-forward-Pfad aus XGBoost-Feature-Importances eines rein autoregressiven SURVSTAT-Modells (`backtester.py:2037-2048`).
   - Diese Feature-Importances werden anschliessend heuristisch auf `bio/market/psycho/context` gemappt (`backtester.py:2855-2917`).
   - Danach werden sie als globale Standardgewichte gespeichert (`backtester.py:2990-3036`).
   - Das ist keine belastbare Schätzung der Business-Dimensionen, sondern eine semantische Nachaggregation.

2. Die Faktor-Zuordnung ist fachlich fragwürdig.
   - `are_*`, `grippeweb*` und `notaufnahme*` werden zu `market` gemappt (`backtester.py:2882-2889`), obwohl sie epidemiologische oder syndromische Signale sind.
   - Diese Umkodierung verschiebt spätere Produktgewichte systematisch.

3. Der Walk-forward-Teil ist stärker als die spätere 4D-/6D-Kalibrierung.
   - Als Backtest-Engine ist der Pfad gut.
   - Als Quelle für globale Score-Gewichte ist derselbe Pfad zu indirekt und semantisch unsauber.

Urteil:

- Walk-forward, Vintage, Quality Gate: `mathematisch konsistent`
- Feature-Importance -> 4D-Gewichte -> globale Defaults: `nicht belastbar`

### 3. Ehemalige Legacy-Risk-Engine: zentrale mathematische Schwachstelle

Zum Auditzeitpunkt hing diese Engine weiterhin produktiv an den Outbreak- und Public-Risk-APIs (`api/outbreak_score.py:63-71`, `api/public_api.py:207-214`).

Hauptprobleme:

1. Das Fusionsgewicht ist größer als 1.0.
   - `WEIGHT_BIO + WEIGHT_MARKET + WEIGHT_PSYCHO + WEIGHT_CONTEXT` summieren standardmäßig auf 1.0.
   - Zusätzlich wurde `prophet_baseline * 0.15` addiert.
   - Das ist kein normierter Weighted Average mehr, sondern ein übergewichteter Score mit anschliessendem Cap.

2. Die Baseline-Korrektur mischt inkompatible Einheiten.
   - Die historische Baseline basierte auf Positivraten aus Labordaten.
   - Der aktuelle Wert war aber `raw_score / 100` aus einem zusammengesetzten Fusionsscore.
   - Ein 0-1 Fusionsscore wird damit gegen eine echte Positivratenverteilung getestet. Das ist mathematisch nicht dieselbe Zielgröße.

3. Meta-Overlay mischt absolute Last mit heuristischem Index.
   - `meta_prediction` wurde auf das Jahresmaximum der Viruslast normalisiert und dann 70/30 mit dem heuristischen Endscore gemischt.
   - Auch hier werden unterschiedliche Semantiken auf dieselbe 0-100 Achse gezwungen.

4. Konfidenz ist Agreement, nicht Evidenzqualitaet.
   - `confidence_numeric` hing nur von der Streuung der Teilscores ab.
   - Das misst Signal-Konsens, nicht Messqualitaet, Coverage oder OOS-Genauigkeit.

Urteil:

- `final_risk_score`: `nicht belastbar`
- `confidence_numeric` / `confidence_level`: `heuristisch konsistent aber nicht statistisch validiert`

### 4. `peix_score_service`: brauchbarer Ranking-Score, aber Probability-Semantik überzogen

Positive Punkte:

- Die 6D-Gewichte summieren sich sauber auf 1.0 (`peix_score_service.py:87-95`).
- Der Score ist begrenzt, die adaptive Epi-Score-Logik bleibt innerhalb `0..1`, und die Endfusion ist intern konsistent (`peix_score_service.py:270-287`).
- Die Implementierung ist wesentlich sauberer als die damalige Legacy-Risk-Engine.

Hauptschwaechen:

1. `impact_probability` ist keine kalibrierte Probability.
   - Sie entsteht nur aus einer Sigmoid-Funktion über den Endscore (`peix_score_service.py:285-287`, `364-367`).
   - Ohne empirische Kalibrierung ist das eine monotone Score-Abbildung, keine Eintrittswahrscheinlichkeit.

2. Die Gewichtskalibrierung ist heuristisch aufgespalten.
   - `context` aus `LabConfiguration` wird willkuerlich 50/30/20 auf `forecast/weather/baseline` verteilt (`peix_score_service.py:150-180`).
   - Das ist dokumentiert und transparent, aber nicht statistisch identifiziert.

3. Regionale und nationale Ebenen mischen nationale und regionale Signale.
   - `forecast`, `search`, `shortage` und `baseline` sind national und fliessen in jede Region identisch ein (`peix_score_service.py:211-217`, `270-278`).
   - Regionale Unterschiede entstehen damit hauptsächlich über `bio` und `weather`.
   - Das ist als Cockpit-Ranking okay, aber nicht als regionale Risikowahrscheinlichkeit.

4. Nationale Aggregation ist ein einfacher Regionsmittelwert.
   - `national_score` ist der ungewichtete Mittelwert aller Regionen (`peix_score_service.py:317-320`).
   - Ohne Populations- oder Abdeckungsgewichtung ist das für nationale Lageaussagen nur eingeschraenkt belastbar.

5. Konfidenz bleibt Agreement-basiert.
   - Wie im Legacy-RiskEngine basiert `confidence` auf der Streuung der Dimensionen, nicht auf Datenfrische, Coverage oder OOS-Qualitaet.

Urteil:

- `score_0_100`: `heuristisch konsistent aber nicht statistisch validiert`
- `impact_probability`: `nicht belastbar` als Probability
- `confidence`: `heuristisch konsistent aber nicht statistisch validiert`

### 5. Cockpit-/Media-Layer: gleiche Feldnamen, sehr unterschiedliche Mathematik

Im Cockpit werden mehrere heterogene Größen unter demselben Feld `impact_probability` zusammengefuehrt (`cockpit_service.py:413-520`).

Beispiele:

- Abwasser: `max_viruslast / 1_200_000 * 100`
- ARE: `inzidenz / 8000 * 100`
- Notaufnahme: `relative_cases / 20 * 100`
- SurvStat: `incidence / 150 * 100`
- BfArM: eigener Mischterm mit ARE-Kopplung
- Wetter, Pollen, Trends: bereits bestehende /100-artige Heuristiken

Das Problem ist nicht, dass diese Formeln existieren. Das Problem ist die gemeinsame Feldsemantik:

- Die Zahlen liegen alle auf `0..100`,
- heissen alle `impact_probability`,
- werden downstream gemeinsam sortiert, gefiltert und in Budget-/Priorisierungslogik verwendet.

Für die Peix-National- und Top-Region-Tiles existiert bereits `score_semantics = "ranking_signal"` (`cockpit_service.py:420-434`).
Für die Einzelquellen fehlt diese semantische Absicherung jedoch.

Urteil:

- Als Dashboard-Ranking: `heuristisch konsistent`
- Als Probability-Sprache: `nicht belastbar`

### 6. `opportunity_engine` und Detektoren: Priorisierung ja, Konfidenz nein

Positive Punkte:

- Viele Detektoren sind offen als Regeln implementiert. Das macht sie nachvollziehbar und reviewbar.
- `playbook_engine` trennt in der Prioritaetsfunktion explizit unabhaengige Signale von Peix (`playbook_engine.py:734-739`).
- In `ai_campaign_planner` wird `impact_probability` bereits korrekt als "Priorisierungsscore, keine empirische Eintrittswahrscheinlichkeit" beschrieben (`ai_campaign_planner.py:206`).

Hauptschwaechen:

1. `urgency_score` ist regelbasiert und nicht empirisch an Outcome/Lift kalibriert.
   - Beispiele: Wetterdetektor skaliert lineare Ratios (`weather_forecast.py:272-287`), Predictive Sales nutzt `velocity * 100 * 1.4 + 15`, Resource Scarcity addiert Bonusstufen.
   - Das ist für Priorisierung okay, aber nicht für robuste numerische Interpretation.

2. `confidence_pct` faellt auf `urgency_score` zurück.
   - Falls kein echtes `raw_confidence` vorliegt, wird `urgency_score` direkt als Konfidenz verwendet (`opportunity_engine.py:2264-2277`).
   - Damit ist "confidence" semantisch oft nur ein umbenanntes Prioritaetsmass.

3. `readiness` basiert auf Policy-Gates, nicht auf einer Wahrscheinlichkeit.
   - Das ist grundsaetzlich in Ordnung, sollte aber explizit als Decision Policy und nicht als Modellwahrscheinlichkeit kommuniziert werden.

Urteil:

- `urgency_score`: `heuristisch konsistent aber nicht statistisch validiert`
- `confidence_pct`: `nicht belastbar`
- `readiness` / `quality_gate`: `mathematisch konsistent` als Governance-Regel, nicht als Probability

## Was aktuell mathematisch valide ist

Ich würde die folgenden Teile heute als mathematisch valide im engeren Sinn einordnen:

- Walk-forward-/Vintage-Mechanik im `backtester`
- Leakageschutz und Warmup-Handling im `forecast_service`
- Baseline-Vergleich gegen Persistence und Seasonal-Naive
- Quantil-Monotonie-Fix in der Forecast-Inferenz
- bounded Composite-Score-Aufbau im `peix_score_service`

Ich würde die folgenden Teile explizit **nicht** als mathematisch valide oder empirisch kalibriert bezeichnen:

- `final_risk_score` der damaligen Legacy-Risk-Engine
- `impact_probability` in Peix und Cockpit, wenn damit Probability gemeint ist
- `forecast.confidence` als Modellkonfidenz
- `confidence_pct` in Opportunities
- die globale Business-Gewichtskalibrierung aus Feature-Importances

## Optimierungs-Blueprint

### P0

1. `[extern sichtbar]` `impact_probability` semantisch aufraeumen.
   - Wenn keine Kalibrierung vorliegt, Feld in `signal_score` oder `ranking_signal` umbenennen.
   - Falls API-Kompatibilitaet benötigt wird: neues Feld `score_semantics` überall einfuehren und im Frontend sichtbar auswerten.

2. `[internal only]` damalige Legacy-Risk-Engine entweder ausser Betrieb nehmen oder mathematisch entkoppeln.
   - Prophet-Gewicht in normierte Fusion überfuehren.
   - Baseline-Korrektur nur gegen dieselbe Zielgröße rechnen.
   - Bis dahin Score nicht als belastbaren Risk Score nach aussen verwenden.

3. `[backtest/model-metadata only]` Gewichtskalibrierung neu aufsetzen.
   - Keine Feature-Importances aus autoregressivem SURVSTAT-Modell mehr in `bio/market/psycho/context` ummappen.
   - Entweder:
     - direkte Optimierung der 4D-/6D-Score-Gewichte auf das spätere Zielformat, oder
     - stabile Handgewichte lassen und nur Forecast-Modelle automatisch promoten.

### P1

4. `[backtest/model-metadata only]` Promotion-Backtest und Live-Inferenz angleichen.
   - Im Candidate-Eval dieselbe Prophet-Komponente wie in Live nutzen oder Prophet in Live ebenfalls auf denselben Proxy reduzieren.
   - Zukunftsfeatures in der Horizon-Schleife rekursiv aktualisieren oder explizit horizon-unabhaengig halten.

5. `[extern sichtbar]` Forecast-`confidence` in ein ehrliches Feld umbauen.
   - `confidence` -> `interval_level_config` oder
   - echte empirische Coverage / Reliability aus Backtests berechnen und getrennt ausgeben.

6. `[extern sichtbar]` `outbreak_risk_score` und Peix-Probability kalibrieren.
   - Isotonic Regression oder Platt Scaling auf OOS-Daten.
   - Ohne Kalibrierung als Ranking-Score labeln.

### P2

7. `[internal only]` Regionale Aggregation verbessern.
   - Populations- oder Abdeckungsgewichtung für `national_score`.
   - Historisch stabile Normierungen statt reiner aktueller Max-Normierung dort, wo Zeitvergleich wichtig ist.

8. `[internal only]` Cockpit-Kacheln vereinheitlichen.
   - Pro Tile explizit `score_semantics`, `scale_basis`, `unit_family`.
   - Keine heterogenen /100-Heuristiken mehr unter demselben Probability-Namen.

9. `[internal only]` Rechenpfade vorkalkulieren.
   - Perzentil-Raenge, Normalisierungen und regionale Signalsummen voraggregieren.
   - Das verbessert Laufzeit und verhindert inkonsistente Ad-hoc-Replikation derselben Mathe in mehreren Services.

## Empfohlene nächste Validierungsrunde

Sobald eine befüllte Datenbank und `.env` verfügbar sind:

1. Walk-forward für jedes Virus und jede relevante Region ausführen.
2. Coverage der Quantile (`10%` / `90%`) empirisch messen.
3. `impact_probability` bzw. `outbreak_risk_score` gegen echte Events oder Aktionsschwellen kalibrieren.
4. `quality_gate` gegen tatsaechliche Business-Entscheidungen und Fehlalarmkosten prüfen.
5. Legacy-RiskEngine und Peix head-to-head gegen denselben Zielmassstab benchmarken.

## Abschlussurteil

FluxEngine ist **nicht insgesamt mathematisch ungültig**. Der Forecast-/Backtest-Unterbau ist ernsthaft und über weite Strecken sauber gebaut.

Aber:

- die **Wahrscheinlichkeits- und Konfidenzsprache** ist aktuell überzogen,
- die **Legacy-RiskEngine** ist mathematisch unsauber genug, dass ich sie nicht als belastbaren Risikoscore bezeichnen würde,
- und die **Kalibrierung der Business-Gewichte** ist derzeit eher eine plausible Heuristik als eine statistisch identifizierte Ableitung.

Die schnellste Wertsteigerung kam daher nicht aus einem kompletten Rebuild, sondern aus drei gezielten Korrekturen:

1. Probability-/Confidence-Semantik ehrlich machen,
2. die damalige Legacy-Risk-Engine aus dem kritischen Pfad nehmen oder hart korrigieren,
3. Gewichtskalibrierung von Forecast-Feature-Importances entkoppeln.
