import React, { useMemo, useState } from 'react';
import { geoMercator, geoPath } from 'd3-geo';

import deBundeslaenderGeo from '../../assets/maps/de-bundeslaender.geo.json';
import { MapRegion } from './types';
import {
  formatPercent,
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
  if (!region) return '#f1f5f9';
  if (hasInsufficientEvidence(region)) return '#f1f5f9';

  const prob = region.impact_probability ?? primarySignalScore(region);
  const normalized = prob <= 1 ? prob : prob / 100;

  if (normalized > 0.7) return '#ef4444';
  if (normalized > 0.5) return '#f97316';
  if (normalized > 0.3) return '#eab308';
  if (normalized > 0.1) return '#84cc16';
  return '#22c55e';
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
  showProbability?: boolean;
  topRegionCode?: string | null;
}

const GermanyMap: React.FC<Props> = ({ regions, selectedRegion, onSelectRegion, showProbability, topRegionCode }) => {
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

  return (
    <div className="vf-map-panel">
      <div className="vf-map-legend" aria-label="Legende">
        <span className="vf-map-legend__item"><span className="vf-map-legend__swatch vf-map-legend__swatch--high" aria-hidden="true" />Hoch</span>
        <span className="vf-map-legend__item"><span className="vf-map-legend__swatch vf-map-legend__swatch--mid" aria-hidden="true" />Mittel</span>
        <span className="vf-map-legend__item"><span className="vf-map-legend__swatch vf-map-legend__swatch--low" aria-hidden="true" />Niedrig</span>
        <span className="vf-map-legend__item"><span className="vf-map-legend__swatch vf-map-legend__swatch--evidence" aria-hidden="true" />Keine Daten</span>
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
              className={[
                'vf-map-region',
                isHovered && 'vf-map-region--hover',
                isSelected && 'vf-map-region--selected',
                code === topRegionCode && !insufficientEvidence && 'region-map__group--pulse',
              ].filter(Boolean).join(' ')}
              onClick={() => code && region && onSelectRegion(code)}
              onMouseEnter={() => code && setHoveredRegion(code)}
              onMouseLeave={() => setHoveredRegion(null)}
              onFocus={() => code && setHoveredRegion(code)}
              onBlur={() => setHoveredRegion(null)}
              onKeyDown={(event) => {
                if ((event.key === 'Enter' || event.key === ' ') && code && region) {
                  event.preventDefault();
                  onSelectRegion(code);
                }
              }}
              style={{
                cursor: code ? 'pointer' : 'default',
                transformOrigin: `${shape.cx}px ${shape.cy}px`,
              }}
              role={code ? 'button' : undefined}
              tabIndex={code ? 0 : -1}
              aria-label={interactionLabel}
              aria-pressed={isSelected}
            >
              <path
                className="vf-map-region__path"
                d={shape.d}
                fill={insufficientEvidence ? '#f1f5f9' : regionColor(region)}
                stroke={isSelected ? 'var(--color-primary)' : isHovered ? 'rgba(99, 102, 241, 0.5)' : 'rgba(203, 213, 225, 0.6)'}
                strokeWidth={isSelected ? 2.5 : isHovered ? 1.8 : 0.8}
              />
              {code && !(code in CALLOUT_TARGETS) && (
                <>
                  <circle
                    cx={shape.cx}
                    cy={showProbability && region?.impact_probability ? shape.cy - 9 : shape.cy - 5}
                    r={9}
                    fill={insufficientEvidence ? '#f1f5f9' : regionColor(region)}
                    stroke="rgba(255,255,255,0.8)"
                    strokeWidth="1.5"
                  />
                  <text
                    x={shape.cx}
                    y={showProbability && region?.impact_probability ? shape.cy - 6.5 : shape.cy - 2.5}
                    textAnchor="middle"
                    fill="#fff"
                    fontSize="8"
                    fontWeight="700"
                  >
                    {code}
                  </text>
                  {showProbability && region?.impact_probability != null && region.impact_probability > 0 && (
                    <text
                      x={shape.cx}
                      y={shape.cy + 5}
                      textAnchor="middle"
                      fill={region.impact_probability > 0.7 ? 'var(--status-danger)' : region.impact_probability > 0.4 ? 'var(--status-warning)' : 'var(--text-muted)'}
                      fontSize="9"
                      fontWeight="700"
                    >
                      {formatFractionPercent(region.impact_probability, 0)}
                    </text>
                  )}
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
              <line x1={shape.cx} y1={shape.cy} x2={target.tx} y2={target.ty} stroke="rgba(99, 102, 241, 0.2)" strokeWidth="0.8" />
              <circle
                cx={target.tx}
                cy={target.ty}
                r={9}
                fill={regionColor(code ? regions[code] : undefined)}
                stroke="rgba(255,255,255,0.8)"
                strokeWidth="1.5"
              />
              <text x={target.tx} y={target.ty + 2.5} textAnchor="middle" fill="#fff" fontSize="8" fontWeight="700">
                {code}
              </text>
            </g>
          );
        })}
      </svg>

      {hoveredRegion && hovered && (
        <div className="vf-map-tooltip">
          <div className="vf-map-tooltip__name">{hovered.name}</div>
          {hovered.impact_probability != null && hovered.impact_probability > 0 && (
            <div className="vf-map-tooltip__probability">
              {formatFractionPercent(hovered.impact_probability, 0)} Wellenwahrscheinlichkeit
            </div>
          )}
          <div className="vf-map-tooltip__meta">
            Trend {hovered.trend} · {formatPercent(Math.abs(hovered.change_pct || 0), 1)} {(hovered.change_pct || 0) >= 0 ? '↑' : '↓'} WoW
          </div>
          <div className="vf-map-tooltip__stage">
            {hovered.decision_mode_label || evidenceLabel(hovered)}
          </div>
        </div>
      )}
    </div>
  );
};

export default GermanyMap;
