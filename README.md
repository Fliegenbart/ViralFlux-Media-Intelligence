# ViralFlux Media Intelligence

ViralFlux ist eine Plattform für **regionale Virus-Frühwarnung** und daraus abgeleitete **operative Media-Entscheidungen**.

Das Ziel ist einfach:
- früh erkennen, **wo** sich respiratorische Dynamiken aufbauen
- abschätzen, **wie** sich die Lage in den nächsten Tagen entwickelt
- daraus ableiten, **welche Bundesländer zuerst geprüft oder aktiviert werden sollten**

Live-Instanz: [https://fluxengine.labpulse.ai/virus-radar](https://fluxengine.labpulse.ai/virus-radar)

## Was die Plattform macht

ViralFlux verbindet öffentliche Gesundheitsdaten, Forecasting und eine operative Entscheidungslogik.

In einfachen Worten läuft das System so:
1. Es sammelt laufend Signale aus mehreren Quellen.
2. Es baut daraus für jedes Virus und jedes Bundesland einen sauberen Datenstand auf.
3. Es schätzt die Entwicklung für die nächsten Tage.
4. Es bewertet, wie relevant ein Bundesland gerade ist.
5. Es zeigt das Ergebnis in einer operativen Oberfläche für PEIX / GELO.

## Was man auf `/virus-radar` sieht

Die Seite [Virus-Radar](https://fluxengine.labpulse.ai/virus-radar) ist die zentrale Entscheidungsseite.

Sie beantwortet vor allem drei Fragen:
- **Welcher Virus ist gerade relevant?**
- **Wie sahen die letzten Wochen aus und wie geht es voraussichtlich weiter?**
- **Welche Bundesländer sollten diese Woche zuerst geprüft werden?**

Der Hero-Graph oben zeigt immer **einen Virus auf einmal**:
- **schwarze durchgezogene Linie** = die letzten beobachteten Wochenwerte
- **farbige gestrichelte Linie** = die erwartete Entwicklung in den nächsten 7 Tagen
- **Heute = 100** = die Darstellung ist auf den letzten beobachteten Punkt normiert, damit man die Richtung klar lesen kann

Wichtig:
- diese Normierung ist **nur für die Darstellung**
- die eigentlichen Modelle rechnen intern weiter auf den echten Werten

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

### 3. Ereigniswahrscheinlichkeit

Die Plattform trennt **Punktprognose** und **Wahrscheinlichkeit eines relevanten Ereignisses** bewusst voneinander.

Die Event-Wahrscheinlichkeit wird nicht einfach aus dem Punktforecast geraten, sondern über ein eigenes Exceedance-/Probability-Modell geschätzt:

```text
P(Ereignis in 7 Tagen | x_t)
```

Diese Wahrscheinlichkeit wird kalibriert, damit sie besser zu realen Häufigkeiten passt.

Vereinfacht:
- bevorzugt `isotonic`
- bei kleinerem Sample `logistic / Platt`
- sonst klar markierter Fallback

### 4. Hero-Graph auf `Virus-Radar`

Der Hero-Graph oben benutzt für die Darstellung einen normierten Index:

```text
hero_index = 100 * Wert / letzter_beobachteter_Wert
```

Das bedeutet:
- `100` = heute / letzter real beobachteter Punkt
- `110` = ungefähr 10 % höher als heute
- `90` = ungefähr 10 % niedriger als heute

So kann man die Richtung schnell lesen, ohne von absoluten Größenordnungen erschlagen zu werden.

### 5. 7-Tage-Veränderung

Die sichtbare Veränderung im Hero wird vereinfacht als Verhältnis zwischen Prognose und aktuellem Wert gelesen:

```text
delta_7d = (forecast_7d - current_value) / current_value
```

Das ist die Zahl, die dann als `+x %` oder `-x %` kommuniziert wird.

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
