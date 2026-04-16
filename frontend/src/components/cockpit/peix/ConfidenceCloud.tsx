import React, { useMemo } from 'react';
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

  const { minY, maxY } = useMemo(() => {
    let lo = Infinity, hi = -Infinity;
    series.forEach((p) => {
      lo = Math.min(lo, p.q10, p.observed ?? p.q10, p.nowcast ?? p.q10);
      hi = Math.max(hi, p.q90, p.observed ?? p.q90, p.nowcast ?? p.q90);
    });
    return { minY: Math.floor(lo - 4), maxY: Math.ceil(hi + 4) };
  }, [series]);

  const n = series.length - 1;
  const xFor = (i: number) => padL + (i / n) * innerW;
  const yFor = (v: number) => padT + (1 - (v - minY) / (maxY - minY)) * innerH;

  // Cloud path Q10..Q90
  const cloud = useMemo(() => {
    const up = series.map((p, i) => `${i === 0 ? 'M' : 'L'}${xFor(i).toFixed(1)},${yFor(p.q90).toFixed(1)}`).join(' ');
    const down = series.slice().reverse().map((p, i) => {
      const realI = series.length - 1 - i;
      return `L${xFor(realI).toFixed(1)},${yFor(p.q10).toFixed(1)}`;
    }).join(' ');
    return `${up} ${down} Z`;
  }, [series]);

  const median = series.map((p, i) => `${i === 0 ? 'M' : 'L'}${xFor(i).toFixed(1)},${yFor(p.q50).toFixed(1)}`).join(' ');
  const observed = series.filter((p) => p.observed != null).map((p, i, arr) => {
    const realI = series.findIndex((x) => x.date === p.date);
    return `${i === 0 ? 'M' : 'L'}${xFor(realI).toFixed(1)},${yFor(p.observed as number).toFixed(1)}`;
  }).join(' ');

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
        {focusPoint && (
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
