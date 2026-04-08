# Release Smoke Strategy

## Ziel

Der Release-Smoke soll nach einem Deploy schnell zeigen, ob ViralFlux:

- technisch lebt
- operativ ready ist
- den eigentlichen Produktkern ohne `500` oder kaputte Payloads bedienen kann

Der Smoke ist bewusst produktnah und nicht mehr cockpit-zentriert.

## Canonical Checks

Der aktuelle Standard-Scope für den Release-Smoke ist:

1. `GET /health/live`
2. `GET /health/ready`
3. `GET /api/v1/forecast/regional/predict`
4. `GET /api/v1/forecast/regional/media-allocation`
5. `GET /api/v1/forecast/regional/campaign-recommendations`

Standardparameter:

- `virus_typ=Influenza A`
- `horizon_days=7`
- `weekly_budget_eur=50000`
- `top_n=3`

Diese Kombination ist bewusst identisch mit dem Day-one-Pilotkandidaten `Influenza A / h7`.

Sie ist nah genug am operativen Produktkern und gleichzeitig eng genug, um kein falsches Bild eines breiten Pilotvertrags zu erzeugen.

## Failure Levels

### `live_failed`

Bedeutung:

- `/health/live` ist nicht `200`
- oder der Prozess meldet nicht `status=alive`

Folge:

- technischer Deploy-Fail
- `deploy-live.sh` rollt zurück

### `business_smoke_failed`

Bedeutung:

- Forecast, Allocation oder Campaign Recommendations liefern `500`
- oder die Response-Shapes sind fachlich unbrauchbar, z. B. leere Kernlisten oder fehlende Pflichtfelder

Folge:

- Produktkern ist nach Deploy nicht belastbar
- `deploy-live.sh` rollt zurück

### `ready_blocked`

Bedeutung:

- `/health/ready` ist nicht healthy
- aber Liveness und Kernpfade funktionieren

Folge:

- Deploy bleibt sichtbar
- Zustand ist operativ blockiert, aber kein technischer Hard-Fail
- typische Ursachen: rote Quality Gates, nicht freigegebener Pilot-Scope, konservative Shadow-/Watch-Policies

## Cockpit-Politik

`/api/v1/media/cockpit` kann weiterhin geprüft werden, aber nur optional:

- per `--check-cockpit`
- als advisory Zusatzsignal
- nicht als alleiniger Release-Gatekeeper

Grund:

- der Produktkern liegt inzwischen im regionalen Forecast-/Decision-/Allocation-/Recommendation-Pfad
- Cockpit ist wertvoll, aber nicht mehr die robusteste einzige Go/No-Go-Prüfung

## CLI

Lokal oder gegen Live:

```bash
cd /Users/davidwegener/Desktop/viralflux/backend
python scripts/smoke_test_release.py \
  --base-url https://fluxengine.labpulse.ai \
  --virus "Influenza A" \
  --horizon 7 \
  --budget-eur 50000 \
  --top-n 3
```

Optional:

```bash
python scripts/smoke_test_release.py \
  --base-url https://fluxengine.labpulse.ai \
  --virus "Influenza A" \
  --horizon 7 \
  --budget-eur 50000 \
  --top-n 3 \
  --check-cockpit
```

## Operative Interpretation

- `pass`
  - live healthy
  - ready healthy
  - Kernpfade liefern brauchbare Produktpayloads
- `warning`
  - live healthy
  - Kernpfade funktionieren
  - readiness ist noch blockiert
- `fail`
  - live kaputt
  - oder Kernpfade kaputt

## Warum dieser Schnitt

Der Smoke soll nicht jedes fachliche Modellproblem lösen. Er soll klar beantworten:

- ist das System da?
- ist der Kernpfad benutzbar?
- ist der Betrieb fachlich freigegeben?

Genau deshalb trennt der aktuelle Smoke sauber zwischen `live_failed`, `ready_blocked` und `business_smoke_failed`.

Wichtig:

- `ready_blocked` ist inzwischen die ehrliche Restkategorie für einen lebenden, aber noch nicht fachlich freigegebenen regionalen Produktkern
- für PEIX / GELO bedeutet ein `ready_blocked` nicht automatisch, dass der Deploy kaputt ist
- es bedeutet, dass Uptime und Produktnutzbarkeit weiter sind als die operative Pilotfreigabe
