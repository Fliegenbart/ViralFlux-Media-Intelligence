# Live Release Evidence 2026-04-12

## Zweck

Dieses Dokument hält den nachweisbaren Live-Stand des Systems vom 12. April 2026 fest.

Es ist bewusst knapp und prüfbar gehalten, damit Repo, Deploy und Live-System dieselbe Geschichte erzählen.

## Release-Identität

- Datum: 2026-04-12
- Branch: `main`
- Live-Commit: `673d6d8fc7c9cec943ab7b649f859a3f1b21ef43`
- Deployment-Host: `fluxengine.labpulse.ai`
- Frontend-Bundle: `/static/js/main.af934dd9.js`
- Frontend-CSS: `/static/css/main.952bcd57.css`

## Was live verifiziert wurde

### Infrastruktur

- `GET /health/live` → `200`
- `GET /health/ready` → `200`

### Auth und Kernpfad

- Release-Smoke lief auf dem Deploy-Host grün
- `POST /api/auth/login` → `200`
- `GET /api/v1/forecast/regional/predict?virus_typ=Influenza%20A&brand=gelo&horizon_days=7` → `200`
- `GET /api/v1/forecast/regional/media-allocation?virus_typ=Influenza%20A&brand=gelo&horizon_days=7&weekly_budget_eur=50000.0` → `200`
- `GET /api/v1/forecast/regional/campaign-recommendations?virus_typ=Influenza%20A&brand=gelo&horizon_days=7&weekly_budget_eur=50000.0&top_n=3` → `200`

### Öffentliche API-Härtung

- `GET /api/v1/public/risk?virus=not-a-virus&plz=abc` → `422`
- Fehlermeldung: `{"detail":"Unsupported virus"}`

### Sichtbare UI-Änderung

Das Live-Bundle enthält den neuen Login-Text:

- `Operational Access`

Der frühere Pilot-Text `Pilot-Scope` ist damit nicht mehr der sichtbare Login-Kicker.

## Was behoben wurde, um diesen Release live zu bekommen

Der vorherige Deploy-Versuch wurde nicht durch den Fachcode blockiert, sondern durch einen veralteten Release-Smoke-Test.

Das Problem war:

- die regionalen Endpoints verlangen inzwischen explizit `brand`
- das alte Smoke-Skript fragte diese Endpoints noch ohne `brand` ab
- dadurch entstanden `422` und der Deploy rollte korrekt zurück

Behoben wurde das in:

- [backend/scripts/smoke_test_release.py](../backend/scripts/smoke_test_release.py)
- [backend/app/tests/test_smoke_test_release.py](../backend/app/tests/test_smoke_test_release.py)

## Offene Grenzen

Dieser Release beweist einen sauberen Live-Kernpfad.

Er beweist **nicht** automatisch:

- dass alle internen Pilot-/Brand-Altlasten im Repo entfernt sind
- dass die Outcome-/Truth-Schicht kausal validiert ist
- dass jede interne Fachnotiz bereits käuferreif formuliert ist

## Empfohlene Anschlussarbeit

1. Käuferdoku weiter verdichten und interne Notizen aus dem Primärpfad drängen
2. verbleibende brand-spezifische Admin- und Datenpfade bereinigen
3. diesen Nachweis bei jedem produktionsrelevanten Release fortschreiben
