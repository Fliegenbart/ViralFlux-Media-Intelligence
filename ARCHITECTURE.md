# ViralFlux Media Intelligence - Architektur

## Kurzfassung

ViralFlux ist ein System fuer **regionale Virus-Fruehwarnung** und daraus abgeleitete **operative Media-Entscheidungen**.

In einfachen Worten macht das System drei Dinge:
1. Es sammelt Gesundheits- und Kontextdaten aus mehreren Quellen.
2. Es berechnet daraus pro `Virus x Bundesland x Horizont` eine belastbare Prognose.
3. Es uebersetzt die Prognose in eine sichtbare Entscheidung wie `Activate`, `Prepare` oder `Watch`.

Die wichtigste Produktoberflaeche dafuer ist aktuell:
- [`/virus-radar`](https://fluxengine.labpulse.ai/virus-radar)

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
Virus-Radar / Regionen / Kampagnen
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

## 3. Oberflaechen-Schicht

Die Oberflaeche zeigt nicht einfach Rohdaten, sondern eine verdichtete Sicht:
- welches Virus ist gerade relevant
- wie sahen die letzten Wochen aus
- was wird fuer die naechsten 7 Tage erwartet
- welche Bundeslaender sollten zuerst geprueft werden
- was ist freigabereif und was noch nicht

Die wichtigste aktuelle Produktseite ist `Virus-Radar`.

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

## C. Hero-Graph auf `Virus-Radar`

Der Hero-Graph oben ist fuer Lesbarkeit normiert:

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

## Was man auf `/virus-radar` sieht

`Virus-Radar` ist die wichtigste Entscheidungsseite.

Sie beantwortet im Kern:
- welcher Virus ist gerade im Fokus
- wie sieht sein Verlauf aus
- welche Bundeslaender sind operativ zuerst relevant
- was ist schon freigabereif
- was bremst noch

## Hero oben

Der Hero zeigt immer **einen Virus auf einmal**.

Er besteht aus:
- kurzer Kernaussage
- Verlauf der letzten Wochen
- 7-Tage-Prognose
- Umschaltern fuer vier Viren

Bedeutung:
- **schwarz, durchgezogen** = letzte beobachtete Wochen
- **farbig, gestrichelt** = naechste 7 Tage Prognose
- **Heute = 100** = normierter Vergleichspunkt

Der Graph ist also **nicht imaginiert**, sondern:
- echte letzte Werte
- plus modellierte Prognose

## Signal Map

Darunter zeigt die Karte:
- welche Bundeslaender diese Woche am wichtigsten sind
- welche Region aktuell im Fokus ist
- wie die Leiter der Top-Regionen aussieht

## Activation Queue / Campaign Readiness

Diese Karten uebersetzen Signal in operative Reihenfolge:
- wer als naechstes geprueft wird
- was schon review- oder freigabereif ist

---

## Zentrale API-Pfade

Die Plattform hat viele Endpunkte. Fuer das aktuelle Produktbild sind diese besonders wichtig:

- `GET /api/v1/forecast/regional/predict`
  - regionale Forecasts je Virus und Horizont

- `GET /api/v1/forecast/regional/hero-overview`
  - schneller Hero-Pfad fuer `Virus-Radar`
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
- Prophet
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
- [docs/OPERATORS_GUIDE.md](docs/OPERATORS_GUIDE.md)
- [docs/forecast_probability_stack.md](docs/forecast_probability_stack.md)
- [docs/forecast_world_class_architecture.md](docs/forecast_world_class_architecture.md)
