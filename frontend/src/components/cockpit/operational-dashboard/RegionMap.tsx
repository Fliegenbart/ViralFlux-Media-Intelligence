import React, { useMemo, useState } from 'react';

import { OPERATOR_LABELS } from '../../../constants/operatorLabels';
import { formatPercent } from '../cockpitUtils';
import { OperationalRegionRow } from './types';

interface RegionTile {
  code: string;
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

const REGION_TILES: RegionTile[] = [
  { code: 'SH', name: 'Schleswig-Holstein', x: 128, y: 18, width: 96, height: 46 },
  { code: 'HH', name: 'Hamburg', x: 168, y: 70, width: 28, height: 24 },
  { code: 'MV', name: 'Mecklenburg-Vorpommern', x: 236, y: 38, width: 118, height: 52 },
  { code: 'HB', name: 'Bremen', x: 122, y: 102, width: 28, height: 24 },
  { code: 'NI', name: 'Niedersachsen', x: 78, y: 108, width: 136, height: 84 },
  { code: 'BE', name: 'Berlin', x: 264, y: 124, width: 28, height: 24 },
  { code: 'BB', name: 'Brandenburg', x: 298, y: 110, width: 92, height: 74 },
  { code: 'ST', name: 'Sachsen-Anhalt', x: 214, y: 156, width: 78, height: 58 },
  { code: 'NW', name: 'Nordrhein-Westfalen', x: 30, y: 174, width: 92, height: 84 },
  { code: 'HE', name: 'Hessen', x: 118, y: 210, width: 82, height: 74 },
  { code: 'TH', name: 'Thüringen', x: 212, y: 222, width: 78, height: 58 },
  { code: 'SN', name: 'Sachsen', x: 294, y: 232, width: 96, height: 62 },
  { code: 'RP', name: 'Rheinland-Pfalz', x: 74, y: 286, width: 86, height: 74 },
  { code: 'SL', name: 'Saarland', x: 26, y: 324, width: 36, height: 34 },
  { code: 'BW', name: 'Baden-Württemberg', x: 100, y: 370, width: 114, height: 78 },
  { code: 'BY', name: 'Bayern', x: 236, y: 336, width: 156, height: 108 },
];

function normalizeStage(value?: string | null): string {
  return String(value || '').trim().toLowerCase();
}

function stageFill(stage?: string | null): string {
  const normalized = normalizeStage(stage);
  if (normalized === 'activate') return 'rgba(168, 54, 75, 0.88)';
  if (normalized === 'prepare') return 'rgba(217, 119, 6, 0.82)';
  if (normalized === 'watch') return 'rgba(5, 150, 105, 0.76)';
  return 'rgba(148, 163, 184, 0.28)';
}

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value <= 1 ? value * 100 : value;
  return formatPercent(pct, digits);
}

interface Props {
  rows: OperationalRegionRow[];
  selectedRegion: string | null;
  onSelectRegion: (code: string) => void;
}

const RegionMap: React.FC<Props> = ({ rows, selectedRegion, onSelectRegion }) => {
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);

  const rowsByCode = useMemo(
    () => new Map(rows.map((row) => [row.code, row])),
    [rows],
  );

  const hoveredRow = hoveredRegion ? rowsByCode.get(hoveredRegion) || null : null;

  return (
    <div className="ops-command-map">
      <div className="ops-command-map__legend" aria-label="Legende Entscheidungsstufen">
        <span className="ops-command-map__legend-item">
          <span className="ops-stage-dot ops-stage-dot--activate" aria-hidden="true" />
          Activate
        </span>
        <span className="ops-command-map__legend-item">
          <span className="ops-stage-dot ops-stage-dot--prepare" aria-hidden="true" />
          Prepare
        </span>
        <span className="ops-command-map__legend-item">
          <span className="ops-stage-dot ops-stage-dot--watch" aria-hidden="true" />
          Watch
        </span>
      </div>

      <svg
        viewBox="0 0 420 460"
        className="ops-command-map__svg"
        role="img"
        aria-label="Deutschlandkarte nach Entscheidungsstufe"
      >
        {REGION_TILES.map((tile) => {
          const row = rowsByCode.get(tile.code);
          const isSelected = selectedRegion === tile.code;
          const isHovered = hoveredRegion === tile.code;
          const canInteract = Boolean(row);
          const label = row
            ? `${row.name}, ${row.stage}, ${formatFractionPercent(row.eventProbability, 0)} ${OPERATOR_LABELS.forecast_event_probability}`
            : `${tile.name}, derzeit ohne belastbare Auswahl im aktuellen Scope`;

          return (
            <g
              key={tile.code}
              role={canInteract ? 'button' : undefined}
              tabIndex={canInteract ? 0 : -1}
              aria-label={label}
              aria-pressed={isSelected}
              onClick={() => canInteract && onSelectRegion(tile.code)}
              onMouseEnter={() => canInteract && setHoveredRegion(tile.code)}
              onMouseLeave={() => setHoveredRegion(null)}
              onFocus={() => canInteract && setHoveredRegion(tile.code)}
              onBlur={() => setHoveredRegion(null)}
              onKeyDown={(event) => {
                if ((event.key === 'Enter' || event.key === ' ') && canInteract) {
                  event.preventDefault();
                  onSelectRegion(tile.code);
                }
              }}
              style={{ cursor: canInteract ? 'pointer' : 'default' }}
            >
              <rect
                x={tile.x}
                y={tile.y}
                width={tile.width}
                height={tile.height}
                rx={16}
                fill={stageFill(row?.stage)}
                opacity={row ? 0.92 : 0.42}
                stroke={isSelected ? 'var(--text-primary)' : isHovered ? 'var(--accent-cyan)' : 'rgba(148, 163, 184, 0.3)'}
                strokeWidth={isSelected ? 2.8 : isHovered ? 1.8 : 1.1}
              />
              <text
                x={tile.x + tile.width / 2}
                y={tile.y + tile.height / 2 - 4}
                textAnchor="middle"
                fill="rgba(255,255,255,0.95)"
                fontSize="12"
                fontWeight="700"
              >
                {tile.code}
              </text>
              <text
                x={tile.x + tile.width / 2}
                y={tile.y + tile.height / 2 + 12}
                textAnchor="middle"
                fill="rgba(255,255,255,0.86)"
                fontSize="10"
              >
                {row?.stage || '—'}
              </text>
            </g>
          );
        })}
      </svg>

      <p className="ops-command-map__note">
        Bundesland-Ebene. Die Karte dient der Auswahl und Orientierung, nicht der Entscheidung allein.
      </p>

      {hoveredRow && (
        <div className="ops-command-map__tooltip" role="status" aria-live="polite">
          <strong>{hoveredRow.name}</strong>
          <span>{hoveredRow.stage} · {formatFractionPercent(hoveredRow.eventProbability, 0)} {OPERATOR_LABELS.forecast_event_probability}</span>
          <span>{hoveredRow.trendLabel} · Budget {hoveredRow.budgetAmount ? new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(hoveredRow.budgetAmount) : '-'}</span>
        </div>
      )}
    </div>
  );
};

export default RegionMap;
