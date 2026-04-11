# Go-To-Pilot Checklist

Stand: 2026-03-24

## Aktueller Entscheidungsstand

- Live erreichbar: ja
- Ready for pilot: nein
- Fully production-grade: nein
- Aktuelle Freigabe: `PILOT GATE CLOSED`

Produktentscheidung seit 24.03.2026:

- `h7` ist der einzige aktiv priorisierte Horizon.
- `h5` ist pausiert.
- `h3` bleibt als Reservepfad erhalten, wird aber nicht aktiv freigeplant.

Diese Bewertung basiert auf dem tatsaechlich laufenden System:

- `GET https://fluxengine.labpulse.ai/health/live` -> `200`
- `GET https://fluxengine.labpulse.ai/health/ready` -> `200` mit `status=degraded`
- `python backend/scripts/smoke_test_release.py --base-url https://fluxengine.labpulse.ai --virus "Influenza A" --horizon 7 --budget-eur 50000 --top-n 3` -> `ready_blocked`

## Harte Blocker heute

- [ ] Der offizielle Day-one-Pilot-Scope hat mindestens einen Scope mit `quality_gate.forecast_readiness = GO`.
- [ ] Der Day-one-Pilot-Scope ist fachlich freigegeben, nicht nur technisch erreichbar.
- [ ] `regional_operational.summary.warning` wird nicht mehr flaechig durch `quality_gate_failures` dominiert.
- [ ] PEIX/GELO können einen explizit freigegebenen Pilot-Scope benennen, statt nur den gesamten technischen Support zu sehen.

## Technische Mindestvoraussetzungen

- [x] Live-Deploy läuft im produktionsnahen Compose-Pfad.
- [x] `ENVIRONMENT=production` ist live aktiv.
- [x] Runtime-Schema-Heilung ist im Live-Standard deaktiviert.
- [x] `health/live` ist grün.
- [x] `health/ready` ist nicht `unhealthy`.
- [x] Release-Smoke für den Kernpfad endet nicht mehr mit `business_smoke_failed`.
- [x] Die drei offiziellen Regional-Endpunkte liefern keine `500` mehr.
- [x] Operative Forecast-Snapshots sind wieder vorhanden.
- [x] Es gibt keinen unbeabsichtigten `legacy_default_window_fallback` mehr im beobachteten Live-Scope.
- [ ] Der offizielle Pilot-Scope hat grüne Quality Gates statt nur `WATCH`.

## Fachliche Mindestvoraussetzungen

- [x] Offizielle Horizon-Matrix ist dokumentiert.
- [x] `RSV A / h3` ist explizit unsupported statt still halb-funktional.
- [x] Der Day-one-Pilotvertrag ist explizit enger als der technische Support.
- [ ] Für den offiziell freizugebenden Pilot-Scope stehen Quality Gates nicht nur auf `WATCH`.
- [ ] Forecast-/Decision-/Allocation-/Recommendation-Outputs für den Pilot-Scope sind nicht nur abrufbar, sondern fachlich freigegeben.
- [ ] Truth-/Pilot-Reporting ist für den externen Pilot intern reproduzierbar abnehmbar.

## Offizieller Pilot-API-Scope

Diese Endpunkte sind der kanonische Pilot-Kern:

- [x] `GET /health/live`
- [x] `GET /health/ready`
- [x] `GET /api/v1/forecast/regional/predict`
- [x] `GET /api/v1/forecast/regional/media-allocation`
- [x] `GET /api/v1/forecast/regional/campaign-recommendations`

Wichtig:

- `/api/v1/media/cockpit` ist nur noch ein Zusatzsignal.
- Alias-Endpunkte wie `/regional`, `/regional/decisions` und `/regional/media-activation` sind nicht der primaere Pilotvertrag.

## Offizielle Virus-/Horizon-Matrix

### Technisch supported

- `Influenza A`: `3/5/7`
- `Influenza B`: `3/5/7`
- `SARS-CoV-2`: `3/5/7`
- `RSV A`: `5/7`
- `RSV A / 3`: explizit unsupported

### Day-one pilot-supported

- `Influenza A / h7`
- `Influenza B / h7`
- `RSV A / h7`

### Reserve-/Beobachtungspfad, nicht aktiv priorisiert

- `Influenza A / h3`
- `Influenza B / h3`
- `SARS-CoV-2 / h3`

Wichtig:

- `Influenza A / h3` und `Influenza B / h3` sind keine Fehlerfaelle mehr.
- Beide bestehen den Hierarchie-Benchmark, aber noch nicht das operative Quality Gate.
- Deshalb bleiben sie ausserhalb der aktiven Produktfreigabe.

### Pausiert im h7-first-Fokus

- `Influenza A / h5`
- `Influenza B / h5`
- `RSV A / h5`
- `SARS-CoV-2 / h5`

### Noch nicht pilot-supported

- `SARS-CoV-2 / h7`

### SARS-Sonderfall

- `SARS-CoV-2 / h7` hat jetzt einen bedingten Promotionspfad.
- Standard bleibt trotzdem:
  - `rollout_mode = shadow`
  - `activation_policy = watch_only`
- Eine Promotion auf aktivierbar ist nur mit expliziter Flag und zwei guten operativen Snapshots erlaubt.

## Bekannte Limitierungen heute

- [x] Live-System ist öffentlich erreichbar.
- [x] Regionale Artefakte für alle offiziell supported `3/5/7`-Scopes sind vorhanden, ausser dem bewusst unsupported `RSV A / h3`.
- [x] Operative Forecast-Snapshots werden geschrieben.
- [x] `health/ready` ist nicht mehr hart rot.
- [ ] Forecast-Monitoring steht fachlich weiter auf `WATCH`.
- [ ] Die Day-one-Pilot-Scopes sind noch nicht formal `GO`.
- [ ] `SARS-CoV-2` bleibt standardmäßig shadow/watch-only.
- [ ] Externe operative Empfehlungen sollten weiter unter manuellem Freigabevorbehalt bleiben.
- [x] `h7` ist als einzige aktive Produktlinie definiert.
- [x] `h5` wird nicht mehr als aktive Ausbau- oder Freigabelinie behandelt.
- [x] `h3` wird nicht mehr als Fehlerfall beschrieben, sondern als Reserve ohne aktuelle Prioritaet.

## Interne Freigabelogik

### Stufe 1: Live erreichbar

Erfüllt, wenn:

- `health/live = 200`
- Deploy im Production-Mode läuft

### Stufe 2: Ready for pilot

Erfüllt erst, wenn:

- `health/ready` nicht `unhealthy` ist
- Release-Smoke nicht `business_smoke_failed` ist
- offizielle Pilot-Endpunkte live Daten liefern
- mindestens ein explizit freigegebener Pilot-Scope auf `GO` steht

### Stufe 3: Fully production-grade

Erfüllt erst, wenn:

- gesamter offiziell verkaufter Scope stabil grün oder bewusst unsupported ist
- Forecast-Recency über operative Snapshots läuft
- keine kritischen Source-/Quality-Blocker im freigegebenen Scope verbleiben
- Release-, Ops- und Pilot-Runbook regelmäßig durchlaufen werden

## Empfehlung heute

Interne Position fuer den aktuellen Design-Partner-Scope:

- Das System ist live sichtbar und technisch belastbarer als zuvor.
- Der Produktkern ist wieder benutzbar.
- Der Pilotvertrag soll jetzt bewusst als `h7-first` gefuehrt werden.
- Externe operative Empfehlungen bleiben gesperrt, bis mindestens ein Day-one-Pilot-Scope fachlich auf `GO` steht.
