# Quickstart

Diese Datei ist die kurze, praktische Startanleitung.

Wenn du mehr Kontext willst, lies zusätzlich:
- [README.md](/Users/davidwegener/Desktop/viralflux/README.md)
- [DEPLOY.md](/Users/davidwegener/Desktop/viralflux/DEPLOY.md)

## Wofür dieser Quickstart gedacht ist

Dieser Quickstart ist für:
- lokale Entwicklung
- schnelles Starten des Frontends
- schnelles Starten des Backends
- einfache Health- und Test-Checks

Nicht dafür:
- Production direkt mit `docker-compose.yml` deployen
- den Live-Server manuell „irgendwie“ hochziehen

Für Live gilt immer:
- erst committen
- dann auf `main` pushen
- dann den Server-Deploy nutzen

## Voraussetzungen

Du brauchst lokal:

- Docker und Docker Compose
- Node.js 18+
- Python 3.11+

Optional:
- `OPENWEATHER_API_KEY`
- einen OpenAI-kompatiblen LLM-Endpunkt über `VLLM_BASE_URL`

## 1. Repository klonen

```bash
git clone <REPO_URL>
cd viralflux
```

## 2. `.env` anlegen

Falls vorhanden, nutze `.env.example` als Basis.

Wichtige Werte für den lokalen Start:

```env
POSTGRES_USER=virusradar
POSTGRES_PASSWORD=changeme
POSTGRES_DB=virusradar_db

OPENWEATHER_API_KEY=
VLLM_BASE_URL=http://host.docker.internal:8000/v1

SECRET_KEY=replace-me
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-me

ENVIRONMENT=development
DB_AUTO_CREATE_SCHEMA=true
DB_ALLOW_RUNTIME_SCHEMA_UPDATES=true
STARTUP_STRICT_READINESS=false
READINESS_REQUIRE_BROKER=false
```

## 3. Datenbank, Redis und Backend starten

Der schnellste Weg für lokal ist:

```bash
docker-compose up -d db redis backend
```

Danach solltest du diese Endpunkte erreichen:

- [http://localhost:8000/health/live](http://localhost:8000/health/live)
- [http://localhost:8000/docs](http://localhost:8000/docs)

## 4. Frontend starten

Für Frontend-Arbeit ist dieser Weg meistens am angenehmsten:

```bash
cd frontend
npm install
npm start
```

Dann läuft die App hier:

- [http://localhost:3000](http://localhost:3000)

Wichtig:
Das Frontend nutzt lokal einen Proxy auf das Backend unter `http://localhost:8000`.

## 5. Optional: Frontend im Container starten

Wenn du lieber auch das Frontend über Docker starten willst:

```bash
docker-compose --profile dev up -d frontend
```

## 6. Optional: Backend ohne Docker starten

Wenn du am Python-Code arbeiten willst, ist das oft praktischer:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Die 3 wichtigsten lokalen URLs

- Frontend: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000](http://localhost:8000)
- Swagger Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Login lokal

Es gibt keinen festen Demo-Login im Frontend.

Lokal funktionieren die Zugangsdaten aus deiner `.env`:

- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

## Nützliche Standardbefehle

### Alle laufenden Container sehen

```bash
docker ps
```

### Logs vom Backend sehen

```bash
docker-compose logs -f backend
```

### Logs von Redis sehen

```bash
docker-compose logs -f redis
```

### Datenbank neu starten

```bash
docker-compose restart db
```

### Frontend testen

```bash
cd frontend
npm test -- --runInBand
```

### Frontend-Build prüfen

```bash
cd frontend
npm run build
```

### Backend-Tests laufen lassen

```bash
cd backend
python3 -m pytest
```

## Health-Checks

### Lokal

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

### Live

```bash
curl https://fluxengine.labpulse.ai/health/live
curl https://fluxengine.labpulse.ai/health/ready
```

Wichtig:
- `live` heißt: der Dienst lebt
- `ready` heißt: der Dienst ist auch operativ ausreichend bereit

Ein `degraded` bei `ready` ist nicht automatisch ein Totalausfall.

## Häufige Probleme

### Frontend startet nicht

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Backend antwortet nicht

Prüfe zuerst:

```bash
docker ps
docker-compose logs -f backend
```

### Datenbank-Verbindung schlägt fehl

```bash
docker-compose restart db
docker-compose logs -f db
```

### Port ist schon belegt

Dann läuft meist schon ein anderer Dienst auf demselben Port.
Prüfe mit:

```bash
lsof -i :3000
lsof -i :8000
lsof -i :15432
```

## Wichtige Warnung für Production

`docker-compose.yml` ist nur für lokale Entwicklung gedacht.

Nicht der richtige Weg für Live-Deploys.

Der produktive Standard-Deploy ist:

```bash
ssh root@5.9.106.75 '/usr/local/bin/viralflux-deploy'
```

Aber nur nachdem dein Stand auf GitHub `main` liegt.

Details:
- [DEPLOY.md](/Users/davidwegener/Desktop/viralflux/DEPLOY.md)

## Wenn du nur 30 Sekunden hast

Das sind die wichtigsten Befehle:

```bash
docker-compose up -d db redis backend
cd frontend
npm install
npm start
```

Dann öffnest du:

- [http://localhost:3000](http://localhost:3000)

Wenn etwas nicht funktioniert, prüfe zuerst:

```bash
docker-compose logs -f backend
curl http://localhost:8000/health/live
```
