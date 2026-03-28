# Deployment Guide (Production)

Diese Anleitung beschreibt einen produktionsnahen Deploy. Ersetze Platzhalter wie
`<deploy-host>`, `<deploy-user>`, `<deploy-root>` und `<deploy-script>` passend für deine Umgebung.

## Zielzustand

- Domain: `https://fluxengine.labpulse.ai/`
- Public Edge: `voxdrop-nginx` auf `80/443`
- Live-Frontend: `virusradar_frontend_prod` auf `172.17.0.1:18080`
- Live-Backend: `virusradar_backend` auf `127.0.0.1:8000`
- App-Stack: `frontend-prod`, `backend`, `celery_worker`, `celery_beat` im Clean-Compose-Projekt
- Persistente Infra: `db` und `redis` im selben Production-Compose-Projekt
- Brand-Default im Prototyp: `gelo`
- Betriebsmodus: `ENVIRONMENT=production`, keine Runtime-Schema-Heilung, keine Host-Bind-Mounts

## Server-Pfade

- Clean Checkout: `<deploy-root>`
- Deploy-Script: `<deploy-script>`
- Versioniertes Deploy-Script im Repo: `<deploy-root>/scripts/deploy-live.sh`
- Aktuell genutztes Live-Compose-Manifest: `<deploy-root>/docker-compose.prod.yml`

## Standard-Deploy

```bash
ssh <deploy-user>@<deploy-host> '<deploy-script>'
```

Was der Command macht:

1. `origin/main` fetchen
2. lokalen Stand im clean Checkout hart auf `origin/main` setzen
3. das aktuelle Live-Compose-Manifest `docker-compose.prod.yml` verwenden
4. Frontend-Image neu bauen
5. Backend-/Worker-/Beat-Images neu bauen, weil der Live-Pfad keine Code-Bind-Mounts mehr verwendet
6. `db` und `redis` im Production-Compose-Projekt hochfahren oder vorhandene Infra-Container sauber wiederverwenden
7. `frontend-prod`, `backend`, `celery_worker` und `celery_beat` sauber neu erzeugen
8. Guard-Checks auf `ENVIRONMENT=production`, harte DB-Flags und bind-mount-freien Live-Modus ausführen
9. Liveness pruefen
10. modernen Release-Smoke gegen Live, Ready und den regionalen Produktkern ausfuehren
11. Status der Live-Services ausgeben

## Produktionsflags

Der Live-Standard setzt im Backend explizit:

- `ENVIRONMENT=production`
- `DB_AUTO_CREATE_SCHEMA=false`
- `DB_ALLOW_RUNTIME_SCHEMA_UPDATES=false`
- `STARTUP_STRICT_READINESS=true`
- `READINESS_REQUIRE_BROKER=true`

## Release-Smoke nach Deploy

```bash
cd backend
python scripts/smoke_test_release.py \
  --base-url https://<your-domain> \
  --virus "Influenza A" \
  --horizon 7 \
  --budget-eur 50000 \
  --top-n 3
```

Der moderne Release-Smoke prueft:

- `/health/live`
- `/health/ready`
- `/api/v1/forecast/regional/predict`
- `/api/v1/forecast/regional/media-allocation`
- `/api/v1/forecast/regional/campaign-recommendations`

Der Deploy nutzt fuer diese Smoke-Requests standardmaessig ein etwas groesseres Request-Timeout (`SMOKE_TIMEOUT=15`), damit frisch gestartete Services nicht zu frueh als Fehler gewertet werden.
Fuer geschuetzte Live-Instanzen nutzt der Smoke-Test bevorzugt `SMOKE_BEARER_TOKEN` oder `SMOKE_ADMIN_EMAIL`/`SMOKE_ADMIN_PASSWORD`.
Wenn diese Werte nicht gesetzt sind und der Test direkt auf dem Deploy-Host laeuft, versucht er als Fallback die laufenden Backend-Container-Credentials aus `virusradar_backend` zu lesen.

Optional kann zusaetzlich `--check-cockpit` gesetzt werden. Der Cockpit-Pfad ist aber nur advisory und nicht mehr der alleinige Go/No-Go-Indikator.

Failure-Levels:

- `live_failed`
  - Prozess lebt nicht oder `/health/live` ist nicht gesund.
  - Deploy-Script rollt zurueck.
- `business_smoke_failed`
  - Kernpfade Forecast / Allocation / Recommendation liefern `500`, leere oder ungueltige Payloads.
  - Deploy-Script rollt zurueck.
- `ready_blocked`
  - Service lebt und Kernpfade antworten, aber `/health/ready` ist nicht healthy.
  - Deploy bleibt sichtbar, aber der Zustand ist operativ blockiert und muss nachgezogen werden.

Direkte Basischecks bleiben trotzdem sinnvoll:

```bash
curl -I https://<your-domain>
curl https://<your-domain>/health/live
curl https://<your-domain>/health/ready
```

## Wichtige Hinweise

- Nicht aus dem alten, lokalen Arbeitsbaum deployen: `/opt/viralflux-media-intelligence` bleibt nur als Altbestand liegen.
- Produktive Deploys nur über den clean Checkout + Deploy-Script.
- Keine manuelle Anpassung der App-Dateien im clean Checkout; Änderungen gehören ins GitHub-Repo.
- `docker-compose.yml` ist nur noch für lokale Entwicklung gedacht und kein zulässiger Live-Deploy-Pfad.
- Der Live-Deploy verweigert standardmäßig non-prod Compose-Manifeste.
- Host-Bind-Mounts sind im Live-Standard nicht erlaubt.
- Runtime-Schema-Mutationen sind im Live-Standard nicht erlaubt.
- `docker-compose.prod.yml` bildet den produktionsnahen Betriebsmodus ohne internes Proxy-Nebenmodell ab; die öffentliche Edge-Terminierung bleibt bei `voxdrop-nginx`.
- Die bestehende Public-Edge proxyt aktuell auf `172.17.0.1:18080`; deshalb bleibt diese Frontend-Bindung im Live-Standard bewusst erhalten.

## Wichtige Betriebsregeln

Es gibt zwei besonders wichtige Unterschiede zwischen lokal und live:

1. `docker-compose.yml` ist nur für lokale Entwicklung gedacht.  
   Dieses Manifest ist kein zulässiger Live-Deploy-Pfad.

2. Live-Deploys laufen über den clean Server-Checkout und das zentrale Deploy-Script.  
   Der Server deployt immer den Stand von `origin/main`, nicht lokale Sonderstände.

## Rollback (schnell)

Wenn ein Commit zurückgerollt werden muss:

```bash
ssh <deploy-user>@<deploy-host>
cd <deploy-root>
git fetch origin
git checkout main
git reset --hard <COMMIT_HASH>
<deploy-script>
```

## Troubleshooting

- `port is already allocated`:
  - prüfen, ob ein anderer Service `172.17.0.1:18080` oder `127.0.0.1:8000` belegt
  - sicherstellen, dass nur der Clean-Stack `virusradar_frontend_prod` bereitstellt
- CORS-Fehler:
  - `ALLOWED_ORIGINS` im Backend-Container prüfen
- API läuft, UI nicht:
  - `docker ps` für `virusradar_frontend_prod` und `virusradar_backend` prüfen
