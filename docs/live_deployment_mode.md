# Live Deployment Mode

Diese Datei beschreibt den verbindlichen Betriebsmodus fuer `https://fluxengine.labpulse.ai/`.

## Kanonischer Standard

Der Live-Deploy nutzt standardmaessig:

- Compose-Manifest: `docker-compose.prod.yml`
- Script: `scripts/deploy-live.sh`
- Environment: `production`
- Backend-Port: `127.0.0.1:8000`
- Frontend-Port: `172.17.0.1:18080`
- Public Edge: externer Reverse Proxy vor dem Compose-Stack

`docker-compose.yml` bleibt ausschliesslich fuer lokale Entwicklung gedacht.

## Pflicht-Flags im Live-Modus

Im produktionsnahen Standard gelten diese Backend-Flags:

- `ENVIRONMENT=production`
- `DB_AUTO_CREATE_SCHEMA=false`
- `DB_ALLOW_RUNTIME_SCHEMA_UPDATES=false`
- `STARTUP_STRICT_READINESS=true`
- `READINESS_REQUIRE_BROKER=true`

Das bedeutet:

- keine implizite Runtime-Schema-Heilung im Normalbetrieb
- keine stillen Dev-Defaults im Live-Pfad
- kein "development"-Environment auf der Live-Instanz
- Readiness ist hart genug, um echte Betriebsblocker sichtbar zu machen

## Mount- und Dateimodell

Der Live-Pfad verwendet keine Host-Bind-Mounts fuer App-Container.

Stattdessen:

- persistente DB ueber `postgres_data`
- persistente App-Daten ueber `app_data`
- persistente Modellartefakte ueber `ml_models`

Das reduziert Drift zwischen Host-Dateisystem und Container-Laufzeit.

Weil der Live-Pfad keine Code-Bind-Mounts verwendet, muessen Backend, Worker und Beat beim Deploy als Images neu gebaut werden. Ein `git pull` allein reicht im Live-Modus nicht aus.

## Dev vs. Live

`docker-compose.yml`:

- lokale Entwicklung
- Host-Bind-Mounts
- Dev-Defaults
- bewusst toleranter fuer Bootstrap und Iteration

`docker-compose.prod.yml`:

- Live-Deploy und produktionsnahe Server-Laufzeit
- keine Host-Bind-Mounts
- produktive Environment-Flags
- loopback-gebundener Backend-Port und stabiler Frontend-Host-Binding fuer den bestehenden Public-Edge

## Deploy-Guardrails

`scripts/deploy-live.sh` erzwingt standardmaessig:

- `docker-compose.prod.yml` als Compose-Datei
- `ENVIRONMENT=production` im Backend/Worker/Beat
- `DB_AUTO_CREATE_SCHEMA=false`
- `DB_ALLOW_RUNTIME_SCHEMA_UPDATES=false`
- `STARTUP_STRICT_READINESS=true` im Backend
- `READINESS_REQUIRE_BROKER=true` im Backend
- keine Bind-Mounts auf den Live-App-Containern

Ein non-prod Compose-Deploy ist nur mit explizitem Override `ALLOW_DEV_COMPOSE_LIVE=true` moeglich und soll nicht fuer Normalbetrieb verwendet werden.

## Failure Modes

Wenn der Live-Pfad falsch konfiguriert ist, soll der Deploy hart scheitern statt still zu starten.

Typische harte Fehler:

- falsches Compose-Manifest
- fehlende produktive Environment-Flags
- Bind-Mounts im Live-Pfad
- Liveness-Fehler nach dem Rollout

Readiness bleibt bewusst advisory im Deploy-Script, damit ein Release nicht wegen bereits bekannter fachlicher Blocker automatisch zurueckrollt. Die Readiness-Antwort muss aber explizit geprueft werden.
