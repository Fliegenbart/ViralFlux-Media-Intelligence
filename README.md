# ViralFlux Media Intelligence

ViralFlux ist eine Plattform für **regionale Virus-Frühwarnung** und daraus abgeleitete **operative Media-Entscheidungen**.
Dieses Repository zeigt den aktiven Produktkern, den Live-Hauptpfad der Oberfläche und die zugehörigen Betriebs- und Datenpfade.

Das Ziel ist einfach:
- früh erkennen, **wo** sich respiratorische Dynamiken aufbauen
- abschätzen, **wie** sich die Lage in den nächsten Tagen entwickelt
- daraus ableiten, **welche Bundesländer zuerst geprüft oder aktiviert werden sollten**

Live-Instanz: [https://fluxengine.labpulse.ai/cockpit](https://fluxengine.labpulse.ai/cockpit)
(password-gated, nur für eingeladene Pilot-Partner)

## Was die Plattform macht

ViralFlux verbindet öffentliche Gesundheitsdaten, Forecasting und eine operative Entscheidungslogik.

In einfachen Worten läuft das System so:
1. Es sammelt laufend Signale aus mehreren Quellen.
2. Es baut daraus für jedes Virus und jedes Bundesland einen sauberen Datenstand auf.
3. Es schätzt die Entwicklung für die nächsten Tage.
4. Es bewertet, wie relevant ein Bundesland gerade ist.
5. Es zeigt das Ergebnis in einer operativen Oberfläche für den aktuellen Partner- und Pilot-Scope.

### Produktoberfläche (Stand 2026-04-17)

Die Plattform hat seit April 2026 **eine einzige user-facing Surface**:

- `/cockpit` — vier Tabs, ein Datenstand, ein Scope
- alles andere (Login, `/virus-radar`, `/jetzt`, `/zeitgraph`, `/regionen`, `/kampagnen`, `/evidenz`, die alte MediaShell) ist retired und leitet client-seitig nach `/cockpit` um

Warum dieser Schnitt:
- die interne Tool-Oberfläche war für den GELO-Pilot zu groß und zu mehrdeutig
- das Cockpit ist die kuratierte Sicht, die pro Woche einen Vorschlag mit Unsicherheit liefert
- ein einfacher shared-password-Gate (HMAC-Cookie, 30 Tage) ersetzt den bisherigen OAuth-Login, damit die URL ohne Account geteilt werden kann

Die vier Tabs im Cockpit:
1. **Entscheidung** — die Empfehlung der Woche (Shift-Vorschlag, Konfidenz, Landkarten-Splitansicht)
2. **Wellen-Atlas** — 16 Bundesländer als 3D-Datenskulptur, Höhe = erwarteter Anstieg
3. **Forecast-Zeitreise** — Fan-Chart Q10/Q50/Q90 mit Kalibrierungs- und Lag-Ehrlichkeits-Panel
4. **Wirkung & Feedback-Loop** — Live-Ranking, Truth-History, Pipeline-Status für Outcome-Daten

Technische Kernpfade sind vor allem:
- `frontend/src/pages/cockpit/` (die vier Tabs + Shell + Gate)
- `frontend/src/components/cockpit/peix/` (Gallery-Hero, DataSculpture, ConfidenceCloud, Roster, …)
- `frontend/src/styles/peix*.css` (Design-System: peix.css Basis, peix-gallery.css Atlas-derived)
- `backend/app/api/media_routes_cockpit_snapshot.py` (Snapshot-API + Gate-Endpoints)
- `backend/app/services/media/cockpit/` (Snapshot-Builder, Freshness, Impact)
- `backend/app/services/ml/` (Forecast + Kalibrierung)
- `backend/app/services/data_ingest/` (Quellen-Import)

## Was man im `/cockpit` sieht

Das Cockpit beantwortet pro Woche drei Fragen:
- **Welchen Shift empfehlen wir und mit welcher Sicherheit?**
- **Wo läuft die Welle hoch, wo klingt sie ab?**
- **Wie weit voraus sind wir gegenüber dem Meldewesen — und wie kalibriert ist der Fan?**

Die Darstellung hält sich bewusst an eine Regel: **wo der Forecast kein belastbares Signal hat, steht ein "—", nicht eine erfundene Zahl**. EUR-Beträge erscheinen nur, wenn ein Media-Plan verbunden ist. Prozentwerte tragen sichtbar entweder das Label *kalibriert* oder *heuristisch*, damit ein Score nie als Wahrscheinlichkeit missverstanden wird.

## Datenquellen

Je nach Signalpfad fließen unter anderem diese Quellen ein:
- AMELAG / Abwasser
- GrippeWeb
- Notaufnahme-Surveillance
- SURVSTAT
- Google Trends
- Wetter
- Ferien / Kalendereffekte
- BfArM-Kontext für Marketing-/Supply-Signale

Nicht jede Quelle ist für jeden Modellschritt gleich wichtig. Die Plattform trennt deshalb bewusst:
- epidemiologische Signale
- Datenqualität und Frische
- Business-/Freigabe-Logik

## Mathematisches Vorgehen

### 1. Point-in-time Feature-Bau

Für jedes `Virus × Bundesland × Forecast-Horizont` werden Features gebaut, die **nur das enthalten, was zum Vorhersagezeitpunkt wirklich sichtbar war**.

Das ist wichtig, damit kein unzulässiger Blick in die Zukunft passiert.

Typische Feature-Klassen:
- aktuelle Niveauwerte
- Trends und Veränderungen
- Lags und gleitende Fenster
- Quellabdeckung und Frische
- Wetter- und Kalendereffekte

### 2. Punktprognose

Das System schätzt einen zukünftigen Zielwert, zum Beispiel die erwartete Inzidenz in 7 Tagen.

Vereinfacht:

```text
y_hat(t+7) = Modell(x_t)
```

Dabei ist:
- `x_t` = der saubere Feature-Satz zum Zeitpunkt `t`
- `y_hat(t+7)` = der erwartete Zielwert in 7 Tagen

Zusätzlich werden Unsicherheitsintervalle berechnet.

### 3. Ereignissignal oder Ereigniswahrscheinlichkeit

Die Plattform trennt **Punktprognose** und **Entscheidungssignal** bewusst voneinander.

Es gibt dabei zwei Pfade:
- **Regional / kalibriert**: Wenn ein gelerntes Exceedance-Modell mit Kalibrierung verfuegbar ist, wird eine echte `event_probability` ausgegeben.
- **Einfach / nationaler Fallback**: Wenn kein belastbares Wahrscheinlichkeitsmodell verfuegbar ist, wird **keine** echte Wahrscheinlichkeit behauptet. Stattdessen gibt die Plattform einen heuristischen `event_signal_score` aus.

Nur der erste Pfad darf als Wahrscheinlichkeit gelesen werden:

```text
P(Ereignis in 7 Tagen | x_t)
```

Diese Wahrscheinlichkeit wird kalibriert, damit sie besser zu realen Haefigkeiten passt.

Vereinfacht:
- bevorzugt `isotonic`
- bei kleinerem Sample `logistic / Platt`
- sonst klar markierter Fallback auf Signal- statt Wahrscheinlichkeitssemantik

### 4. Normierung für die Darstellung

Wo das Cockpit einen Verlauf zeigt (Fan-Chart, Wellen-Atlas-Höhe, Ranking-Deltas), wird intern ein normierter Index verwendet:

```text
index = 100 * Wert / letzter_beobachteter_Wert
```

Das bedeutet:
- `100` = heute / letzter real beobachteter Punkt
- `110` = ungefähr 10 % höher als heute
- `90` = ungefähr 10 % niedriger als heute

So lässt sich die Richtung schnell lesen, ohne von absoluten Größenordnungen erschlagen zu werden.

### 5. 7-Tage-Veränderung

Die sichtbare Veränderung auf dem Wellen-Atlas wird vereinfacht als Verhältnis zwischen Prognose und aktuellem Wert gelesen:

```text
delta_7d = (forecast_7d - current_value) / current_value
```

Das ist die Zahl, die dann als `+x %` oder `-x %` im Roster und als Turmhöhe in der 3D-Skulptur kommuniziert wird.

### 6. Regionale Priorisierung

Die Plattform entscheidet nicht allein über einen Trend-Prozentwert.

Stattdessen fließen mehrere Ebenen zusammen:
- Wahrscheinlichkeit
- Trendrichtung
- Datenfrische
- Quellabdeckung
- Cross-Source Agreement
- Unsicherheit / Reliability
- Business-/Freigabe-Regeln

Erst daraus entstehen Stufen wie:
- `Activate`
- `Prepare`
- `Watch`

## Wie belastbar ist das?

Die Prognosen sind **nicht imaginiert**, aber sie sind natürlich auch **keine Fakten aus der Zukunft**.

Wichtig ist deshalb die Trennung:
- **Vergangenheit**: echte beobachtete Werte
- **Forecast**: modellierte Erwartung
- **Probability Stack**: getrennte Wahrscheinlichkeits- und Reliability-Ebene
- **Decision Layer**: eigene operative Freigabe-/Priorisierungslogik

Das System ist also so gebaut, dass:
- Vergangenheit und Prognose sichtbar getrennt bleiben
- kein stiller Future-Leakage-Pfad benutzt wird
- epidemiologischer Forecast und Business-Entscheidung nicht verwechselt werden

## Repo-Hygiene

Dieses GitHub-Repo soll **Code, Dokumentation und stabile Referenzartefakte** enthalten, aber **keine alten generierten Laufzeit-Ausgaben**.

Deshalb werden diese Dinge bewusst nicht versioniert:
- `output/`
- `data/raw/`
- `data/processed/`
- `demo-data/`
- `Test-Daten/`
- lokale Hilfs-/Experimentdateien

Wenn Benchmarks, Screenshots oder Reports lokal erzeugt werden, bleiben sie lokal und gehören nicht dauerhaft ins Repo.

## Tech-Stack

- Frontend: React, TypeScript, Recharts
- Backend: FastAPI, Pandas, scikit-learn, Prophet
- Datenbank: PostgreSQL / TimescaleDB
- Scheduling: Celery Beat + Celery Worker
- Deployment: Docker Compose

## Einstieg

- [QUICKSTART.md](QUICKSTART.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/OPERATORS_GUIDE.md](docs/OPERATORS_GUIDE.md)
- [DEPLOY.md](DEPLOY.md)
