import React, { useMemo, useState } from 'react';
import type { RegionForecast, Bundesland } from '../../../pages/cockpit/types';
import { fmtSignedPct, fmtEurCompact } from '../../../pages/cockpit/format';

/**
 * Simplified schematic Germany map used in Tab A split-view.
 *
 * We do *not* use real TopoJSON here because the existing GermanyMap.tsx
 * component is already wired to d3-geo and can be swapped in as a
 * drop-in replacement once the visual style is approved. The schematic
 * tile layout keeps the demo file-count low and the editorial look clean.
 *
 * Coordinates are a stylised hexagonal grid, loosely matching the
 * geographic position of each Bundesland (north = small y).
 */
interface TileDef { code: Bundesland; x: number; y: number; w?: number; h?: number; }
const TILES: TileDef[] = [
  { code: 'SH', x: 3, y: 0, w: 2, h: 1 },
  { code: 'HH', x: 3, y: 1 },
  { code: 'MV', x: 4, y: 1, w: 2 },
  { code: 'HB', x: 2, y: 2 },
  { code: 'NI', x: 3, y: 2, w: 2 },
  { code: 'BE', x: 5, y: 2 },
  { code: 'BB', x: 5, y: 3 },
  { code: 'NW', x: 1, y: 3, w: 2 },
  { code: 'ST', x: 4, y: 3 },
  { code: 'SN', x: 5, y: 4 },
  { code: 'HE', x: 2, y: 4 },
  { code: 'TH', x: 3, y: 4 },
  { code: 'RP', x: 1, y: 5 },
  { code: 'BW', x: 2, y: 5, h: 2 },
  { code: 'BY', x: 3, y: 5, w: 2, h: 2 },
  { code: 'SL', x: 1, y: 6 },
];

interface Props {
  regions: RegionForecast[];
  mode: 'rising' | 'falling';
  title: string;
  kicker: string;
  caption: string;
}

function palette(mode: 'rising' | 'falling', delta7d: number | null): string {
  // null => no regional forecast for this BL, paint neutral.
  if (delta7d === null || !Number.isFinite(delta7d)) return 'var(--peix-card-dim)';
  if (mode === 'rising') {
    if (delta7d <= 0) return 'var(--peix-card-dim)';
    if (delta7d < 0.10) return 'var(--peix-rising-1)';
    if (delta7d < 0.18) return 'var(--peix-rising-2)';
    if (delta7d < 0.26) return 'var(--peix-rising-3)';
    return 'var(--peix-rising-4)';
  } else {
    if (delta7d >= 0) return 'var(--peix-card-dim)';
    if (delta7d > -0.06) return 'var(--peix-falling-1)';
    if (delta7d > -0.12) return 'var(--peix-falling-2)';
    return 'var(--peix-falling-3)';
  }
}

const CELL = 52;
const GAP = 4;

export const GermanyChoropleth: React.FC<Props> = ({ regions, mode, title, kicker, caption }) => {
  const [hover, setHover] = useState<RegionForecast | null>(null);

  const byCode = useMemo(() => {
    const m = new Map<Bundesland, RegionForecast>();
    regions.forEach((r) => m.set(r.code, r));
    return m;
  }, [regions]);

  if (regions.length === 0) {
    return (
      <div className="peix-figure">
        <header style={{ marginBottom: 8 }}>
          <div className="peix-kicker">{kicker}</div>
          <h3 className="peix-headline" style={{ marginTop: 4 }}>{title}</h3>
        </header>
        <p className="peix-body" style={{ color: 'var(--peix-ink-soft)' }}>
          Für den aktuellen Virus-Scope liegen keine regionalen Forecasts vor.
          Siehe Modell-Status oben — entweder existiert kein regionales Modell
          oder das Panel hat aktuell keine ausreichenden Features.
        </p>
      </div>
    );
  }

  const width = 6 * (CELL + GAP);
  const height = 7 * (CELL + GAP);

  return (
    <div className="peix-figure">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
        <div>
          <div className="peix-kicker">{kicker}</div>
          <h3 className="peix-headline" style={{ marginTop: 4 }}>{title}</h3>
        </div>
        <span className={`peix-pill ${mode === 'rising' ? 'warm' : 'cool'}`}>
          {mode === 'rising' ? '▲ Welle steigt' : '▼ Welle fällt'}
        </span>
      </header>

      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={title} style={{ minHeight: 280 }}>
        {TILES.map((t) => {
          const region = byCode.get(t.code);
          if (!region) return null;
          const x = t.x * (CELL + GAP);
          const y = t.y * (CELL + GAP);
          const w = (t.w || 1) * CELL + ((t.w || 1) - 1) * GAP;
          const h = (t.h || 1) * CELL + ((t.h || 1) - 1) * GAP;
          const fill = palette(mode, region.delta7d);
          const delta = region.delta7d;
          const dim =
            delta === null || !Number.isFinite(delta)
              ? true
              : mode === 'rising'
              ? delta <= 0
              : delta >= 0;
          return (
            <g
              key={t.code}
              onMouseEnter={() => setHover(region)}
              onMouseLeave={() => setHover(null)}
              style={{ cursor: 'pointer', opacity: dim ? 0.35 : 1, transition: 'opacity 200ms' }}
            >
              <rect x={x} y={y} width={w} height={h} rx="6" ry="6" fill={fill} stroke="var(--peix-line)" strokeWidth="1" />
              <text x={x + 8} y={y + 16} fontSize="10" fontFamily="var(--peix-font-mono)" fill="var(--peix-ink-soft)" fontWeight="600">
                {t.code}
              </text>
              <text x={x + 8} y={y + h - 10} fontSize="11" fontFamily="var(--peix-font-sans)" fontWeight="600"
                    fill={dim ? 'var(--peix-ink-mute)' : 'var(--peix-ink)'}>
                {fmtSignedPct(region.delta7d)}
              </text>
            </g>
          );
        })}
      </svg>

      <footer style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
        <figcaption style={{ fontFamily: 'var(--peix-font-display)', fontStyle: 'italic', fontSize: 13, color: 'var(--peix-ink-soft)', flex: 1 }}>
          {hover
            ? `${hover.name} · ${fmtSignedPct(hover.delta7d)} · Signalstärke ${hover.pRising !== null ? hover.pRising.toFixed(2) : '—'} · Spend ${hover.currentSpendEur !== null ? fmtEurCompact(hover.currentSpendEur) : '—'}`
            : caption}
        </figcaption>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--peix-font-mono)', fontSize: 10, color: 'var(--peix-ink-mute)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
          <span>{mode === 'rising' ? 'niedrig' : 'stabil'}</span>
          <span style={{
            display: 'inline-block', width: 120, height: 6, borderRadius: 3,
            background: mode === 'rising'
              ? 'linear-gradient(90deg, var(--peix-rising-1), var(--peix-rising-2), var(--peix-rising-3), var(--peix-rising-4))'
              : 'linear-gradient(90deg, var(--peix-falling-1), var(--peix-falling-2), var(--peix-falling-3))',
          }} />
          <span>{mode === 'rising' ? 'hoch' : 'rückläufig'}</span>
        </div>
      </footer>
    </div>
  );
};

export default GermanyChoropleth;
