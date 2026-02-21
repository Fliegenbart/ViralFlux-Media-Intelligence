# Deployment Guide (Production)

Diese Anleitung beschreibt den produktiven Deploy für `https://fluxengine.labpulse.ai/`.

## Zielzustand

- Domain: `https://fluxengine.labpulse.ai/`
- Public Edge: externer Nginx/TLS-Terminator
- App-Proxy: Caddy im Docker-Stack auf Host-Port `18180`
- Backend/DB/Redis: nur intern im Docker-Netzwerk
- Brand-Default im Prototyp: `gelo`

## Server-Pfade

- Clean Checkout: `/opt/viralflux-media-intelligence-clean`
- Edge-Konfiguration: `/opt/viralflux-media-config/Caddyfile.edge`
- Deploy-Script: `/usr/local/bin/viralflux-deploy`

## Standard-Deploy

```bash
ssh root@5.9.106.75 '/usr/local/bin/viralflux-deploy'
```

Was der Command macht:

1. `origin/main` fetchen
2. lokalen Stand im clean Checkout hart auf `origin/main` setzen
3. serverseitige Edge-Caddy-Konfiguration injizieren
4. Compose-Stack bauen und starten
5. Status der Services ausgeben

## Smoke-Checks nach Deploy

```bash
curl -I https://fluxengine.labpulse.ai
curl https://fluxengine.labpulse.ai/health
curl 'https://fluxengine.labpulse.ai/api/v1/media/cockpit?virus_typ=Influenza%20A&target_source=RKI_ARE'
curl -X OPTIONS \
  -H 'Origin: https://fluxengine.labpulse.ai' \
  -H 'Access-Control-Request-Method: GET' \
  'https://fluxengine.labpulse.ai/api/v1/media/products' -I
```

Erwartung:

- `/` -> `200`
- `/health` -> JSON mit `status: healthy`
- API-Endpunkte liefern JSON
- CORS-Header erlaubt `https://fluxengine.labpulse.ai`

## Wichtige Hinweise

- Nicht aus dem alten, lokalen Arbeitsbaum deployen: `/opt/viralflux-media-intelligence` kann absichtlich `dirty` sein.
- Produktive Deploys nur über den clean Checkout + Deploy-Script.
- Keine manuelle Anpassung der App-Dateien im clean Checkout; Änderungen gehören ins GitHub-Repo.

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
  - prüfen, ob ein anderer Service `80/443` belegt
  - sicherstellen, dass der App-Proxy nur auf `18180` bindet
- CORS-Fehler:
  - `ALLOWED_ORIGINS` im Backend-Container prüfen
- API läuft, UI nicht:
  - `docker compose ... ps` und Proxy-Logs prüfen
