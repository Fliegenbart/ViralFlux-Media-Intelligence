import React, { useMemo } from 'react';
import type { CockpitSnapshot, TimelinePoint } from '../types';
import { Drawer } from './Drawer';

/**
 * ForecastDrawer — Drawer III.
 *
 * Hand-drawn SVG fan-chart on paper. Same editorial "chart from a very
 * expensive trade weekly" feel as the design prototype. Under the chart:
 * legend + two calibration stats (coverage, lag).
 *
 * We index the timeline by a calendar-week number derived from each
 * point's date, so the axis reads "KW 10 · KW 11 · …" which matches the
 * Wochenausgabe framing used everywhere else.
 */

interface ForecastDrawerProps {
  open: boolean;
  onClose: () => void;
  snapshot: CockpitSnapshot;
}

function isoWeekNumber(iso: string): number {
  // ISO-week calculation (Thu-based).
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

interface ChartPoint {
  kw: number;
  q10: number | null;
  q50: number | null;
  q90: number | null;
  obs: number | null;
  er: number | null;
  isForecast: boolean;
}

const FanChart: React.FC<{ points: ChartPoint[]; currentKw: number }> = ({
  points,
  currentKw,
}) => {
  const W = 880;
  const H = 360;
  const pad = { t: 20, r: 24, b: 40, l: 48 };

  if (points.length === 0) {
    return (
      <svg
        className="ex-fanchart-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Keine Zeitreihe verfügbar"
      >
        <text
          x={W / 2}
          y={H / 2}
          textAnchor="middle"
          fontFamily="Fraunces, Georgia, serif"
          fontStyle="italic"
          fontSize="16"
          fill="rgba(26,23,19,.45)"
        >
          Keine Zeitreihe für diesen Horizont.
        </text>
      </svg>
    );
  }

  const minKw = points[0].kw;
  const maxKw = points[points.length - 1].kw;
  const xFor = (kw: number) =>
    pad.l + ((kw - minKw) / Math.max(1, maxKw - minKw)) * (W - pad.l - pad.r);

  // Auto-scale Y based on q90 / obs.
  const ys: number[] = [];
  points.forEach((p) => {
    if (p.q90 !== null) ys.push(p.q90);
    if (p.obs !== null) ys.push(p.obs);
    if (p.er !== null) ys.push(p.er);
  });
  const rawMax = ys.length > 0 ? Math.max(...ys) : 1;
  const yMax = Math.max(0.2, rawMax * 1.12);
  const yFor = (v: number) =>
    pad.t + (1 - v / yMax) * (H - pad.t - pad.b);

  // Band path — connect Q90 forward, then Q10 reversed.
  const bandPoints = points.filter(
    (p) => p.q10 !== null && p.q90 !== null,
  );
  const topPts = bandPoints
    .map((d) => `${xFor(d.kw).toFixed(1)},${yFor(d.q90 as number).toFixed(1)}`)
    .join(' ');
  const botPts = bandPoints
    .slice()
    .reverse()
    .map((d) => `${xFor(d.kw).toFixed(1)},${yFor(d.q10 as number).toFixed(1)}`)
    .join(' ');
  const bandPath = `M ${topPts} L ${botPts} Z`;

  const medianPath = points
    .filter((d) => d.q50 !== null)
    .map(
      (d, i) =>
        `${i === 0 ? 'M' : 'L'} ${xFor(d.kw).toFixed(1)} ${yFor(d.q50 as number).toFixed(1)}`,
    )
    .join(' ');

  const obs = points.filter((d) => d.obs !== null);
  const obsPath = obs
    .map(
      (d, i) =>
        `${i === 0 ? 'M' : 'L'} ${xFor(d.kw).toFixed(1)} ${yFor(d.obs as number).toFixed(1)}`,
    )
    .join(' ');

  const er = points.filter((d) => d.er !== null);
  const erPath = er
    .map(
      (d, i) =>
        `${i === 0 ? 'M' : 'L'} ${xFor(d.kw).toFixed(1)} ${yFor(d.er as number).toFixed(1)}`,
    )
    .join(' ');

  // Y ticks — pretty rounded values based on yMax.
  const tickStep = yMax > 1.2 ? 0.4 : yMax > 0.6 ? 0.2 : 0.1;
  const ticks: number[] = [];
  for (let v = 0; v <= yMax; v += tickStep) {
    ticks.push(Number(v.toFixed(2)));
  }

  return (
    <svg
      className="ex-fanchart-svg"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Fan-Chart: Q10, Q50, Q90 mit SURVSTAT-Meldung und Notaufnahme-Spur"
    >
      {/* y gridlines + labels */}
      {ticks.map((v) => (
        <g key={v}>
          <line
            x1={pad.l}
            x2={W - pad.r}
            y1={yFor(v)}
            y2={yFor(v)}
            stroke="rgba(26,23,19,.08)"
            strokeWidth="1"
          />
          <text
            x={pad.l - 8}
            y={yFor(v) + 4}
            textAnchor="end"
            fontFamily="JetBrains Mono, monospace"
            fontSize="10"
            fill="rgba(26,23,19,.45)"
          >
            {v.toFixed(1)}
          </text>
        </g>
      ))}
      {/* band */}
      {bandPoints.length > 1 && (
        <path d={bandPath} fill="#d68a5a" opacity="0.18" />
      )}
      {/* median */}
      {medianPath && (
        <path d={medianPath} stroke="#b94a2e" strokeWidth="1.25" fill="none" />
      )}
      {/* obs */}
      {obsPath && (
        <path d={obsPath} stroke="#1a1713" strokeWidth="1.5" fill="none" />
      )}
      {/* er (lead indicator) */}
      {erPath && (
        <path
          d={erPath}
          stroke="#1a1713"
          strokeWidth="1"
          strokeDasharray="3 3"
          fill="none"
        />
      )}
      {/* current week divider */}
      <line
        x1={xFor(currentKw)}
        x2={xFor(currentKw)}
        y1={pad.t}
        y2={H - pad.b}
        stroke="rgba(26,23,19,.3)"
        strokeDasharray="2 3"
        strokeWidth="1"
      />
      <text
        x={xFor(currentKw) + 6}
        y={pad.t + 12}
        fontFamily="JetBrains Mono, monospace"
        fontSize="10"
        fill="rgba(26,23,19,.6)"
        letterSpacing="0.08em"
      >
        HEUTE · KW {currentKw}
      </text>
      {/* x ticks */}
      {points.map((d) => (
        <text
          key={d.kw}
          x={xFor(d.kw)}
          y={H - pad.b + 18}
          textAnchor="middle"
          fontFamily="JetBrains Mono, monospace"
          fontSize="10"
          fill="rgba(26,23,19,.45)"
        >
          KW{d.kw}
        </text>
      ))}
      {/* data points on obs */}
      {obs.map((d) => (
        <circle
          key={d.kw}
          cx={xFor(d.kw)}
          cy={yFor(d.obs as number)}
          r="2.5"
          fill="#1a1713"
        />
      ))}
    </svg>
  );
};

export const ForecastDrawer: React.FC<ForecastDrawerProps> = ({
  open,
  onClose,
  snapshot,
}) => {
  const cov80 = snapshot.modelStatus?.intervalCoverage80Pct ?? null;
  const bestLag =
    snapshot.modelStatus?.lead?.bestLagDays ?? null;
  const leadHorizon =
    snapshot.modelStatus?.lead?.horizonDays ??
    snapshot.modelStatus?.horizonDays ??
    14;
  const leadTarget =
    snapshot.modelStatus?.lead?.targetLabel ?? 'Notaufnahme-Syndromsurveillance';

  const { points, currentKw } = useMemo(() => {
    const tl: TimelinePoint[] = snapshot.timeline ?? [];
    const pts: ChartPoint[] = tl.map((p) => {
      const kw = isoWeekNumber(p.date);
      return {
        kw,
        q10: p.q10,
        q50: p.q50,
        q90: p.q90,
        obs: p.observed,
        er: p.edActivity,
        isForecast: p.horizonDays > 0,
      };
    });
    // Deduplicate by kw (snapshots often have daily granularity; we pick
    // the first point per week to keep the chart legible).
    const seen = new Set<number>();
    const deduped: ChartPoint[] = [];
    pts.forEach((p) => {
      if (!seen.has(p.kw)) {
        seen.add(p.kw);
        deduped.push(p);
      }
    });
    deduped.sort((a, b) => a.kw - b.kw);
    const today = tl.find((p) => p.horizonDays === 0);
    const cur = today ? isoWeekNumber(today.date) : deduped[0]?.kw ?? 0;
    return { points: deduped, currentKw: cur };
  }, [snapshot.timeline]);

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
          <span>{snapshot.virusLabel}</span>
        </>
      }
      title={
        <>
          Fan-Chart, <em>ehrlich beschriftet.</em>
        </>
      }
      footLeft={
        bestLag !== null
          ? `Q10–Q90 · Notaufnahme ${bestLag >= 0 ? `führt +${bestLag}` : `lagt ${bestLag}`} d`
          : 'Q10–Q90-Intervall'
      }
      footRight={
        cov80 !== null
          ? `Abdeckung ${cov80.toFixed(0)} % · Ziel 80 %`
          : 'Kalibrierungsabgleich ausstehend'
      }
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr',
          gap: 24,
        }}
      >
        <div>
          <FanChart points={points} currentKw={currentKw} />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 24,
              marginTop: 20,
            }}
          >
            <LegendItem
              swatch={
                <span
                  style={{
                    display: 'inline-block',
                    width: 16,
                    height: 2,
                    background: '#d68a5a',
                    opacity: 0.4,
                  }}
                />
              }
              label="Q10 – Q90 · Band"
              note="80 % der plausiblen Verläufe."
            />
            <LegendItem
              swatch={
                <span
                  style={{
                    display: 'inline-block',
                    width: 16,
                    height: 1.25,
                    background: '#b94a2e',
                  }}
                />
              }
              label="Q50 · Median"
              note="Forecast, nicht Realität."
            />
            <LegendItem
              swatch={
                <span
                  style={{
                    display: 'inline-block',
                    width: 16,
                    height: 1.5,
                    background: '#1a1713',
                  }}
                />
              }
              label="SURVSTAT-Meldung"
              note="Amtlich, lagging."
            />
            <LegendItem
              swatch={
                <span
                  style={{
                    display: 'inline-block',
                    width: 16,
                    height: 1,
                    background: '#1a1713',
                  }}
                />
              }
              label="- - - Notaufnahme"
              note={
                bestLag !== null && bestLag >= 0
                  ? `Frühindikator · +${bestLag} d.`
                  : 'Frühindikator.'
              }
            />
          </div>
          <hr
            style={{
              margin: '32px 0',
              height: 1,
              background: 'rgba(26,23,19,.10)',
              border: 0,
            }}
          />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 40,
            }}
          >
            <div>
              <div
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 11,
                  letterSpacing: '.08em',
                  textTransform: 'uppercase',
                  color: 'rgba(26,23,19,.45)',
                  marginBottom: 8,
                }}
              >
                Kalibrierung · retrospektiv
              </div>
              <div
                style={{
                  fontFamily: 'Fraunces, Georgia, serif',
                  fontSize: 40,
                  fontVariationSettings: '"opsz" 144',
                  letterSpacing: '-0.02em',
                }}
              >
                {cov80 !== null ? (cov80 / 100).toFixed(2) : '—'}
              </div>
              <div
                style={{
                  fontFamily: 'Fraunces, Georgia, serif',
                  fontStyle: 'italic',
                  fontSize: 13,
                  color: 'rgba(26,23,19,.60)',
                  marginTop: 4,
                  maxWidth: '40ch',
                }}
              >
                Anteil der beobachteten Werte in Q10–Q90. Zielwert: 0.80.
              </div>
            </div>
            <div>
              <div
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 11,
                  letterSpacing: '.08em',
                  textTransform: 'uppercase',
                  color: 'rgba(26,23,19,.45)',
                  marginBottom: 8,
                }}
              >
                Lag · diese Woche
              </div>
              <div
                style={{
                  fontFamily: 'Fraunces, Georgia, serif',
                  fontSize: 40,
                  fontVariationSettings: '"opsz" 144',
                  letterSpacing: '-0.02em',
                }}
              >
                {bestLag !== null
                  ? bestLag >= 0
                    ? `+${bestLag} Tage`
                    : `${bestLag} Tage`
                  : '—'}
              </div>
              <div
                style={{
                  fontFamily: 'Fraunces, Georgia, serif',
                  fontStyle: 'italic',
                  fontSize: 13,
                  color: 'rgba(26,23,19,.60)',
                  marginTop: 4,
                  maxWidth: '40ch',
                }}
              >
                {bestLag !== null && bestLag >= 0
                  ? `${leadTarget} führt amtliches Meldewesen.`
                  : bestLag !== null
                    ? `Forecast liegt gegen ${leadTarget} zurück, bleibt dem Meldewesen aber strukturell voraus.`
                    : 'Lag-Messung liegt nicht vor.'}
              </div>
            </div>
          </div>
          <div
            style={{
              marginTop: 24,
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 10,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              color: 'rgba(26,23,19,.45)',
            }}
          >
            Lead-Horizont {leadHorizon} Tage · Ziel {leadTarget}
          </div>
        </div>
      </div>
    </Drawer>
  );
};

const LegendItem: React.FC<{
  swatch: React.ReactNode;
  label: string;
  note: string;
}> = ({ swatch, label, note }) => (
  <div>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {swatch}
      <span
        style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 10,
          color: 'rgba(26,23,19,.60)',
          letterSpacing: '.08em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </span>
    </div>
    <div
      style={{
        fontFamily: 'Fraunces, Georgia, serif',
        fontStyle: 'italic',
        fontSize: 13,
        color: 'rgba(26,23,19,.60)',
        marginTop: 4,
      }}
    >
      {note}
    </div>
  </div>
);

export default ForecastDrawer;
