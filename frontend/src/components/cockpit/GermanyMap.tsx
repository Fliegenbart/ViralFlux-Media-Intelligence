import React, { useMemo, useState } from 'react';
import { geoMercator, geoPath } from 'd3-geo';

import deBundeslaenderGeo from '../../assets/maps/de-bundeslaender.geo.json';
import { MapRegion } from './types';
import {
  formatPercent,
  metricContractBadge,
  metricContractDisplayLabel,
  metricContractNote,
  primarySignalScore,
} from './cockpitUtils';

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

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value <= 1 ? value * 100 : value;
  return formatPercent(pct, digits);
}

function hasInsufficientEvidence(region?: MapRegion): boolean {
  if (!region) return true;
  const sourceCount = region.source_trace?.length || 0;
  const driverCount = region.signal_drivers?.length || 0;
  const signal = primarySignalScore(region);
  return signal <= 0 || (sourceCount < 2 && driverCount === 0);
}

function regionColor(region?: MapRegion): string {
  if (!region) return 'rgba(226, 232, 240, 0.7)';
  if (hasInsufficientEvidence(region)) return 'rgba(148, 163, 184, 0.22)';

  const signalScore = primarySignalScore(region);
  const normalized = signalScore <= 1 ? signalScore : signalScore / 100;
  const alpha = Math.max(0.24, Math.min(0.78, normalized));
  return `rgba(27, 83, 155, ${alpha})`;
}

function evidenceLabel(region?: MapRegion): string {
  if (!region || hasInsufficientEvidence(region)) return 'Zu wenig Evidenz';
  const sourceCount = region.source_trace?.length || 0;
  if (sourceCount >= 2) return 'Mehrere Quellen';
  return 'Erste Evidenz';
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
  const hoveredSignalLabel = metricContractDisplayLabel(hovered?.field_contracts, 'signal_score', 'Signal-Score');
  const hoveredSignalBadge = metricContractBadge(hovered?.field_contracts, 'signal_score', 'Kennzahl');
  const hoveredSignalNote = metricContractNote(
    hovered?.field_contracts,
    'signal_score',
    'Hilft beim Vergleichen und Priorisieren, ist aber keine Eintrittswahrscheinlichkeit.',
  );

  return (
    <div className="vf-map-panel">
      <div className="vf-map-legend" aria-label="Legende Bundeslandkarte">
        <div className="vf-map-legend__title">Legende Bundeslandkarte</div>
        <div className="vf-map-legend__items">
          <span className="vf-map-legend__item">
            <span className="vf-map-legend__swatch vf-map-legend__swatch--signal" aria-hidden="true" />
            Event-Signal im Bundesland-Ranking
          </span>
          <span className="vf-map-legend__item">
            <span className="vf-map-legend__swatch vf-map-legend__swatch--selected" aria-hidden="true" />
            Ausgewähltes Bundesland
          </span>
          <span className="vf-map-legend__item">
            <span className="vf-map-legend__swatch vf-map-legend__swatch--evidence" aria-hidden="true" />
            Zu wenig Evidenz
          </span>
        </div>
        <p className="vf-map-legend__note">
          Bundesland-Level. Kein City-Forecast. Die Flächenfarbe zeigt nur Orientierung im Ranking, nicht punktgenaue Sicherheit.
        </p>
      </div>

      <svg viewBox="0 0 420 460" style={{ width: '100%', maxHeight: 520 }} role="img" aria-label="Deutschlandkarte auf Bundesland-Level">
        <defs>
          <filter id="vf-map-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#94a3b8" floodOpacity="0.2" />
          </filter>
          <pattern id="vf-map-pattern-evidence" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="8" stroke="rgba(100, 116, 139, 0.28)" strokeWidth="3" />
          </pattern>
        </defs>

        {shapes.map((shape) => {
          const code = shape.code;
          const region = code ? regions[code] : undefined;
          const isSelected = Boolean(code && selectedRegion === code);
          const isHovered = Boolean(code && hoveredRegion === code);
          const insufficientEvidence = hasInsufficientEvidence(region);
          const interactionLabel = `${shape.name}, Bundesland-Level, ${evidenceLabel(region)}`;
          return (
            <g
              key={`${shape.name}-${shape.code || 'na'}`}
              onClick={() => code && region && onSelectRegion(code)}
              onMouseEnter={() => code && region && setHoveredRegion(code)}
              onMouseLeave={() => setHoveredRegion(null)}
              onFocus={() => code && region && setHoveredRegion(code)}
              onBlur={() => setHoveredRegion(null)}
              onKeyDown={(event) => {
                if ((event.key === 'Enter' || event.key === ' ') && code && region) {
                  event.preventDefault();
                  onSelectRegion(code);
                }
              }}
              style={{ cursor: code && region ? 'pointer' : 'default' }}
              role={code && region ? 'button' : undefined}
              tabIndex={code && region ? 0 : -1}
              aria-label={interactionLabel}
              aria-pressed={isSelected}
            >
              <path
                d={shape.d}
                fill={insufficientEvidence ? 'url(#vf-map-pattern-evidence)' : regionColor(region)}
                stroke={isSelected ? '#0f4c6e' : isHovered ? 'rgba(15, 76, 110, 0.64)' : 'rgba(203, 213, 225, 0.9)'}
                strokeWidth={isSelected ? 3 : isHovered ? 2 : 1.1}
                filter="url(#vf-map-shadow)"
              />
              {!insufficientEvidence && (
                <path
                  d={shape.d}
                  fill={regionColor(region)}
                  opacity={isSelected ? 1 : 0.9}
                  pointerEvents="none"
                />
              )}
              {code && !(code in CALLOUT_TARGETS) && (
                <>
                  <circle
                    cx={shape.cx}
                    cy={shape.cy - 5}
                    r={8.4}
                    fill={isSelected ? '#0f4c6e' : 'rgba(255,255,255,0.95)'}
                    stroke={isSelected ? '#0f4c6e' : 'rgba(203, 213, 225, 0.7)'}
                  />
                  <text x={shape.cx} y={shape.cy - 2.5} textAnchor="middle" fill={isSelected ? '#f8fafc' : '#334155'} fontSize="8" fontWeight="700">
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
              <circle
                cx={target.tx}
                cy={target.ty}
                r={8.4}
                fill={selectedRegion === code ? '#0f4c6e' : 'rgba(255,255,255,0.95)'}
                stroke={selectedRegion === code ? '#0f4c6e' : 'rgba(203, 213, 225, 0.7)'}
              />
              <text x={target.tx} y={target.ty + 2.5} textAnchor="middle" fill={selectedRegion === code ? '#f8fafc' : '#334155'} fontSize="8" fontWeight="700">
                {code}
              </text>
            </g>
          );
        })}
      </svg>

      {hoveredRegion && hovered && (
        <div className="vf-map-tooltip">
          <div style={{ fontSize: 13, fontWeight: 700 }}>{hovered.name}</div>
          <div style={{ marginTop: 6, fontSize: 12, color: 'rgba(226, 232, 240, 0.92)' }}>
            Bundesland-Level · {hoveredSignalLabel} {formatFractionPercent(primarySignalScore(hovered), 0)}
          </div>
          <div style={{ marginTop: 4, fontSize: 12, color: 'rgba(203, 213, 225, 0.88)' }}>
            Trend {hovered.trend} · Veränderung {formatPercent(hovered.change_pct || 0, 1)}
          </div>
          <div style={{ marginTop: 6, fontSize: 11, color: 'rgba(191, 219, 254, 0.86)' }}>
            {evidenceLabel(hovered)} · Kein City-Forecast
          </div>
          <div style={{ marginTop: 6, fontSize: 11, color: 'rgba(191, 219, 254, 0.86)' }}>
            {hoveredSignalBadge}: {hoveredSignalNote}
          </div>
        </div>
      )}
    </div>
  );
};

export default GermanyMap;
