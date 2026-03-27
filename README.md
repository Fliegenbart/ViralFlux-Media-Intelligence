# ViralFlux Media Intelligence

ViralFlux ist eine Operator-Plattform für regionale Virus-Frühwarnung und daraus abgeleitete Media-Entscheidungen.

In einfachen Worten:
- das System erkennt auf Bundesland-Level, wo sich Viruswellen wahrscheinlich zuerst aufbauen
- es trennt bewusst zwischen epidemiologischem Forecast und kommerzieller Freigabe
- es zeigt diese Information in einem operativen Cockpit für Entscheidungen, Review und Freigabe

Die Live-Instanz läuft aktuell unter:

- [https://fluxengine.labpulse.ai/](https://fluxengine.labpulse.ai/)

## Was das Produkt heute macht

ViralFlux ist keine reine Forecast-Demo und auch kein reines Marketing-Dashboard.
Es ist eine Arbeitsoberfläche für Operatoren.

Der aktuelle Produktkern besteht aus 3 Schichten:

1. Epidemiologischer Forecast
   Vorhersagen auf Bundesland-Level für relevante Viruslinien und definierte Zeitfenster.

2. Decision Layer
   Ableitung von priorisierten Regionen, Handlungsvorschlägen, Portfoliogewichtung und Review-Fällen.

3. Evidence- und Business-Gate
   Prüfung, ob aus einem Signal schon eine belastbare operative oder budgetwirksame Entscheidung werden darf.

Wichtige fachliche Leitplanken im Frontend:
- `Event-Wahrscheinlichkeit` ist nicht dasselbe wie `Ranking-Signal`
- `Entscheidungs-Priorität` ist nicht dasselbe wie Sicherheit
- `Unsicherheit` wird nie nur über Farbe gezeigt
- Aussagen gelten auf `Bundesland-Level`
- die UI soll ausdrücklich keinen `City-Forecast` vortäuschen

## Forecast-Hinweis zum Legacy/Simple-Pfad

Der einfache Forecast-Pfad wurde im Probability-Stack sauberer gemacht:

- Früher:
  Die `event_probability` wurde dort aus einer Heuristik nachgelagert über eine Sigmoid-Funktion aus Punktforecast, Intervall und Baseline angenähert.

- Jetzt:
  Die `event_probability` kommt aus einem gelernten `Exceedance-Modell`, das auf dem horizon-spezifischen `event_target` trainiert wird und nur issue-date-saubere Out-of-Fold-Vorhersagen für Backtest und Kalibrierung nutzt.

- Kalibrierung:
  Bevorzugt wird `isotonic`, bei kleineren Kalibrierungs-Samples `Platt/logistic`, sonst rohe Modellwahrscheinlichkeit als klar gekennzeichneter Fallback.

- Feld-Semantik:
  `confidence` ist nicht mehr als Fehler-Proxy gedacht.
  Zusätzlich gibt es additive Metadaten wie `reliability_score`, `backtest_quality_score`, `probability_source`, `calibration_mode`, `uncertainty_source` und `fallback_reason`.

- Was weiter bewusst getrennt bleibt:
  Epidemiologischer Forecast, Business-/Evidence-Gates, Ranking-Signal und Entscheidungs-Priorität bleiben getrennte Ebenen.

## Hauptbereiche im Frontend

Die App ist heute grob in diese Arbeitsflächen aufgeteilt:

- Landing / Welcome
  Produkt-Einstieg mit derselben Markenlogik wie die App, aber emotionaler als das Cockpit

- Jetzt / Operational Dashboard
  Die erste Operator-Entscheidungsoberfläche: Was passiert, wo muss gehandelt werden, wie sicher ist das Signal

- Regionen
  Vergleich von Bundesländern mit Karte und Listenansicht, bewusst ohne falsche lokale Präzision

- Kampagnen
  Vorschläge, Priorisierung, Detailansicht und Review-/Freigabe-Flow

- Evidenz
  Forecast, Truth, Unsicherheit, Quality Gates und Backtest-Einordnung

- Bericht
  Export- und Kommunikationsoberflächen

## Tech-Stack

### Frontend
- React 18
- TypeScript
- React Router
- Recharts
- Tailwind als Utility-Basis, aber mit semantischen Tokens und Klassen in `frontend/src/index.css`

### Backend
- FastAPI
- SQLAlchemy
- PostgreSQL / Timescale
- Celery + Redis
- Prophet, scikit-learn, statsmodels, xgboost

### Infrastruktur
- Docker Compose für lokale Entwicklung
- eigener Live-Deploy auf Hetzner
- `voxdrop-nginx` als Public Edge vor dem Produktiv-Stack

## Projektstruktur

```text
viralflux/
├── backend/                  # API, Business-Logik, Ingestion, ML, Readiness
├── frontend/                 # React-App, Cockpit, Landing, Tests
├── data/                     # lokale Datenablage für Entwicklung und Imports
├── docs/                     # Fach- und Betriebsdokumentation
├── docker/                   # Dockerfiles und nginx-Konfiguration
├── scripts/                  # Hilfs- und Deploy-Skripte
├── docker-compose.yml        # nur lokale Entwicklung
├── docker-compose.prod.yml   # produktionsnahes Compose-Manifest
├── DEPLOY.md                 # verbindliche Live-Deploy-Anleitung
└── QUICKSTART.md             # ergänzende Schnellstart-Hilfe
```

## Lokal starten

### Voraussetzungen

Du brauchst lokal:

- Docker und Docker Compose
- Node.js 18+
- Python 3.11+

Optional, je nach Anwendungsfall:
- OpenWeather API Key
- Zugriff auf einen OpenAI-kompatiblen LLM-Endpunkt

### 1. Repository klonen

```bash
git clone <REPO_URL>
cd viralflux
```

### 2. Umgebungsvariablen anlegen

Falls eine `.env.example` vorhanden ist, nutze sie als Startpunkt. Wichtig für die lokale Entwicklung sind vor allem:

```env
POSTGRES_USER=virusradar
POSTGRES_PASSWORD=changeme
POSTGRES_DB=virusradar_db

OPENWEATHER_API_KEY=
VLLM_BASE_URL=http://host.docker.internal:8001/v1

SECRET_KEY=replace-me
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-me

ENVIRONMENT=development
DB_AUTO_CREATE_SCHEMA=true
DB_ALLOW_RUNTIME_SCHEMA_UPDATES=true
STARTUP_STRICT_READINESS=false
READINESS_REQUIRE_BROKER=false
```

Wenn dein vLLM nicht im Host-Docker-Kontext läuft, setze stattdessen einen eigenen Endpunkt wie `http://127.0.0.1:8001/v1`. Wichtig ist nur: vLLM darf nicht denselben Port wie das FastAPI-Backend (`8000`) benutzen.

### 3. Lokale Infrastruktur starten

```bash
docker-compose up -d db redis backend
```

Wenn du das React-Frontend ebenfalls im Container nutzen willst:

```bash
docker-compose --profile dev up -d frontend
```

### 4. Frontend lokal im Entwicklungsmodus starten

Meist ist dieser Weg für die Frontend-Arbeit am angenehmsten:

```bash
cd frontend
npm install
npm start
```

Die React-App läuft dann auf:

- `http://localhost:3000`

Das Frontend nutzt lokal einen Proxy auf das Backend:
- `http://localhost:8000`

### 5. Backend lokal starten, wenn du ohne Container arbeiten willst

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API und Swagger Docs:

- `http://localhost:8000`
- `http://localhost:8000/docs`

## Tests und Qualitätschecks

### Frontend

```bash
cd frontend
npm test -- --runInBand
npm run build
```

### Backend

```bash
cd backend
python3 -m pytest
```

## Wichtige Betriebsregeln

Es gibt zwei sehr wichtige Unterschiede zwischen lokal und live:

1. `docker-compose.yml` ist nur für lokale Entwicklung gedacht
   Nicht für Live-Deploys verwenden.

2. Live-Deploys laufen über den clean Server-Checkout und das zentrale Deploy-Script
   Der aktuelle Standard ist in [DEPLOY.md](DEPLOY.md) dokumentiert.

## Live deployen

Der produktive Standard-Deploy ist:

```bash
ssh <deploy-user>@<deploy-host> '<deploy-script>'
```

Wichtig:
- der Server deployt immer den Stand von `origin/main`
- lokale Änderungen müssen also zuerst committet und gepusht werden
- das Live-System läuft nicht direkt aus deinem lokalen Arbeitsordner

Mehr Details stehen in:

- [DEPLOY.md](DEPLOY.md)

## Readiness und Health

Wichtige Endpunkte:

- `/health/live`
- `/health/ready`

Unterschied:
- `live` sagt: der Dienst lebt grundsätzlich
- `ready` sagt: der Dienst ist auch operativ ausreichend bereit

Ein `degraded` bei `/health/ready` bedeutet nicht automatisch Ausfall.
Oft heißt das eher:
- Forecast-Frische nicht im grünen Bereich
- Monitoring veraltet
- operative Blocker oder Watch-Zustände vorhanden

## Login

Das Frontend hat keinen festen öffentlichen Demo-Login eingebaut.

Die Login-Prüfung läuft über:

- `POST /api/auth/login`

Die gültigen Zugangsdaten kommen aus den gesetzten Umgebungsvariablen:

- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

## Datenquellen und Modellkontext

Je nach Pipeline und Betriebsmodus nutzt ViralFlux unter anderem:

- AMELAG
- GrippeWeb
- Notaufnahme-Surveillance
- SURVSTAT
- Wetter
- Ferien
- Google Trends
- Outcome- und Truth-Daten aus Partnerkontexten wie GELO

Die genaue fachliche und operative Dokumentation liegt in `docs/`.
Besonders nützlich sind:

- [docs/frontend_operational_dashboard.md](docs/frontend_operational_dashboard.md)
- [docs/metric_semantics_contract.md](docs/metric_semantics_contract.md)
- [docs/decision_engine_spec.md](docs/decision_engine_spec.md)
- [docs/ops_runbook.md](docs/ops_runbook.md)
- [docs/live_readiness_blockers_current.md](docs/live_readiness_blockers_current.md)

## Was zuletzt im Frontend modernisiert wurde

Der aktuelle Frontend-Stand ist nicht mehr nur ein klassisches Dashboard, sondern stärker als Operator-Oberfläche gebaut. Zuletzt wurden unter anderem verbessert:

- klarere Operator-Entscheidungsoberflächen im Cockpit
- ehrlichere Bundesland-Semantik in Karten und Regionenlisten
- sauberere Trennung von Forecast, Truth, Unsicherheit und Ranking-Signalen
- Dark-Mode-Architektur über semantische Tokens statt fragile Überschreibungen
- Accessibility für Tastatur, Fokusführung und Screenreader
- Responsive Verhalten für reale Laptop-Fenster
- konsistentere Sprache für Wahrscheinlichkeiten, Scores und Evidenzlücken

## Für neue Entwickler wichtig

Wenn du neu im Projekt bist, sind diese Punkte am wichtigsten:

1. Nicht von alten README-Annahmen ausgehen
   Der heutige Live-Deploy läuft über den Clean-Checkout auf dem Server.

2. Nicht `Event-Wahrscheinlichkeit`, `Ranking-Signal` und `Priorität` vermischen
   Diese Trennung ist fachlich wichtig und inzwischen auch bewusst im UI umgesetzt.

3. Bei Frontend-Änderungen immer Build und die betroffenen Tests laufen lassen
   Vor allem bei Cockpit-Komponenten.

4. Live nie direkt aus lokalen Sonderständen denken
   Erst committen, pushen, dann deployen.

## Nützliche Befehle

### Git-Status prüfen

```bash
git status --short --branch
```

### Frontend-Build testen

```bash
cd frontend
npm run build
```

### Einzelnen Frontend-Test ausführen

```bash
cd frontend
npm test -- --runInBand src/components/cockpit/OperationalDashboard.test.tsx
```

### Produktive Health-Checks prüfen

```bash
curl https://fluxengine.labpulse.ai/health/live
curl https://fluxengine.labpulse.ai/health/ready
```

## Kurzfazit

ViralFlux ist heute ein arbeitsorientiertes Frühwarn- und Decision-System für regionale Media-Entscheidungen.

Der wichtigste Gedanke des Produkts ist:
Nicht jede auffällige Zahl ist automatisch eine belastbare Freigabe.

Darum trennt das System bewusst zwischen:
- Forecast
- Ranking
- Priorität
- Unsicherheit
- Evidenz
- tatsächlicher operativer Freigabe
