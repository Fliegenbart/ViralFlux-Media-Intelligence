import React from 'react';

import LoadingSkeleton from '../LoadingSkeleton';
import {
  PilotReadoutRegion,
  PilotReadoutResponse,
  PilotReadoutStatus,
  PilotSurfaceScope,
  PilotSurfaceStageFilter,
} from '../../types/media';
import { VIRUS_OPTIONS, formatCurrency, formatDateShort, formatDateTime } from './cockpitUtils';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  horizonDays: number;
  onHorizonChange: (value: number) => void;
  scope: PilotSurfaceScope;
  onScopeChange: (value: PilotSurfaceScope) => void;
  stage: PilotSurfaceStageFilter;
  onStageChange: (value: PilotSurfaceStageFilter) => void;
  pilotReadout: PilotReadoutResponse | null;
  loading: boolean;
}

const HORIZON_OPTIONS = [3, 5, 7] as const;
const STAGE_OPTIONS: Array<{ key: PilotSurfaceStageFilter; label: string }> = [
  { key: 'ALL', label: 'Alle Stages' },
  { key: 'Activate', label: 'Activate' },
  { key: 'Prepare', label: 'Prepare' },
  { key: 'Watch', label: 'Watch' },
];
const SCOPE_OPTIONS: Array<{ key: PilotSurfaceScope; label: string; copy: string }> = [
  { key: 'forecast', label: 'Forecast', copy: 'Epidemiologische Lage und Priorisierung' },
  { key: 'allocation', label: 'Allocation', copy: 'Budgetlogik und Freigabestatus' },
  { key: 'recommendation', label: 'Recommendation', copy: 'Produkt-, Keyword- und Kampagnenplan' },
  { key: 'evidence', label: 'Evidence', copy: 'Pilot-Evidenz, Gates und Readiness' },
];

function normalizeStage(value?: string | null): string {
  return String(value || '').trim().toLowerCase();
}

function stageLabel(value?: string | null): string {
  const normalized = normalizeStage(value);
  if (normalized === 'activate') return 'Activate';
  if (normalized === 'prepare') return 'Prepare';
  if (normalized === 'watch') return 'Watch';
  return value ? String(value) : 'Watch';
}

function matchesStage(value: string | undefined, filter: PilotSurfaceStageFilter): boolean {
  if (filter === 'ALL') return true;
  return normalizeStage(value) === normalizeStage(filter);
}

function readinessModifier(value?: PilotReadoutStatus | null): 'go' | 'watch' | 'no-go' {
  if (value === 'GO') return 'go';
  if (value === 'WATCH') return 'watch';
  return 'no-go';
}

function stageModifier(value?: string | null): 'go' | 'prepare' | 'watch' {
  const normalized = normalizeStage(value);
  if (normalized === 'activate') return 'go';
  if (normalized === 'prepare') return 'prepare';
  return 'watch';
}

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(digits)}%`;
}

function formatTableMetric(value: unknown, digits = 3): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  return value.toFixed(digits);
}

function scopeCopy(scope: PilotSurfaceScope): string {
  return SCOPE_OPTIONS.find((item) => item.key === scope)?.copy || '';
}

function budgetModeLabel(value?: string | null): string {
  if (value === 'validated_allocation') return 'Validated Allocation';
  return 'Scenario Split';
}

function forecastReadinessCopy(value?: PilotReadoutStatus | null): string {
  if (value === 'GO') {
    return 'Regional viral pressure can already be shown, ranked, and discussed externally.';
  }
  if (value === 'WATCH') {
    return 'The forecast path exists, but evidence or promotion is not stable enough for a clean external readout yet.';
  }
  return 'The current scope is not forecast-ready.';
}

function commercialValidationCopy(value?: PilotReadoutStatus | null): string {
  if (value === 'GO') {
    return 'Commercial validation is closed and budget release can rely on outcome-backed evidence.';
  }
  if (value === 'WATCH') {
    return 'Commercial validation is building, but GELO outcome evidence is not complete enough for a hard ROI claim yet.';
  }
  return 'No GELO outcome basis is connected yet, so commercial validation is still missing.';
}

function sectionReadiness(
  pilotReadout: PilotReadoutResponse | null,
  scope: PilotSurfaceScope,
): PilotReadoutStatus {
  return pilotReadout?.run_context?.scope_readiness_by_section?.[scope] || 'NO_GO';
}

function regionIdentity(row?: PilotReadoutRegion | null): string {
  return row?.region_name || row?.region_code || '-';
}

function nonEmpty(values: Array<string | null | undefined>): string[] {
  return values
    .map((item) => String(item || '').trim())
    .filter(Boolean);
}

function uniqueValues(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(nonEmpty(values)));
}

function badgeClassName(
  kind: 'readiness' | 'stage',
  value?: string | null,
): string {
  if (kind === 'readiness') {
    return `pilot-badge pilot-badge--${readinessModifier(value as PilotReadoutStatus | undefined)}`;
  }
  return `pilot-badge pilot-badge--${stageModifier(value)}`;
}

function EmptyState({
  code,
  title,
  body,
  supportingReasons,
}: {
  code?: string;
  title?: string;
  body?: string;
  supportingReasons?: string[];
}) {
  const modifier = (() => {
    if (code === 'no_model') return 'no-model';
    if (code === 'no_data') return 'no-data';
    if (code === 'no_go') return 'no-go';
    return 'watch-only';
  })();

  return (
    <section className={`pilot-empty-state pilot-empty-state--${modifier}`}>
      <div className="pilot-empty-state__kicker">Current Pilot State</div>
      <h2 className="pilot-empty-state__title">{title || 'No customer-facing pilot state is available yet.'}</h2>
      <p className="pilot-empty-state__body">{body || 'The pilot stays visible, but this scope is not ready for a clean business decision.'}</p>
      {supportingReasons && supportingReasons.length > 0 && (
        <ul className="pilot-empty-state__list">
          {supportingReasons.slice(0, 3).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function FeaturedRegionCard({
  row,
  lead = false,
}: {
  row: PilotReadoutRegion;
  lead?: boolean;
}) {
  const reasonTrace = nonEmpty(row.reason_trace || []);
  const focusCopy = nonEmpty([
    row.recommended_product,
    row.recommended_keywords,
    row.campaign_recommendation,
  ]).join(' · ');

  return (
    <article className={`pilot-feature-card${lead ? ' pilot-feature-card--lead' : ''}`}>
      <div className="pilot-feature-card__top">
        <span className="pilot-feature-card__rank">#{row.priority_rank || '-'}</span>
        <span className={badgeClassName('stage', row.decision_stage)}>
          {stageLabel(row.decision_stage)}
        </span>
      </div>

      <div className="pilot-feature-card__heading">
        <h3>{regionIdentity(row)}</h3>
        <p>{focusCopy || 'Noch kein produktiver Fokus im Recommendation-Layer vorhanden.'}</p>
      </div>

      <div className="pilot-feature-card__metrics">
        <div className="pilot-inline-metric">
          <span>Priority Score</span>
          <strong>{formatFractionPercent(row.priority_score, 0)}</strong>
        </div>
        <div className="pilot-inline-metric">
          <span>Wave Chance</span>
          <strong>{formatFractionPercent(row.event_probability, 0)}</strong>
        </div>
        <div className="pilot-inline-metric">
          <span>Budget Split</span>
          <strong>{formatCurrency(row.budget_amount_eur)}</strong>
        </div>
        <div className="pilot-inline-metric">
          <span>Confidence</span>
          <strong>{formatFractionPercent(row.confidence, 0)}</strong>
        </div>
      </div>

      <div className="pilot-feature-card__reasoning">
        <div className="pilot-section-label">Warum jetzt?</div>
        <ul>
          {(reasonTrace.length > 0 ? reasonTrace : ['Keine zusätzliche Klartext-Begründung vorhanden.']).slice(0, 3).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      {(row.uncertainty_summary || row.budget_release_recommendation) && (
        <div className="pilot-feature-card__footer">
          {row.uncertainty_summary && (
            <div>
              <span>Unsicherheit</span>
              <p>{row.uncertainty_summary}</p>
            </div>
          )}
          {row.budget_release_recommendation && (
            <div>
              <span>Release Note</span>
              <p>{row.budget_release_recommendation}</p>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function RankedRegionRow({ row }: { row: PilotReadoutRegion }) {
  const reason = nonEmpty(row.reason_trace || [row.uncertainty_summary || ''])[0] || 'Keine zusätzliche Klartext-Begründung vorhanden.';

  return (
    <article className="pilot-ranked-row">
      <div className="pilot-ranked-row__rank">#{row.priority_rank || '-'}</div>

      <div className="pilot-ranked-row__main">
        <div className="pilot-ranked-row__heading">
          <strong>{regionIdentity(row)}</strong>
          <span className={badgeClassName('stage', row.decision_stage)}>
            {stageLabel(row.decision_stage)}
          </span>
        </div>
        <div className="pilot-ranked-row__focus">
          {nonEmpty([row.recommended_product, row.recommended_keywords, row.campaign_recommendation]).join(' · ') || 'Noch keine operative Fokussierung vorhanden.'}
        </div>
        <div className="pilot-ranked-row__reason">{reason}</div>
      </div>

      <div className="pilot-ranked-row__stats">
        <div className="pilot-ranked-stat">
          <span>Budget Split</span>
          <strong>{formatCurrency(row.budget_amount_eur)}</strong>
        </div>
        <div className="pilot-ranked-stat">
          <span>Wave Chance</span>
          <strong>{formatFractionPercent(row.event_probability, 0)}</strong>
        </div>
        <div className="pilot-ranked-stat">
          <span>Confidence</span>
          <strong>{formatFractionPercent(row.confidence, 0)}</strong>
        </div>
      </div>
    </article>
  );
}

const PilotSurface: React.FC<Props> = ({
  virus,
  onVirusChange,
  horizonDays,
  onHorizonChange,
  scope,
  onScopeChange,
  stage,
  onStageChange,
  pilotReadout,
  loading,
}) => {
  const allRegions = pilotReadout?.operational_recommendations?.regions || [];
  const filteredRegions = allRegions.filter((item) => matchesStage(item.decision_stage, stage));
  const visibleRegions = filteredRegions.length > 0 ? filteredRegions : allRegions;
  const featuredRegions = visibleRegions.slice(0, 3);
  const rankedRegions = visibleRegions.slice(3);
  const executive = pilotReadout?.executive_summary;
  const evidence = pilotReadout?.pilot_evidence;
  const gateSnapshot = pilotReadout?.run_context?.gate_snapshot;
  const currentScopeStatus = sectionReadiness(pilotReadout, scope);
  const evaluationRows = (evidence?.evaluation?.comparison_table || []) as Array<Record<string, unknown>>;
  const heroRegion = executive?.top_regions?.[0] || allRegions[0] || null;
  const leadOperationalRegion = allRegions[0] || null;
  const heroReasonTrace = uniqueValues([
    ...(executive?.reason_trace || []),
    ...(heroRegion?.reason_trace || []),
  ]);
  const heroBlockers = uniqueValues([
    ...(executive?.budget_recommendation?.blocked_reasons || []),
    ...(gateSnapshot?.missing_requirements || []),
  ]);
  const currentScopeCopy = scopeCopy(scope);
  const generatedAtLabel = formatDateTime(
    pilotReadout?.run_context?.generated_at
    || pilotReadout?.generated_at
    || evidence?.evaluation?.generated_at
    || null,
  );
  const asOfLabel = formatDateShort(pilotReadout?.run_context?.as_of_date || null);
  const targetWeekLabel = formatDateShort(pilotReadout?.run_context?.target_week_start || null);
  const forecastReadiness = pilotReadout?.run_context?.forecast_readiness || pilotReadout?.run_context?.scope_readiness || 'NO_GO';
  const commercialValidationStatus =
    pilotReadout?.run_context?.commercial_validation_status
    || gateSnapshot?.commercial_validation_status
    || gateSnapshot?.commercial_data_status
    || 'NO_GO';
  const budgetMode =
    executive?.budget_mode
    || executive?.budget_recommendation?.budget_mode
    || pilotReadout?.run_context?.budget_mode
    || gateSnapshot?.budget_mode
    || 'scenario_split';
  const validationDisclaimer =
    executive?.validation_disclaimer
    || pilotReadout?.run_context?.validation_disclaimer
    || gateSnapshot?.validation_disclaimer
    || '';
  const scenarioBudgetLabel = budgetMode === 'validated_allocation' ? 'Validated Budget' : 'Scenario Budget';
  const focusProduct = leadOperationalRegion?.recommended_product || heroRegion?.recommended_product;
  const focusKeyword = leadOperationalRegion?.recommended_keywords || heroRegion?.recommended_keywords;
  const scopeCards: Array<{ key: PilotSurfaceScope; label: string; value: PilotReadoutStatus }> = [
    { key: 'forecast', label: 'Forecast', value: sectionReadiness(pilotReadout, 'forecast') },
    { key: 'allocation', label: 'Allocation', value: sectionReadiness(pilotReadout, 'allocation') },
    { key: 'recommendation', label: 'Recommendation', value: sectionReadiness(pilotReadout, 'recommendation') },
    { key: 'evidence', label: 'Evidence', value: sectionReadiness(pilotReadout, 'evidence') },
  ];
  const readinessRows = [
    { label: 'Forecast Readiness', value: forecastReadiness },
    { label: 'Commercial Validation', value: commercialValidationStatus },
    { label: 'Holdout', value: gateSnapshot?.holdout_status || 'WATCH' },
    { label: 'Budget Release', value: gateSnapshot?.budget_release_status || 'WATCH' },
  ];

  if (loading) {
    return (
      <div className="pilot-surface pilot-surface--loading">
        <LoadingSkeleton lines={10} />
      </div>
    );
  }

  if (!pilotReadout) {
    return (
      <div className="pilot-surface">
        <EmptyState
          code="no_data"
          title="The pilot surface is currently unavailable."
          body="The customer-facing readout could not be loaded. The backend contract stays unchanged, but the page has no usable payload right now."
        />
      </div>
    );
  }

  return (
    <div className="pilot-surface">
      <section className="pilot-hero">
        <div className="pilot-hero__grid">
          <div className="pilot-hero__content">
            <div className="pilot-hero__eyebrow-row">
              <span className="pilot-kicker">PEIX / GELO Pilot Surface</span>
              <span className="pilot-kicker pilot-kicker--muted">
                {currentScopeCopy}
              </span>
            </div>

            <div className="pilot-hero__badge-row">
              <span className={badgeClassName('readiness', pilotReadout?.run_context?.scope_readiness)}>
                {pilotReadout?.run_context?.scope_readiness || 'NO_GO'}
              </span>
              <span className={badgeClassName('stage', executive?.decision_stage)}>
                {stageLabel(executive?.decision_stage)}
              </span>
            </div>

            <div className="pilot-hero__copy">
              <p className="pilot-section-label">What should we do now?</p>
              <h1 className="pilot-hero__title">{executive?.what_should_we_do_now || 'No executive summary is available yet.'}</h1>
              <p className="pilot-hero__subtitle">
                {executive?.headline || 'Regional viral-wave guidance with one honest decision chain.'}
              </p>
            </div>

            <div className="pilot-hero__track-grid">
              <article className="pilot-track-card">
                <div className="pilot-track-card__head">
                  <span className="pilot-section-label">Forecast Ready</span>
                  <span className={badgeClassName('readiness', forecastReadiness)}>
                    {forecastReadiness}
                  </span>
                </div>
                <p className="pilot-track-card__copy">{forecastReadinessCopy(forecastReadiness)}</p>
              </article>

              <article className="pilot-track-card">
                <div className="pilot-track-card__head">
                  <span className="pilot-section-label">Commercial Validation</span>
                  <span className={badgeClassName('readiness', commercialValidationStatus)}>
                    {commercialValidationStatus}
                  </span>
                </div>
                <p className="pilot-track-card__copy">{commercialValidationCopy(commercialValidationStatus)}</p>
              </article>

              <article className="pilot-track-card">
                <div className="pilot-track-card__head">
                  <span className="pilot-section-label">Budget Logic</span>
                  <span className={badgeClassName('readiness', budgetMode === 'validated_allocation' ? 'GO' : 'WATCH')}>
                    {budgetModeLabel(budgetMode)}
                  </span>
                </div>
                <p className="pilot-track-card__copy">
                  {validationDisclaimer || 'The current budget view stays readable, but without an implied ROI guarantee.'}
                </p>
              </article>
            </div>

            <div className="pilot-hero__meta">
              <span>Updated {generatedAtLabel}</span>
              <span>Datenstand {asOfLabel}</span>
              <span>Zielwoche {targetWeekLabel}</span>
            </div>

            <div className="pilot-control-rail">
              <label className="pilot-filter-group" htmlFor="pilot-virus">
                <span className="pilot-filter-label">Virus</span>
                <select
                  id="pilot-virus"
                  className="pilot-select"
                  value={virus}
                  onChange={(event) => onVirusChange(event.target.value)}
                >
                  {VIRUS_OPTIONS.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </label>

              <label className="pilot-filter-group" htmlFor="pilot-horizon">
                <span className="pilot-filter-label">Horizon</span>
                <select
                  id="pilot-horizon"
                  className="pilot-select"
                  value={horizonDays}
                  onChange={(event) => onHorizonChange(Number(event.target.value))}
                >
                  {HORIZON_OPTIONS.map((item) => (
                    <option key={item} value={item}>{`h${item}`}</option>
                  ))}
                </select>
              </label>

              <div className="pilot-filter-group">
                <span className="pilot-filter-label">Scope</span>
                <div className="pilot-pill-row">
                  {SCOPE_OPTIONS.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      className={`pilot-pill${scope === item.key ? ' active' : ''}`}
                      onClick={() => onScopeChange(item.key)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="pilot-filter-group">
                <span className="pilot-filter-label">Stage</span>
                <div className="pilot-pill-row">
                  {STAGE_OPTIONS.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      className={`pilot-pill${stage === item.key ? ' active' : ''}`}
                      onClick={() => onStageChange(item.key)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="pilot-readiness-grid">
              {scopeCards.map((item) => (
                <article
                  key={item.key}
                  className={`pilot-readiness-card${scope === item.key ? ' pilot-readiness-card--active' : ''}`}
                >
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </article>
              ))}
            </div>
          </div>

          <aside className="pilot-spotlight">
            <div className="pilot-spotlight__head">
              <span className="pilot-kicker pilot-kicker--light">Executive Spotlight</span>
              <span className={badgeClassName('stage', heroRegion?.decision_stage || executive?.decision_stage)}>
                {stageLabel(heroRegion?.decision_stage || executive?.decision_stage)}
              </span>
            </div>

            <div className="pilot-spotlight__title-block">
              <p>Lead Region</p>
              <h2>{regionIdentity(heroRegion)}</h2>
              <span>{nonEmpty([focusProduct, focusKeyword]).join(' · ') || 'No product or keyword focus is currently available.'}</span>
            </div>

            <div className="pilot-spotlight__metrics">
              <div className="pilot-spotlight__metric">
                <span>Budget Mode</span>
                <strong>{budgetModeLabel(budgetMode)}</strong>
              </div>
              <div className="pilot-spotlight__metric">
                <span>{scenarioBudgetLabel}</span>
                <strong>{formatCurrency(executive?.budget_recommendation?.scenario_budget_eur || executive?.budget_recommendation?.recommended_active_budget_eur)}</strong>
              </div>
              <div className="pilot-spotlight__metric">
                <span>Wave Chance</span>
                <strong>{formatFractionPercent(executive?.confidence_summary?.lead_region_event_probability, 0)}</strong>
              </div>
              <div className="pilot-spotlight__metric">
                <span>Confidence</span>
                <strong>{formatFractionPercent(executive?.confidence_summary?.lead_region_confidence, 0)}</strong>
              </div>
            </div>

            <div className="pilot-spotlight__reason">
              <div className="pilot-section-label">Reason Trace</div>
              <ul>
                {(heroReasonTrace.length > 0 ? heroReasonTrace : ['No short-form reason trace is currently available.']).slice(0, 3).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>

            {executive?.uncertainty_summary && (
              <div className="pilot-spotlight__note">
                <span>Uncertainty</span>
                <p>{executive.uncertainty_summary}</p>
              </div>
            )}

            {validationDisclaimer && (
              <div className="pilot-spotlight__note">
                <span>Validation Note</span>
                <p>{validationDisclaimer}</p>
              </div>
            )}
          </aside>
        </div>
      </section>

      <section className="pilot-value-grid">
        <article className="pilot-value-card">
          <span className="pilot-section-label">Already Live</span>
          <h2>What PEIX can already show GELO</h2>
          <ul className="pilot-blocker-list">
            <li>Regional viral waves are ranked early and with a visible confidence trail.</li>
            <li>Top regions are prioritized with a clear timing and stage recommendation.</li>
            <li>The budget view already shows a forecast-based scenario split for the current week.</li>
          </ul>
        </article>

        <article className="pilot-value-card">
          <span className="pilot-section-label">What GELO Data Unlocks</span>
          <h2>What becomes stronger with outcome data</h2>
          <ul className="pilot-blocker-list">
            <li>Sales and spend can be mirrored against the same regional signal.</li>
            <li>Holdout and lift evidence can move the scope from scenario planning to validated budget release.</li>
            <li>The commercial layer can then prove where the forecast translated into business impact.</li>
          </ul>
        </article>
      </section>

      {pilotReadout?.empty_state?.code && pilotReadout.empty_state.code !== 'ready' && (
        <EmptyState
          code={pilotReadout.empty_state.code}
          title={pilotReadout.empty_state.title}
          body={pilotReadout.empty_state.body}
          supportingReasons={heroBlockers}
        />
      )}

      <section className="pilot-section">
        <div className="pilot-section__header">
          <div className="pilot-section__headline">
            <span className="pilot-kicker">Operational Recommendations</span>
            <h2>Operational Recommendations</h2>
            <p>
              {budgetMode === 'validated_allocation'
                ? 'Validated regional recommendation chain for the current scope.'
                : 'Forecast-first region and budget scenario for the current scope.'}
            </p>
          </div>
          <span className={badgeClassName('readiness', currentScopeStatus)}>
            {currentScopeStatus}
          </span>
        </div>

        <div className="pilot-summary-strip">
          <div className="pilot-summary-stat">
            <span>Activate Regionen</span>
            <strong>{pilotReadout?.operational_recommendations?.summary?.activate_regions ?? '-'}</strong>
          </div>
          <div className="pilot-summary-stat">
            <span>Prepare Regionen</span>
            <strong>{pilotReadout?.operational_recommendations?.summary?.prepare_regions ?? '-'}</strong>
          </div>
          <div className="pilot-summary-stat">
            <span>Watch Regionen</span>
            <strong>{pilotReadout?.operational_recommendations?.summary?.watch_regions ?? '-'}</strong>
          </div>
          <div className="pilot-summary-stat">
            <span>Bereite Empfehlungen</span>
            <strong>{pilotReadout?.operational_recommendations?.summary?.ready_recommendations ?? '-'}</strong>
          </div>
        </div>

        <div className="pilot-feature-grid">
          {featuredRegions.map((row, index) => (
            <FeaturedRegionCard
              key={row.region_code || `${row.region_name}-${index}`}
              row={row}
              lead={index === 0}
            />
          ))}
        </div>

        {rankedRegions.length > 0 && (
          <div className="pilot-ranked-stack">
            <div className="pilot-section-label">Remaining Ranked Regions</div>
            {rankedRegions.map((row) => (
              <RankedRegionRow key={row.region_code || row.region_name} row={row} />
            ))}
          </div>
        )}

        {visibleRegions.length === 0 && (
          <div className="pilot-ranked-empty">
            Kein Regions-Output passt aktuell zum gewählten Stage-Filter.
          </div>
        )}
      </section>

      <section className="pilot-section pilot-section--evidence">
        <div className="pilot-section__header">
          <div className="pilot-section__headline">
            <span className="pilot-kicker">Pilot Evidence / Readiness</span>
            <h2>Pilot Evidence / Readiness</h2>
            <p>
              Forecast evidence stays visible as its own layer. Commercial validation remains separate and explicit.
            </p>
          </div>
          <span className={badgeClassName('readiness', evidence?.scope_readiness || pilotReadout?.run_context?.scope_readiness)}>
            {evidence?.scope_readiness || pilotReadout?.run_context?.scope_readiness || 'NO_GO'}
          </span>
        </div>

        <div className="pilot-evidence-grid">
          <article className="pilot-evidence-card">
            <div className="pilot-section-label">Current Gate Outcome</div>
            <div className="pilot-gate-list">
              {readinessRows.map((item) => (
                <div key={item.label} className="pilot-gate-row">
                  <span>{item.label}</span>
                  <strong className={badgeClassName('readiness', item.value)}>{item.value}</strong>
                </div>
              ))}
            </div>
            <div className="pilot-evidence-card__footer">
              <span>Validation Status</span>
              <strong>{gateSnapshot?.validation_status || '-'}</strong>
            </div>
          </article>

          <article className="pilot-evidence-card">
            <div className="pilot-section-label">Commercial Validation</div>
            {heroBlockers.length > 0 ? (
              <ul className="pilot-blocker-list">
                {heroBlockers.slice(0, 6).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="pilot-muted-copy">No active commercial blockers are currently reported for this scope.</p>
            )}
            <div className="pilot-evidence-card__footer">
              <span>{budgetMode === 'validated_allocation' ? 'Commercial Mode' : 'Current Budget Mode'}</span>
              <strong>{budgetModeLabel(budgetMode)}</strong>
            </div>
          </article>

          <article className="pilot-evidence-card">
            <div className="pilot-section-label">Live Evaluation Winner</div>
            <div className="pilot-evaluation-highlight">
              <strong>{evidence?.evaluation?.selected_experiment_name || 'No retained winner yet.'}</strong>
              <span>{evidence?.evaluation?.calibration_mode || '-'}</span>
            </div>
            <div className="pilot-evaluation-meta">
              <div>
                <span>Gate Outcome</span>
                <strong>{evidence?.evaluation?.gate_outcome || '-'}</strong>
              </div>
              <div>
                <span>Retained</span>
                <strong>{evidence?.evaluation?.retained ? 'Yes' : 'No'}</strong>
              </div>
              <div>
                <span>Generated</span>
                <strong>{formatDateTime(evidence?.evaluation?.generated_at || null)}</strong>
              </div>
            </div>
          </article>
        </div>

        <div className="pilot-comparison-panel">
          <div className="pilot-section-label">Comparison Metrics</div>
          {evaluationRows.length > 0 ? (
            <div className="pilot-comparison-table-wrap">
              <table className="pilot-comparison-table">
                <thead>
                  <tr>
                    <th>Track</th>
                    <th>precision_at_top3</th>
                    <th>activation_fp_rate</th>
                    <th>ece</th>
                    <th>brier</th>
                    <th>gate_outcome</th>
                    <th>retained</th>
                  </tr>
                </thead>
                <tbody>
                  {evaluationRows.map((row, index) => (
                    <tr key={`${String(row.name || row.role || 'row')}-${index}`}>
                      <td>{String(row.name || row.role || '-')}</td>
                      <td>{formatTableMetric(row.precision_at_top3)}</td>
                      <td>{formatTableMetric(row.activation_false_positive_rate)}</td>
                      <td>{formatTableMetric(row.ece)}</td>
                      <td>{formatTableMetric(row.brier)}</td>
                      <td>{String(row.gate_outcome || '-')}</td>
                      <td>{row.retained === true ? 'Yes' : row.retained === false ? 'No' : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="pilot-ranked-empty">
              Keine archivierte Vergleichstabelle fuer diesen Scope verfuegbar.
            </div>
          )}
        </div>

        {evidence?.legacy_context?.note && (
          <div className="pilot-legacy-note">
            <span className="pilot-section-label">Legacy Context</span>
            <p>{evidence.legacy_context.note}</p>
            <small>Sunset: {evidence.legacy_context.sunset_date || '-'}</small>
          </div>
        )}
      </section>
    </div>
  );
};

export default PilotSurface;
