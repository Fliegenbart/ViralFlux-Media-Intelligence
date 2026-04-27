import React, { useMemo } from 'react';
import type { CockpitSnapshot, Bundesland } from '../types';
import { fmtSignedPct } from '../format';

/**
 * AtlasHexgrid — 2026-04-23.
 *
 * Alternative zur 3D-Szene: 16 Bundesländer als Honeycomb-Tiles in
 * geo-approximierter Anordnung. Gleichgewichtig (Bayern dominiert
 * nicht visuell), modern (NPR-Election-/Bloomberg-Stil), in 2 Sekunden
 * lesbar.
 *
 * Encoding:
 *   Position  = Geographie (approximiert auf Honeycomb-Raster)
 *   Farbe     = 7-Tage-Trend (rot = Riser, grün = Faller, grau = flach)
 *   Outline   = Top-1-Riser bekommt schwarzen Stroke + Glow
 *   Linie     = Transfer-Vorschlag (FROM → TO der primaryRecommendation)
 */

interface Props {
  snapshot: CockpitSnapshot;
  topRiserCode: Bundesland | null;
  shiftFromCode: Bundesland | null;
  shiftToCode: Bundesland | null;
}

// Honeycomb-Position pro BL — geo-approximiert.
// (col, row) als logische Indizes; Pointy-Top-Layout mit Versatz pro Zeile.
const HEX_POS: Record<Bundesland, { col: number; row: number }> = {
  SH: { col: 1, row: 0 },
  MV: { col: 3, row: 0 },
  HB: { col: 0, row: 1 },
  HH: { col: 1, row: 1 },
  BB: { col: 3, row: 1 },
  NI: { col: 1, row: 2 },
  BE: { col: 3, row: 2 },
  NW: { col: 0, row: 3 },
  ST: { col: 1, row: 3 },
  SN: { col: 3, row: 3 },
  HE: { col: 1, row: 4 },
  TH: { col: 2, row: 4 },
  RP: { col: 0, row: 5 },
  SL: { col: 0, row: 6 },
  BW: { col: 1, row: 6 },
  BY: { col: 3, row: 6 },
};

// Pointy-Top-Hex: Höhe = 2·R, Breite = √3·R.
const HEX_RADIUS = 60;
const HEX_WIDTH = Math.sqrt(3) * HEX_RADIUS; // ≈ 104
const HEX_HEIGHT = 2 * HEX_RADIUS;            // 120
const COL_STRIDE = HEX_WIDTH;
const ROW_STRIDE = HEX_HEIGHT * 0.75;          // 90 (Pointy-Top vertical packing)
const PADDING = 32;

// Pointy-Top Hexagon-Pfad als SVG-points-Liste.
function hexPoints(cx: number, cy: number, r: number): string {
  const pts: string[] = [];
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 2;
    pts.push(`${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`);
  }
  return pts.join(' ');
}

// Trend → Farbe. Schwellen pragmatisch gewählt für 7-Tage-Delta.
function trendFill(delta: number | null | undefined): string {
  if (delta == null || !Number.isFinite(delta)) return '#52525B'; // zinc-600
  if (delta >= 0.10) return '#DC2626';   // strong riser (red-600)
  if (delta >= 0.03) return '#F97316';   // mild riser (orange-500)
  if (delta <= -0.05) return '#16A34A';  // faller (green-600)
  return '#71717A';                       // flat (zinc-500)
}

// Delta-Text-Farbe — auf dunklen Tiles immer paper, sonst angepasst.
const TEXT_FILL = '#FAFAFA';

export const AtlasHexgrid: React.FC<Props> = ({
  snapshot,
  topRiserCode,
  shiftFromCode,
  shiftToCode,
}) => {
  // Cells berechnen: (col, row) → (cx, cy) im SVG-Koordinatensystem.
  const cells = useMemo(() => {
    return snapshot.regions
      .map((r) => {
        const pos = HEX_POS[r.code as Bundesland];
        if (!pos) return null;
        // Ungerade Reihen versetzt um halbe Hex-Breite (Honeycomb).
        const xOffset = pos.row % 2 === 0 ? 0 : HEX_WIDTH / 2;
        const cx = PADDING + pos.col * COL_STRIDE + xOffset + HEX_WIDTH / 2;
        const cy = PADDING + pos.row * ROW_STRIDE + HEX_RADIUS;
        return { region: r, cx, cy };
      })
      .filter((c): c is NonNullable<typeof c> => c !== null);
  }, [snapshot.regions]);

  const maxCol = Math.max(...Object.values(HEX_POS).map((p) => p.col));
  const maxRow = Math.max(...Object.values(HEX_POS).map((p) => p.row));
  const svgWidth = (maxCol + 1) * COL_STRIDE + HEX_WIDTH + 2 * PADDING;
  const svgHeight = maxRow * ROW_STRIDE + HEX_HEIGHT + 2 * PADDING;

  const fromCell = cells.find((c) => c.region.code === shiftFromCode);
  const toCell = cells.find((c) => c.region.code === shiftToCode);

  return (
    <svg
      className="atlas-hexgrid"
      viewBox={`0 0 ${svgWidth} ${svgHeight}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Bundesländer-Frühsignal-Karte als Hexagon-Raster"
    >
      <defs>
        <marker
          id="hexgrid-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="#DC2626" />
        </marker>
      </defs>

      {/* Transfer-Linie zuerst rendern, damit Hexagons sie überlappen */}
      {fromCell && toCell && fromCell !== toCell ? (
        <line
          x1={fromCell.cx}
          y1={fromCell.cy}
          x2={toCell.cx}
          y2={toCell.cy}
          stroke="#DC2626"
          strokeWidth={3}
          strokeDasharray="6 4"
          markerEnd="url(#hexgrid-arrow)"
          opacity={0.85}
        />
      ) : null}

      {cells.map(({ region, cx, cy }) => {
        const isTop = region.code === topRiserCode;
        const isFrom = region.code === shiftFromCode;
        const isTo = region.code === shiftToCode;
        const fill = trendFill(region.delta7d);
        const deltaLabel =
          typeof region.delta7d === 'number' && Number.isFinite(region.delta7d)
            ? fmtSignedPct(region.delta7d)
            : '—';
        const cellClass = [
          'hex-cell',
          isTop ? 'is-top' : '',
          isFrom ? 'is-from' : '',
          isTo ? 'is-to' : '',
        ]
          .filter(Boolean)
          .join(' ');

        return (
          <g key={region.code} className={cellClass}>
            <polygon
              points={hexPoints(cx, cy, HEX_RADIUS)}
              fill={fill}
              stroke={isTop ? '#0A0A0F' : 'rgba(10, 10, 15, 0.18)'}
              strokeWidth={isTop ? 3 : 1}
            />
            <text
              x={cx}
              y={cy - 6}
              textAnchor="middle"
              className="hex-code"
              fill={TEXT_FILL}
            >
              {region.code}
            </text>
            <text
              x={cx}
              y={cy + 18}
              textAnchor="middle"
              className="hex-delta"
              fill={TEXT_FILL}
            >
              {deltaLabel}
            </text>
            <title>
              {region.name} · Δ7d {deltaLabel}
              {isTop ? ' · Top-Riser' : ''}
              {isFrom ? ' · Transfer-Quelle' : ''}
              {isTo ? ' · Transfer-Ziel' : ''}
            </title>
          </g>
        );
      })}
    </svg>
  );
};

export default AtlasHexgrid;
