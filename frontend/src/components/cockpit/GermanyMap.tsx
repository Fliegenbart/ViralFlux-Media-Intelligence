import React, { useMemo, useState } from 'react';
import { geoMercator, geoPath } from 'd3-geo';

import deBundeslaenderGeo from '../../assets/maps/de-bundeslaender.geo.json';
import { MapRegion } from './types';
import { formatPercent, metricContractLabel, primarySignalScore } from './cockpitUtils';

interface GeoBundeslandFeature {
  type: 'Feature';
  properties?: { code?: string; name?: string };
  geometry: unknown;
}

interface GeoBundeslandCollection {
  type: 'FeatureCollection';
  features: GeoBundeslandFeature[];
}

interface GeoBundeslandShape {
  code?: string;
  name: string;
  d: string;
  cx: number;
  cy: number;
}

const BUNDESLAND_NAME_TO_CODE: Record<string, string> = {
  'Baden-Württemberg': 'BW',
  Bayern: 'BY',
  Berlin: 'BE',
  Brandenburg: 'BB',
  Bremen: 'HB',
  Hamburg: 'HH',
  Hessen: 'HE',
  'Mecklenburg-Vorpommern': 'MV',
  Niedersachsen: 'NI',
  'Nordrhein-Westfalen': 'NW',
  'Rheinland-Pfalz': 'RP',
  Saarland: 'SL',
  Sachsen: 'SN',
  'Sachsen-Anhalt': 'ST',
  'Schleswig-Holstein': 'SH',
  Thüringen: 'TH',
};

const CALLOUT_TARGETS: Record<string, { tx: number; ty: number }> = {
  HH: { tx: 385, ty: 52 },
  BE: { tx: 395, ty: 138 },
  HB: { tx: 385, ty: 92 },
};

const GEO = deBundeslaenderGeo as GeoBundeslandCollection;

function regionColor(region?: MapRegion): string {
  if (!region) return 'rgba(226, 232, 240, 0.7)';
  const signalScore = primarySignalScore(region);
  const alpha = Math.max(0.18, Math.min(0.78, signalScore / 100));
  return `rgba(27, 83, 155, ${alpha})`;
}

interface Props {
  regions: Record<string, MapRegion>;
  selectedRegion: string | null;
  onSelectRegion: (code: string) => void;
}

const GermanyMap: React.FC<Props> = ({ regions, selectedRegion, onSelectRegion }) => {
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);
  const projection = useMemo(
    () => geoMercator().fitSize([420, 460], GEO as never),
    [],
  );

  const shapes = useMemo(() => {
    const pathBuilder = geoPath(projection);
    return GEO.features
      .map((feature) => {
        const props = feature.properties || {};
        const fallbackCode = props.name ? BUNDESLAND_NAME_TO_CODE[props.name] : undefined;
        const code = (props.code || fallbackCode || '').toUpperCase() || undefined;
        const d = pathBuilder(feature as never);
        if (!d) return null;
        const [cx, cy] = pathBuilder.centroid(feature as never);
        if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null;
        return { code, name: props.name || code || 'Unbekannt', d, cx, cy } as GeoBundeslandShape;
      })
      .filter((shape): shape is GeoBundeslandShape => Boolean(shape));
  }, [projection]);

  const hovered = hoveredRegion ? regions[hoveredRegion] : null;
  const hoveredSignalLabel = metricContractLabel(hovered?.field_contracts, 'signal_score', 'Signal-Score');

  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox="0 0 420 460" style={{ width: '100%', maxHeight: 560 }}>
        <defs>
          <filter id="vf-map-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#94a3b8" floodOpacity="0.2" />
          </filter>
        </defs>

        <rect x="0" y="0" width="420" height="460" rx="22" fill="rgba(255, 255, 255, 0.68)" />

        {shapes.map((shape) => {
          const code = shape.code;
          const region = code ? regions[code] : undefined;
          const isSelected = Boolean(code && selectedRegion === code);
          return (
            <g
              key={`${shape.name}-${shape.code || 'na'}`}
              onClick={() => code && region && onSelectRegion(code)}
              onMouseEnter={() => code && region && setHoveredRegion(code)}
              onMouseLeave={() => setHoveredRegion(null)}
              style={{ cursor: code && region ? 'pointer' : 'default' }}
            >
              <path
                d={shape.d}
                fill={regionColor(region)}
                stroke={isSelected ? 'var(--accent-violet)' : 'rgba(203, 213, 225, 0.9)'}
                strokeWidth={isSelected ? 2.4 : 1.1}
                filter="url(#vf-map-shadow)"
              />
              {code && !(code in CALLOUT_TARGETS) && (
                <>
                  <circle
                    cx={shape.cx}
                    cy={shape.cy - 5}
                    r={8.4}
                    fill="rgba(255,255,255,0.95)"
                    stroke={isSelected ? 'var(--accent-violet)' : 'rgba(203, 213, 225, 0.7)'}
                  />
                  <text x={shape.cx} y={shape.cy - 2.5} textAnchor="middle" fill="#334155" fontSize="8" fontWeight="700">
                    {code}
                  </text>
                </>
              )}
            </g>
          );
        })}

        {Object.entries(CALLOUT_TARGETS).map(([code, target]) => {
          const shape = shapes.find((item) => item.code === code);
          if (!shape) return null;
          return (
            <g key={code} pointerEvents="none">
              <line x1={shape.cx} y1={shape.cy} x2={target.tx} y2={target.ty} stroke="rgba(71, 85, 105, 0.35)" strokeWidth="1" />
              <circle cx={target.tx} cy={target.ty} r={8.4} fill="rgba(255,255,255,0.95)" stroke="rgba(203, 213, 225, 0.7)" />
              <text x={target.tx} y={target.ty + 2.5} textAnchor="middle" fill="#334155" fontSize="8" fontWeight="700">
                {code}
              </text>
            </g>
          );
        })}
      </svg>

      {hoveredRegion && hovered && (
        <div
          style={{
            position: 'absolute',
            left: 16,
            bottom: 16,
            maxWidth: 240,
            padding: '12px 14px',
            borderRadius: 14,
            background: 'rgba(15, 23, 42, 0.92)',
            color: '#f8fafc',
            boxShadow: '0 18px 48px rgba(15, 23, 42, 0.24)',
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700 }}>{hovered.name}</div>
          <div style={{ marginTop: 6, fontSize: 12, color: 'rgba(226, 232, 240, 0.92)' }}>
            {hoveredSignalLabel} {formatPercent(primarySignalScore(hovered))}
          </div>
          <div style={{ marginTop: 4, fontSize: 12, color: 'rgba(203, 213, 225, 0.88)' }}>
            Trend {hovered.trend} · Veränderung {formatPercent(hovered.change_pct || 0, 1)}
          </div>
        </div>
      )}
    </div>
  );
};

export default GermanyMap;
