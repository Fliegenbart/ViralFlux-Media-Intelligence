# Pilot Acceptance Criteria

Stand: 2026-03-17

## Zweck

Dieses Dokument definiert die ehrliche Freigabelogik fuer einen PEIX-/GELO-Pilot auf Basis des real laufenden Systems.

Es trennt bewusst:

- `live erreichbar`
- `ready for pilot`
- `fully production-grade`

## Aktuelle Bewertung

Heute gilt:

- `live erreichbar`: `yes`
- `ready for pilot`: `no`
- `fully production-grade`: `no`

Begruendung:

- `health/live` ist gruen
- `health/ready` ist `degraded`, nicht mehr `unhealthy`
- der moderne Business-Smoke endet auf `ready_blocked`, nicht mehr auf `business_smoke_failed`
- der eigentliche Blocker ist jetzt Quality Gate / Pilotvertrag, nicht mehr Kernpfad-Uptime

## Mindestkriterien fuer `live erreichbar`

Alle Punkte muessen gelten:

1. `GET /health/live` liefert `200`.
2. Die Produktionsumgebung laeuft mit `ENVIRONMENT=production`.
3. Keine Runtime-Schema-Heilung im Live-Standard.
4. Frontend und Backend sind ueber die produktive Domain erreichbar.

## Mindestkriterien fuer `ready for pilot`

Alle Punkte muessen gelten:

1. `GET /health/ready` ist nicht `unhealthy`.
2. Der moderne Release-Smoke endet nicht mit `live_failed` oder `business_smoke_failed`.
3. Die offiziellen Regional-Endpunkte liefern fuer den Pilot-Scope erfolgreich JSON:
   - `GET /api/v1/forecast/regional/predict`
   - `GET /api/v1/forecast/regional/media-allocation`
   - `GET /api/v1/forecast/regional/campaign-recommendations`
4. Forecast-Recency fuer den Pilot-Scope ist nicht kritisch.
5. Im Pilot-Scope gibt es keine stillen Legacy-Fallbacks.
6. Unsupported-Kombinationen sind explizit dokumentiert und werden als `unsupported` behandelt.
7. Mindestens ein explizit freigegebener Pilot-Scope steht fachlich auf `GO`, nicht nur technisch auf `warning`.
8. Ein interner Operator kann die Pilot-Ausgaben ueber das Runbook reproduzierbar erzeugen.

## Mindestkriterien fuer `fully production-grade`

Alle Punkte muessen gelten:

1. Der gesamte offiziell verkaufte Scope ist gruen oder bewusst unsupported.
2. Operative Forecast-Snapshots werden regelmaessig neu geschrieben.
3. Forecast-Recency laeuft nicht mehr aus Trainings-Snapshots, sondern aus operativen Snapshots.
4. Kritische Source-Coverage-Probleme sind fuer den verkauften Scope beseitigt oder bewusst aus dem Support herausgenommen.
5. Release-Smoke, Go/No-Go und Rollback sind als Betriebsroutine belastbar.
6. Support-, Risiko- und Governance-Dokumente sind konsistent mit dem realen Systemstand.

## Offiziell unterstuetzte Pilot-Endpunkte

### Operativ / technisch

- `GET /health/live`
- `GET /health/ready`

### Produktkern

- `GET /api/v1/forecast/regional/predict`
- `GET /api/v1/forecast/regional/media-allocation`
- `GET /api/v1/forecast/regional/campaign-recommendations`

### Nicht primaerer Pilotvertrag

- `GET /api/v1/media/cockpit`
- regionale Alias-Endpunkte ohne eigenstaendigen Mehrwert wie `/regional` oder `/regional/media-activation`

## Offiziell unterstuetzte Outputs im Pilot

Sobald ein Pilot-Scope freigegeben ist, gelten mindestens diese Outputs als offiziell:

### Forecast / Decision

- per Region:
  - `decision_label`
  - `priority_score`
  - `reason_trace`
  - `uncertainty_summary`
  - nested `decision`

### Allocation

- per Region:
  - `recommended_activation_level`
  - `priority_rank`
  - `suggested_budget_share`
  - `suggested_budget_amount`
  - `confidence`
  - `allocation_reason_trace`

### Recommendation

- per Empfehlung:
  - `region`
  - `recommended_product_cluster`
  - `recommended_keyword_cluster`
  - `activation_level`
  - `suggested_budget_amount`
  - `confidence`
  - `evidence_class`
  - `recommendation_rationale`

## Offizielle Virus-/Horizon-Matrix

### Technisch supported

- `Influenza A`: `3/5/7`
- `Influenza B`: `3/5/7`
- `SARS-CoV-2`: `3/5/7`
- `RSV A`: `5/7`
- `RSV A / 3`: unsupported

### Day-one pilot-supported

- `Influenza A / h7`
- `Influenza B / h7`
- `RSV A / h7`

### Nicht pilot-supported in diesem Pass

- `Influenza A / h3,h5`
- `Influenza B / h3,h5`
- `RSV A / h5`
- `SARS-CoV-2 / h3,h5,h7`

### SARS-CoV-2 Sonderregel

- `SARS-CoV-2` bleibt standardmaessig:
  - `rollout_mode = shadow`
  - `activation_policy = watch_only`
- `SARS-CoV-2 / h7` kann nur dann promotet werden, wenn:
  - `REGIONAL_SARS_H7_PROMOTION_ENABLED=true`
  - die letzten zwei operativen Snapshots `quality_gate=GO`, `forecast_recency_status=ok`, `source_coverage_required_status=ok` und keinen `artifact_transition_mode` zeigen

## Known Limitations heute

1. Die regionalen Kernendpunkte laufen wieder, aber die Day-one-Pilot-Scopes sind fachlich noch nicht freigegeben.
2. `health/ready` ist aktuell `degraded`, nicht `healthy`.
3. `regional_operational.summary.critical = 0`, aber `quality_gate_failures` dominieren weiter die Warning-Lage.
4. `forecast_monitoring` steht fachlich weiter auf `WATCH`.
5. `SARS-CoV-2` bleibt standardmaessig shadow/watch-only.
6. Der Day-one-Pilot-Scope ist enger als der technische Support und muss auch in Sales-/Pilotkommunikation so benannt werden.

## Freigabeentscheidung

### Extern pilotfreigeben

Nur wenn:

- alle Kriterien fuer `ready for pilot` erfuellt sind
- mindestens ein bewusst begrenzter Day-one-Pilot-Scope auf `GO` steht
- bekannte Limitierungen nicht im Widerspruch zum verkauften Scope stehen

### Intern weiterhaerten

Wenn eine der folgenden Bedingungen gilt:

- `health/ready = unhealthy`
- Release-Smoke = `business_smoke_failed`
- Kernpfad liefert `500`
- kein Day-one-Pilot-Scope erreicht `quality_gate = GO`
- der operative Vertrag und der verkaufte Pilot-Scope laufen auseinander

## Harte Aussage fuer heute

Die ehrliche Freigabe am 17. Maerz 2026 lautet:

- ViralFlux ist live erreichbar.
- ViralFlux ist technisch deutlich belastbarer als zuvor.
- ViralFlux ist noch nicht pilotfreigegeben.
- Der naechste harte Hebel ist nicht Uptime, sondern die fachliche Freigabe mindestens eines kleinen Day-one-Pilot-Scopes.
