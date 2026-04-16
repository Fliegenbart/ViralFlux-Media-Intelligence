/**
 * Curated demo snapshot for GELO pilot.
 *
 * Mirrors the structure of the future GET /api/cockpit/snapshot
 * endpoint; the backend snapshot_service.py will replace this fixture
 * once wired up.
 *
 * Numbers are *illustrative* — drawn from the April-2026 GELO test
 * scenario (RSV/Reizhusten). Replace via demo_snapshot.py in backend.
 */
import type { CockpitSnapshot, RegionForecast } from './types';

const BL: RegionForecast[] = [
  { code: 'SH', name: 'Schleswig-Holstein',      delta7d:  0.12, pRising: 0.62, forecast: { q10: 102, q50: 112, q90: 122 }, drivers: ['Abwasser +14%', 'Google-Trends Husten 1.4×'], currentSpendEur:  85000, recommendedShiftEur: -10000 },
  { code: 'HH', name: 'Hamburg',                 delta7d:  0.04, pRising: 0.48, forecast: { q10:  96, q50: 104, q90: 112 }, drivers: ['stabil', 'leicht fallend Trends'], currentSpendEur:  70000, recommendedShiftEur: -15000 },
  { code: 'NI', name: 'Niedersachsen',           delta7d:  0.09, pRising: 0.55, forecast: { q10:  98, q50: 109, q90: 120 }, drivers: ['Wetter kälter', 'Schulbeginn nach Ferien'], currentSpendEur: 180000, recommendedShiftEur: 0 },
  { code: 'HB', name: 'Bremen',                  delta7d:  0.18, pRising: 0.70, forecast: { q10: 104, q50: 118, q90: 132 }, drivers: ['Abwasser +22%', 'Notaufnahme +9%'], currentSpendEur:  30000, recommendedShiftEur: 15000 },
  { code: 'NW', name: 'Nordrhein-Westfalen',     delta7d: -0.08, pRising: 0.28, forecast: { q10:  84, q50:  92, q90:  99 }, drivers: ['Welle erreicht Plateau', 'GT fällt 18%'], currentSpendEur: 420000, recommendedShiftEur: -240000, primary: true as unknown as number } as unknown as RegionForecast,
  { code: 'HE', name: 'Hessen',                  delta7d: -0.06, pRising: 0.35, forecast: { q10:  88, q50:  94, q90: 101 }, drivers: ['Abwasser stabil', 'Trends −12%'], currentSpendEur:  95000, recommendedShiftEur: -80000 },
  { code: 'RP', name: 'Rheinland-Pfalz',         delta7d:  0.10, pRising: 0.58, forecast: { q10: 100, q50: 110, q90: 121 }, drivers: ['Wetterfront Mo', 'GT +28%'], currentSpendEur:  55000, recommendedShiftEur: 10000 },
  { code: 'SL', name: 'Saarland',                delta7d:  0.02, pRising: 0.44, forecast: { q10:  94, q50: 102, q90: 110 }, drivers: ['kleine Stichprobe', 'Unsicher'], currentSpendEur:  20000, recommendedShiftEur: 0 },
  { code: 'BW', name: 'Baden-Württemberg',       delta7d: -0.15, pRising: 0.22, forecast: { q10:  78, q50:  85, q90:  93 }, drivers: ['Welle rollt ab', 'Abwasser −24%'], currentSpendEur: 160000, recommendedShiftEur: -60000 },
  { code: 'BY', name: 'Bayern',                  delta7d:  0.26, pRising: 0.78, forecast: { q10: 112, q50: 126, q90: 141 }, drivers: ['Abwasser +40%', 'Notaufnahme Atemwege +18%', 'Wetter: Kälteeinbruch Mo'], currentSpendEur: 195000, recommendedShiftEur: 160000 },
  { code: 'BE', name: 'Berlin',                  delta7d:  0.34, pRising: 0.82, forecast: { q10: 118, q50: 134, q90: 151 }, drivers: ['GT „Reizhusten\" 2.1×', 'Abwasser +44%'], currentSpendEur: 120000, recommendedShiftEur: 80000 },
  { code: 'BB', name: 'Brandenburg',             delta7d:  0.29, pRising: 0.74, forecast: { q10: 114, q50: 129, q90: 145 }, drivers: ['Abwasser-Cluster Potsdam', 'Trends +62%'], currentSpendEur:  65000, recommendedShiftEur: 45000 },
  { code: 'MV', name: 'Mecklenburg-Vorpommern',  delta7d:  0.21, pRising: 0.68, forecast: { q10: 108, q50: 121, q90: 136 }, drivers: ['Schulbeginn', 'Wetterfront'], currentSpendEur:  45000, recommendedShiftEur: 40000 },
  { code: 'SN', name: 'Sachsen',                 delta7d:  0.31, pRising: 0.80, forecast: { q10: 116, q50: 131, q90: 148 }, drivers: ['Surveillance-Z +1.8', 'Abwasser +38%'], currentSpendEur: 100000, recommendedShiftEur: 60000 },
  { code: 'ST', name: 'Sachsen-Anhalt',          delta7d:  0.24, pRising: 0.71, forecast: { q10: 110, q50: 124, q90: 140 }, drivers: ['Cross-source konsistent', 'Trends 1.8×'], currentSpendEur:  75000, recommendedShiftEur: 80000 },
  { code: 'TH', name: 'Thüringen',               delta7d:  0.14, pRising: 0.60, forecast: { q10: 104, q50: 114, q90: 126 }, drivers: ['moderates Signal', 'verzögerter Nowcast'], currentSpendEur:  60000, recommendedShiftEur: 15000 },
];

// Build a 21-day timeline (-14..+7) for the dominant wave scenario (national aggregate).
const timeline = [] as CockpitSnapshot['timeline'];
for (let d = -14; d <= 7; d++) {
  const dateObj = new Date(2026, 3, 16 + d); // April 16, 2026 as anchor
  const iso = dateObj.toISOString().slice(0, 10);
  // observed past:
  const observed = d <= 0 ? 86 + d * 1.1 + Math.sin(d / 2) * 1.4 : null;
  // nowcast (last 14 days): slight uplift vs observed
  const nowcast = d <= 0 && d >= -14 ? (observed ?? 0) + Math.max(0, -d) * 0.35 : null;
  // forecast q50 accelerates after today
  const base = 96;
  const q50 = d < 0 ? base + d * 1.0 : base + d * 3.2;
  const width = 4 + Math.max(0, d) * 1.3;
  timeline.push({
    date: iso,
    observed,
    nowcast,
    q10: q50 - width,
    q50,
    q90: q50 + width,
    horizonDays: d,
  });
}

export const GELO_SNAPSHOT: CockpitSnapshot = {
  client: 'GELO',
  virusLabel: 'RSV / Reizhusten',
  isoWeek: 'KW 16 / 2026',
  generatedAt: '2026-04-16T09:12:00+02:00',
  totalSpendEur: 1_840_000,
  averageConfidence: 0.72,

  primaryRecommendation: {
    id: 'P1',
    fromCode: 'NW',
    toCode: 'BY',
    fromName: 'Nordrhein-Westfalen',
    toName: 'Bayern',
    amountEur: 240_000,
    confidence: 0.78,
    expectedReachUplift: 0.18,
    why: 'Abwasser-Signal in BY +40 %, GT „Husten\" 2.1× — gleichzeitig kühlt NW deutlich ab (−14 %).',
    primary: true,
  },

  secondaryRecommendations: [
    { id: 'S1', fromCode: 'HE', toCode: 'BE', fromName: 'Hessen',           toName: 'Berlin',                   amountEur:  80_000, confidence: 0.74, expectedReachUplift: 0.14, why: 'Abwasser +44 %, GT „Reizhusten\" 2.1×.' },
    { id: 'S2', fromCode: 'BW', toCode: 'SN', fromName: 'Baden-Württemberg', toName: 'Sachsen',                  amountEur:  60_000, confidence: 0.68, expectedReachUplift: 0.11, why: 'Surveillance-Z +1.8, Wetter: Temperatursturz 72 h.' },
    { id: 'S3', fromCode: 'HH', toCode: 'MV', fromName: 'Hamburg',           toName: 'Mecklenburg-Vorpommern',   amountEur:  45_000, confidence: 0.61, expectedReachUplift: 0.08, why: 'Notaufnahme Atemwege +22 %, Schulbeginn.' },
    { id: 'S4', fromCode: 'SL', toCode: 'BB', fromName: 'Saarland',          toName: 'Brandenburg',              amountEur:  25_000, confidence: 0.56, expectedReachUplift: 0.05, why: 'Abwasser-Cluster Potsdam, GT +62 %.' },
  ],

  regions: BL,
  timeline,

  sources: [
    { name: 'AMELAG Abwasser',       lastUpdate: '2026-04-08', latencyDays: 8, health: 'delayed', note: 'Publikationsrhythmus wöchentlich' },
    { name: 'Google Trends',          lastUpdate: '2026-04-15', latencyDays: 1, health: 'good' },
    { name: 'SURVSTAT Meldungen',    lastUpdate: '2026-04-13', latencyDays: 3, health: 'good', note: 'Meldeverzug korrigiert' },
    { name: 'GrippeWeb',              lastUpdate: '2026-04-13', latencyDays: 3, health: 'good' },
    { name: 'Notaufnahme-Surveillance', lastUpdate: '2026-04-14', latencyDays: 2, health: 'good' },
    { name: 'Wetter-Forecast (ECMWF)', lastUpdate: '2026-04-16', latencyDays: 0, health: 'good', note: 'Vintage-konform' },
  ],

  topDrivers: [
    { label: 'Abwasser (AMELAG)', value: '+40 % in BY, BE, SN' },
    { label: 'Google Trends „Husten\"', value: '2.1× ggü. Vorwoche' },
    { label: 'Wetter', value: 'Kälteeinbruch Mo 20.04.' },
    { label: 'Schulbeginn', value: 'MV, BE nach Osterferien' },
  ],
};
