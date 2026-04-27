import React, { useMemo } from 'react';
import type { CockpitSnapshot } from '../types';
import { fmtSignedPct } from '../format';
import { DE_MAP } from './deMapData';

/**
 * AtlasChoropleth — 2026-04-23, ersetzt die 3D-Türme.
 *
 * Echte Deutschland-Karte (deutschlandGeoJSON, Public Domain). Bundesländer-
 * Flächen leuchten in kontinuierlicher HSL-Schattierung pro Δ7d-Wert.
 * Mini-BL (HB / HH / BE / SL) bekommen Leader-Linie nach außen, weil
 * ihre Fläche zu klein für Inline-Labels ist. Top-Riser: weißer Stroke
 * + starker pulsierender Glow. Alle anderen Riser pulsieren leichter
 * mit Geschwindigkeit proportional zur Stärke.
 */

const SMALL_OFFSET: Record<string, { dx: number; dy: number }> = {
  HB: { dx: -55, dy: -8 },    // Bremen — links rausziehen
  HH: { dx: 0, dy: -45 },     // Hamburg — nach oben
  BE: { dx: 50, dy: 5 },      // Berlin — nach rechts
  SL: { dx: -45, dy: 22 },    // Saarland — links unten
};

// 2026-04-23 v2.1 — Kontinuierliche HSL-Interpolation statt 4 Bins.
// Neutral-dunkel (hsl 220, 5%, 22%) → Saturated Red bzw. Green auf ±30 %.
// |delta| zwischen 0 und 0.30 wird nicht-linear auf HSL-Space gemappt,
// sodass auch kleine Deltas (z.B. +4 %) farblich spürbar werden, ohne
// die Karte zu überwältigen.
function trendFill(delta: number | null | undefined): string {
  if (delta == null || !Number.isFinite(delta)) return 'hsl(220, 5%, 22%)';
  const clamped = Math.max(-0.30, Math.min(0.30, delta));
  const t = Math.abs(clamped) / 0.30; // 0..1
  if (clamped >= 0) {
    // Riser — rot: Hue rutscht minimal von 8° nach 0°, Sättigung + Lightness rampen.
    const h = Math.round(8 - t * 8);
    const s = Math.round(20 + t * 65);
    const l = Math.round(28 + t * 22);
    return `hsl(${h}, ${s}%, ${l}%)`;
  } else {
    // Faller — grün: Hue 140° → 155° (leicht smaragd), Sättigung/Lightness rampen.
    const h = Math.round(140 + t * 15);
    const s = Math.round(20 + t * 55);
    const l = Math.round(28 + t * 18);
    return `hsl(${h}, ${s}%, ${l}%)`;
  }
}

// Pulse-Dauer in Sekunden — je stärker der Riser, desto schneller.
// Faller & Flat: null = keine Animation.
function pulseDuration(delta: number | null | undefined): number | null {
  if (delta == null || !Number.isFinite(delta)) return null;
  if (delta >= 0.10) return 1.8;   // strong — schneller Puls
  if (delta >= 0.03) return 3.5;   // mild — ruhiger Puls
  return null;                      // flat / faller — kein Puls
}

export const AtlasChoropleth: React.FC<{ snapshot: CockpitSnapshot }> = ({
  snapshot,
}) => {
  const ranked = useMemo(() => {
    return [...snapshot.regions]
      .filter((r) => typeof r.delta7d === 'number')
      .sort((a, b) => (b.delta7d ?? 0) - (a.delta7d ?? 0));
  }, [snapshot.regions]);
  const topCode = ranked[0]?.code ?? null;

  const regionByCode = useMemo(() => {
    const m = new Map<string, (typeof snapshot.regions)[number]>();
    snapshot.regions.forEach((r) => m.set(r.code as string, r));
    return m;
  }, [snapshot.regions]);

  return (
    <svg
      className="atlas-choropleth"
      viewBox={DE_MAP.viewBox}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Deutschland-Karte mit Bundesländern in Trend-Farben"
    >
      {/* Bundesländer als gefüllte Polygone */}
      {Object.entries(DE_MAP.states).map(([code, state]) => {
        const region = regionByCode.get(code);
        const isTop = code === topCode;
        const pulse = pulseDuration(region?.delta7d);
        const classes = [
          'choropleth-state',
          isTop ? 'is-top' : '',
          pulse != null && !isTop ? 'is-pulsing' : '',
        ]
          .filter(Boolean)
          .join(' ');
        const pulseStyle = pulse != null
          ? ({ ['--pulse-duration']: `${pulse}s` } as React.CSSProperties)
          : undefined;
        return (
          <path
            key={`fill-${code}`}
            className={classes}
            style={pulseStyle}
            d={state.d}
            fill={trendFill(region?.delta7d)}
            stroke={isTop ? 'rgba(250, 250, 250, 0.95)' : 'rgba(250, 250, 250, 0.28)'}
            strokeWidth={isTop ? 1.8 : 0.5}
            strokeLinejoin="round"
          >
            <title>
              {state.name} · Δ7d{' '}
              {typeof region?.delta7d === 'number' ? fmtSignedPct(region.delta7d) : '—'}
            </title>
          </path>
        );
      })}

      {/* Labels — Code + Delta. Für Mini-BL versetzt + Leader-Line. */}
      {Object.entries(DE_MAP.states).map(([code, state]) => {
        const region = regionByCode.get(code);
        if (!region) return null;
        const offset = SMALL_OFFSET[code];
        const labelX = state.cx + (offset?.dx ?? 0);
        const labelY = state.cy + (offset?.dy ?? 0);
        const isTop = code === topCode;
        const deltaLabel =
          typeof region.delta7d === 'number' ? fmtSignedPct(region.delta7d) : '—';

        return (
          <g key={`lbl-${code}`} className={`choropleth-label-group ${isTop ? 'is-top' : ''}`}>
            {offset ? (
              <line
                x1={state.cx}
                y1={state.cy}
                x2={labelX}
                y2={labelY}
                stroke="rgba(250, 250, 250, 0.55)"
                strokeWidth={0.6}
                strokeDasharray="2 2"
              />
            ) : null}
            <text x={labelX} y={labelY - 2} textAnchor="middle" className="choropleth-code">
              {code}
            </text>
            <text x={labelX} y={labelY + 13} textAnchor="middle" className="choropleth-delta">
              {deltaLabel}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

export default AtlasChoropleth;
