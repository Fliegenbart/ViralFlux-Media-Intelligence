# Deployment Guide (Production)

Diese Datei beschreibt den **sicheren Live-Weg**.

In einfachen Worten:
- lokal entwickeln
- gezielt pruefen
- auf `main` pushen
- auf dem Server das Deploy-Script ausfuehren

Nicht machen:
- nicht direkt aus dem lokalen Arbeitsbaum deployen
- nicht manuell im Live-Checkout herumeditieren
- nicht `docker-compose.yml` als Live-Manifest benutzen

## Was ein guter Live-Deploy erreichen soll

Nach einem guten Deploy gilt:
- die neue Version kommt aus `origin/main`
- Frontend, Backend, Worker und Beat laufen sauber neu
- `db` und `redis` bleiben als laufende Infra erhalten
- `/health/live` ist gesund
- `/health/ready` ist gesund oder zumindest sauber erklaert
- die wichtigsten Produktpfade antworten

## Der normale Live-Weg

Auf dem Server gibt es einen **clean Checkout** und das versionierte Script:

- Repo-Script: `scripts/deploy-live.sh`

Der typische Aufruf auf dem Server sieht so aus:

```bash
ssh <deploy-user>@<deploy-host> 'cd <deploy-root> && ./scripts/deploy-live.sh'
```

Wichtig:
- `<deploy-root>` ist der **saubere Server-Checkout**
- deployt wird immer der Stand von `origin/main`
- lokale Sonderstaende werden dabei bewusst ignoriert

## Was das Deploy-Script wirklich macht

`scripts/deploy-live.sh` arbeitet in dieser Reihenfolge:

1. Es holt den neuesten Stand von `origin/main`.
2. Es setzt den clean Checkout hart auf genau diesen Stand.
3. Es erzwingt fuer Live das Produktions-Manifest `docker-compose.prod.yml`.
4. Es baut Frontend und Backend-Images neu.
5. Es startet zuerst `db` und `redis`.
6. Es startet danach `frontend-prod`, `backend`, `celery_worker` und `celery_beat`.
7. Es prueft Sicherheits-Guards wie:
   - `ENVIRONMENT=production`
   - keine Runtime-Schema-Aenderungen
   - keine Host-Bind-Mounts im Live-Modus
8. Es prueft `/health/live`.
9. Es fuehrt den Release-Smoke gegen die Kernpfade aus.
10. Wenn der Kern fehlschlaegt, rollt es auf den vorherigen Commit zurueck.

## Das richtige Compose-Manifest fuer Live

Fuer Live gilt:
- `docker-compose.prod.yml` ist der erlaubte Standard
- `docker-compose.yml` ist nur fuer lokale Entwicklung gedacht

Das Script verweigert standardmaessig absichtlich non-prod Compose-Dateien.

## Produktionsflags

Im Live-Standard setzt das Backend explizit:

- `ENVIRONMENT=production`
- `DB_AUTO_CREATE_SCHEMA=false`
- `DB_ALLOW_RUNTIME_SCHEMA_UPDATES=false`
- `STARTUP_STRICT_READINESS=true`
- `STARTUP_BFARM_IMPORT_ENABLED=false`
- `READINESS_REQUIRE_BROKER=true`

In einfachen Worten:
- live soll sich die Datenbankstruktur **nicht still selbst heilen**
- fehlende Tabellen oder Spalten muessen vor dem Backend-Start explizit per Alembic migriert werden
- die App soll ehrlich melden, wenn operative Abhaengigkeiten fehlen
- der BfArM-Import soll nicht ungefragt beim API-Start loslaufen

## Pflichtschritt fuer Datenbankschema

Wenn ein Release Schema-Aenderungen enthaelt, musst du die Migration bewusst ausfuehren, bevor oder waehrend du das Backend neu startest:

```bash
cd backend
alembic upgrade head
```

Wichtig:
- der aktuelle Backend-Startup erstellt keine Tabellen mehr selbst
- der aktuelle Backend-Startup fuehrt keine Runtime-Schema-Reparaturen mehr aus
- diese Migration ist daher ein expliziter Betriebs-Schritt und nicht mehr implizit im App-Start versteckt

## BfArM-Import bewusst ausloesen

Der BfArM-Import laeuft nicht mehr automatisch beim API-Start.

Nutze dafuer den bestehenden Ingest-Pfad, zum Beispiel:

```bash
curl -X POST https://<your-domain>/api/v1/ingest/bfarm
```

Oder fuehre die bestehende Ingest-Pipeline / den dafuer vorgesehenen Task aus.

## Der wichtigste operative Check nach dem Deploy

Wenn du nach dem Deploy nur wenig Zeit hast, pruefe zuerst:

```bash
curl https://<your-domain>/health/live
curl https://<your-domain>/health/ready
```

Die Bedeutung:
- `live` = Prozess lebt
- `ready` = Dienst ist auch operativ ausreichend bereit

Ein `degraded` bei `ready` bedeutet:
- die App lebt
- aber Datenfrische, Monitoring oder andere operative Bedingungen sind noch nicht voll gruen

## Release-Smoke

Nach dem Deploy wird zusaetzlich ein Release-Smoke ausgefuehrt.

Manuell kannst du ihn so starten:

```bash
cd backend
python scripts/smoke_test_release.py \
  --base-url https://<your-domain> \
  --virus "Influenza A" \
  --horizon 7 \
  --budget-eur 50000 \
  --top-n 3
```

Der Smoke-Test prueft vor allem:
- `/health/live`
- `/health/ready`
- `/api/v1/forecast/regional/predict`
- `/api/v1/forecast/regional/media-allocation`
- `/api/v1/forecast/regional/campaign-recommendations`

Fuer geschuetzte Umgebungen nutzt der Test bevorzugt:
- `SMOKE_BEARER_TOKEN`
- oder `SMOKE_ADMIN_EMAIL` plus `SMOKE_ADMIN_PASSWORD`

Wenn diese Werte nicht gesetzt sind und der Test direkt auf dem Deploy-Host laeuft, versucht er als Fallback die laufenden Backend-Credentials aus dem Container zu lesen.

## Wie das Script Fehlschlaege bewertet

### `live_failed`

Das heisst:
- der Prozess lebt nicht sauber
- oder `/health/live` wird nicht gesund

Folge:
- das Script rollt zurueck

### `business_smoke_failed`

Das heisst:
- Kernpfade wie Forecast, Allocation oder Recommendation sind kaputt
- oder liefern ungueltige / leere Antworten

Folge:
- das Script rollt zurueck

### `ready_blocked`

Das heisst:
- die App lebt
- Kernpfade antworten
- aber `/health/ready` ist operativ noch nicht gesund

Folge:
- der Deploy bleibt sichtbar
- aber man muss die operative Ursache nachziehen

## Was du live niemals tun solltest

- nicht direkt im alten Arbeitsbaum deployen
- nicht manuell Dateien im clean Checkout editieren
- nicht `docker-compose.yml` fuer Production nehmen
- nicht Sicherheits-Flags wie Runtime-Schema-Aenderungen “kurz mal” auf locker stellen
- nicht Bind-Mounts als Live-Standard einfuehren

## Rollback

Wenn ein Commit sauber zurueck muss:

```bash
ssh <deploy-user>@<deploy-host>
cd <deploy-root>
git fetch origin
git checkout main
git reset --hard <COMMIT_HASH>
./scripts/deploy-live.sh
```

Wichtig:
- der Rollback passiert ebenfalls ueber den clean Checkout
- auch hier gilt: nicht manuell an einzelnen Containern herumoperieren, wenn es vermeidbar ist

## Haeufige Probleme

### `port is already allocated`

Pruefe:
- ob schon ein anderer Dienst auf `172.17.0.1:18080` oder `127.0.0.1:8000` lauscht
- ob wirklich nur der vorgesehene Live-Stack das Frontend bereitstellt

### API laeuft, UI aber nicht

Pruefe:

```bash
docker ps
```

Achte besonders auf:
- `virusradar_frontend_prod`
- `virusradar_backend`

### CORS-Fehler

Dann sollte man im Backend-Container `ALLOWED_ORIGINS` pruefen.

### `/health/ready` ist `degraded`

Dann lebt die App oft trotzdem schon.

Typische Ursachen sind:
- Datenquellen zu alt
- operative Snapshots nicht frisch
- Monitoring-/Forecast-Status noch gelb oder rot

Wichtig:
- nicht sofort das Deploy rueckgaengig machen
- erst verstehen, **warum** `ready` degradiert ist

## Die wichtigste Regel zum Schluss

Live-Deploys sollen **wiederholbar, langweilig und sicher** sein.

Wenn ein Deploy davon lebt, dass jemand noch schnell von Hand auf dem Server etwas fixt, ist der Prozess noch nicht gut genug dokumentiert oder automatisiert.
