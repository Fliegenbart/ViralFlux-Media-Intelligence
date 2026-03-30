import React, { useMemo, useState } from 'react';

import { OPERATOR_LABELS } from '../../constants/operatorLabels';
import { REGION_MAP_SHAPES } from './regionMapShapes';

export interface RegionMapRegion {
  region_id: string;
  region_name: string;
  decision_stage: 'activate' | 'prepare' | 'watch';
  signal_score?: number;
}

interface Props {
  regions: RegionMapRegion[];
  selectedRegion: string | null;
  onRegionClick: (region_id: string) => void;
}

function formatStage(stage: RegionMapRegion['decision_stage']): string {
  if (stage === 'activate') return 'Activate';
  if (stage === 'prepare') return 'Prepare';
  return 'Watch';
}

function formatSignalScore(score?: number): string {
  if (score == null || Number.isNaN(score)) return '—';
  const normalized = score <= 1 ? score * 100 : score;
  return `${Math.round(normalized)}%`;
}

function stageFill(stage: RegionMapRegion['decision_stage']): string {
  if (stage === 'activate') return 'rgba(220, 38, 38, 0.15)';
  if (stage === 'prepare') return 'rgba(217, 119, 6, 0.12)';
  return 'rgba(5, 150, 105, 0.08)';
}

function stageStroke(stage: RegionMapRegion['decision_stage']): string {
  if (stage === 'activate') return 'rgba(220, 38, 38, 0.4)';
  if (stage === 'prepare') return 'rgba(217, 119, 6, 0.3)';
  return 'rgba(5, 150, 105, 0.2)';
}

const RegionMap: React.FC<Props> = ({ regions, selectedRegion, onRegionClick }) => {
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);
  const [focusedRegion, setFocusedRegion] = useState<string | null>(null);

  const regionsById = useMemo(() => {
    const map = new Map<string, RegionMapRegion>();
    regions.forEach((region) => {
      map.set(region.region_id, region);
    });
    return map;
  }, [regions]);

  const activeRegionId = hoveredRegion || focusedRegion;
  const activeRegion = activeRegionId ? regionsById.get(activeRegionId) || null : null;

  return (
    <div className="region-map" data-testid="region-map">
      <svg
        viewBox="0 0 420 460"
        className="region-map__svg"
        role="img"
        aria-label="Deutschlandkarte mit Bundesländern"
      >
        <defs>
          <filter id="region-map-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="0" stdDeviation="2" floodColor="var(--color-primary)" floodOpacity="0.2" />
          </filter>
        </defs>

        {REGION_MAP_SHAPES.map((shape) => {
          const region = regionsById.get(shape.code);
          const decisionStage = region?.decision_stage || 'watch';
          const regionName = region?.region_name || shape.name;
          const selected = selectedRegion === shape.code;
          const hovered = hoveredRegion === shape.code;
          const focused = focusedRegion === shape.code;
          const highlighted = selected || hovered || focused;
          const ariaLabel = `${regionName}, ${formatStage(decisionStage)}, ${OPERATOR_LABELS.ranking_signal} ${formatSignalScore(region?.signal_score)}`;

          return (
            <path
              key={shape.code}
              d={shape.d}
              role="button"
              tabIndex={0}
              data-testid={`region-map-${shape.code}`}
              data-stage={decisionStage}
              data-selected={selected ? 'true' : 'false'}
              aria-label={ariaLabel}
              aria-pressed={selected}
              fill={stageFill(decisionStage)}
              stroke={highlighted ? 'var(--color-primary)' : 'var(--border-color, #e5e5e5)'}
              strokeWidth={selected ? 2 : highlighted ? 1.5 : 0.75}
              filter={selected ? 'url(#region-map-glow)' : undefined}
              className="region-map__path"
              onClick={() => onRegionClick(shape.code)}
              onMouseEnter={() => setHoveredRegion(shape.code)}
              onMouseLeave={() => setHoveredRegion(null)}
              onFocus={() => setFocusedRegion(shape.code)}
              onBlur={() => setFocusedRegion(null)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onRegionClick(shape.code);
                }
              }}
            />
          );
        })}
      </svg>

      {activeRegion && (
        <div className="region-map__tooltip" role="status" aria-live="polite">
          <strong>{activeRegion.region_name}</strong>
          <span>Stage: {formatStage(activeRegion.decision_stage)}</span>
          <span>{OPERATOR_LABELS.ranking_signal}: {formatSignalScore(activeRegion.signal_score)}</span>
        </div>
      )}
    </div>
  );
};

export default RegionMap;
