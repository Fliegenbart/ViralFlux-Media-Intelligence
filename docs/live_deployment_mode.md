# Live Deployment Mode

Diese Datei beschreibt den verbindlichen Betriebsmodus für `https://fluxengine.labpulse.ai/`.

## Kanonischer Standard

Der Live-Deploy nutzt standardmäßig:

- Compose-Manifest: `docker-compose.prod.yml`
- Script: `scripts/deploy-live.sh`
- Environment: `production`
- Backend-Port: `127.0.0.1:8000`
- Frontend-Port: `172.17.0.1:18080`
- Public Edge: externer Reverse Proxy vor dem Compose-Stack

`docker-compose.yml` bleibt ausschliesslich für lokale Entwicklung gedacht.

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

Der Live-Pfad verwendet keine Host-Bind-Mounts für App-Container.

Stattdessen:

- persistente DB über `postgres_data`
- persistente App-Daten über `app_data`
- persistente Modellartefakte über `ml_models`

Das reduziert Drift zwischen Host-Dateisystem und Container-Laufzeit.

Weil der Live-Pfad keine Code-Bind-Mounts verwendet, müssen Backend, Worker und Beat beim Deploy als Images neu gebaut werden. Ein `git pull` allein reicht im Live-Modus nicht aus.

## Dev vs. Live

`docker-compose.yml`:

- lokale Entwicklung
- Host-Bind-Mounts
- Dev-Defaults
- bewusst toleranter für Bootstrap und Iteration

`docker-compose.prod.yml`:

- Live-Deploy und produktionsnahe Server-Laufzeit
- keine Host-Bind-Mounts
- produktive Environment-Flags
- loopback-gebundener Backend-Port und stabiler Frontend-Host-Binding für den bestehenden Public-Edge

## Deploy-Guardrails

`scripts/deploy-live.sh` erzwingt standardmäßig:

- `docker-compose.prod.yml` als Compose-Datei
- `ENVIRONMENT=production` im Backend/Worker/Beat
- `DB_AUTO_CREATE_SCHEMA=false`
- `DB_ALLOW_RUNTIME_SCHEMA_UPDATES=false`
- `STARTUP_STRICT_READINESS=true` im Backend
- `READINESS_REQUIRE_BROKER=true` im Backend
- keine Bind-Mounts auf den Live-App-Containern

Ein non-prod Compose-Deploy ist nur mit explizitem Override `ALLOW_DEV_COMPOSE_LIVE=true` möglich und soll nicht für Normalbetrieb verwendet werden.

Bestehende Infra-Container für Postgres und Redis werden im Migrationspfad bewusst wiederverwendet, falls sie bereits unter den kanonischen Namen `virusradar_db` und `viralflux_redis` laufen. Dadurch wird die Umstellung vom alten dev-lastigen Live-Stack auf den neuen Prod-Pfad ohne unnötige Datenbank-Neuanlage möglich.

Vor dem Ersetzen der Live-App-Container läuft jetzt ausserdem immer:

- `alembic upgrade head` im Backend-Image

Das verhindert, dass ein Release erst die laufenden Container abschiesst und dann an einer fehlenden Pflichtmigration scheitert.

## Failure Modes

Wenn der Live-Pfad falsch konfiguriert ist, soll der Deploy hart scheitern statt still zu starten.

Typische harte Fehler:

- falsches Compose-Manifest
- fehlende produktive Environment-Flags
- Bind-Mounts im Live-Pfad
- Liveness-Fehler nach dem Rollout

Readiness bleibt bewusst advisory im Deploy-Script, damit ein Release nicht wegen bereits bekannter fachlicher Blocker automatisch zurückrollt. Die Readiness-Antwort muss aber explizit geprüft werden.

## Rollback-Verhalten

Der automatische Rollback setzt nicht mehr nur Git zurueck, sondern baut fuer den vorherigen Commit die App-Images neu und startet sie erneut.

Das ist wichtig, weil ein nacktes `git reset --hard` den Host-Checkout zwar zuruecksetzt, aber bereits gebaute Docker-Images sonst auf dem neueren Stand bleiben koennen.

Grenze dieses Mechanismus:

- Nicht jede Datenbankmigration ist rueckwaertskompatibel.
- Wenn ein Release die Datenbankstruktur bewusst veraendert, muss im Incident-Fall geprueft werden, ob der alte Commit mit dem neuen Schema noch lauffaehig ist.

## Worktree-Hygiene

Der Live-Checkout ist kein Ablageort fuer:

- Debug-Skripte
- Exportdaten
- Experiment-Artefakte
- lokale Modellordner

Der Grund ist simpel:

- ein schmutziger Checkout macht Deploys schwerer pruefbar
- unversionierte Dateien wirken in Due Diligence unprofessionell
- Debug- und Datenreste vergroessern Drift zwischen Repo, Server und Laufzeit
