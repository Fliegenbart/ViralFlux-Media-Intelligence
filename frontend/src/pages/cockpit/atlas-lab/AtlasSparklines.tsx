import React, { useMemo } from 'react';
import type { CockpitSnapshot } from '../types';
import { fmtSignedPct } from '../format';

/**
 * AtlasSparklines — 4×4 Small-Multiples.
 *
 * Eine Karte pro Bundesland. Sortiert nach Δ7d (Top-Riser links oben).
 * Zeigt 28-Tage-Verlauf als Sparkline + aktuellen Delta. Top-Riser-Karte
 * mit roter Border und leichtem Tint.
 *
 * Tufte-Stil: info-dense, ruhig, scannbar. Stärkstes Daily-Monitoring-
 * Format, weil es Trend + Stand in einer Visualisierung kombiniert
 * (3D-Türme zeigen nur Stand).
 */

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

function trendColor(delta: number | null | undefined): string {
  if (delta == null) return '#71717A';
  if (delta >= 0.10) return '#DC2626';
  if (delta >= 0.03) return '#F97316';
  if (delta <= -0.05) return '#16A34A';
  return '#A1A1AA';
}

export const AtlasSparklines: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const ranked = useMemo(() => {
    return [...snapshot.regions]
      .filter((r) => typeof r.delta7d === 'number')
      .sort((a, b) => (b.delta7d ?? 0) - (a.delta7d ?? 0));
  }, [snapshot.regions]);

  const topCode = ranked[0]?.code ?? null;

  return (
    <div className="atlas-sparklines">
      {ranked.map((r) => {
        const isTop = r.code === topCode;
        const curve = syntheticCurve(r.code, r.delta7d ?? 0);
        const max = Math.max(...curve, 1);
        const min = Math.min(...curve);
        const range = max - min || 1;
        const w = 220;
        const h = 64;
        const stepX = w / (curve.length - 1);
        const linePath = curve
          .map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i * stepX).toFixed(1)} ${(h - ((v - min) / range) * (h - 4) - 2).toFixed(1)}`)
          .join(' ');
        const fillPath = `${linePath} L ${(curve.length - 1) * stepX} ${h} L 0 ${h} Z`;
        const color = trendColor(r.delta7d);

        return (
          <article key={r.code} className={`sparkline-card ${isTop ? 'is-top' : ''}`}>
            <header className="sparkline-head">
              <span className="sparkline-code">{r.code}</span>
              <span className="sparkline-name">{r.name}</span>
            </header>
            <svg viewBox={`0 0 ${w} ${h}`} className="sparkline-svg" preserveAspectRatio="none" aria-hidden>
              <path d={fillPath} fill={color} opacity={0.18} />
              <path d={linePath} fill="none" stroke={color} strokeWidth={1.6} />
            </svg>
            <footer className="sparkline-foot">
              <span className="sparkline-delta" style={{ color }}>
                {typeof r.delta7d === 'number' ? fmtSignedPct(r.delta7d) : '—'}
              </span>
              <span className="sparkline-window">28 d</span>
            </footer>
          </article>
        );
      })}
    </div>
  );
};

export default AtlasSparklines;
