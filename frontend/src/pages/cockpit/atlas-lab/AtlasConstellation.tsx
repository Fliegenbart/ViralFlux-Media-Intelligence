import React, { useMemo } from 'react';
import type { CockpitSnapshot } from '../types';
import { fmtSignedPct } from '../format';

/**
 * AtlasConstellation — Bundesländer als Sterne in einer dunklen Karte.
 *
 * Position    = Geographie (aus LAENDER_COORDS, projiziert auf SVG)
 * Größe       = aktuelle Aktivität (|delta|)
 * Farbe       = Trend (rot Riser, orange mild, grün fallend, zinc flach)
 * Pulse       = Top-Riser sanft animiert + radialer Glow
 * Hintergrund = subtile Zufalls-Sterne für atmosphärischen Tiefen-Eindruck
 */

const COORDS: Record<string, { x: number; z: number; name: string }> = {
  SH: { x: -0.3, z: -3.6, name: 'Schleswig-Holstein' },
  HH: { x: -0.2, z: -2.9, name: 'Hamburg' },
  NI: { x: -1.1, z: -2.3, name: 'Niedersachsen' },
  HB: { x: -1.5, z: -2.7, name: 'Bremen' },
  MV: { x: 1.4, z: -3.2, name: 'Mecklenburg-Vorpommern' },
  BE: { x: 1.8, z: -1.5, name: 'Berlin' },
  BB: { x: 1.9, z: -2.1, name: 'Brandenburg' },
  ST: { x: 0.6, z: -1.5, name: 'Sachsen-Anhalt' },
  NW: { x: -2.4, z: -0.9, name: 'Nordrhein-Westfalen' },
  HE: { x: -1.3, z: 0.2, name: 'Hessen' },
  TH: { x: 0.3, z: 0.3, name: 'Thüringen' },
  SN: { x: 1.8, z: 0.2, name: 'Sachsen' },
  RP: { x: -2.2, z: 1.1, name: 'Rheinland-Pfalz' },
  SL: { x: -2.8, z: 1.8, name: 'Saarland' },
  BW: { x: -1.4, z: 2.3, name: 'Baden-Württemberg' },
  BY: { x: 0.8, z: 2.4, name: 'Bayern' },
};

const SVG_W = 640;
const SVG_H = 760;
const PAD = 60;

function project(x: number, z: number) {
  // x ∈ [-2.8, 1.9], z ∈ [-3.6, 2.4]
  const px = ((x + 2.8) / 4.7) * (SVG_W - 2 * PAD) + PAD;
  const py = ((z + 3.6) / 6.0) * (SVG_H - 2 * PAD) + PAD;
  return { px, py };
}

function trendColor(delta: number | null | undefined): string {
  if (delta == null) return '#52525B';
  if (delta >= 0.10) return '#DC2626';
  if (delta >= 0.03) return '#F97316';
  if (delta <= -0.05) return '#16A34A';
  return '#71717A';
}

function starRadius(delta: number | null | undefined): number {
  if (delta == null) return 6;
  return 7 + Math.min(22, Math.abs(delta) * 70);
}

export const AtlasConstellation: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const ranked = useMemo(() => {
    return [...snapshot.regions]
      .filter((r) => typeof r.delta7d === 'number')
      .sort((a, b) => (b.delta7d ?? 0) - (a.delta7d ?? 0));
  }, [snapshot.regions]);
  const topCode = ranked[0]?.code ?? null;

  const cells = snapshot.regions
    .map((r) => {
      const c = COORDS[r.code as string];
      if (!c) return null;
      const { px, py } = project(c.x, c.z);
      return { region: r, px, py };
    })
    .filter((c): c is NonNullable<typeof c> => c !== null);

  // Deterministic background star field — Sin/Cos Hash über Index.
  const bgStars = Array.from({ length: 110 }).map((_, i) => ({
    x: (Math.sin(i * 17.13) * 0.5 + 0.5) * SVG_W,
    y: (Math.cos(i * 23.71) * 0.5 + 0.5) * SVG_H,
    r: ((Math.sin(i * 7.3) + 1) / 2) * 0.9 + 0.4,
    o: ((Math.cos(i * 3.7) + 1) / 2) * 0.18 + 0.05,
  }));

  return (
    <svg
      className="atlas-constellation"
      viewBox={`0 0 ${SVG_W} ${SVG_H}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Bundesländer als Sterne in einer geographischen Karte"
    >
      <defs>
        <radialGradient id="lab-star-glow">
          <stop offset="0%" stopColor="#DC2626" stopOpacity={0.55} />
          <stop offset="60%" stopColor="#DC2626" stopOpacity={0.15} />
          <stop offset="100%" stopColor="#DC2626" stopOpacity={0} />
        </radialGradient>
      </defs>

      {bgStars.map((s, i) => (
        <circle key={`bg-${i}`} cx={s.x} cy={s.y} r={s.r} fill="white" opacity={s.o} />
      ))}

      {cells.map(({ region, px, py }) => {
        const isTop = region.code === topCode;
        const r = starRadius(region.delta7d);
        const color = trendColor(region.delta7d);
        return (
          <g key={region.code} className={`star-cell ${isTop ? 'is-top' : ''}`}>
            {isTop ? <circle cx={px} cy={py} r={r * 3.4} fill="url(#lab-star-glow)" /> : null}
            <circle cx={px} cy={py} r={r} fill={color}>
              {isTop ? (
                <animate
                  attributeName="r"
                  values={`${r};${r * 1.18};${r}`}
                  dur="2.6s"
                  repeatCount="indefinite"
                />
              ) : null}
            </circle>
            <text x={px} y={py - r - 8} textAnchor="middle" className="star-label">
              {region.code}
            </text>
            <text x={px} y={py + r + 14} textAnchor="middle" className="star-delta">
              {typeof region.delta7d === 'number' ? fmtSignedPct(region.delta7d) : '—'}
            </text>
            <title>{region.name} · Δ7d {typeof region.delta7d === 'number' ? fmtSignedPct(region.delta7d) : '—'}</title>
          </g>
        );
      })}
    </svg>
  );
};

export default AtlasConstellation;
