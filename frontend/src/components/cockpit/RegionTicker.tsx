import React from 'react';

import { RegionalDecisionPayload } from '../../types/media/regional';

export interface RegionTickerRegion {
  region_id?: string;
  region_name?: string;
  bundesland: string;
  bundesland_name: string;
  virus_typ: string;
  as_of_date: string;
  target_week_start: string;
  target_window_days: number[];
  horizon_days: number;
  event_probability_calibrated: number;
  current_known_incidence: number;
  change_pct?: number | null;
  trend?: string;
  decision_rank?: number | null;
  rank?: number | null;
  decision_stage?: 'activate' | 'prepare' | 'watch' | string;
  decision_label?: string | null;
  budget_amount?: number | null;
  budget_eur?: number | null;
  suggested_budget_amount?: number | null;
  suggested_budget_eur?: number | null;
  stage?: string | null;
  decision?: RegionalDecisionPayload;
}

interface Props {
  regions: RegionTickerRegion[];
  selectedRegion: string | null;
  onRegionSelect: (region_id: string) => void;
}

function normalizeStage(region: RegionTickerRegion): 'activate' | 'prepare' | 'watch' {
  const raw = String(
    region.decision_stage
      || region.stage
      || region.decision_label
      || region.decision?.stage
      || 'watch',
  ).trim().toLowerCase();

  if (raw === 'activate') return 'activate';
  if (raw === 'prepare') return 'prepare';
  return 'watch';
}

function stageLabel(stage: 'activate' | 'prepare' | 'watch'): string {
  if (stage === 'activate') return 'Activate';
  if (stage === 'prepare') return 'Prepare';
  return 'Watch';
}

function actionLabel(stage: 'activate' | 'prepare' | 'watch'): string {
  if (stage === 'activate') return 'Freigeben';
  if (stage === 'prepare') return 'Prüfen';
  return 'Beobachten';
}

function resolveRegionId(region: RegionTickerRegion): string {
  return region.region_id || region.bundesland;
}

function resolveRegionName(region: RegionTickerRegion): string {
  return region.region_name || region.bundesland_name || region.bundesland;
}

function resolveBudget(region: RegionTickerRegion): number | null {
  const value = region.suggested_budget_amount
    ?? region.budget_amount
    ?? region.suggested_budget_eur
    ?? region.budget_eur;

  if (value == null || Number.isNaN(value)) return null;
  return value;
}

function formatBudget(value: number | null): string {
  if (value == null) return '—';
  const thousands = Math.round(value / 1000);
  return `€${thousands}k`;
}

function trendArrow(changePct?: number | null): '↑' | '↗' | '→' | '↘' | '↓' {
  if (changePct == null || Number.isNaN(changePct)) return '→';
  if (changePct >= 8) return '↑';
  if (changePct >= 2) return '↗';
  if (changePct <= -8) return '↓';
  if (changePct <= -2) return '↘';
  return '→';
}

function trendTone(changePct?: number | null): 'rising' | 'falling' | 'stable' {
  if (changePct == null || Number.isNaN(changePct)) return 'stable';
  if (changePct >= 2) return 'rising';
  if (changePct <= -2) return 'falling';
  return 'stable';
}

function formatTrend(changePct?: number | null): string {
  if (changePct == null || Number.isNaN(changePct)) return '—';
  const sign = changePct > 0 ? '+' : '';
  return `${sign}${changePct.toFixed(0)}%`;
}

const RegionTicker: React.FC<Props> = ({
  regions,
  selectedRegion,
  onRegionSelect,
}) => {
  const hasScrollableBody = regions.length > 8;

  return (
    <div className={['region-ticker', hasScrollableBody ? 'region-ticker--scrollable' : ''].filter(Boolean).join(' ')}>
      <div className="region-ticker__table-wrap">
        <table className="region-ticker__table">
          <thead>
            <tr>
              <th className="region-ticker__col-rank">#</th>
              <th>Region</th>
              <th>Stage</th>
              <th>Trend</th>
              <th className="region-ticker__col-budget">Budget</th>
              <th className="region-ticker__col-action">Aktion</th>
            </tr>
          </thead>
          <tbody>
            {regions.map((region, index) => {
              const stage = normalizeStage(region);
              const regionId = resolveRegionId(region);
              const selected = selectedRegion === regionId;
              const budget = resolveBudget(region);
              const arrow = trendArrow(region.change_pct);
              const tone = trendTone(region.change_pct);

              return (
                <tr
                  key={regionId}
                  tabIndex={0}
                  role="button"
                  aria-label={`${resolveRegionName(region)} ${stageLabel(stage)}`}
                  aria-pressed={selected}
                  className={[
                    'region-ticker__row',
                    selected ? 'region-ticker__row--selected' : '',
                  ].filter(Boolean).join(' ')}
                  onClick={() => onRegionSelect(regionId)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onRegionSelect(regionId);
                    }
                  }}
                >
                  <td className="region-ticker__rank">{region.decision_rank ?? region.rank ?? index + 1}</td>
                  <td className="region-ticker__region">{resolveRegionName(region)}</td>
                  <td>
                    <span className="region-ticker__stage">
                      <span
                        className={`region-ticker__stage-dot region-ticker__stage-dot--${stage}`}
                        data-stage={stage}
                        aria-hidden="true"
                      />
                      <span className="region-ticker__stage-text">{stageLabel(stage)}</span>
                    </span>
                  </td>
                  <td>
                    <span className={`region-ticker__trend region-ticker__trend--${tone}`}>
                      <span className="region-ticker__trend-arrow" aria-hidden="true">{arrow}</span>
                      <span>{formatTrend(region.change_pct)}</span>
                    </span>
                  </td>
                  <td className="region-ticker__budget">{formatBudget(budget)}</td>
                  <td className="region-ticker__action-cell">
                    <span className={`region-ticker__action region-ticker__action--${stage}`}>
                      {actionLabel(stage)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default RegionTicker;
