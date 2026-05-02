# Changelog

## Unreleased

### Experimental Tri-Layer Evidence Fusion

- Added documentation for the research-only `/cockpit/tri-layer` sub-route and its dedicated backend endpoints.
- Documented that Early Warning is not Budget Approval, Sales Relevance is not inferred from epidemiology alone, and Budget Permission remains blocked/shadow-only unless Sales Calibration and Budget Isolation pass.
- Clarified that this module does not alter live allocation or campaign recommendation outputs and makes no validation, ROI or production-readiness claim.

## 2026-04-30 — v1.2a Operational Readiness accepted

### Layered operational readiness

- `v1.2a-layered-operational-readiness` marks the deployed operational baseline.
- Live commit: `168900a60955dac70ee17dec7d9c484953903d54`.
- `/health/ready` now means operationally deployable and able to serve the production core scope.
- Science and forecast warnings remain visible, but no longer block the top-level readiness status by themselves.
- Budget isolation remains explicit: green readiness does not change `can_change_budget`, `budget_can_change`, MediaSpendingTruth gates or domain `global_status`.

### Accepted live state

- Operational: `healthy`
- Science: `review`
- Forecast Monitoring: `warning`
- Budget: `diagnostic_only`

### Known warnings at acceptance

- Influenza A h7: ECE/calibration review required.
- SARS-CoV-2 and RSV A: forecast monitoring drift warnings remain visible.
- AMELAG/evidence remains diagnostic-only and not budget-effective.

### v1.3 research backtest kickoff

- Live virus wave backtests were run in `historical_cutoff` mode.
- Canonical scope report covers `Influenza A+B`, `RSV` and `SARS-CoV-2`.
- Legacy acceptance scope report covers `Influenza A`, `Influenza B`, `RSV A` and `SARS-CoV-2`.
- Both reports remain research-only and preserve `budget_can_change=false`.

## 2026-04-17 — Cockpit-Pivot und Gallery-Refresh

### Cockpit als einzige user-facing Surface

- `/cockpit` ist seit diesem Stand die einzige live gerenderte Seite
- alle bisherigen Routes (`/login`, `/welcome`, `/virus-radar`, `/jetzt`, `/zeitgraph`, `/regionen`, `/kampagnen`, `/evidenz`, `/dashboard`, `/entscheidung`, `/lagebild`, `/pilot`, `/bericht`, `/empfehlungen`, `/validierung`, `/backtest`) leiten client-seitig nach `/cockpit` um — alte Bookmarks 404en nicht
- shared-password Gate loest den bisherigen OAuth-Login ab: `POST /api/v1/media/cockpit/unlock` validiert das Passwort aus `COCKPIT_ACCESS_PASSWORD` und setzt ein HMAC-signiertes Cookie (30 Tage). Drei Zugangsarten gleichzeitig: Session-Cookie, `X-API-Key` (M2M), `cockpit_unlock`-Cookie (Gate)
- `frontend/public/robots.txt` mit `Disallow: /` verhindert Indexierung

### Gallery-Design-Refresh der vier Tabs

- Atlas-Aesthetik als gemeinsames Design-System extrahiert: warm-schwarze Gallery-Stage, editorial Split-Komposition, eine Terracotta-Akzentfarbe, drei Schriften mit klaren Rollen (Fraunces / JetBrains Mono / Inter Tight), Roster-Pattern, Caption-Strip
- neue shared Components `GalleryHero.tsx`, `RosterList.tsx`, neues Stylesheet `peix-gallery.css`
- Decision / Timeline / Impact komplett neu gezogen — weniger, groessere Cards, deutlich mehr Weissraum
- warm-tint / cool-tint / ink-Gradienten entfernt zugunsten ruhiger paper-quiet-Cards unter dem dunklen Hero

### Atlas 3D-Map Polish

- "Zuppel"-Artefakt behoben: breath-Animation durch signed sin² easing (14 s Periode, geschwindigkeit faellt smooth gegen 0 an den Umkehrpunkten)
- IntersectionObserver pausiert rAF wenn Canvas offscreen
- resize-Handler gehaertet (3 px Delta-Gate, setPixelRatio re-assert, setSize ohne CSS-Write)
- `contain: layout size` auf `.peix-sculpture__canvas` isoliert das Canvas von Parent-Layout-Jitter

## Frontend-Modernisierung (Historie)

Der aktuelle Frontend-Stand ist nicht mehr nur ein klassisches Dashboard, sondern stärker als Operator-Oberfläche gebaut.

Zuletzt wurden unter anderem verbessert:

- klarere Operator-Entscheidungsoberflächen im Cockpit
- ehrlichere Bundesland-Semantik in Karten und Regionenlisten
- sauberere Trennung von Forecast, Truth, Unsicherheit und Ranking-Signalen
- Dark-Mode-Architektur über semantische Tokens statt fragile Überschreibungen
- Accessibility für Tastatur, Fokusführung und Screenreader
- Responsive Verhalten für reale Laptop-Fenster
- konsistentere Sprache für Wahrscheinlichkeiten, Scores und Evidenzlücken
