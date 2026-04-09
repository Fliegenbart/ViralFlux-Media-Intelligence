import React, { useMemo, useState } from 'react';
import { geoMercator, geoPath } from 'd3-geo';

import deBundeslaenderGeo from '../../assets/maps/de-bundeslaender.geo.json';
import { MapRegion } from './types';
import {
  formatPercent,
  formatSignalScore,
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

const CITY_STATE_HIT_AREAS: Record<string, number> = {
  HH: 22,
  BE: 20,
  HB: 18,
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
  if (!region) return 'rgba(226, 232, 240, 0.5)';
  if (hasInsufficientEvidence(region)) return 'rgba(226, 232, 240, 0.5)';

  const prob = region.impact_probability ?? primarySignalScore(region);
  const normalized = prob <= 1 ? prob : prob / 100;

  if (normalized > 0.7) return '#dc2626';
  if (normalized > 0.5) return '#ea580c';
  if (normalized > 0.3) return '#d97706';
  if (normalized > 0.1) return '#16a34a';
  return '#15803d';
}

function evidenceLabel(region?: MapRegion): string {
  if (!region || hasInsufficientEvidence(region)) return 'Keine Evidenz';
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
  variant?: 'default' | 'radar';
}

function mapFocusMeta(region?: MapRegion): string {
  if (!region) return 'Noch keine belastbare Einordnung';

  const parts: string[] = [];
  const signalScore = primarySignalScore(region);
  if (signalScore > 0) {
    parts.push(`Signalwert ${formatSignalScore(signalScore)}`);
  }
  if (region.trend) {
    parts.push(`Trend ${region.trend}`);
  }
  if (region.change_pct != null && !Number.isNaN(region.change_pct)) {
    parts.push(`${formatPercent(region.change_pct, 1)} zur Vorwoche`);
  }

  return parts.join(' · ') || evidenceLabel(region);
}

const GermanyMap: React.FC<Props> = ({
  regions,
  selectedRegion,
  onSelectRegion,
  showProbability,
  topRegionCode,
  variant = 'default',
}) => {
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);
  const projection = useMemo(
    () => geoMercator().fitSize([470, 520], GEO as never),
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
  const focusCode = hoveredRegion || selectedRegion || topRegionCode || null;
  const focusRegion = focusCode ? regions[focusCode] : null;
  const focusLabel = focusCode === topRegionCode ? 'Stärkstes Signal auf der Karte' : 'Gerade im Fokus';
  const radarVariant = variant === 'radar';

  return (
    <div className={`vf-map-panel ${radarVariant ? 'vf-map-panel--radar' : ''}`}>
      {radarVariant && (
        <div className="vf-map-panel__status" aria-label="Kartenfokus">
          <span className="vf-map-panel__status-eyebrow">{focusLabel}</span>
          <div className="vf-map-panel__status-head">
            <strong>{focusRegion?.name || 'Deutschlandkarte'}</strong>
            <span className={`vf-map-panel__status-pill ${focusCode === topRegionCode ? 'is-top' : ''}`}>
              {focusCode === topRegionCode ? 'Top-Region' : 'Ausgewählt'}
            </span>
          </div>
          <span className="vf-map-panel__status-meta">
            {mapFocusMeta(focusRegion ?? undefined)}
          </span>
        </div>
      )}

      <div className="vf-map-legend" aria-label="Legende">
        <span className="vf-map-legend__item"><span className="vf-map-legend__swatch vf-map-legend__swatch--high" aria-hidden="true" />Stark</span>
        <span className="vf-map-legend__item"><span className="vf-map-legend__swatch vf-map-legend__swatch--mid" aria-hidden="true" />Mittel</span>
        <span className="vf-map-legend__item"><span className="vf-map-legend__swatch vf-map-legend__swatch--low" aria-hidden="true" />Leicht</span>
        <span className="vf-map-legend__item"><span className="vf-map-legend__swatch vf-map-legend__swatch--evidence" aria-hidden="true" />Keine Evidenz</span>
      </div>

      <svg viewBox="0 0 470 520" style={{ width: '100%', maxHeight: 620 }} role="img" aria-label="Deutschlandkarte auf Bundesland-Level">
        <defs>
          <filter id="vf-map-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#64748b" floodOpacity="0.22" />
          </filter>
          <pattern id="vf-map-pattern-evidence" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">
            <rect x="0" y="0" width="8" height="8" fill="rgba(226, 232, 240, 0.9)" />
            <line x1="0" y1="0" x2="0" y2="8" stroke="rgba(100, 116, 139, 0.5)" strokeWidth="2.6" />
          </pattern>
        </defs>

        {shapes.map((shape) => {
          const code = shape.code;
          const region = code ? regions[code] : undefined;
          const isSelected = Boolean(code && selectedRegion === code);
          const isHovered = Boolean(code && hoveredRegion === code);
          const isTop = Boolean(code && topRegionCode === code);
          const insufficientEvidence = hasInsufficientEvidence(region);
          const impactProbability = region?.impact_probability ?? null;
          const impactProbabilityValue = impactProbability ?? 0;
          const shouldShowProbability = Boolean(
            showProbability
            && impactProbability != null
            && (!radarVariant || isSelected || isTop || isHovered),
          );
          const badgeRadius = radarVariant ? ((isSelected || isTop) ? 12 : 8.5) : 10;
          const badgeFill = insufficientEvidence
            ? '#e2e8f0'
            : (radarVariant && !isSelected && !isTop ? 'rgba(255, 255, 255, 0.8)' : regionColor(region));
          const badgeStroke = radarVariant && !isSelected && !isTop
            ? 'rgba(71, 85, 105, 0.22)'
            : 'rgba(15, 23, 42, 0.58)';
          const badgeTextFill = insufficientEvidence
            ? '#475569'
            : (radarVariant && !isSelected && !isTop ? '#334155' : '#ffffff');
          const interactionLabel = `${shape.name}, Bundesland-Level, ${evidenceLabel(region)}`;
          return (
            <g
              key={`${shape.name}-${shape.code || 'na'}`}
              className={[
                'vf-map-region',
                isHovered && 'vf-map-region--hover',
                isSelected && 'vf-map-region--selected',
                isTop && !insufficientEvidence && 'vf-map-region--top',
                isTop && !insufficientEvidence && 'region-map__group--pulse',
                radarVariant && !isSelected && !isTop && 'vf-map-region--muted',
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
              {radarVariant && (isSelected || isTop) && (
                <path
                  className={`vf-map-region__halo ${isTop ? 'vf-map-region__halo--top' : 'vf-map-region__halo--selected'}`}
                  d={shape.d}
                />
              )}
              {code && code in CITY_STATE_HIT_AREAS && (
                <circle
                  className="vf-map-region__hit-area"
                  cx={shape.cx}
                  cy={shape.cy}
                  r={CITY_STATE_HIT_AREAS[code]}
                />
              )}
              <path
                className="vf-map-region__path"
                d={shape.d}
                fill={insufficientEvidence ? 'url(#vf-map-pattern-evidence)' : regionColor(region)}
                stroke={isSelected ? 'var(--color-primary)' : isHovered ? 'rgba(37, 99, 235, 0.6)' : 'rgba(71, 85, 105, 0.35)'}
                strokeWidth={isSelected ? 2.8 : isHovered ? 2.1 : 1.4}
              />
              {code && (
                <>
                  <circle
                    cx={shape.cx}
                    cy={showProbability ? shape.cy - 11 : shape.cy - 6}
                    r={badgeRadius}
                    fill={badgeFill}
                    stroke={badgeStroke}
                    strokeWidth={radarVariant && !isSelected && !isTop ? '1.2' : '1.6'}
                    opacity={radarVariant && !isSelected && !isTop ? 0.8 : 1}
                  />
                  <text
                    x={shape.cx}
                    y={showProbability ? shape.cy - 7.2 : shape.cy - 2.2}
                    textAnchor="middle"
                    fill={badgeTextFill}
                    fontSize={radarVariant && (isSelected || isTop) ? '9.5' : '9'}
                    fontWeight={radarVariant && !isSelected && !isTop ? '700' : '800'}
                    opacity={radarVariant && !isSelected && !isTop ? 0.9 : 1}
                  >
                    {code}
                  </text>
                  {shouldShowProbability && (
                    <text
                      x={shape.cx}
                      y={shape.cy + 6.5}
                      textAnchor="middle"
                      fill={impactProbabilityValue > 0.7 ? 'var(--status-danger)' : impactProbabilityValue > 0.4 ? 'var(--status-warning)' : 'var(--text-secondary)'}
                      fontSize="10"
                      fontWeight="800"
                    >
                      {formatFractionPercent(impactProbabilityValue, 0)}
                    </text>
                  )}
                </>
              )}
            </g>
          );
        })}
      </svg>

      {hoveredRegion && hovered && (
        <div className="vf-map-tooltip">
          <div className="vf-map-tooltip__name">{hovered.name}</div>
          {primarySignalScore(hovered) > 0 && (
            <div className="vf-map-tooltip__probability">
              {formatSignalScore(primarySignalScore(hovered))} Signalwert
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
