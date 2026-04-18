# ViralFlux Media Intelligence - Architektur

## Kurzfassung

ViralFlux ist ein System fuer **regionale Virus-Fruehwarnung** und daraus abgeleitete **operative Media-Entscheidungen**.

In einfachen Worten macht das System drei Dinge:
1. Es sammelt Gesundheits- und Kontextdaten aus mehreren Quellen.
2. Es berechnet daraus pro `Virus x Bundesland x Horizont` eine belastbare Prognose.
3. Es uebersetzt die Prognose in eine sichtbare Entscheidung wie `Activate`, `Prepare` oder `Watch`.

Die wichtigste Produktoberflaeche dafuer ist aktuell:
- [`/cockpit`](https://fluxengine.labpulse.ai/cockpit) (password-gated, single user-facing surface seit 2026-04-17)

Historie:
- Bis April 2026 war `/virus-radar` die Hauptseite, begleitet von `/jetzt`, `/regionen`, `/kampagnen`, `/evidenz` und der MediaShell. Diese Routes wurden im Zuge des GELO-Pilots konsolidiert und leiten client-seitig nach `/cockpit` um. Der Code liegt teilweise noch im Repo, wird aber nicht mehr gerendert.

---

## Systembild

```text
Externe Quellen
    ↓
Data Ingestion
    ↓
Zeitreihen + Feature-Bau
    ↓
Forecast + Event-Wahrscheinlichkeit
    ↓
Regionale Priorisierung + Freigabe-Logik
    ↓
API + Snapshots
    ↓
/cockpit (4 Tabs)
```

Anders gesagt:
- **Quellen** liefern Rohsignale
- **Feature-Bau** formt daraus saubere Modell-Eingaben
- **Forecast** schaetzt den kuenftigen Verlauf
- **Probability / Decision Layer** entscheidet, wie relevant ein Signal operativ ist
- **Frontend** zeigt das Ergebnis so, dass ein Mensch es schnell lesen und nutzen kann

---

## Die drei Schichten

## 1. Daten-Schicht

Die Daten-Schicht sammelt die laufenden Signale.

Wichtige Quellen:
- AMELAG / Abwasser
- GrippeWeb
- Notaufnahme-Surveillance
- SURVSTAT
- Google Trends
- Wetter
- Ferien / Kalendereffekte
- BfArM-Kontext fuer Marketing- und Supply-Signale

Die Rohdaten landen in PostgreSQL / TimescaleDB.

Wichtig:
- Zeitreihen bleiben moeglichst nah an der Quelle gespeichert
- Import, Frische und Fehler werden protokolliert
- lokale Test- und Report-Artefakte gehoeren **nicht** dauerhaft ins Repo

## 2. Modell- und Entscheidungs-Schicht

Hier passiert die eigentliche Fachlogik.

Sie besteht aus mehreren getrennten Ebenen:

1. **Point-in-time Feature-Bau**
2. **Punktprognose**
3. **Ereigniswahrscheinlichkeit**
4. **Unsicherheit / Reliability**
5. **Regionale Priorisierung**

Diese Trennung ist wichtig, weil ein Forecast allein noch keine gute Business-Entscheidung ist.

### Modellstack (Code-Wahrheit)

Das produktive Forecast-Pipeline liegt in `backend/app/services/ml/` und ist **XGBoost-zentriert**:

- **Punktprognose (Regression)**: XGBRegressor, orchestriert in [`forecast_service_inference.py`](backend/app/services/ml/forecast_service_inference.py) und [`forecast_service_pipeline.py`](backend/app/services/ml/forecast_service_pipeline.py). Training in [`forecast_service_direct_training.py`](backend/app/services/ml/forecast_service_direct_training.py).
- **Event-Wahrscheinlichkeit (Classification)**: XGBClassifier in [`forecast_service_event_probability.py`](backend/app/services/ml/forecast_service_event_probability.py), Exceedance-Ziele in [`backtester_targets.py`](backend/app/services/ml/backtester_targets.py).
- **Kalibrierung**: Isotonic (preferred) oder Platt/Logistic im gleichen Event-Probability-Modul; fuer kleine Samples bleibt der Output explizit als heuristischer Score markiert.
- **Regionale Pipelines**: [`regional_forecast.py`](backend/app/services/ml/regional_forecast.py), [`regional_trainer*.py`](backend/app/services/ml/) fuer Virus × Bundesland × Horizont, inkl. Artifact-Persistenz und Hierarchie-Training.
- **Backtesting**: Walk-Forward in [`backtester_walk_forward.py`](backend/app/services/ml/backtester_walk_forward.py) mit Hold-out-Reporting in [`backtester_reporting.py`](backend/app/services/ml/backtester_reporting.py).
- **Prophet**: nur als optionaler Fallback-Estimator in [`forecast_service_estimators.py`](backend/app/services/ml/forecast_service_estimators.py) / `fusion_engine/prophet_predictor.py`. Nicht auf dem Haupt-Pfad des Cockpits.

## 3. Oberflaechen-Schicht

Die Oberflaeche zeigt nicht einfach Rohdaten, sondern eine verdichtete Sicht:
- welches Virus ist gerade relevant
- wie sahen die letzten Wochen aus
- was wird fuer die naechsten 7 Tage erwartet
- welche Bundeslaender sollten zuerst geprueft werden
- was ist freigabereif und was noch nicht

Die einzige user-facing Produktseite ist `/cockpit` mit vier Tabs (Entscheidung, Wellen-Atlas, Forecast-Zeitreise, Wirkung). Legacy-Routes wie `/virus-radar`, `/jetzt`, `/regionen`, `/kampagnen`, `/evidenz` leiten client-seitig nach `/cockpit` um.

---

## Datenfluss im Alltag

## 1. Ingestion

Mehrere Jobs holen regelmaessig neue Daten.

Typischer Ablauf:
- TSV / CSV / API abrufen
- Daten parsen
- Plausibilitaet pruefen
- in die Datenbank schreiben
- Fehler / Erfolg loggen

Der Betrieb ist bewusst scheduler-basiert.

Aktuell laeuft der Tagesrhythmus grob so:
- `06:00` Ingestion
- `07:00` Training / Refresh
- `07:30` Live-Forecasts
- `08:00` Regionale operative Snapshots
- `08:10` Marketing Opportunities

## 2. Feature-Bau

Aus den Rohdaten wird fuer jeden Vorhersagepunkt ein sauberer Feature-Satz gebaut.

Ganz wichtig:

```text
Ein Modell darf nur sehen, was zum Vorhersagezeitpunkt wirklich bekannt war.
```

Das nennt man hier **point-in-time sauber**.

Typische Features:
- aktuelle Niveauwerte
- Trend und Beschleunigung
- Lags
- gleitende Fenster
- Quellabdeckung
- Datenfrische
- Wetter- und Kalender-Effekte

## 3. Forecast

Danach wird ein Zukunftswert geschaetzt, zum Beispiel fuer 7 Tage.

Vereinfacht:

```text
y_hat(t+7) = Modell(x_t)
```

Dabei ist:
- `x_t` = alle zum Zeitpunkt `t` sichtbaren Features
- `y_hat(t+7)` = erwarteter Zielwert in 7 Tagen

Zusatzlich gibt es Unsicherheitsintervalle.

## 4. Event-Wahrscheinlichkeit

Die Plattform trennt Punktwert und Ereigniswahrscheinlichkeit bewusst voneinander.

Nicht die Logik ist:
- "Punktforecast hoch, also wird es schon wichtig sein"

Sondern:

```text
P(Ereignis in 7 Tagen | x_t)
```

Diese Wahrscheinlichkeit kommt aus einem eigenen Probability-/Exceedance-Pfad und wird kalibriert.

Kalibrierung:
- bevorzugt `isotonic`
- bei kleineren Samples `logistic / Platt`
- sonst klar markierter Fallback

## 5. Regionale Entscheidung

Die Plattform priorisiert nicht einfach nach "groesster Prozent-Anstieg".

Stattdessen fliessen mehrere Ebenen zusammen:
- Event-Wahrscheinlichkeit
- Trend
- Datenfrische
- Quellabdeckung
- Cross-Source Agreement
- Unsicherheit / Reliability
- Business- und Freigabe-Regeln

Erst daraus entstehen Stufen wie:
- `Activate`
- `Prepare`
- `Watch`

---

## Mathematisches Vorgehen

## A. Punktprognose

Das Modell berechnet einen kuenftigen Zielwert.

Vereinfacht:

```text
y_hat = f(x)
```

Das ist die Basis fuer:
- erwartete Inzidenz
- erwartete Last
- erwartete Bewegung in den naechsten Tagen

## B. 7-Tage-Veränderung

Die sichtbare Richtungszahl im Produkt liest sich vereinfacht so:

```text
delta_7d = (forecast_7d - current_value) / current_value
```

Das ist die Zahl, die spaeter als `+x %` oder `-x %` erscheint.

## C. Fan-Chart im `/cockpit`

Der Fan-Chart (Tab 03 Forecast-Zeitreise) ist fuer Lesbarkeit normiert:

```text
hero_index = 100 * Wert / letzter_beobachteter_Wert
```

Das bedeutet:
- `100` = heute / letzter real beobachteter Punkt
- `110` = ungefaehr 10 % ueber heute
- `90` = ungefaehr 10 % unter heute

Wichtig:
- das ist **nur die Darstellungslogik**
- intern rechnen die Modelle weiterhin mit echten Werten

## D. Warum das wichtig ist

Ohne diese Normierung wuerde oft ein Virus die Achse dominieren und die anderen waeren schlecht lesbar.

Mit der Normierung wird sichtbar:
- wie der Verlauf zuletzt aussah
- wie sich das Modell ab heute bewegt
- ob die Richtung eher steigt, faellt oder stabil bleibt

---

## Was man im `/cockpit` sieht

Das Cockpit ist die einzige user-facing Produktseite. Es besteht aus vier Tabs mit einem gemeinsamen Masthead und einem Virus-Scope-Toggle (Influenza A regional / RSV A national).

## Tab 01 — Entscheidung

Die Empfehlung der Woche als editorial Lede. Ein warm-schwarzer Gallery-Hero nennt den konkreten Shift ("verschiebe EUR X aus Region A nach Region B") mit Konfidenz oder Signalstaerke. Darunter zwei paper-Landkarten mit den steigenden und abklingenden Bundeslaendern sowie eine Roster-Liste mit weiteren Shift-Kandidaten.

## Tab 02 — Wellen-Atlas

Die Signatur-Flaeche. 16 Bundeslaender als extrudierte three.js-Bloecke auf einer Keramikpalette; Turmhoehe = erwarteter Anstieg ueber den Horizont. Links im dunklen Hero die editorial Lede und eine Top-Riser-Liste, rechts der 3D-Canvas auf einem Sockel.

## Tab 03 — Forecast-Zeitreise

Fan-Chart mit Q10 bis Q90-Band, SURVSTAT-Meldung und Notaufnahme-Spur. Ein TimeScrubber macht jeden Tag anwaehlbar; die grossen Zahlen im Hero aktualisieren sich live. Zwei miniatur-Ehrlichkeits-Panel darunter zeigen Abdeckung 80/95 Prozent und den aktuellen Lag gegen die Notaufnahme-Aktivitaet.

## Tab 04 — Wirkung und Feedback-Loop

Was wir gerade empfehlen, was in den letzten Wochen real passierte, und wo die Outcome-Daten andocken werden. Solange keine Verkaufsdaten fliessen, bleiben die entsprechenden Felder ehrlich leer statt auf Platzhalter-Zahlen zurueckzufallen.

## Gemeinsame Regeln fuer alle Tabs

- wo der Forecast kein belastbares Signal hat, steht `—` statt einer erfundenen Zahl
- EUR-Werte erscheinen nur mit verbundenem Media-Plan
- Event-Scores tragen entweder das Label `kalibriert` (echte Wahrscheinlichkeit) oder `heuristisch` (Ranking-Score 0..1) -- nie beides zugleich
- eine einzige Akzentfarbe (Terracotta) kennzeichnet Aktion, Empfehlung und Anstieg; alles andere bleibt in Cream, Hairlines und Mute-Grey

---

## Zentrale API-Pfade

Die Plattform hat viele Endpunkte. Fuer das aktuelle Produktbild sind diese besonders wichtig:

- `GET /api/v1/media/cockpit/snapshot?virus_typ=...`
  - der Haupt-Endpoint der Live-Surface
  - liefert die gesamte Payload des `/cockpit`: Hero, Regions, Timeline, ModelStatus, Sources
  - geschuetzt ueber Session-Cookie ODER `X-API-Key` (M2M) ODER `cockpit_unlock`-Cookie (shared password gate, 30 Tage HMAC-signiert)

- `POST /api/v1/media/cockpit/unlock`
  - validiert das shared password aus `COCKPIT_ACCESS_PASSWORD` und setzt das gate-Cookie

- `GET /api/v1/media/cockpit/impact`
  - Tab 04: Live-Ranking, Truth-History, Outcome-Pipeline-Status

- `GET /api/v1/forecast/regional/predict`
  - regionale Forecasts je Virus und Horizont (intern vom snapshot-builder genutzt)

- `GET /api/v1/forecast/regional/hero-overview`
  - schneller Snapshot-Pfad (historisch fuer `/virus-radar`, heute nur noch intern vom Cockpit-Snapshot-Builder genutzt)
  - liest vorbereitete Snapshots / Wochenhistorie statt jedes Mal den schweren Portfolio-Pfad neu zu rechnen

- `GET /api/v1/forecast/regional/media-allocation`
  - Budget-/Stage-Sicht auf Regionen

- `GET /api/v1/forecast/regional/campaign-recommendations`
  - verdichtete Kampagnen-Vorschlaege

- `POST /api/v1/marketing/export/crm`
  - mutierender Export, bewusst als `POST`

---

## Datenhaltung

## Wichtige Gruppen

### Zeitreihen
- Abwasser
- Trends
- Wetter
- GrippeWeb
- Notaufnahme
- SURVSTAT

### Modell-Ausgaben
- Forecasts
- Unsicherheitsintervalle
- Kalibrierungs- und Quality-Metadaten

### Operative Ebenen
- Snapshots fuer schnelle Produktpfade
- Entscheidungs-Spuren
- Audit-Logs
- Kampagnen- und Opportunity-Zustaende

## Warum Snapshots wichtig sind

Fuer die Produktoberflaeche ist nicht jeder Live-Weg sinnvoll.

Einige Screens brauchen:
- schnell
- stabil
- reproduzierbar

Deshalb werden operative Snapshots geschrieben, damit das Frontend nicht jedes Mal schwere Rechenpfade live neu ausloest.

---

## Security und Produktschutz

## Auth

- Browser laufen ueber Session-Cookies
- interne Legacy-Routen sind JWT-geschuetzt
- schreibende Admin-Aktionen brauchen Admin-Rolle

## Session-Verhalten

- `/api/auth/login` setzt eine Browser-Session
- `/api/auth/session` liefert fuer anonyme Browser ruhig `authenticated: false`
- `/api/auth/logout` widerruft neue Sessions serverseitig

## Oeffentliche vs. interne Daten

Das System trennt bewusst:
- oeffentliche / landing-geeignete Kurzfassungen
- interne Detailansichten

Beispiel:
- `/api/v1/outbreak-score/peix-score` gibt nur die sichere Kurzfassung
- `/api/v1/outbreak-score/peix-score/full` braucht Auth

---

## Betriebslogik

## Health

- `/health/live`
  - lebt der Prozess?

- `/health/ready`
  - ist das System operativ ausreichend frisch und gesund?

Wichtig:
- `live = healthy` bedeutet nur, dass die App laeuft
- `ready = healthy` bedeutet, dass auch Daten, Snapshots und operative Voraussetzungen passen

## Warum `ready` degradiert sein kann

Typische Gruende:
- externe Quelle alt
- Snapshot-Refresh fehlt
- Forecast-Monitoring kritisch
- regionale operative Sicht zu alt

Das ist bewusst strenger als nur "Server lebt".

---

## Repo-Hygiene

Das GitHub-Repo soll enthalten:
- Code
- Dokumentation
- stabile Referenzdateien

Das GitHub-Repo soll **nicht** enthalten:
- alte generierte Reports
- lokale Screenshots
- lokale Benchmark-Artefakte
- lokale Hilfsdaten

Deshalb sind unter anderem ignoriert:
- `output/`
- `data/raw/`
- `data/processed/`
- `demo-data/`
- `Test-Daten/`

---

## Tech-Stack

### Frontend
- React
- TypeScript
- Recharts
- React Router

### Backend
- FastAPI
- Pandas / NumPy
- scikit-learn
- **XGBoost** (primary point-forecast und event-probability model)
- Prophet (optional fallback estimator)
- Celery

### Infrastruktur
- PostgreSQL / TimescaleDB
- Docker Compose
- Nginx

---

## Die wichtigste Architektur-Idee

Die wichtigste Architektur-Idee ist nicht ein bestimmtes Framework, sondern diese Trennung:

1. **Daten sammeln**
2. **point-in-time sauber Features bauen**
3. **Forecast und Wahrscheinlichkeit getrennt rechnen**
4. **Business-/Freigabe-Logik getrennt anwenden**
5. **das Ergebnis fuer Menschen klar darstellen**

So wird vermieden, dass:
- Rohsignal und Business-Entscheidung vermischt werden
- Prognose und Fakt verwechselt werden
- die Oberflaeche schwere Rechenpfade dauernd live neu ausloest

---

## Weiterfuehrende Dokumente

- [README.md](README.md)
- [QUICKSTART.md](QUICKSTART.md)
- [DEPLOY.md](DEPLOY.md)
- [docs/README.md](docs/README.md) (Index der aktiven Dokumentation)
- [docs/forecast_probability_stack.md](docs/forecast_probability_stack.md)
- [docs/forecast_h7_science_contract.md](docs/forecast_h7_science_contract.md)
- [docs/model_release_process.md](docs/model_release_process.md)
