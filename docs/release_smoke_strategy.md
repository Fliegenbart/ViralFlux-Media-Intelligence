# Release Smoke Strategy

## Ziel

Der Release-Smoke soll nach einem Deploy schnell zeigen, ob ViralFlux:

- technisch lebt
- operativ ready ist
- den eigentlichen Produktkern ohne `500` oder kaputte Payloads bedienen kann

Der Smoke ist bewusst produktnah und nicht mehr cockpit-zentriert.

## Canonical Checks

Der aktuelle Standard-Scope fuer den Release-Smoke ist:

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

Diese Kombination ist nah genug am operativen Produktkern und gleichzeitig stabil genug fuer einen schnellen Deploy-Check.

## Failure Levels

### `live_failed`

Bedeutung:

- `/health/live` ist nicht `200`
- oder der Prozess meldet nicht `status=alive`

Folge:

- technischer Deploy-Fail
- `deploy-live.sh` rollt zurueck

### `business_smoke_failed`

Bedeutung:

- Forecast, Allocation oder Campaign Recommendations liefern `500`
- oder die Response-Shapes sind fachlich unbrauchbar, z. B. leere Kernlisten oder fehlende Pflichtfelder

Folge:

- Produktkern ist nach Deploy nicht belastbar
- `deploy-live.sh` rollt zurueck

### `ready_blocked`

Bedeutung:

- `/health/ready` ist nicht healthy
- aber Liveness und Kernpfade funktionieren

Folge:

- Deploy bleibt sichtbar
- Zustand ist operativ blockiert, aber kein technischer Hard-Fail
- typische Ursachen: stale data, fehlende Artefakte, rote Quality Gates

## Cockpit-Politik

`/api/v1/media/cockpit` kann weiterhin geprueft werden, aber nur optional:

- per `--check-cockpit`
- als advisory Zusatzsignal
- nicht als alleiniger Release-Gatekeeper

Grund:

- der Produktkern liegt inzwischen im regionalen Forecast-/Decision-/Allocation-/Recommendation-Pfad
- Cockpit ist wertvoll, aber nicht mehr die robusteste einzige Go/No-Go-Pruefung

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

Der Smoke soll nicht jedes fachliche Modellproblem loesen. Er soll klar beantworten:

- ist das System da?
- ist der Kernpfad benutzbar?
- ist der Betrieb fachlich freigegeben?

Genau deshalb trennt der aktuelle Smoke sauber zwischen `live_failed`, `ready_blocked` und `business_smoke_failed`.
