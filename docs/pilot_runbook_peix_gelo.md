# Pilot Runbook PEIX / GELO

Stand: 2026-03-17

## Zweck

Dieses Runbook beschreibt, wie ein interner PEIX-/GELO-Pilot operativ vorbereitet, geprueft und nur bei echter Freigabe extern genutzt wird.

Wichtig:

- Das Runbook ist bewusst streng.
- `live erreichbar` bedeutet nicht `pilotfreigegeben`.
- Wenn die Gate-Checks rot sind, werden keine externen Handlungsempfehlungen aus dem System verschickt.

## Rollen

### ViralFlux Produkt / Ops

- prueft Live-, Ready- und Smoke-Status
- bewertet bekannte Limitierungen
- dokumentiert Go / No-Go
- ist verantwortlich fuer Incident- und Rollback-Entscheidungen

### PEIX

- bewertet operative Verwendbarkeit der Empfehlungen
- entscheidet nicht allein ueber technische Freigabe
- nutzt Outputs nur in freigegebenen Scope-Kombinationen

### GELO

- bewertet Produktcluster, Keywordcluster und Budget-Guardrails
- entscheidet mit ueber fachliche Akzeptanz
- bekommt keine als "produktiv" bezeichneten Empfehlungen aus einem roten Gate-Zustand

## Vor jedem Pilot-Readout

### 1. Live-Pruefung

```bash
curl -s https://fluxengine.labpulse.ai/health/live
```

Erwartung:

- HTTP `200`
- `status = alive`

### 2. Readiness-Pruefung

```bash
curl -s https://fluxengine.labpulse.ai/health/ready
```

Erwartung fuer echte Pilot-Freigabe:

- kein `unhealthy`
- keine kritischen Blocker im offiziell freizugebenden Pilot-Scope

### 3. Produktkern-Smoke

```bash
cd /Users/davidwegener/Desktop/viralflux/backend
python scripts/smoke_test_release.py \
  --base-url https://fluxengine.labpulse.ai \
  --virus "Influenza A" \
  --horizon 7 \
  --budget-eur 50000 \
  --top-n 3
```

Erwartung fuer echte Pilot-Freigabe:

- kein `live_failed`
- kein `business_smoke_failed`
- idealerweise auch kein `ready_blocked`

## Go / No-Go Entscheidung

### Go

Ein Pilot-Readout darf extern genutzt werden, wenn:

1. `health/live` gruen ist
2. `health/ready` nicht `unhealthy` ist
3. der Produktkern-Smoke nicht faellt
4. die verwendete Virus-/Horizon-Kombination offiziell supported ist
5. die bekannten Limitierungen den konkreten Readout nicht entwerten

### No-Go

Ein Pilot-Readout bleibt intern, wenn:

1. `health/live` nicht gruen ist
2. `health/ready = 503`
3. Forecast / Allocation / Recommendation live `500` liefern
4. die Kombination offiziell unsupported ist
5. Recency, Source-Coverage oder Quality-Gates den Scope fachlich entwerten

## Offizieller Pilot-Scope

### Geplante Pilot-Endpunkte

- `GET /api/v1/forecast/regional/predict`
- `GET /api/v1/forecast/regional/media-allocation`
- `GET /api/v1/forecast/regional/campaign-recommendations`

### Geplante Pilot-Virus-/Horizon-Matrix

- `Influenza A`: `3/5/7`
- `Influenza B`: `3/5/7`
- `SARS-CoV-2`: `3/5/7`
- `RSV A`: `5/7`
- `RSV A / 3`: unsupported

### Aktueller externer Freigabestand

- keine Kombination ist heute extern freigegeben

## Was im Pilot offiziell gezeigt werden darf

Nur wenn Go-Status vorliegt:

- Regionen-Ranking mit `decision_label`, `priority_score`, `reason_trace`
- Budget-/Allocation-Empfehlungen mit `recommended_activation_level`, `suggested_budget_share`, `suggested_budget_amount`
- Campaign Recommendations mit Produktcluster, Keywordcluster, Evidenzklasse und Rationale

Wenn No-Go-Status vorliegt:

- nur interner Technik-/Readiness-Status
- keine operativen Kundenempfehlungen als freigegebene Wahrheit

## Empfohlener Ablauf pro Pilot-Meeting

1. Live-, Ready- und Smoke-Status erfassen
2. Go / No-Go festhalten
3. Nur bei Go:
   - Forecast-Output fuer den offiziellen Scope ziehen
   - Allocation-Output ziehen
   - Campaign Recommendations ziehen
   - Truth-/Pilot-Reporting als Kontext hinzunehmen
4. Nur bei No-Go:
   - keine externen Budget- oder Aktivierungsempfehlungen ausgeben
   - stattdessen bekannte Blocker und naechsten Fix-Schritt dokumentieren

## Eskalationslogik

### Fall A: `live_failed`

- Incident
- kein Pilotbetrieb
- Deploy / Rollback / Plattformproblem priorisieren

### Fall B: `ready_blocked`

- System laeuft technisch
- kein externer Pilot-Output ohne expliziten internen Vorbehalt
- Daten-/Artefakt-/Recency-Blocker zuerst beheben

### Fall C: `business_smoke_failed`

- haertester Pilot-Blocker fuer den Produktkern
- keine externen Handlungsempfehlungen
- Kernpfad-Fix vor jeder weiteren Pilotfreigabe

## Aktueller Ist-Zustand am 2026-03-17

- `health/live` = gruen
- `health/ready` = `503`
- moderner Kernpfad-Smoke = `business_smoke_failed`
- regionale Forecast-, Allocation- und Recommendation-Endpunkte liefern aktuell `500`
- `RSV A / h3` ist bewusst unsupported

## Harte operative Aussage

Am 17. Maerz 2026 ist der richtige Modus fuer PEIX / GELO:

- System live zeigen: ja
- Produktbild und Pilot-Scope diskutieren: ja
- operative Empfehlungen extern freigeben: nein

Der Pilot darf erst geoeffnet werden, wenn der Kernpfad-Smoke gruen ist und die regionale Readiness nicht mehr durch kritische operative Blocker dominiert wird.
