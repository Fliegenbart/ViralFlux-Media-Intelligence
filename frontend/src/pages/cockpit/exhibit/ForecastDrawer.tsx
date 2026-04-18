import React, { useMemo } from 'react';
import type { CockpitSnapshot, TimelinePoint } from '../types';
import { Drawer } from './Drawer';

/**
 * ForecastDrawer — Drawer III: die Zeit-Tafel.
 *
 * Ausgangspunkt war ein generisches Dashboard-Fan-Chart mit 4-Spalten-
 * Legende und zwei fetten Zahlen darunter. Hier ist die Neufassung als
 * „Scientific-atlas plate":
 *
 *   ┌── DIAGRAMM · III ────────────── MMXXVI · XVI ──┐
 *   │   L-Eckmarken statt voller Border             │
 *   │                                               │
 *   │   ◣ Papierkorn (feTurbulence, sehr zart)      │
 *   │   ◣ Tinten-Hierarchie 3 Strokes:              │
 *   │       1.75 px  Beobachtung (SURVSTAT)         │
 *   │       1.25 px  Q50-Median (terracotta)        │
 *   │       0.75 px  Notaufnahme-Spur (gepunktet)   │
 *   │   ◣ 10 % Ochre-Fill für Q10–Q90-Band          │
 *   │   ◣ HEUTE als ochrefarbene Hairline mit       │
 *   │     serifed Plaque + radialem Schein          │
 *   │   ◣ J-Hook-Annotation am Peak (italic)        │
 *   │   ◣ X-Achse: KW-Stanza + Monats-Stanza        │
 *   │                                               │
 *   │        .. Naturgemälde · März · April · Mai .. │
 *   └────────────────────────────────────────────────┘
 *
 *   α Lesart       β Lag · Rail+Perle   γ Kalibrierungs-Thermometer
 *
 * Kein generischer Legend-Swatch-Grid mehr — die drei Unterpanele
 * erzählen jeweils *einen* Gedanken mit kuratorischer Stimme.
 */

interface ForecastDrawerProps {
  open: boolean;
  onClose: () => void;
  snapshot: CockpitSnapshot;
}

// --------------------------------------------------------------
// Helpers
// --------------------------------------------------------------

/** ISO-week number (Thursday-indexed). */
function isoWeekNumber(iso: string): number {
  const d = new Date(iso);
  const target = new Date(d.valueOf());
  const dayNr = (d.getDay() + 6) % 7;
  target.setDate(target.getDate() - dayNr + 3);
  const firstThursday = target.valueOf();
  target.setMonth(0, 1);
  if (target.getDay() !== 4) {
    target.setMonth(0, 1 + ((4 - target.getDay() + 7) % 7));
  }
  return 1 + Math.ceil((firstThursday - target.valueOf()) / (7 * 24 * 3600 * 1000));
}

/** Returns the Monday (ISO-week start) date of a given ISO year+week. */
function isoWeekStart(year: number, week: number): Date {
  // Jan 4 is always in week 1
  const jan4 = new Date(year, 0, 4);
  const jan4Day = (jan4.getDay() + 6) % 7; // Mon=0
  const week1Monday = new Date(jan4);
  week1Monday.setDate(jan4.getDate() - jan4Day);
  const d = new Date(week1Monday);
  d.setDate(d.getDate() + (week - 1) * 7);
  return d;
}

const MONTH_NAMES_DE = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
];

function toRomanYear(y: number): string {
  // Naïve 4-digit conversion for years 1000–2999 — enough for our dates.
  const map: Array<[number, string]> = [
    [1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'],
    [100, 'C'],  [90, 'XC'],  [50, 'L'],  [40, 'XL'],
    [10, 'X'],   [9, 'IX'],   [5, 'V'],   [4, 'IV'], [1, 'I'],
  ];
  let n = y;
  let s = '';
  for (const [v, sym] of map) {
    while (n >= v) { s += sym; n -= v; }
  }
  return s;
}
function toRomanWeek(k: number): string {
  // Weeks up to 53
  return toRomanYear(k);
}

interface ChartPoint {
  kw: number;
  year: number;
  q10: number | null;
  q50: number | null;
  q90: number | null;
  obs: number | null;
  er: number | null;
  isForecast: boolean;
}

function buildPoints(timeline: TimelinePoint[]): {
  points: ChartPoint[];
  currentKw: number;
  year: number;
} {
  if (timeline.length === 0) {
    return { points: [], currentKw: 0, year: new Date().getFullYear() };
  }
  const raw: ChartPoint[] = timeline.map((p) => {
    const d = new Date(p.date);
    return {
      kw: isoWeekNumber(p.date),
      year: d.getFullYear(),
      q10: p.q10,
      q50: p.q50,
      q90: p.q90,
      obs: p.observed,
      er: p.edActivity,
      isForecast: p.horizonDays > 0,
    };
  });
  // Dedup by (kw) — first sample wins. Timeline is daily; one point per week
  // keeps the chart legible.
  const seen = new Set<number>();
  const deduped: ChartPoint[] = [];
  raw.forEach((p) => {
    if (!seen.has(p.kw)) {
      seen.add(p.kw);
      deduped.push(p);
    }
  });
  deduped.sort((a, b) => a.kw - b.kw);
  const today = timeline.find((p) => p.horizonDays === 0);
  const currentKw = today ? isoWeekNumber(today.date) : deduped[0]?.kw ?? 0;
  const year = deduped[0]?.year ?? new Date().getFullYear();
  return { points: deduped, currentKw, year };
}

// --------------------------------------------------------------
// Forecast plate — the SVG
// --------------------------------------------------------------

interface PlateProps {
  points: ChartPoint[];
  currentKw: number;
  year: number;
  virusLabel: string;
}

const ForecastPlate: React.FC<PlateProps> = ({
  points,
  currentKw,
  year,
  virusLabel,
}) => {
  const W = 960;
  const H = 440;
  const pad = { t: 72, r: 72, b: 92, l: 72 };

  // --- Empty plate --------------------------------------------------------
  if (points.length === 0) {
    return (
      <div className="ex-fc-plate-wrap">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="ex-fc-plate"
          role="img"
          aria-label="Keine Zeitreihe verfügbar"
        >
          <defs>
            <filter id="plateGrain">
              <feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="2" stitchTiles="stitch" />
              <feColorMatrix values="0 0 0 0 0.10  0 0 0 0 0.09  0 0 0 0 0.07  0 0 0 0.06 0" />
            </filter>
          </defs>
          <rect width={W} height={H} fill="#f0ebdf" />
          <rect width={W} height={H} fill="#000" opacity="0" filter="url(#plateGrain)" />
          <CornerMarks W={W} H={H} />
          <PlateStamps W={W} year={year} currentKw={currentKw} virusLabel={virusLabel} />
          <text
            x={W / 2}
            y={H / 2}
            textAnchor="middle"
            className="ex-fc-peak-label"
            style={{ fontSize: 15 }}
          >
            Keine Zeitreihe für diesen Horizont.
          </text>
        </svg>
      </div>
    );
  }

  // --- Coordinate system -------------------------------------------------
  const minKw = points[0].kw;
  const maxKw = points[points.length - 1].kw;
  const kwRange = Math.max(1, maxKw - minKw);
  const xFor = (kw: number) =>
    pad.l + ((kw - minKw) / kwRange) * (W - pad.l - pad.r);

  // Auto-scale Y based on the max across q90/obs/er so the chart fills.
  const ys: number[] = [];
  points.forEach((p) => {
    if (p.q90 !== null) ys.push(p.q90);
    if (p.obs !== null) ys.push(p.obs);
    if (p.er !== null) ys.push(p.er);
  });
  const rawMax = ys.length > 0 ? Math.max(...ys) : 1;
  const yMax = Math.max(0.2, rawMax * 1.18);
  const yFor = (v: number) =>
    pad.t + (1 - v / yMax) * (H - pad.t - pad.b);

  // --- Paths -------------------------------------------------------------
  const bandPts = points.filter((p) => p.q10 !== null && p.q90 !== null);
  const bandPath = (() => {
    if (bandPts.length < 2) return '';
    const top = bandPts
      .map((d) => `${xFor(d.kw).toFixed(1)},${yFor(d.q90 as number).toFixed(1)}`)
      .join(' ');
    const bot = bandPts
      .slice()
      .reverse()
      .map((d) => `${xFor(d.kw).toFixed(1)},${yFor(d.q10 as number).toFixed(1)}`)
      .join(' ');
    return `M ${top} L ${bot} Z`;
  })();

  const medianPts = points.filter((p) => p.q50 !== null);
  const medianPath = medianPts
    .map((d, i) => `${i === 0 ? 'M' : 'L'} ${xFor(d.kw).toFixed(1)} ${yFor(d.q50 as number).toFixed(1)}`)
    .join(' ');

  const obsPts = points.filter((p) => p.obs !== null);
  const obsPath = obsPts
    .map((d, i) => `${i === 0 ? 'M' : 'L'} ${xFor(d.kw).toFixed(1)} ${yFor(d.obs as number).toFixed(1)}`)
    .join(' ');

  const erPts = points.filter((p) => p.er !== null);
  const erPath = erPts
    .map((d, i) => `${i === 0 ? 'M' : 'L'} ${xFor(d.kw).toFixed(1)} ${yFor(d.er as number).toFixed(1)}`)
    .join(' ');

  // --- HEUTE position ---------------------------------------------------
  const xHeute = xFor(currentKw);

  // --- Peak annotation (forecast side only) -----------------------------
  const forecastMedians = medianPts.filter((p) => p.kw > currentKw);
  const peak = forecastMedians.length > 0
    ? forecastMedians.reduce((best, p) =>
        (p.q50 as number) > (best.q50 as number) ? p : best,
      )
    : null;
  const peakX = peak ? xFor(peak.kw) : 0;
  const peakY = peak ? yFor(peak.q50 as number) : 0;
  // Flip direction if peak is in the right third — J-hook points up-LEFT
  // instead of up-RIGHT to keep the label inside the plate.
  const peakFlip = peak ? peakX > W - pad.r - 180 : false;
  const peakLabelX = peak ? (peakFlip ? peakX - 16 : peakX + 16) : 0;
  const peakLabelY = peak ? peakY - 36 : 0;
  const peakAnchor = peakFlip ? 'end' : 'start';

  // --- Axis ticks -------------------------------------------------------
  // Pick every other KW if there are many weeks; every week otherwise.
  const tickEvery = kwRange >= 12 ? 2 : 1;
  const tickKws: number[] = [];
  for (let k = minKw; k <= maxKw; k += tickEvery) tickKws.push(k);
  if (tickKws[tickKws.length - 1] !== maxKw) tickKws.push(maxKw);

  // --- Month stanza — compute month spans across the visible KWs --------
  const monthSpans = (() => {
    const spans: { month: number; year: number; kwStart: number; kwEnd: number }[] = [];
    for (let k = minKw; k <= maxKw; k++) {
      const d = isoWeekStart(year, k);
      const m = d.getMonth();
      const y = d.getFullYear();
      const last = spans[spans.length - 1];
      if (!last || last.month !== m || last.year !== y) {
        spans.push({ month: m, year: y, kwStart: k, kwEnd: k });
      } else {
        last.kwEnd = k;
      }
    }
    return spans;
  })();

  return (
    <div className="ex-fc-plate-wrap">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="ex-fc-plate"
        role="img"
        aria-label={`Fan-Chart: Beobachtung und Prognose für ${virusLabel}`}
      >
        <defs>
          <filter id="plateGrain">
            <feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="2" stitchTiles="stitch" />
            <feColorMatrix values="0 0 0 0 0.10  0 0 0 0 0.09  0 0 0 0 0.07  0 0 0 0.06 0" />
          </filter>
          <radialGradient
            id="heuteGlow"
            cx={xHeute}
            cy={pad.t}
            r={220}
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0" stopColor="#b94a2e" stopOpacity="0.10" />
            <stop offset="1" stopColor="#b94a2e" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Paper (behind grain) */}
        <rect width={W} height={H} fill="#f0ebdf" />
        {/* Grain layer */}
        <rect
          width={W}
          height={H}
          fill="#000"
          opacity="0"
          filter="url(#plateGrain)"
        />

        {/* HEUTE glow — a subtle radial from the break moment */}
        <rect
          x={xHeute}
          y={pad.t - 8}
          width={W - pad.r - xHeute + 8}
          height={H - pad.t - pad.b + 8}
          fill="url(#heuteGlow)"
        />

        {/* Chart baselines — a single left y-rule and a bottom x-rule,
            both hairline, no tick labels on Y. */}
        <line
          x1={pad.l}
          y1={pad.t}
          x2={pad.l}
          y2={H - pad.b}
          stroke="rgba(26,23,19,.28)"
          strokeWidth="0.5"
        />
        <line
          x1={pad.l}
          y1={H - pad.b}
          x2={W - pad.r}
          y2={H - pad.b}
          stroke="rgba(26,23,19,.28)"
          strokeWidth="0.5"
        />

        {/* y-axis unit label, floating top-left of the chart area */}
        <text
          x={pad.l}
          y={pad.t - 14}
          className="ex-fc-axis-unit"
        >
          Relative Aktivität · Q50 mit Q10–Q90-Band
        </text>

        {/* Fan band */}
        {bandPath && (
          <path d={bandPath} fill="#d68a5a" opacity="0.18" />
        )}

        {/* Notaufnahme (ED) trace — whispered dashed ink */}
        {erPath && (
          <path
            d={erPath}
            stroke="#1a1713"
            strokeWidth="0.75"
            strokeDasharray="2 3"
            fill="none"
            opacity="0.65"
          />
        )}

        {/* Q50 median — terracotta */}
        {medianPath && (
          <path
            d={medianPath}
            stroke="#b94a2e"
            strokeWidth="1.25"
            fill="none"
            strokeLinecap="round"
          />
        )}

        {/* Observation (SURVSTAT) — the ink spine */}
        {obsPath && (
          <path
            d={obsPath}
            stroke="#1a1713"
            strokeWidth="1.75"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {/* Observed dots */}
        {obsPts.map((d) => (
          <circle
            key={`obs-${d.kw}`}
            cx={xFor(d.kw)}
            cy={yFor(d.obs as number)}
            r={2.25}
            fill="#1a1713"
          />
        ))}

        {/* Q50 forecast dots — small, ochre */}
        {medianPts
          .filter((p) => p.kw >= currentKw)
          .map((d) => (
            <circle
              key={`med-${d.kw}`}
              cx={xFor(d.kw)}
              cy={yFor(d.q50 as number)}
              r={1.6}
              fill="#b94a2e"
            />
          ))}

        {/* HEUTE vertical — the single dramatic event */}
        <line
          className="ex-fc-heute-line"
          x1={xHeute}
          y1={pad.t - 24}
          x2={xHeute}
          y2={H - pad.b}
        />
        {/* HEUTE plaque (above the chart) */}
        <g transform={`translate(${xHeute},${pad.t - 38})`}>
          <line
            x1="-36"
            x2="36"
            y1="0"
            y2="0"
            stroke="#b94a2e"
            strokeWidth="0.5"
          />
          <text
            x="0"
            y="-4"
            textAnchor="middle"
            className="ex-fc-heute-label"
          >
            HEUTE · KW {currentKw}
          </text>
        </g>

        {/* Peak J-hook annotation */}
        {peak && (
          <g>
            <circle cx={peakX} cy={peakY} r={3.2} fill="#b94a2e" />
            <line
              x1={peakX}
              y1={peakY - 4}
              x2={peakX}
              y2={peakLabelY + 6}
              stroke="rgba(26,23,19,.45)"
              strokeWidth="0.5"
            />
            <line
              x1={peakX}
              y1={peakLabelY + 6}
              x2={peakLabelX}
              y2={peakLabelY + 6}
              stroke="rgba(26,23,19,.45)"
              strokeWidth="0.5"
            />
            <text
              x={peakFlip ? peakLabelX - 6 : peakLabelX + 6}
              y={peakLabelY + 3}
              textAnchor={peakAnchor}
              className="ex-fc-peak-label"
            >
              <tspan fontStyle="italic">Spitze erwartet</tspan>
              <tspan
                x={peakFlip ? peakLabelX - 6 : peakLabelX + 6}
                dy="15"
                fontFamily="JetBrains Mono, monospace"
                fontStyle="normal"
                fontSize="10"
                letterSpacing="0.08em"
              >
                KW {peak.kw} · {(peak.q50 as number).toFixed(2)}
              </tspan>
            </text>
          </g>
        )}

        {/* X-axis ticks */}
        {tickKws.map((k) => (
          <g key={`tick-${k}`}>
            <line
              x1={xFor(k)}
              x2={xFor(k)}
              y1={H - pad.b}
              y2={H - pad.b + 4}
              stroke="rgba(26,23,19,.40)"
              strokeWidth="0.5"
            />
            <text
              x={xFor(k)}
              y={H - pad.b + 16}
              textAnchor="middle"
              className="ex-fc-axis-kw"
            >
              KW {k}
            </text>
          </g>
        ))}

        {/* Month stanza — italic labels under the KW row, spanning each month */}
        {monthSpans.map((s, i) => {
          const xStart = xFor(s.kwStart);
          const xEnd = xFor(s.kwEnd);
          const xMid = (xStart + xEnd) / 2;
          const wide = xEnd - xStart > 40;
          return (
            <g key={`m-${s.year}-${s.month}`}>
              {wide && (
                <>
                  <line
                    x1={xStart + 4}
                    x2={xMid - 28}
                    y1={H - pad.b + 34}
                    y2={H - pad.b + 34}
                    stroke="rgba(26,23,19,.18)"
                    strokeWidth="0.5"
                  />
                  <line
                    x1={xMid + 28}
                    x2={xEnd - 4}
                    y1={H - pad.b + 34}
                    y2={H - pad.b + 34}
                    stroke="rgba(26,23,19,.18)"
                    strokeWidth="0.5"
                  />
                </>
              )}
              <text
                x={xMid}
                y={H - pad.b + 38}
                textAnchor="middle"
                className="ex-fc-axis-month"
              >
                {MONTH_NAMES_DE[s.month]}
              </text>
              {/* ignore i warn */}
              {i < 0 && <></>}
            </g>
          );
        })}

        {/* Plate stamps (corners) */}
        <CornerMarks W={W} H={H} />
        <PlateStamps
          W={W}
          year={year}
          currentKw={currentKw}
          virusLabel={virusLabel}
        />
      </svg>
    </div>
  );
};

// L-shaped corner marks at each corner — museum plate flavour
const CornerMarks: React.FC<{ W: number; H: number }> = ({ W, H }) => {
  const L = 14;
  const inset = 20;
  const stroke = 'rgba(26,23,19,.45)';
  const sw = 0.8;
  return (
    <g>
      {/* top-left */}
      <line x1={inset} y1={inset} x2={inset + L} y2={inset} stroke={stroke} strokeWidth={sw} />
      <line x1={inset} y1={inset} x2={inset} y2={inset + L} stroke={stroke} strokeWidth={sw} />
      {/* top-right */}
      <line x1={W - inset - L} y1={inset} x2={W - inset} y2={inset} stroke={stroke} strokeWidth={sw} />
      <line x1={W - inset} y1={inset} x2={W - inset} y2={inset + L} stroke={stroke} strokeWidth={sw} />
      {/* bottom-left */}
      <line x1={inset} y1={H - inset - L} x2={inset} y2={H - inset} stroke={stroke} strokeWidth={sw} />
      <line x1={inset} y1={H - inset} x2={inset + L} y2={H - inset} stroke={stroke} strokeWidth={sw} />
      {/* bottom-right */}
      <line x1={W - inset} y1={H - inset - L} x2={W - inset} y2={H - inset} stroke={stroke} strokeWidth={sw} />
      <line x1={W - inset - L} y1={H - inset} x2={W - inset} y2={H - inset} stroke={stroke} strokeWidth={sw} />
    </g>
  );
};

const PlateStamps: React.FC<{
  W: number;
  year: number;
  currentKw: number;
  virusLabel: string;
}> = ({ W, year, currentKw, virusLabel }) => (
  <g>
    <text x="44" y="34" className="ex-fc-plate-num">
      DIAGRAMM · III
    </text>
    <line
      x1="44"
      x2="168"
      y1="42"
      y2="42"
      stroke="rgba(26,23,19,.30)"
      strokeWidth="0.5"
    />
    <text x="44" y="56" className="ex-fc-plate-virus">
      {virusLabel}
    </text>
    <text x={W - 44} y="34" textAnchor="end" className="ex-fc-plate-date">
      {toRomanYear(year)} · {toRomanWeek(currentKw)}
    </text>
  </g>
);

// --------------------------------------------------------------
// Panel α — Lesart
// --------------------------------------------------------------
const LesartPanel: React.FC<{ bestLag: number | null }> = ({ bestLag }) => (
  <div className="ex-fc-panel">
    <div className="ex-fc-panel-head">
      <span className="ex-fc-alpha">α</span>
      <span className="ex-fc-panel-title">Lesart</span>
    </div>
    <ul className="ex-fc-legend-list">
      <li>
        <span className="ex-fc-legend-swatch ex-fc-legend-swatch--obs" aria-hidden />
        <span>
          <em>Beobachtung</em> (SURVSTAT)
        </span>
      </li>
      <li>
        <span className="ex-fc-legend-swatch ex-fc-legend-swatch--band" aria-hidden />
        <span>
          <em>Q10–Q90-Band</em> — 80 % der plausiblen Verläufe
        </span>
      </li>
      <li>
        <span className="ex-fc-legend-swatch ex-fc-legend-swatch--med" aria-hidden />
        <span>
          <em>Median</em> (Q50) — Forecast, nicht Realität
        </span>
      </li>
      <li>
        <span className="ex-fc-legend-swatch ex-fc-legend-swatch--er" aria-hidden />
        <span>
          <em>Notaufnahme</em>{' '}
          {bestLag !== null && bestLag > 0
            ? `· ${bestLag} Tage Frühindikator`
            : '· Frühindikator'}
        </span>
      </li>
    </ul>
    <p className="ex-fc-panel-body">
      Das Band wird breiter, je weiter in die Zukunft —{' '}
      <em>bewusst sichtbar, nicht geglättet.</em>
    </p>
  </div>
);

// --------------------------------------------------------------
// Panel β — Lag · Rail
// --------------------------------------------------------------
const LagPanel: React.FC<{
  bestLag: number | null;
  leadTarget: string;
}> = ({ bestLag, leadTarget }) => {
  // Rail domain: covers before the wave through to RKI reporting
  const domainMin = -8;
  const domainMax = 14;
  const pctFor = (d: number) =>
    ((d - domainMin) / (domainMax - domainMin)) * 100;

  const REFS: Array<{ at: number; label: string }> = [
    { at: 0, label: 'Welle' },
    { at: 2, label: 'AMELAG' },
    { at: 3, label: 'Notaufn.' },
    { at: 10, label: 'RKI' },
  ];
  const NOTAUFNAHME_DAY = 3;
  // Convention used throughout the codebase (see TimelinePage.tsx history):
  //   bestLag >= 0 → forecast is AHEAD of Notaufnahme (hero state)
  //   bestLag <  0 → forecast is BEHIND Notaufnahme
  // Pin position = NotaufnahmeDay - bestLag so that "ahead" lands LEFT.
  const pinDay = bestLag !== null ? NOTAUFNAHME_DAY - bestLag : null;
  const pinLabel =
    bestLag === null
      ? null
      : bestLag > 0
        ? `+${bestLag} d`
        : bestLag < 0
          ? `\u2212${Math.abs(bestLag)} d`
          : '0 d';

  const statement =
    bestLag === null
      ? 'Lag-Messung liegt noch nicht vor.'
      : bestLag > 0
        ? `Der Forecast ${bestLag === 1 ? 'sieht' : 'sieht'} die Welle ${bestLag} Tage vor der Notaufnahme.`
        : bestLag < 0
          ? `Der Forecast läuft ${Math.abs(bestLag)} Tage hinter der Notaufnahme — bleibt dem Meldewesen aber strukturell voraus.`
          : 'Forecast und Notaufnahme laufen synchron.';

  return (
    <div className="ex-fc-panel">
      <div className="ex-fc-panel-head">
        <span className="ex-fc-alpha">β</span>
        <span className="ex-fc-panel-title">Lag · gegen {leadTarget.split(' ')[0]}</span>
      </div>

      <div className="ex-fc-rail" aria-hidden>
        <div className="ex-fc-rail-base" />
        {REFS.map((r) => (
          <React.Fragment key={r.label}>
            <div
              className="ex-fc-rail-ref-label"
              style={{ left: `${pctFor(r.at)}%` }}
            >
              {r.label}
            </div>
            <div
              className="ex-fc-rail-bead"
              style={{ left: `${pctFor(r.at)}%` }}
            />
            <div
              className="ex-fc-rail-ref-day"
              style={{ left: `${pctFor(r.at)}%` }}
            >
              {r.at === 0 ? '\u00B1 0' : `+${r.at} d`}
            </div>
          </React.Fragment>
        ))}
        {pinDay !== null && pinLabel !== null && (
          <>
            <div
              className="ex-fc-rail-pin"
              style={{ left: `${pctFor(pinDay)}%` }}
            >
              <span className="ex-fc-rail-pin-cap" />
            </div>
            <div
              className="ex-fc-rail-pin-label"
              style={{ left: `${pctFor(pinDay)}%` }}
            >
              {pinLabel}
            </div>
          </>
        )}
      </div>

      <p className="ex-fc-panel-body">{statement}</p>
    </div>
  );
};

// --------------------------------------------------------------
// Panel γ — Kalibrierung (coverage thermometer)
// --------------------------------------------------------------
const KalibrierungPanel: React.FC<{
  coverage: number | null;    // 0..100 or null
  calibrationMode: string | undefined;
}> = ({ coverage, calibrationMode }) => {
  const measured = typeof coverage === 'number' && Number.isFinite(coverage);
  const fillFrac = measured ? Math.max(0, Math.min(100, coverage as number)) / 100 : 0;
  const isCalibrated = calibrationMode === 'calibrated';

  return (
    <div className="ex-fc-panel">
      <div className="ex-fc-panel-head">
        <span className="ex-fc-alpha">γ</span>
        <span className="ex-fc-panel-title">Kalibrierung · 80 %-Band</span>
      </div>

      <div
        className={
          'ex-fc-cov' + (measured ? '' : ' unmeasured')
        }
      >
        {measured && (
          <div
            className="ex-fc-cov-fill reveal"
            style={{ ['--fill' as string]: fillFrac }}
          />
        )}
        <div className="ex-fc-cov-ticks" />
        <div className="ex-fc-cov-target" style={{ left: '80%' }} />
      </div>
      <div className="ex-fc-cov-scale">
        <span>0 %</span>
        <span style={{ marginLeft: 'auto', marginRight: 'calc(20% - 14px)' }}>
          0.80 · Ziel
        </span>
      </div>

      <div className={'ex-fc-cov-value' + (measured ? '' : ' absent')}>
        {measured ? (coverage as number).toFixed(0) + ' %' : '—'}
      </div>

      <p className="ex-fc-panel-body">
        {measured && isCalibrated ? (
          <>
            Anteil tatsächlicher Werte im 80 %-Band über die letzten
            12 Wochen. Ziel: 0.80.
          </>
        ) : measured ? (
          <>
            Band gemessen, aber die Score-Skala ist noch heuristisch. Ein
            kalibrierter Abgleich wird mit dem Outcome-Loop nachgereicht.
          </>
        ) : (
          <>
            <em>Noch nicht gemessen —</em> der Abgleich gegen beobachtete
            Werte läuft nach KW 20, sobald der Outcome-Loop genügend
            Rückmeldungen liefert.
          </>
        )}
      </p>
    </div>
  );
};

// --------------------------------------------------------------
// ForecastDrawer root
// --------------------------------------------------------------
export const ForecastDrawer: React.FC<ForecastDrawerProps> = ({
  open,
  onClose,
  snapshot,
}) => {
  const cov80 = snapshot.modelStatus?.intervalCoverage80Pct ?? null;
  const bestLag = snapshot.modelStatus?.lead?.bestLagDays ?? null;
  const leadTarget =
    snapshot.modelStatus?.lead?.targetLabel ?? 'Notaufnahme-Syndromsurveillance';
  const calibrationMode = snapshot.modelStatus?.calibrationMode;
  const virusLabel = snapshot.virusLabel;

  const { points, currentKw, year } = useMemo(
    () => buildPoints(snapshot.timeline ?? []),
    [snapshot.timeline],
  );

  // Foot copy is derived so it stays honest under every state.
  const footLeft = (() => {
    if (bestLag === null) return 'Q10–Q90 · Lag-Messung ausstehend';
    if (bestLag > 0)
      return `Q10–Q90 · Forecast läuft Notaufnahme +${bestLag} d voraus`;
    if (bestLag < 0)
      return `Q10–Q90 · Forecast lagt Notaufnahme ${bestLag} d hinterher`;
    return 'Q10–Q90 · Forecast und Notaufnahme synchron';
  })();

  const footRight =
    typeof cov80 === 'number' && Number.isFinite(cov80)
      ? `Abdeckung ${cov80.toFixed(0)} % · Ziel 80 %`
      : 'Kalibrierung · noch nicht gemessen';

  return (
    <Drawer
      open={open}
      onClose={onClose}
      kicker={
        <>
          <span>Drawer III</span>
          <span>·</span>
          <span>Forecast-Zeitreise</span>
          <span>·</span>
          <span>{virusLabel}</span>
        </>
      }
      title={
        <>
          Fan-Chart, <em>ehrlich beschriftet.</em>
        </>
      }
      footLeft={footLeft}
      footRight={footRight}
    >
      <div className="ex-fc-wrap">
        <p className="ex-fc-margin ex-fc-reveal-1">
          <span className="ex-fc-margin-idx">F.01</span>
          Links die beobachtete Vergangenheit, rechts die Prognose mit
          Q10–Q90-Fan. Das Band wird breiter, je weiter in die Zukunft —
          bewusst sichtbar, nicht geglättet.
        </p>

        <div className="ex-fc-reveal-2">
          <ForecastPlate
            points={points}
            currentKw={currentKw}
            year={year}
            virusLabel={virusLabel}
          />
        </div>

        <p
          className="ex-fc-margin ex-fc-reveal-3"
          style={{ marginTop: 20 }}
        >
          <span className="ex-fc-margin-idx">F.02</span>
          Die HEUTE-Linie trennt, was gemessen wurde, von dem, was
          erwartet wird. Was links davon steht, ist Tinte. Was rechts
          steht, ist Wäsche.
        </p>

        <div className="ex-fc-panels ex-fc-reveal-4">
          <LesartPanel bestLag={bestLag} />
          <LagPanel bestLag={bestLag} leadTarget={leadTarget} />
          <KalibrierungPanel
            coverage={cov80}
            calibrationMode={calibrationMode}
          />
        </div>
      </div>
    </Drawer>
  );
};

export default ForecastDrawer;
