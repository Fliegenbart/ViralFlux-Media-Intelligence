# Deployment Guide (Production)

Diese Anleitung beschreibt den produktiven Deploy für `https://fluxengine.labpulse.ai/`.

## Zielzustand

- Domain: `https://fluxengine.labpulse.ai/`
- Public Edge: `voxdrop-nginx` auf `80/443`
- Live-Frontend: `virusradar_frontend_prod` auf Host-Port `18080`
- App-Stack: `backend`, `celery_worker`, `celery_beat` im Clean-Compose-Projekt
- Persistente Infra: `virusradar_db` und `viralflux_redis`
- Brand-Default im Prototyp: `gelo`

## Server-Pfade

- Clean Checkout: `/opt/viralflux-media-intelligence-clean`
- Deploy-Script: `/usr/local/bin/viralflux-deploy`
- Versioniertes Deploy-Script im Repo: `/opt/viralflux-media-intelligence-clean/scripts/deploy-live.sh`
- Aktuell genutztes Live-Compose-Manifest: `/opt/viralflux-media-intelligence-clean/docker-compose.yml`

## Standard-Deploy

```bash
ssh root@5.9.106.75 '/usr/local/bin/viralflux-deploy'
```

Was der Command macht:

1. `origin/main` fetchen
2. lokalen Stand im clean Checkout hart auf `origin/main` setzen
3. das aktuelle Live-Compose-Manifest `docker-compose.yml` verwenden
4. Frontend-Image neu bauen
5. sicherstellen, dass `virusradar_db` und `viralflux_redis` im Clean-Netz hängen
6. `frontend-prod`, `backend`, `celery_worker` und `celery_beat` sauber neu erzeugen
7. Status der Live-Services ausgeben

## Smoke-Checks nach Deploy

```bash
curl -I https://fluxengine.labpulse.ai
curl https://fluxengine.labpulse.ai/health/live
curl https://fluxengine.labpulse.ai/health/ready
curl 'https://fluxengine.labpulse.ai/api/v1/media/cockpit?virus_typ=Influenza%20A&target_source=RKI_ARE'
curl -X OPTIONS \
  -H 'Origin: https://fluxengine.labpulse.ai' \
  -H 'Access-Control-Request-Method: GET' \
  'https://fluxengine.labpulse.ai/api/v1/media/products' -I
```

Erwartung:

- `/` -> `200`
- `/health/live` -> JSON mit `status: alive`
- `/health/ready` -> JSON mit Readiness-Snapshot; `200` bedeutet operativ bereit, `503` zeigt explizite Blocker
- API-Endpunkte liefern JSON
- CORS-Header erlaubt `https://fluxengine.labpulse.ai`

## Wichtige Hinweise

- Nicht aus dem alten, lokalen Arbeitsbaum deployen: `/opt/viralflux-media-intelligence` bleibt nur als Altbestand liegen.
- Produktive Deploys nur über den clean Checkout + Deploy-Script.
- Keine manuelle Anpassung der App-Dateien im clean Checkout; Änderungen gehören ins GitHub-Repo.
- Der aktuelle Live-Pfad nutzt `docker-compose.yml`; `docker-compose.prod.yml` ist derzeit nicht der aktive Deploy-Entry-Point.
- `virusradar_caddy_proxy` und das alte Compose-Netzwerk sind nicht mehr Teil des Live-Pfads.

## Rollback (schnell)

Wenn ein Commit zurückgerollt werden muss:

```bash
ssh root@5.9.106.75
cd /opt/viralflux-media-intelligence-clean
git fetch origin
git checkout main
git reset --hard <COMMIT_HASH>
/usr/local/bin/viralflux-deploy
```

## Troubleshooting

- `port is already allocated`:
  - prüfen, ob ein anderer Service `18080` oder `8000` belegt
  - sicherstellen, dass nur der Clean-Stack `virusradar_frontend_prod` bereitstellt
- CORS-Fehler:
  - `ALLOWED_ORIGINS` im Backend-Container prüfen
- API läuft, UI nicht:
  - `docker ps` für `virusradar_frontend_prod` und `virusradar_backend` prüfen
