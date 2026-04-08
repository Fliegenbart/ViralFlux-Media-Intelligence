# Virus-Radar Hero Mockup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den oberen Bereich von `Virus-Radar` so umbauen, dass er die Klarheit des Hero-Mockups übernimmt: dominante Wochenaussage, große Forecast-Kurve, klare CTA-Hierarchie.

**Architecture:** Die Datenanbindung bleibt bestehen. Wir bauen den Hero in `VirusRadarWorkspace` strukturell neu, ergänzen kleine Hilfsfunktionen für Headline/Subline/Peak-Logik und geben `ForecastChart` eine klar definierte Hero-Variante, ohne bestehende Verwendungen zu brechen.

**Tech Stack:** React, TypeScript, CSS, Jest, React Testing Library, Recharts

---

### Task 1: Neue Hero-Hierarchie absichern

**Files:**
- Modify: `frontend/src/components/cockpit/VirusRadarWorkspace.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it('renders a hero-style weekly signal with peak framing', () => {
  render(
    <VirusRadarWorkspace
      virus="Influenza A"
      onVirusChange={noop}
      horizonDays={7}
      nowData={{
        view: {
          generatedAt: '2026-04-04T08:00:00Z',
          heroRecommendation: {
            direction: 'Aktivieren',
            region: 'Berlin',
            whyNow: 'Berlin zeigt die stärkste Dynamik für GELO in dieser Woche.',
          },
          focusRegion: {
            code: 'BE',
            name: 'Berlin',
            recommendationId: 'rec-1',
          },
          reasons: ['Berlin führt Forecast, Signal und Reife zusammen.'],
          risks: ['Kundendaten bleiben noch im Aufbau.'],
          summary: 'Berlin ist diese Woche der klarste Fokusfall.',
        },
        forecast: {
          predictions: [
            {
              bundesland: 'BE',
              bundesland_name: 'Berlin',
              event_probability_calibrated: 0.81,
              trend: 'steigend',
              change_pct: 12.4,
              decision_rank: 1,
            },
          ],
        },
        workspaceStatus: {
          data_freshness: 'Aktuell',
          summary: 'Die wichtigsten Daten sind aktuell genug für die Wochenentscheidung.',
          blocker_count: 1,
          blockers: ['Eine Freigabe ist noch offen.'],
          open_blockers: '1 offen',
        },
        focusRegionBacktest: {
          timeline: [
            {
              bundesland: 'BE',
              as_of_date: '2026-04-03',
              target_date: '2026-04-03',
              horizon_days: 7,
              current_known_incidence: 24,
              expected_target_incidence: 24,
            },
            {
              bundesland: 'BE',
              as_of_date: '2026-04-04',
              target_date: '2026-04-08',
              horizon_days: 7,
              current_known_incidence: 31,
              expected_target_incidence: 58,
              prediction_interval_lower: 49,
              prediction_interval_upper: 64,
            },
          ],
        },
      } as any}
      regionsData={{ regionsView: { map: { regions: {}, top_regions: [], activation_suggestions: [] } } } as any}
      campaignsData={{ campaignsView: { summary: { publishable_cards: 1, active_cards: 2 }, cards: [] } } as any}
      evidenceData={{ evidence: { truth_gate: { passed: true, state: 'Aktiv', message: 'Evidenz ist sichtbar.' } } } as any}
      onOpenRecommendation={noop}
      onOpenRegions={noop}
      onOpenCampaigns={noop}
      onOpenEvidence={noop}
    />,
  );

  expect(screen.getByText('Live-Signal · Influenza A')).toBeInTheDocument();
  expect(screen.getByText('Berlin läuft heiß.')).toBeInTheDocument();
  expect(screen.getByText('Peak in 4 Tagen.')).toBeInTheDocument();
  expect(screen.getByText('Forecast · 7 Tage')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npm test -- --watch=false src/components/cockpit/VirusRadarWorkspace.test.tsx`
Expected: FAIL because the current hero still renders the old terminal-style structure.

- [ ] **Step 3: Write minimal implementation**

```tsx
const heroNarrative = buildHeroNarrative({
  virus,
  focusRegionName: topPrediction?.bundesland_name || focusRegion?.name,
  generatedAt: nowData.view.generatedAt,
  timeline: nowData.focusRegionBacktest?.timeline || [],
  probability: topPrediction?.event_probability_calibrated,
  recommendationDirection: heroRecommendation?.direction,
});

<div className="virus-radar-hero__eyebrow">
  <span className="virus-radar-hero__pulse" />
  {heroNarrative.kicker}
</div>
<h2 className="virus-radar-hero__headline">
  <span>{heroNarrative.headlinePrimary}</span>
  <span>{heroNarrative.headlineSecondary}</span>
</h2>
```
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && CI=true npm test -- --watch=false src/components/cockpit/VirusRadarWorkspace.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cockpit/VirusRadarWorkspace.test.tsx frontend/src/components/cockpit/VirusRadarWorkspace.tsx
git commit -m "test: lock virus radar hero hierarchy"
```

### Task 2: Hero-Struktur und Peak-Logik umsetzen

**Files:**
- Modify: `frontend/src/components/cockpit/VirusRadarWorkspace.tsx`

- [ ] **Step 1: Write the failing test**

Use the test from Task 1 as the red test for headline, peak framing, and hero legend.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npm test -- --watch=false src/components/cockpit/VirusRadarWorkspace.test.tsx`
Expected: FAIL on missing live-signal headline and hero legend.

- [ ] **Step 3: Write minimal implementation**

```tsx
type HeroNarrative = {
  kicker: string;
  headlinePrimary: string;
  headlineSecondary: string;
  summary: string;
  peakLabel: string | null;
  peakDateLabel: string | null;
};

function buildHeroNarrative(...) {
  const peakPoint = timeline
    .filter((point) => point.target_date >= referenceDate)
    .sort((left, right) => (right.expected_target_incidence || 0) - (left.expected_target_incidence || 0))[0];
  ...
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && CI=true npm test -- --watch=false src/components/cockpit/VirusRadarWorkspace.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cockpit/VirusRadarWorkspace.tsx frontend/src/components/cockpit/VirusRadarWorkspace.test.tsx
git commit -m "feat: rebuild virus radar hero narrative"
```

### Task 3: Hero-Chart optisch an das Mockup anpassen

**Files:**
- Modify: `frontend/src/components/cockpit/ForecastChart.tsx`
- Modify: `frontend/src/styles/pages/virus-radar.css`

- [ ] **Step 1: Write the failing test**

Add a focused render expectation in `VirusRadarWorkspace.test.tsx` that checks for the hero legend labels:

```tsx
expect(screen.getByText('Ist · 28 Tage')).toBeInTheDocument();
expect(screen.getByText('Forecast · 7 Tage')).toBeInTheDocument();
expect(screen.getByText(/Konfidenz/i)).toBeInTheDocument();
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npm test -- --watch=false src/components/cockpit/VirusRadarWorkspace.test.tsx`
Expected: FAIL because the legend is not yet rendered in the hero.

- [ ] **Step 3: Write minimal implementation**

```tsx
<div className="virus-radar-hero-chart-card">
  <div className="virus-radar-hero-chart-card__meta">...</div>
  <ForecastChart
    timeline={nowData.focusRegionBacktest?.timeline || []}
    regionName={chartRegionName}
    className="virus-radar-hero-chart"
    variant={heroNarrative.tone}
  />
</div>
```

```css
.virus-radar-hero-chart-card {
  padding: 28px 32px 18px;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(15,28,26,.04), 0 12px 40px rgba(15,28,26,.06);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && CI=true npm test -- --watch=false src/components/cockpit/VirusRadarWorkspace.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cockpit/ForecastChart.tsx frontend/src/styles/pages/virus-radar.css frontend/src/components/cockpit/VirusRadarWorkspace.tsx frontend/src/components/cockpit/VirusRadarWorkspace.test.tsx
git commit -m "feat: style virus radar hero chart like weekly signal mockup"
```

### Task 4: Rest der Seite unterordnen und Regression prüfen

**Files:**
- Modify: `frontend/src/components/cockpit/VirusRadarWorkspace.tsx`
- Modify: `frontend/src/styles/pages/virus-radar.css`

- [ ] **Step 1: Write the failing test**

Add an assertion that the old hierarchy marker is no longer the primary above-the-fold copy:

```tsx
expect(screen.queryByText('Entscheidung diese Woche')).not.toBeInTheDocument();
expect(screen.getByText('Radar-Tape')).toBeInTheDocument();
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npm test -- --watch=false src/components/cockpit/VirusRadarWorkspace.test.tsx`
Expected: FAIL because the old label still exists.

- [ ] **Step 3: Write minimal implementation**

```tsx
<section className="virus-radar-strip-shell" aria-label="Schnellstatus">
  ...
</section>
```

```css
.virus-radar-strip-shell {
  gap: 8px;
}

.virus-radar-core-grid {
  margin-top: 4px;
}
```

- [ ] **Step 4: Run verification**

Run:
- `cd frontend && CI=true npm test -- --watch=false src/components/cockpit/VirusRadarWorkspace.test.tsx`
- `cd frontend && npx tsc --noEmit`

Expected:
- Jest: PASS
- TypeScript: exit code 0

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/cockpit/VirusRadarWorkspace.tsx frontend/src/styles/pages/virus-radar.css frontend/src/components/cockpit/VirusRadarWorkspace.test.tsx
git commit -m "refactor: subordinate virus radar detail panels"
```
