import React, { useCallback, useMemo } from 'react';
import type { TimelinePoint } from '../../../pages/cockpit/types';

interface Props {
  series: TimelinePoint[];
  /** Current scrubber position in days (−14..+7). */
  focusDay: number;
  height?: number;
  /** Optional sub-title shown italic beneath chart. */
  caption?: string;
}

/**
 * Three-layer chart: observed line (ink), nowcast zone (orange dashed),
 * forecast median + Q10/Q90 cloud (marine).
 *
 * Pure SVG, zero dependencies — predictable render, no recharts layout churn.
 */
export const ConfidenceCloud: React.FC<Props> = ({ series, focusDay, height = 280, caption }) => {
  const W = 720;
  const H = height;
  const padL = 36, padR = 12, padT = 20, padB = 26;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  // Restrict chart math to points that actually have q10/q50/q90 — after the
  // fixture switch-off a timeline row without an ml_forecasts entry carries
  // all quantiles as null, which would NaN out the SVG path.
  const cloudSeries = useMemo(
    () =>
      series.filter(
        (p) => p.q10 !== null && p.q50 !== null && p.q90 !== null,
      ),
    [series],
  );

  const { minY, maxY } = useMemo(() => {
    if (cloudSeries.length === 0) return { minY: 0, maxY: 1 };
    let lo = Infinity, hi = -Infinity;
    cloudSeries.forEach((p) => {
      const q10 = p.q10 as number;
      const q90 = p.q90 as number;
      lo = Math.min(lo, q10, p.observed ?? q10, p.nowcast ?? q10);
      hi = Math.max(hi, q90, p.observed ?? q90, p.nowcast ?? q90);
    });
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo === hi) {
      return { minY: lo - 1, maxY: hi + 1 };
    }
    return { minY: Math.floor(lo - 4), maxY: Math.ceil(hi + 4) };
  }, [cloudSeries]);

  const n = Math.max(series.length - 1, 1);
  const xFor = useCallback(
    (i: number) => padL + (i / n) * innerW,
    [n, innerW, padL],
  );
  const yFor = useCallback(
    (v: number) => padT + (1 - (v - minY) / Math.max(maxY - minY, 1)) * innerH,
    [minY, maxY, innerH, padT],
  );

  // Cloud path Q10..Q90 — only over points where both bounds are defined.
  const cloud = useMemo(() => {
    if (cloudSeries.length < 2) return '';
    const up = cloudSeries
      .map((p, i) => {
        const realI = series.findIndex((x) => x.date === p.date);
        return `${i === 0 ? 'M' : 'L'}${xFor(realI).toFixed(1)},${yFor(p.q90 as number).toFixed(1)}`;
      })
      .join(' ');
    const down = cloudSeries
      .slice()
      .reverse()
      .map((p) => {
        const realI = series.findIndex((x) => x.date === p.date);
        return `L${xFor(realI).toFixed(1)},${yFor(p.q10 as number).toFixed(1)}`;
      })
      .join(' ');
    return `${up} ${down} Z`;
  }, [cloudSeries, series, xFor, yFor]);

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

  // Gridlines
  const gridY = [0.25, 0.5, 0.75].map((f) => padT + innerH * f);
  const nowcastZone = {
    x: xFor(0),
    width: xFor(todayI) - xFor(0),
  };

  return (
    <figure className="peix-figure" style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="Forecast mit Konfidenzwolke">
        {/* Nowcast-zone background (from -14 up to today) */}
        <rect x={nowcastZone.x} y={padT} width={nowcastZone.width} height={innerH} fill="var(--peix-card-dim)" opacity={0.55} />

        {/* grid */}
        {gridY.map((y, i) => (
          <line key={i} x1={padL} x2={padL + innerW} y1={y} y2={y} stroke="var(--peix-line)" strokeWidth={1} />
        ))}

        {/* confidence cloud */}
        <path d={cloud} className="peix-cloud-fill" />

        {/* median forecast */}
        <path d={median} className="peix-cloud-mid" />

        {/* observed */}
        <path d={observed} className="peix-cloud-obs" />

        {/* today vertical */}
        <line x1={xFor(todayI)} x2={xFor(todayI)} y1={padT} y2={padT + innerH} className="peix-cloud-now" />
        <text x={xFor(todayI) + 6} y={padT + 12} fontFamily="var(--peix-font-mono)" fontSize="10" fill="var(--peix-warm)">heute</text>

        {/* focus marker */}
        {focusPoint && focusPoint.q50 !== null && (
          <>
            <line x1={xFor(focusI)} x2={xFor(focusI)} y1={padT} y2={padT + innerH} stroke="var(--peix-ink)" strokeWidth="1" strokeDasharray="2 3" opacity={0.6} />
            <circle cx={xFor(focusI)} cy={yFor(focusPoint.q50)} r="5" fill="var(--peix-ink)" />
            <circle cx={xFor(focusI)} cy={yFor(focusPoint.q50)} r="10" fill="none" stroke="var(--peix-ink)" strokeOpacity="0.3" />
          </>
        )}

        {/* Y-axis labels */}
        <text x={6} y={padT + 4} className="peix-axis-label">hoch</text>
        <text x={6} y={padT + innerH} className="peix-axis-label">niedrig</text>
        {/* X-axis labels */}
        <text x={padL} y={H - 6} className="peix-axis-label">−14 Tage</text>
        <text x={xFor(todayI) - 18} y={H - 6} className="peix-axis-label">heute</text>
        <text x={padL + innerW - 30} y={H - 6} className="peix-axis-label" textAnchor="end">+7</text>
      </svg>
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
};

export default ConfidenceCloud;
