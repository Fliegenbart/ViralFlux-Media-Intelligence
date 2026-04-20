# ViralFlux Media Intelligence

ViralFlux ist eine Plattform für **regionale Virus-Frühwarnung** und daraus
abgeleitete **operative Media-Entscheidungen**. Ziel: früh erkennen **wo**
eine Welle hochkommt, abschätzen **wie** sie sich entwickelt, und daraus
ableiten **welche Bundesländer zuerst aktiviert werden sollten** — eine
Entscheidung pro Woche, mit Begründung und Unsicherheit.

Live: [fluxengine.labpulse.ai/cockpit](https://fluxengine.labpulse.ai/cockpit)
(password-gated, Pilot-Partner-Zugang).

---

## Das Cockpit

Eine einzige user-facing Surface (`/cockpit`), umgebaut im April 2026 von
einem 4-Tab-Drawer-Layout auf eine **Broadside-One-Page-Scrolling-Komposition**
mit fünf stacked Sektionen — alles auf einen Scroll sichtbar, keine
Click-to-Reveal. Design-Haltung: *Labormessgerät, kein SaaS-Dashboard* —
Supreme (Display) + General Sans (Body) + JetBrains Mono (Ticks/Coord),
5-Farben-Palette strikt, Haarlinien statt Boxen, Papier-Feed-Übergänge.

### ChronoBar (sticky, schwarz)

Ganz oben über die volle Breite. Tickendes Epoch-Counter (1 Hz),
KW-Ticker mit aktueller Woche in Signal-Terracotta, Countdown bis zum
nächsten Forecast-Run (Montag 08:00), Client-Stempel, Link zum Data
Office. Wie ein wissenschaftliches Instrument das sich selbst in der
Zeit verankert.

### § I Entscheidung der Woche

Die eine Empfehlung als ein Satz: *„Verschiebe €X aus Bayern nach
Brandenburg — die bayerische Welle plateaut, die brandenburgische zieht
an."* Transfer-Flow-Visualisierung (From → To mit EUR-Label),
Begründungs-Block, und rechts die **Vernier-Konfidenz-Skala** —
mechanische Skala mit Haarlinien-Ticks und Nadel bei dem exakten
Kalibrations-Wert (keine Progress-Bar, kein Pie-Chart).

### § II Wellen-Atlas (3D)

Full-bleed schwarzer Block mit den 16 Bundesländern als Hex-Prism-Türme
auf einem stilisierten Deutschland-Raster. Turmhöhe = erwarteter Anstieg
über den Forecast-Horizont, Farbe = Richtung (Terracotta = Riser, Slate
= Faller). Top-3-Riser bekommen Spotlights, Pulse-Rings am Sockel und
Floating-Billboard-Labels im 3D-Raum. Ein **Transfer-Beam** im Bogen
verbindet den From-Turm und den To-Turm der aktiven Empfehlung — der
narrative Brücken-Moment zwischen § I und § II. HUD-Overlays (Corner-
Brackets, Projektions-Info, LAT/LON/ALT-Readout, Top-Riser-Ticker)
framen das Ganze wie eine Ground-Station-Ansicht.

### § III Forecast-Zeitreise

Kein Fan-Chart — ein **dreikanaliger Labor-Streifenschreiber**. Papier
feedet von links (Vergangenheit) nach rechts (Zukunft), mit Papier-
Tonwechsel und 1 px Ink-Naht am HEUTE-Moment:

- **CH·01 ED · Notaufnahmen** — Lead-Sensor (tagesaktuell)
- **CH·02 SURVSTAT · Meldewesen** — Referenz-Pegel (verzögert)
- **CH·03 Modell · Q-Quantile** — Forecast-Kegel mit Index-Normalisierung
  (HEUTE = 100), Cone-of-Uncertainty-Expansion

Oberhalb der Kanäle eine **Chronologie-Timeline** mit vier Event-Dots
(ED-Peak · SURVSTAT-Peak · HEUTE · Q50-Horizont) als narrative Vor-
Lesung. Zwischen Kanal 2 und HEUTE markiert eine gestreifte Hatching-
Zone die **Lead-Time-Lücke** — ED-Spur endet später als SURVSTAT-Spur,
die Lücke ist der operationale Vorsprung gegenüber dem Meldewesen.

Darunter:

- **Lead-Time-Hero-Monument** (Supreme Thin, 160 px): der Median-Lead
  aus dem Regional-Backtest über 68 Walk-forward-Folds
- **Ephemeris-Tabelle** zweispaltig (Observed · bis HEUTE /
  Forecast · Modell) mit Peak-KWs, Q50-Horizont, Coverage Q80/Q95
- **Modell-Gütenachweis** als dark Monument-Row: PR-AUC, Precision @
  Top-3, Median Lead-Zeit, plus kompakter Hit-Barcode-Streifen über
  alle Walk-forward-Wochen

Zwei Controls direkt über dem Chart:

- **Virus-Switcher** — 3-Chip-Row (Influenza A / Influenza B / RSV A)
- **Vintage-Spuren-Toggle** — überlagert historische Forecast-Runs als
  gestrichelte Slate-Spuren in CH·03, jeder Run auf seinen eigenen
  Anchor normalisiert und mit Run-Datum als Tick beschriftet. Proof-by-
  Overlay: *was hat das Modell vor 3/6/10 Wochen für heute vorhergesagt*

### § IV Wirkung & Feedback-Loop

Honest-by-default Outcome-Rückblick: drei Monument-Kacheln *Empfehlungen
ausgegeben / Real umgesetzt / Mit Outcome verknüpft*, alle Werte aus
der Outcome-Pipeline (oder Dash wenn nicht angebunden), darunter ein
Impact-Log mit den letzten Shift-Empfehlungen und ihrem Umsetzungs-
Status. Wo echte Sales-/Plan-Daten fehlen steht ein italic-Hinweis,
nie ein erfundener Wert.

### § V Backtest

Walk-forward-Validation über die Pilot-Fensterperiode. Dark Monument-
Head mit PR-AUC Gesamt, Precision @ Top-3, Median Lead-Zeit — alle drei
jeweils gegen eine Persistenz-Baseline und als *N× besser* ausgewiesen.
Virus-Switcher für Flu A / Flu B / RSV A, per-Bundesland-Roster nach
PR-AUC absteigend mit Lead-Days pro BL, und der **Hit-Barcode**: jede
Woche ein Balken, Terracotta = Top-3-Traf-Welle, Slate = Miss, Grau =
keine Ground Truth.

---

## Data Office (`/cockpit/data`)

Separate Route für die Datenverwaltung: Truth-Coverage-Heatmap pro
Bundesland (welche BL haben wie viele Wochen Truth-Daten), CSV-Upload
mit Validate-First-Workflow (erst prüfen, dann committen) plus
Drag-and-Drop, Import-Batch-Historie mit Klick-Drilldown auf Issues,
und die M2M-API-Integration-Dokumentation inklusive Live-curl-Beispiel
für den produktiven Weg: GELO-BI → `POST /api/v1/media/outcomes/ingest`
mit strukturiertem Observations-JSON und langlebigem API-Key.

Read-only Ansichten sind mit dem Cockpit-Gate erreichbar (gleiches
Passwort wie `/cockpit`). Der eigentliche Commit eines CSV-Imports ist
admin-only — honest Hinweis im UI wenn ein Gate-Nutzer den Commit-
Button drückt.

---

## Modell-Gütenachweis (auf dem aktuellen Regional-Forecast)

Für den Pilot-Scope (Influenza A, horizon=7, Walk-forward über 68
Wochen) zeigt der Backend-Endpoint `/api/v1/media/cockpit/backtest`
aktuell:

| Metrik                  | Modell | Persistenz-Baseline | Uplift      |
|-------------------------|--------|---------------------|-------------|
| PR-AUC                  | 0.746  | 0.292               | **2.6× besser** |
| Precision @ Top-3       | 77.5 % | 68.5 %              | **+9.0 pp** |
| Median Lead-Zeit        | +5 d   | —                   | strukturell |

Die Zahlen stehen im Modell-Gütenachweis-Panel unter § III *und* in § V
Backtest — beide Sektionen lesen denselben Endpoint. Das Legacy-
`forecast_accuracy_log`-System (SARS-CoV-2-basiert, nicht Pilot-Teil)
ist in der UI nicht mehr sichtbar; es taugte semantisch nicht zum
aktuellen Regional-Ranking-Modell.

---

## Vintage-Persistenz (Option C + D)

Damit die „Forecast-Zeitreise"-Story ab sofort wachsende Historie zeigt,
persistiert die Plattform seit April 2026 die vollen Cockpit-Timelines
als Audit-Events:

- **Action**: `COCKPIT_TIMELINE_SNAPSHOT`
- **Trigger**: der erste `GET /cockpit/snapshot`-Call pro (Virus, Horizon,
  Tag) schreibt idempotent einen Eintrag in `audit_logs` mit der vollen
  Timeline-Payload (observed, edActivity, q10/q50/q90 pro Tag)
- **Backfill** (`backend/scripts/backfill_cockpit_timeline_snapshots.py`):
  migrierte die historischen `ml_forecasts`-Runs in dasselbe Format,
  single source of truth für den Vintage-Endpoint

Der neue Endpoint `/api/v1/media/cockpit/forecast-vintage` liest aus
`audit_logs` bevorzugt, fällt auf `ml_forecasts` zurück und liefert dem
Frontend die Vintage-Runs für den Overlay in § III.

---

## Datenquellen

Je nach Signalpfad fließen unter anderem ein:
- SURVSTAT (RKI-Meldewesen, wöchentlich, Referenz-Pegel)
- Notaufnahme-Syndromsurveillance (AKTIN, tagesaktuell, Lead-Sensor)
- AMELAG / Abwasser
- GrippeWeb
- Google Trends
- Wetter, Ferien, Kalendereffekte
- BfArM-Kontext für Marketing-/Supply-Signale

Die Plattform trennt bewusst drei Ebenen: *epidemiologische Signale*,
*Datenqualität und Frische*, *Business-/Freigabe-Logik*. Der Snapshot-
Builder (`backend/app/services/media/cockpit/snapshot_builder.py`)
orchestriert alle drei und liefert dem Frontend ein einziges Payload,
bei dem jeder Wert entweder eine Quelle hat oder explizit `null` ist.

---

## Mathematisches Vorgehen

### 1. Point-in-time Feature-Bau

Pro Bundesland und Zeitpunkt ein sauberer Feature-Satz aus Niveau,
Trend, Lag, Quellabdeckung, Frische, Wetter und Kalender — mit
strikter Point-in-Time-Semantik, damit Walk-forward-Backtests keine
Future-Leakage-Fehler haben.

### 2. Punktprognose + Unsicherheit

XGBoost-Stack pro (Virus, Region, Horizon) liefert `y_hat(t+h)` und
Q10/Q50/Q90-Bänder. Direct-Ansatz (ein Modell pro Horizont), nicht
recursive. Die Forecast-Trajektorie T+1 … T+h wird im Anschluss per
Cone-of-Uncertainty-Expansion aus dem End-Punkt-Forecast rekonstruiert
(sqrt-wachsende Unsicherheit mit Offset).

### 3. Ereigniswahrscheinlichkeit

Trennung von Punktprognose und Entscheidungssignal:

- **Regional / kalibriert**: gelerntes Exceedance-Modell mit isotonic-
  oder Platt-Kalibrierung → echte `event_probability`
- **Fallback**: wenn kein belastbares Wahrscheinlichkeitsmodell da ist,
  gibt die Plattform **keine** Wahrscheinlichkeit aus. Stattdessen ein
  heuristischer `event_signal_score` mit klarem Label *heuristisch*.

Das UI unterscheidet die beiden semantisch: `78 %` vs. `0.78` (Index).
Nie stille Verwechslung.

### 4. Index-Normalisierung in der Darstellung

Wo das Cockpit Verläufe zeigt (Strip-Chart, Atlas-Höhe, Ranking-Deltas),
wird intern normalisiert auf HEUTE = 100. Ein `110` bedeutet +10 %
relativ zum letzten beobachteten Punkt. Das löst die Skalen-
Inkompatibilität zwischen SURVSTAT-Meldewesen (~500/100k) und Modell-
Q50 (~1200 abs) — beide Serien treffen sich am HEUTE-Anchor auf 100.

### 5. Regionale Priorisierung

Die Entscheidungs-Engine kombiniert Wahrscheinlichkeit, Trendrichtung,
Datenfrische, Quellabdeckung, Cross-Source-Agreement, Unsicherheit und
Business-/Freigabe-Regeln zu Decision-Labels:

- `Activate` — klarer Anstieg, kalibriert, Media-Plan anbindbar
- `Prepare` — starker Trend, aber Unsicherheit zu hoch für Activation
- `Watch` — Signal zu schwach oder zu eng im Ranking

---

## Wie belastbar ist das?

Die Prognosen sind **nicht imaginiert**, aber auch **keine Fakten aus
der Zukunft**. Trennung strikt:

- **Vergangenheit** — echte beobachtete Werte (SURVSTAT, ED)
- **Forecast** — modellierte Erwartung mit ausgewiesener Unsicherheit
- **Probability Stack** — getrennte Wahrscheinlichkeits-/Reliability-Ebene
- **Decision Layer** — eigene operative Freigabe-/Priorisierungslogik

Das System hält sich an vier Regeln:

1. Vergangenheit und Prognose bleiben sichtbar getrennt (der HEUTE-
   Paper-Feed-Übergang ist genau dafür da)
2. Kein stiller Future-Leakage-Pfad (Walk-forward-Training + Point-in-
   Time-Features)
3. Epidemiologischer Forecast und Business-Entscheidung werden nicht
   verwechselt (eigene Gates, eigene Labels)
4. Wo keine belastbare Zahl vorhanden ist, steht ein `—` mit italic-
   Note — nie eine erfundene Zahl

---

## Technische Kernpfade

Frontend:
- `frontend/src/pages/cockpit/broadside/` — die fünf Sektionen + Shell
- `frontend/src/pages/cockpit/data/` — Data Office (Upload, Batches, Coverage)
- `frontend/src/styles/peix-instr.css` — Instrumentation-Design-System
- `frontend/src/styles/peix-data.css` — Data-Office-Design-System
- `frontend/src/pages/cockpit/useCockpitSnapshot.ts` / `useBacktest.ts` /
  `useForecastVintage.ts` / `useImpact.ts` — SWR-Hooks für die Backend-APIs

Backend:
- `backend/app/api/media_routes_cockpit_snapshot.py` — Snapshot + Gate
- `backend/app/api/media_routes_cockpit_backtest.py` — Modell-Gütenachweis
- `backend/app/api/media_routes_cockpit_forecast_vintage.py` — Vintage-Runs
- `backend/app/api/media_routes_cockpit_impact.py` — Outcome-Loop
- `backend/app/api/media_routes_outcomes.py` — Data-Office-APIs
- `backend/app/services/media/cockpit/` — Snapshot-Builder, Freshness,
  Impact, Backtest-Builder, Timeline-Snapshot-Persistenz
- `backend/app/services/ml/` — Regional-Forecast, XGBoost-Stack,
  Walk-forward-Backtest, Kalibrierung
- `backend/app/services/data_ingest/` — Quellen-Importer
- `backend/scripts/backfill_cockpit_timeline_snapshots.py` — einmaliges
  Backfill-Script für die historische Vintage-Migration

---

## Tech-Stack

- Frontend: React 18, TypeScript, SWR, three.js (Atlas), Pure-SVG (Strip-Chart)
- Backend: FastAPI, Pandas, scikit-learn, XGBoost, Prophet
- Datenbank: PostgreSQL
- Scheduling: Celery Beat + Celery Worker
- Deployment: Docker Compose, Nginx-Proxy

---

## Repo-Hygiene

Code, Dokumentation, stabile Referenzartefakte gehören hierher — aber
keine generierten Laufzeit-Ausgaben. Explizit ausgeschlossen:

- `output/`
- `data/raw/` und `data/processed/`
- `demo-data/` und `Test-Daten/`
- lokale Benchmarks, Screenshots, Reports

Wenn solche Artefakte temporär entstehen, bleiben sie lokal.

---

## Einstieg

- [QUICKSTART.md](QUICKSTART.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/OPERATORS_GUIDE.md](docs/OPERATORS_GUIDE.md)
- [DEPLOY.md](DEPLOY.md)
