# Quickstart

Diese Datei zeigt den schnellsten praktischen Einstieg in die aktive Oberfläche und den technischen Kern.

Wenn du mehr Hintergrund willst, lies danach:
- [README.md](README.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [DEPLOY.md](DEPLOY.md)

## Wofür dieser Quickstart gedacht ist

Dieser Quickstart ist für:
- lokale Entwicklung
- Frontend und Backend schnell starten
- die wichtigsten Health-Checks und Tests ausführen
- den produktnahen Einstieg ohne alte Umbau- oder Laborsprache

Nicht dafür:
- direkt live deployen
- den Production-Server manuell “irgendwie” anfassen

Für Live gilt immer:
1. lokal ändern
2. gezielt prüfen
3. committen
4. auf `main` pushen
5. den Server über das Deploy-Script aktualisieren

## Der schnellste gute Start

Wenn du nur schnell lokal arbeiten willst, ist das der beste Weg:

```bash
docker compose up -d db redis backend
cd frontend
npm install
npm start
```

Danach solltest du erreichen:
- Frontend: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000](http://localhost:8000)
- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)

Wenn etwas klemmt, prüfe zuerst:

```bash
curl http://localhost:8000/health/live
docker compose logs -f backend
```

## Voraussetzungen

Du brauchst lokal:
- Docker
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

Wenn vorhanden, nimm `.env.example` als Startpunkt.

Wichtige lokale Werte:

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

Wichtig:
- `VLLM_BASE_URL` darf **nicht versehentlich auf das Backend selbst zeigen**
- wenn du das Backend **nicht** in Docker betreibst, nutze z. B. `http://127.0.0.1:8001/v1`
- `http://localhost:8000` ist der FastAPI-Port und kein guter Default fuer einen externen LLM-Endpunkt

## 3. Backend lokal starten

### Empfohlener Weg fuer die meisten Arbeiten

```bash
docker compose up -d db redis backend
```

Danach pruefst du:

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

Wichtig:
- `live` heisst: der Dienst lebt
- `ready` heisst: der Dienst ist operativ ausreichend bereit
- `degraded` bei `ready` ist **nicht automatisch** ein Totalausfall

### Optional: Backend ohne Docker starten

Wenn du direkt am Python-Code arbeitest, ist das oft praktischer:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 4. Frontend lokal starten

```bash
cd frontend
npm install
npm start
```

Dann laeuft die App hier:
- [http://localhost:3000](http://localhost:3000)

Wichtig:
- lokal nutzt das Frontend einen Proxy auf `http://localhost:8000`

### Optional: Frontend im Container starten

```bash
docker compose --profile dev up -d frontend
```

## 5. Login lokal

Es gibt keinen fest eingebauten Demo-User im Frontend.

Lokal nutzt du die Werte aus deiner `.env`:
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

## Die 3 wichtigsten lokalen URLs

- Frontend: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000](http://localhost:8000)
- Swagger Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Die wichtigsten Befehle im Alltag

### Laufende Container sehen

```bash
docker ps
```

### Backend-Logs ansehen

```bash
docker compose logs -f backend
```

### Redis-Logs ansehen

```bash
docker compose logs -f redis
```

### Datenbank neu starten

```bash
docker compose restart db
```

## Die wichtigsten Mindestchecks vor einem Merge

## Frontend

```bash
cd frontend
npx tsc --noEmit
CI=true npm test -- --watch=false --runInBand
```

Wenn du groessere Frontend-Aenderungen gemacht hast:

```bash
cd frontend
npm run build
```

## Backend

Wenn `.venv-backend311` existiert, ist das der bevorzugte Weg:

```bash
cd backend
source .venv-backend311/bin/activate
pytest
```

Ohne diese Umgebung:

```bash
cd backend
python3 -m pytest
```

Bei gezielten Aenderungen gilt:
- Frontend: nur die betroffenen Tests laufen lassen
- Backend: nur die kleinste passende `pytest`-Auswahl laufen lassen
- Docker-/Compose-Aenderungen: `docker compose config` pruefen

## Haeufige Probleme

### Frontend startet nicht

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Backend antwortet nicht

Pruefe zuerst:

```bash
docker ps
docker compose logs -f backend
curl http://localhost:8000/health/live
```

### Datenbank-Verbindung schlaegt fehl

```bash
docker compose restart db
docker compose logs -f db
```

### Ein Port ist schon belegt

Dann laeuft meist schon ein anderer Dienst auf demselben Port.

Pruefe mit:

```bash
lsof -i :3000
lsof -i :8000
lsof -i :15432
```

## Wichtige Warnung fuer Production

`docker-compose.yml` bzw. `docker compose` im lokalen Arbeitsbaum ist **nur fuer Entwicklung** gedacht.

Fuer Live gilt:
- niemals direkt aus dem lokalen Arbeitsbaum deployen
- niemals ad hoc auf dem Server “nachflicken”
- immer den beschriebenen Weg aus [DEPLOY.md](DEPLOY.md) benutzen

## Wenn du nur 30 Sekunden hast

Das hier ist der sicherste Kurzweg:

```bash
docker compose up -d db redis backend
cd frontend
npm install
npm start
```

Dann oeffnest du:
- [http://localhost:3000](http://localhost:3000)

Und wenn etwas nicht funktioniert, pruefst du zuerst:

```bash
docker compose logs -f backend
curl http://localhost:8000/health/live
```
