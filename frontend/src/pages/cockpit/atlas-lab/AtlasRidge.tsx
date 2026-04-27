import React, { useMemo } from 'react';
import type { CockpitSnapshot } from '../types';
import { fmtSignedPct } from '../format';

/**
 * AtlasRidge — Joy-Plot-Stil (16 BL gestapelt).
 *
 * Jede BL hat eine eigene Reihe; eine 28-Tage-Kurve ist deterministisch
 * aus Code + Delta synthetisiert (echter History wird später aus dem
 * Snapshot kommen). Top-Riser ist farblich gefüllt (Vermilion); der
 * Rest bleibt transparent-weiß für den Joy-Division-Look.
 */

const ROW_HEIGHT = 56;
const ROW_PAD = 6;
const LABEL_W = 160;
const DELTA_W = 70;
const CHART_PAD = 12;
const CURVE_LEN = 28;

function syntheticCurve(seed: string, finalDelta: number): number[] {
  const seedNum = (seed.charCodeAt(0) || 0) + (seed.charCodeAt(1) || 0);
  const trend = (finalDelta || 0) * 60;
  const arr: number[] = [];
  for (let i = 0; i < CURVE_LEN; i++) {
    const t = i / (CURVE_LEN - 1);
    const base = 30 + trend * t;
    const wave = Math.sin((seedNum + i * 7) * 0.18) * 7;
    const wave2 = Math.cos((seedNum + i * 13) * 0.27) * 3;
    arr.push(Math.max(0, base + wave + wave2));
  }
  return arr;
}

function curvePath(values: number[], width: number, maxVal: number, height: number): string {
  if (values.length === 0) return '';
  const stepX = width / (values.length - 1);
  const points: string[] = [];
  for (let i = 0; i < values.length; i++) {
    const x = i * stepX;
    const y = height - (values[i] / maxVal) * (height - 4);
    points.push(`${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`);
  }
  // Close to baseline
  points.push(`L ${(values.length - 1) * stepX} ${height}`);
  points.push(`L 0 ${height} Z`);
  return points.join(' ');
}

export const AtlasRidge: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const ranked = useMemo(() => {
    return [...snapshot.regions]
      .filter((r) => typeof r.delta7d === 'number' && Number.isFinite(r.delta7d))
      .sort((a, b) => (b.delta7d ?? 0) - (a.delta7d ?? 0));
  }, [snapshot.regions]);

  const topCode = ranked[0]?.code ?? null;
  const chartW = 760;
  const totalW = LABEL_W + CHART_PAD + chartW + CHART_PAD + DELTA_W;
  const totalH = ranked.length * (ROW_HEIGHT + ROW_PAD);

  return (
    <svg
      className="atlas-ridge"
      viewBox={`0 0 ${totalW} ${totalH}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Bundesländer als gestapelte Wellenkurven"
    >
      {ranked.map((r, i) => {
        const y = i * (ROW_HEIGHT + ROW_PAD);
        const isTop = r.code === topCode;
        const curve = syntheticCurve(r.code, r.delta7d ?? 0);
        const maxVal = Math.max(...curve, 60);
        const path = curvePath(curve, chartW, maxVal, ROW_HEIGHT);
        const fill = isTop ? '#DC2626' : 'rgba(250, 250, 250, 0.06)';
        const stroke = isTop ? '#FCA5A5' : 'rgba(250, 250, 250, 0.45)';
        const fillOpacity = isTop ? 0.85 : 1;

        return (
          <g key={r.code} transform={`translate(0, ${y})`}>
            <text x={0} y={ROW_HEIGHT - 14} className="ridge-label">
              {r.code}
            </text>
            <text x={28} y={ROW_HEIGHT - 14} className="ridge-name">
              {r.name}
            </text>
            <g transform={`translate(${LABEL_W + CHART_PAD}, 0)`}>
              <path
                d={path}
                fill={fill}
                fillOpacity={fillOpacity}
                stroke={stroke}
                strokeWidth={isTop ? 1.8 : 1.2}
              />
            </g>
            <text
              x={totalW - 4}
              y={ROW_HEIGHT - 14}
              textAnchor="end"
              className={`ridge-delta ${isTop ? 'is-top' : ''}`}
            >
              {typeof r.delta7d === 'number' ? fmtSignedPct(r.delta7d) : '—'}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

export default AtlasRidge;
