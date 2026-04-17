import React, { useCallback, useMemo } from 'react';
import type { TimelinePoint } from '../../../pages/cockpit/types';

interface Props {
  series: TimelinePoint[];
  /** Current scrubber position in days (−14..+7). */
  focusDay: number;
  height?: number;
  /** Optional sub-title shown italic beneath chart. */
  caption?: string;
  /**
   * Optional lead-time horizon to annotate at the right side of the chart
   * (e.g. "+14 Tage" caption under the last tick). Defaults to 7.
   */
  leadHorizonDays?: number;
}

/**
 * Editorial fan-chart. Mirrors the aesthetic of a printed chart in a
 * business weekly: cream paper, hair-line grid, double-layered Q10–Q90
 * band, 1.2-px median hairline, and flag-style today / monument-style
 * focus annotations.
 *
 * Pure SVG. No dependencies. All visual detail is in the CSS classes —
 * the component stays structural so a future redesign can restyle
 * without rewriting geometry.
 */
export const ConfidenceCloud: React.FC<Props> = ({
  series,
  focusDay,
  height = 320,
  caption,
  leadHorizonDays = 7,
}) => {
  const W = 760;
  const H = height;
  const padL = 56;
  const padR = 28;
  const padT = 28;
  const padB = 40;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const cloudSeries = useMemo(
    () => series.filter((p) => p.q10 !== null && p.q50 !== null && p.q90 !== null),
    [series],
  );

  const { minY, maxY } = useMemo(() => {
    if (cloudSeries.length === 0) return { minY: 0, maxY: 1 };
    let lo = Infinity;
    let hi = -Infinity;
    cloudSeries.forEach((p) => {
      const q10 = p.q10 as number;
      const q90 = p.q90 as number;
      lo = Math.min(lo, q10, p.observed ?? q10, p.nowcast ?? q10);
      hi = Math.max(hi, q90, p.observed ?? q90, p.nowcast ?? q90);
    });
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { minY: 0, maxY: 1 };
    if (lo === hi) return { minY: lo - 1, maxY: hi + 1 };
    // More breathing room at top and bottom for annotations.
    const range = hi - lo;
    return {
      minY: Math.floor(lo - range * 0.08),
      maxY: Math.ceil(hi + range * 0.12),
    };
  }, [cloudSeries]);

  const n = Math.max(series.length - 1, 1);
  const xFor = useCallback((i: number) => padL + (i / n) * innerW, [n, innerW, padL]);
  const yFor = useCallback(
    (v: number) => padT + (1 - (v - minY) / Math.max(maxY - minY, 1)) * innerH,
    [minY, maxY, innerH, padT],
  );

  // Inner narrow band (≈ Q25–Q75 shape via contraction of Q10/Q90 toward
  // Q50 by 50%). Q25/Q75 aren't in the payload today, so we fake the
  // layered-fan look by rendering a second, tighter band on top.
  const outerCloud = useMemo(() => buildCloudPath(cloudSeries, series, xFor, yFor, 1.0), [cloudSeries, series, xFor, yFor]);
  const innerCloud = useMemo(() => buildCloudPath(cloudSeries, series, xFor, yFor, 0.5), [cloudSeries, series, xFor, yFor]);

  const median = cloudSeries
    .map((p, i) => {
      const realI = series.findIndex((x) => x.date === p.date);
      return `${i === 0 ? 'M' : 'L'}${xFor(realI).toFixed(1)},${yFor(p.q50 as number).toFixed(1)}`;
    })
    .join(' ');

  const observed = series
    .filter((p) => p.observed != null)
    .map((p, i) => {
      const realI = series.findIndex((x) => x.date === p.date);
      return `${i === 0 ? 'M' : 'L'}${xFor(realI).toFixed(1)},${yFor(p.observed as number).toFixed(1)}`;
    })
    .join(' ');

  const todayI = series.findIndex((p) => p.horizonDays === 0);
  const focusI = series.findIndex((p) => p.horizonDays === focusDay);
  const focusPoint = focusI >= 0 ? series[focusI] : null;

  // Ticks: show Monday-ish ticks (every 7 days from min).
  const tickIndices = useMemo(() => {
    const indices: number[] = [];
    series.forEach((p, i) => {
      if (p.horizonDays % 7 === 0) indices.push(i);
    });
    return indices;
  }, [series]);

  // Y-axis: a gentle 3-line grid with actual numeric labels.
  const yTicks = useMemo(() => {
    const steps = 4;
    const out: Array<{ v: number; y: number }> = [];
    for (let i = 1; i < steps; i++) {
      const v = minY + ((maxY - minY) * i) / steps;
      out.push({ v, y: yFor(v) });
    }
    return out;
  }, [minY, maxY, yFor]);

  // Δ versus today (for the focus annotation)
  const anchorQ50 = series.find((p) => p.horizonDays === 0)?.q50 ?? null;
  const focusDelta =
    focusPoint?.q50 != null && anchorQ50 != null && anchorQ50 !== 0
      ? (focusPoint.q50 - anchorQ50) / anchorQ50
      : null;

  const focusX = focusI >= 0 ? xFor(focusI) : null;
  const focusY = focusPoint?.q50 != null ? yFor(focusPoint.q50) : null;
  const todayX = todayI >= 0 ? xFor(todayI) : null;

  return (
    <figure className="peix-fanchart" style={{ margin: 0 }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        role="img"
        aria-label="Forecast mit Konfidenzband"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          {/* Paper grain — extremely subtle, only on the forecast side */}
          <pattern id="fc-grain" width="4" height="4" patternUnits="userSpaceOnUse">
            <rect width="4" height="4" fill="transparent" />
            <circle cx="2" cy="2" r="0.3" fill="rgba(27, 22, 18, 0.09)" />
          </pattern>
          {/* Outer (Q10–Q90) fill gradient — fades into the future */}
          <linearGradient id="fc-outer" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%"   stopColor="rgba(184, 92, 58, 0.14)" />
            <stop offset="100%" stopColor="rgba(184, 92, 58, 0.30)" />
          </linearGradient>
          {/* Inner (≈Q25–Q75) fill */}
          <linearGradient id="fc-inner" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%"   stopColor="rgba(184, 92, 58, 0.22)" />
            <stop offset="100%" stopColor="rgba(184, 92, 58, 0.42)" />
          </linearGradient>
        </defs>

        {/* Nowcast zone — diagonal hatch, very light */}
        {todayX != null && (
          <g className="peix-fanchart__nowcast">
            <rect
              x={xFor(0)}
              y={padT}
              width={todayX - xFor(0)}
              height={innerH}
              fill="url(#fc-grain)"
              opacity={0.7}
            />
            <text
              x={xFor(0) + 4}
              y={padT + 14}
              className="peix-fanchart__zone-label"
            >
              Nowcast
            </text>
          </g>
        )}

        {/* Y-axis grid + labels */}
        {yTicks.map((t, i) => (
          <g key={`yt-${i}`}>
            <line
              x1={padL}
              x2={padL + innerW}
              y1={t.y}
              y2={t.y}
              className="peix-fanchart__grid"
            />
            <text
              x={padL - 8}
              y={t.y + 3}
              className="peix-fanchart__ytick"
              textAnchor="end"
            >
              {t.v.toFixed(0)}
            </text>
          </g>
        ))}

        {/* Outer band: Q10–Q90 */}
        <path d={outerCloud} fill="url(#fc-outer)" stroke="none" />
        {/* Inner band: tighter, darker */}
        <path d={innerCloud} fill="url(#fc-inner)" stroke="none" />

        {/* Median forecast — hairline */}
        <path d={median} className="peix-fanchart__median" />

        {/* Observed — dark ink line */}
        <path d={observed} className="peix-fanchart__observed" />

        {/* Observed end cap: small solid circle at last observed point */}
        {(() => {
          const lastObserved = [...series].reverse().find((p) => p.observed != null);
          if (!lastObserved) return null;
          const idx = series.findIndex((p) => p.date === lastObserved.date);
          return (
            <circle
              cx={xFor(idx)}
              cy={yFor(lastObserved.observed as number)}
              r="2.5"
              className="peix-fanchart__observed-cap"
            />
          );
        })()}

        {/* Today — monument vertical + flag-label */}
        {todayX != null && (
          <g className="peix-fanchart__today">
            <line x1={todayX} x2={todayX} y1={padT - 4} y2={padT + innerH} />
            <rect
              x={todayX - 22}
              y={padT - 18}
              width="44"
              height="14"
              rx="1.5"
              className="peix-fanchart__today-flag"
            />
            <text x={todayX} y={padT - 7} textAnchor="middle" className="peix-fanchart__today-label">
              HEUTE
            </text>
          </g>
        )}

        {/* Focus — dashed vertical + pin + callout */}
        {focusX != null && focusPoint && focusY != null && (
          <g className="peix-fanchart__focus">
            <line
              x1={focusX}
              x2={focusX}
              y1={padT + 4}
              y2={padT + innerH}
              className="peix-fanchart__focus-line"
            />
            <circle cx={focusX} cy={focusY} r="6" className="peix-fanchart__focus-halo" />
            <circle cx={focusX} cy={focusY} r="3.2" className="peix-fanchart__focus-dot" />
            {/* Callout to the right if we have room, else to the left */}
            {(() => {
              const calloutRight = focusX < padL + innerW * 0.7;
              const cx = calloutRight ? focusX + 14 : focusX - 14;
              const anchor = calloutRight ? 'start' : 'end';
              return (
                <g>
                  <text x={cx} y={focusY - 10} textAnchor={anchor} className="peix-fanchart__callout-date">
                    {formatDateShort(focusPoint.date)}
                  </text>
                  <text x={cx} y={focusY + 6} textAnchor={anchor} className="peix-fanchart__callout-delta">
                    {focusDelta != null ? formatSigned(focusDelta) : '—'}
                    <tspan className="peix-fanchart__callout-unit"> vs heute</tspan>
                  </text>
                </g>
              );
            })()}
          </g>
        )}

        {/* X-axis ticks + week labels */}
        {tickIndices.map((i) => {
          const day = series[i]?.horizonDays ?? 0;
          const x = xFor(i);
          const isTodayish = day === 0;
          return (
            <g key={`xt-${i}`} className="peix-fanchart__xtick-group">
              <line x1={x} x2={x} y1={padT + innerH} y2={padT + innerH + 4} className="peix-fanchart__xtick" />
              {!isTodayish && (
                <text
                  x={x}
                  y={padT + innerH + 18}
                  textAnchor="middle"
                  className="peix-fanchart__xlabel"
                >
                  {day < 0 ? `${day}d` : `+${day}d`}
                </text>
              )}
            </g>
          );
        })}

        {/* Bottom baseline */}
        <line
          x1={padL}
          x2={padL + innerW}
          y1={padT + innerH}
          y2={padT + innerH}
          className="peix-fanchart__baseline"
        />

        {/* Horizon endpoint hair line "+N Tage" */}
        <text
          x={padL + innerW}
          y={padT + innerH + 32}
          textAnchor="end"
          className="peix-fanchart__horizon-end"
        >
          Lead-Horizont {leadHorizonDays} Tage
        </text>
      </svg>
      {caption && <figcaption className="peix-fanchart__caption">{caption}</figcaption>}
    </figure>
  );
};

// --------------------------------------------------------------------------
function buildCloudPath(
  cloudSeries: TimelinePoint[],
  series: TimelinePoint[],
  xFor: (i: number) => number,
  yFor: (v: number) => number,
  bandFraction: number,
): string {
  if (cloudSeries.length < 2) return '';
  const up = cloudSeries
    .map((p, i) => {
      const realI = series.findIndex((x) => x.date === p.date);
      const q50 = p.q50 as number;
      const q90 = p.q90 as number;
      const y = yFor(q50 + (q90 - q50) * bandFraction);
      return `${i === 0 ? 'M' : 'L'}${xFor(realI).toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const down = cloudSeries
    .slice()
    .reverse()
    .map((p) => {
      const realI = series.findIndex((x) => x.date === p.date);
      const q50 = p.q50 as number;
      const q10 = p.q10 as number;
      const y = yFor(q50 - (q50 - q10) * bandFraction);
      return `L${xFor(realI).toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return `${up} ${down} Z`;
}

function formatDateShort(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: 'short',
    });
  } catch {
    return iso;
  }
}

function formatSigned(p: number): string {
  const v = p * 100;
  const sign = v > 0 ? '+' : v < 0 ? '−' : '±';
  return `${sign}${Math.abs(v).toFixed(1)} %`;
}

export default ConfidenceCloud;
