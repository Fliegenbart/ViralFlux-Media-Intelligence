import React, { useMemo, useState } from 'react';
import { differenceInCalendarDays, parseISO } from 'date-fns';
import { geoMercator, geoPath } from 'd3-geo';

import deBundeslaenderGeo from '../../assets/maps/de-bundeslaender.geo.json';
import { WaveRadarRegion, WaveRadarResponse } from '../../types/media';
import { formatDateShort } from './cockpitUtils';

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

function parseDate(value?: string | null): Date | null {
  if (!value) return null;
  try {
    return parseISO(value);
  } catch {
    return null;
  }
}

function waveRankColor(region: WaveRadarRegion | undefined, maxRank: number): string {
  if (!region?.wave_rank) return 'rgba(226, 232, 240, 0.72)';
  if (region.wave_rank === 1) return 'rgba(42, 161, 152, 0.92)';

  const normalized = 1 - ((region.wave_rank - 1) / Math.max(maxRank - 1, 1));
  const alpha = 0.26 + (normalized * 0.52);
  return `rgba(10, 132, 255, ${alpha.toFixed(3)})`;
}

interface Props {
  result: WaveRadarResponse | null;
  selectedBundesland: string | null;
  onSelectBundesland: (bundesland: string) => void;
}

const HistoricalWaveMap: React.FC<Props> = ({
  result,
  selectedBundesland,
  onSelectBundesland,
}) => {
  const [hoveredBundesland, setHoveredBundesland] = useState<string | null>(null);
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

  const regionByName = useMemo(() => {
    const entries = (result?.regions || []).map((region) => [region.bundesland, region] as const);
    return Object.fromEntries(entries);
  }, [result]);

  const firstOnsetDate = parseDate(result?.summary?.first_onset?.date);
  const maxRank = Math.max(
    ...((result?.regions || []).map((region) => Number(region.wave_rank || 0))),
    1,
  );
  const hoveredRegion = hoveredBundesland ? regionByName[hoveredBundesland] : undefined;
  const hoveredOffsetDays = hoveredRegion?.wave_start && firstOnsetDate
    ? Math.max(differenceInCalendarDays(parseDate(hoveredRegion.wave_start) || firstOnsetDate, firstOnsetDate), 0)
    : null;

  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox="0 0 420 460" style={{ width: '100%', maxHeight: 520 }}>
        <defs>
          <filter id="vf-wave-map-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#94a3b8" floodOpacity="0.2" />
          </filter>
        </defs>

        {shapes.map((shape) => {
          const region = regionByName[shape.name];
          const isSelected = selectedBundesland === shape.name;
          return (
            <g
              key={`${shape.name}-${shape.code || 'na'}`}
              onClick={() => onSelectBundesland(shape.name)}
              onMouseEnter={() => setHoveredBundesland(shape.name)}
              onMouseLeave={() => setHoveredBundesland(null)}
              style={{ cursor: 'pointer' }}
            >
              <path
                d={shape.d}
                fill={waveRankColor(region, maxRank)}
                stroke={isSelected ? 'var(--accent-violet)' : 'rgba(203, 213, 225, 0.92)'}
                strokeWidth={isSelected ? 2.6 : 1.1}
                filter="url(#vf-wave-map-shadow)"
                role="button"
                aria-label={`Historische Wellenkarte ${shape.name}`}
                data-testid={`historical-wave-map-${shape.code || shape.name}`}
              />
              {shape.code && !(shape.code in CALLOUT_TARGETS) ? (
                <>
                  <circle
                    cx={shape.cx}
                    cy={shape.cy - 5}
                    r={8.4}
                    fill="rgba(255,255,255,0.95)"
                    stroke={isSelected ? 'var(--accent-violet)' : 'rgba(203, 213, 225, 0.7)'}
                  />
                  <text x={shape.cx} y={shape.cy - 2.5} textAnchor="middle" fill="#334155" fontSize="8" fontWeight="700">
                    {shape.code}
                  </text>
                </>
              ) : null}
            </g>
          );
        })}

        {Object.entries(CALLOUT_TARGETS).map(([code, target]) => {
          const shape = shapes.find((item) => item.code === code);
          if (!shape) return null;
          const isSelected = selectedBundesland === shape.name;
          return (
            <g key={code} pointerEvents="none">
              <line x1={shape.cx} y1={shape.cy} x2={target.tx} y2={target.ty} stroke="rgba(71, 85, 105, 0.35)" strokeWidth="1" />
              <circle
                cx={target.tx}
                cy={target.ty}
                r={8.4}
                fill="rgba(255,255,255,0.95)"
                stroke={isSelected ? 'var(--accent-violet)' : 'rgba(203, 213, 225, 0.7)'}
              />
              <text x={target.tx} y={target.ty + 2.5} textAnchor="middle" fill="#334155" fontSize="8" fontWeight="700">
                {code}
              </text>
            </g>
          );
        })}
      </svg>

      {hoveredBundesland ? (
        <div
          style={{
            position: 'absolute',
            left: 16,
            bottom: 16,
            maxWidth: 250,
            padding: '12px 14px',
            borderRadius: 14,
            background: 'rgba(15, 23, 42, 0.92)',
            color: '#f8fafc',
            boxShadow: '0 18px 48px rgba(15, 23, 42, 0.24)',
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700 }}>{hoveredBundesland}</div>
          {hoveredRegion?.wave_rank ? (
            <>
              <div style={{ marginTop: 6, fontSize: 12, color: 'rgba(226, 232, 240, 0.92)' }}>
                Rang #{hoveredRegion.wave_rank} · Start {formatDateShort(hoveredRegion.wave_start)}
              </div>
              <div style={{ marginTop: 4, fontSize: 12, color: 'rgba(203, 213, 225, 0.88)' }}>
                {hoveredOffsetDays === 0
                  ? 'Hier begann die Welle zuerst.'
                  : `${hoveredOffsetDays} Tage nach dem ersten Start sichtbar.`}
              </div>
            </>
          ) : (
            <div style={{ marginTop: 6, fontSize: 12, color: 'rgba(226, 232, 240, 0.92)' }}>
              In dieser Saison kein klarer Wellenstart ueber der gewaelten Schwelle.
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
};

export default HistoricalWaveMap;
