import React from 'react';

import LoadingSkeleton from '../LoadingSkeleton';
import { explainInPlainGerman } from '../../lib/plainLanguage';
import {
  PilotReadoutRegion,
  PilotReadoutResponse,
  PilotReadoutStatus,
  PilotSurfaceScope,
  PilotSurfaceStageFilter,
  StructuredReasonItem,
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
  { key: 'ALL', label: 'Alle Stufen' },
  { key: 'Activate', label: 'Jetzt aktivieren' },
  { key: 'Prepare', label: 'Vorbereiten' },
  { key: 'Watch', label: 'Beobachten' },
];
const SCOPE_OPTIONS: Array<{ key: PilotSurfaceScope; label: string; copy: string }> = [
  { key: 'forecast', label: 'Forecast', copy: 'Epidemiologische Lage und Priorisierung' },
  { key: 'allocation', label: 'Allokation', copy: 'Budgetlogik und Freigabestatus' },
  { key: 'recommendation', label: 'Empfehlung', copy: 'Produkt-, Keyword- und Kampagnenplan' },
  { key: 'evidence', label: 'Evidenz', copy: 'Pilot-Evidenz und Freigabestatus' },
];

function normalizeStage(value?: string | null): string {
  return String(value || '').trim().toLowerCase();
}

function stageLabel(value?: string | null): string {
  const normalized = normalizeStage(value);
  if (normalized === 'activate') return 'Jetzt aktivieren';
  if (normalized === 'prepare') return 'Vorbereiten';
  if (normalized === 'watch') return 'Beobachten';
  return value ? String(value) : 'Beobachten';
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

const PRIORITY_SCORE_LABEL = 'Prioritäts-Score';
const EVENT_PROBABILITY_LABEL = 'Event-Wahrscheinlichkeit';
const SIGNAL_CONFIDENCE_LABEL = 'Signal-Sicherheit';

function scopeCopy(scope: PilotSurfaceScope): string {
  return SCOPE_OPTIONS.find((item) => item.key === scope)?.copy || '';
}

function budgetModeLabel(value?: string | null): string {
  if (value === 'validated_allocation') return 'Validierte Allokation';
  return 'Szenario-Split';
}

function forecastReadinessCopy(value?: PilotReadoutStatus | null): string {
  if (value === 'GO') {
    return 'Die regionale virale Dynamik ist belastbar genug, um sie extern zu zeigen, zu priorisieren und zu besprechen.';
  }
  if (value === 'WATCH') {
    return 'Der Forecast-Pfad ist sichtbar, aber Evidenz oder Promotion sind noch nicht stabil genug für eine saubere externe Freigabe.';
  }
  return 'Der aktuelle Scope ist noch nicht forecast-fähig.';
}

function commercialValidationCopy(value?: PilotReadoutStatus | null): string {
  if (value === 'GO') {
    return 'Die kommerzielle Validierung ist abgeschlossen und die Budgetfreigabe kann sich auf echte Outcome-Evidenz stützen.';
  }
  if (value === 'WATCH') {
    return 'Die kommerzielle Validierung baut sich auf, aber die GELO-Outcome-Evidenz ist noch nicht stark genug für einen harten ROI-Claim.';
  }
  return 'Es ist noch keine GELO-Outcome-Basis angeschlossen, deshalb fehlt die kommerzielle Validierung noch.';
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

function explainedValues(
  values: Array<string | StructuredReasonItem | null | undefined>,
): string[] {
  return Array.from(new Set(
    values
      .map((item) => explainInPlainGerman(item))
      .filter(Boolean),
  ));
}

function preferredReasonEntries(
  details?: StructuredReasonItem[] | null,
  fallback?: string[] | null,
): Array<string | StructuredReasonItem> {
  if (details && details.length > 0) return details;
  return fallback || [];
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
      <div className="pilot-empty-state__kicker">Aktueller Pilotstatus</div>
      <h2 className="pilot-empty-state__title">{title || 'Aktuell liegt noch kein kundenfähiger Pilotstatus vor.'}</h2>
      <p className="pilot-empty-state__body">{body || 'Der Pilot bleibt sichtbar, aber dieser Scope ist noch nicht bereit für eine saubere Geschäftsentscheidung.'}</p>
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
  const reasonTrace = explainedValues(preferredReasonEntries(row.reason_trace_details, row.reason_trace));
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
        <p>{focusCopy || 'Aktuell ist noch kein Produkt- oder Keyword-Fokus hinterlegt.'}</p>
      </div>

      <div className="pilot-feature-card__metrics">
        <div className="pilot-inline-metric">
          <span>{PRIORITY_SCORE_LABEL}</span>
          <strong>{formatFractionPercent(row.priority_score, 0)}</strong>
        </div>
        <div className="pilot-inline-metric">
          <span>{EVENT_PROBABILITY_LABEL}</span>
          <strong>{formatFractionPercent(row.event_probability, 0)}</strong>
        </div>
        <div className="pilot-inline-metric">
          <span>Budget-Split</span>
          <strong>{formatCurrency(row.budget_amount_eur)}</strong>
        </div>
        <div className="pilot-inline-metric">
          <span>{SIGNAL_CONFIDENCE_LABEL}</span>
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
          {(row.uncertainty_summary_detail || row.uncertainty_summary) && (
            <div>
              <span>Unsicherheit</span>
              <p>{explainInPlainGerman(row.uncertainty_summary_detail || row.uncertainty_summary)}</p>
            </div>
          )}
          {row.budget_release_recommendation && (
            <div>
              <span>Freigabehinweis</span>
              <p>{explainInPlainGerman(row.budget_release_recommendation)}</p>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function RankedRegionRow({ row }: { row: PilotReadoutRegion }) {
  const reason = explainedValues([
    ...preferredReasonEntries(row.reason_trace_details, row.reason_trace),
    row.uncertainty_summary_detail,
    row.uncertainty_summary,
  ])[0] || 'Keine zusätzliche Klartext-Begründung vorhanden.';

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
          {nonEmpty([row.recommended_product, row.recommended_keywords, row.campaign_recommendation]).join(' · ') || 'Aktuell ist noch keine operative Fokussierung hinterlegt.'}
        </div>
        <div className="pilot-ranked-row__reason">{reason}</div>
      </div>

      <div className="pilot-ranked-row__stats">
        <div className="pilot-ranked-stat">
          <span>Budget-Split</span>
          <strong>{formatCurrency(row.budget_amount_eur)}</strong>
        </div>
        <div className="pilot-ranked-stat">
          <span>{EVENT_PROBABILITY_LABEL}</span>
          <strong>{formatFractionPercent(row.event_probability, 0)}</strong>
        </div>
        <div className="pilot-ranked-stat">
          <span>{SIGNAL_CONFIDENCE_LABEL}</span>
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
  const heroReasonTrace = explainedValues([
    ...preferredReasonEntries(executive?.reason_trace_details, executive?.reason_trace),
    ...preferredReasonEntries(heroRegion?.reason_trace_details, heroRegion?.reason_trace),
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
  const scenarioBudgetLabel = budgetMode === 'validated_allocation' ? 'Validiertes Budget' : 'Szenariobudget';
  const focusProduct = leadOperationalRegion?.recommended_product || heroRegion?.recommended_product;
  const focusKeyword = leadOperationalRegion?.recommended_keywords || heroRegion?.recommended_keywords;
  const scopeCards: Array<{ key: PilotSurfaceScope; label: string; value: PilotReadoutStatus }> = [
    { key: 'forecast', label: 'Forecast', value: sectionReadiness(pilotReadout, 'forecast') },
    { key: 'allocation', label: 'Allocation', value: sectionReadiness(pilotReadout, 'allocation') },
    { key: 'recommendation', label: 'Recommendation', value: sectionReadiness(pilotReadout, 'recommendation') },
    { key: 'evidence', label: 'Evidence', value: sectionReadiness(pilotReadout, 'evidence') },
  ];
  const readinessRows = [
    { label: 'Forecast-Readiness', value: forecastReadiness },
    { label: 'Kommerzielle Validierung', value: commercialValidationStatus },
    { label: 'Test-/Kontrolllogik', value: gateSnapshot?.holdout_status || 'WATCH' },
    { label: 'Budgetfreigabe', value: gateSnapshot?.budget_release_status || 'WATCH' },
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
          title="Die Pilotansicht ist aktuell nicht verfügbar."
          body="Der kundennahe Readout konnte gerade nicht geladen werden. Die Datenbasis bleibt unverändert, aber im Moment liegt kein nutzbarer Payload vor."
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
              <span className="pilot-kicker">PEIX / GELO Pilotansicht</span>
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
              <p className="pilot-section-label">Was sollten wir jetzt tun?</p>
              <h1 className="pilot-hero__title">{executive?.what_should_we_do_now || 'Aktuell liegt noch keine belastbare Kurzempfehlung vor.'}</h1>
              <p className="pilot-hero__subtitle">
                {executive?.headline || 'Regionale Forecast-, Priorisierungs- und Budgetlogik in einer ehrlichen Entscheidungskette.'}
              </p>
            </div>

            <div className="pilot-hero__track-grid">
              <article className="pilot-track-card">
                <div className="pilot-track-card__head">
                  <span className="pilot-section-label">Forecast bereit</span>
                  <span className={badgeClassName('readiness', forecastReadiness)}>
                    {forecastReadiness}
                  </span>
                </div>
                <p className="pilot-track-card__copy">{forecastReadinessCopy(forecastReadiness)}</p>
              </article>

              <article className="pilot-track-card">
                <div className="pilot-track-card__head">
                  <span className="pilot-section-label">Kommerzielle Validierung</span>
                  <span className={badgeClassName('readiness', commercialValidationStatus)}>
                    {commercialValidationStatus}
                  </span>
                </div>
                <p className="pilot-track-card__copy">{commercialValidationCopy(commercialValidationStatus)}</p>
              </article>

              <article className="pilot-track-card">
                <div className="pilot-track-card__head">
                  <span className="pilot-section-label">Budgetmodus</span>
                  <span className={badgeClassName('readiness', budgetMode === 'validated_allocation' ? 'GO' : 'WATCH')}>
                    {budgetModeLabel(budgetMode)}
                  </span>
                </div>
                <p className="pilot-track-card__copy">
                  {validationDisclaimer || 'Die aktuelle Budgetsicht bleibt lesbar, aber ohne implizite ROI-Garantie.'}
                </p>
              </article>

              <article className="pilot-track-card">
                <div className="pilot-track-card__head">
                  <span className="pilot-section-label">So sind die Zahlen gemeint</span>
                </div>
                <p className="pilot-track-card__copy">
                  {EVENT_PROBABILITY_LABEL} ist die Forecast-Chance. {PRIORITY_SCORE_LABEL} ordnet Regionen. {SIGNAL_CONFIDENCE_LABEL} zeigt, wie belastbar das Signal ist.
                </p>
              </article>
            </div>

            <div className="pilot-hero__meta">
              <span>Aktualisiert {generatedAtLabel}</span>
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
                <span className="pilot-filter-label">Zeitraum</span>
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
                <span className="pilot-filter-label">Bereich</span>
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
                <span className="pilot-filter-label">Stufe</span>
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
              <span className="pilot-kicker pilot-kicker--light">Fokusbereich</span>
              <span className={badgeClassName('stage', heroRegion?.decision_stage || executive?.decision_stage)}>
                {stageLabel(heroRegion?.decision_stage || executive?.decision_stage)}
              </span>
            </div>

            <div className="pilot-spotlight__title-block">
              <p>Fokusregion</p>
              <h2>{regionIdentity(heroRegion)}</h2>
              <span>{nonEmpty([focusProduct, focusKeyword]).join(' · ') || 'Aktuell ist noch kein Produkt- oder Keyword-Fokus hinterlegt.'}</span>
            </div>

            <div className="pilot-spotlight__metrics">
              <div className="pilot-spotlight__metric">
                <span>Budgetmodus</span>
                <strong>{budgetModeLabel(budgetMode)}</strong>
              </div>
              <div className="pilot-spotlight__metric">
                <span>{scenarioBudgetLabel}</span>
                <strong>{formatCurrency(executive?.budget_recommendation?.scenario_budget_eur || executive?.budget_recommendation?.recommended_active_budget_eur)}</strong>
              </div>
              <div className="pilot-spotlight__metric">
                <span>{EVENT_PROBABILITY_LABEL}</span>
                <strong>{formatFractionPercent(executive?.confidence_summary?.lead_region_event_probability, 0)}</strong>
              </div>
              <div className="pilot-spotlight__metric">
                <span>{SIGNAL_CONFIDENCE_LABEL}</span>
                <strong>{formatFractionPercent(executive?.confidence_summary?.lead_region_confidence, 0)}</strong>
              </div>
            </div>

            <div className="pilot-spotlight__reason">
              <div className="pilot-section-label">Begründung</div>
              <ul>
                {(heroReasonTrace.length > 0 ? heroReasonTrace : ['Aktuell liegt keine kurze Begründung vor.']).slice(0, 3).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>

            {(executive?.uncertainty_summary_detail || executive?.uncertainty_summary) && (
              <div className="pilot-spotlight__note">
                <span>Unsicherheit</span>
                <p>{explainInPlainGerman(executive?.uncertainty_summary_detail || executive?.uncertainty_summary)}</p>
              </div>
            )}

            {validationDisclaimer && (
              <div className="pilot-spotlight__note">
                <span>Validierungshinweis</span>
                <p>{validationDisclaimer}</p>
              </div>
            )}
          </aside>
        </div>
      </section>

      <section className="pilot-value-grid">
        <article className="pilot-value-card">
          <span className="pilot-section-label">Schon heute sichtbar</span>
          <h2>Was PEIX GELO heute schon zeigen kann</h2>
          <ul className="pilot-blocker-list">
            <li>Regionale virale Wellen werden früh erkannt und mit sichtbarer Signal-Sicherheit eingeordnet.</li>
            <li>Top-Regionen werden klar priorisiert und mit einer verständlichen Stufenempfehlung versehen.</li>
            <li>Die Budgetsicht zeigt bereits einen forecast-basierten Szenario-Split für die aktuelle Woche.</li>
          </ul>
        </article>

        <article className="pilot-value-card">
          <span className="pilot-section-label">Was GELO-Daten freischalten</span>
          <h2>Was mit Outcome-Daten noch stärker wird</h2>
          <ul className="pilot-blocker-list">
            <li>Spend- und Sales-Daten können gegen genau dasselbe regionale Signal gespiegelt werden.</li>
            <li>Test-/Kontrolllogik und Lift-Evidenz können den Scope von Szenarioplanung zu validierter Budgetfreigabe entwickeln.</li>
            <li>Der kommerzielle Layer kann dann zeigen, wo der Forecast wirklich in Business-Wirkung übergegangen ist.</li>
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
            <span className="pilot-kicker">Operative Empfehlungen</span>
            <h2>Operative Empfehlungen</h2>
            <p>
              {budgetMode === 'validated_allocation'
                ? 'Validierte regionale Empfehlungskette für den aktuellen Scope.'
                : 'Forecast-basierte Regionen- und Budgetsicht für den aktuellen Scope.'}
            </p>
          </div>
          <span className={badgeClassName('readiness', currentScopeStatus)}>
            {currentScopeStatus}
          </span>
        </div>

        <div className="pilot-track-card" style={{ marginBottom: 20 }}>
          <div className="pilot-track-card__head">
            <span className="pilot-section-label">Kennzahl-Hinweis</span>
          </div>
          <p className="pilot-track-card__copy">
            {EVENT_PROBABILITY_LABEL} beschreibt die Forecast-Chance. {SIGNAL_CONFIDENCE_LABEL} ist keine zweite Wahrscheinlichkeit, sondern sagt, wie stabil das Signal wirkt.
          </p>
        </div>

        <div className="pilot-summary-strip">
          <div className="pilot-summary-stat">
            <span>Aktivieren-Regionen</span>
            <strong>{pilotReadout?.operational_recommendations?.summary?.activate_regions ?? '-'}</strong>
          </div>
          <div className="pilot-summary-stat">
            <span>Vorbereiten-Regionen</span>
            <strong>{pilotReadout?.operational_recommendations?.summary?.prepare_regions ?? '-'}</strong>
          </div>
          <div className="pilot-summary-stat">
            <span>Beobachten-Regionen</span>
            <strong>{pilotReadout?.operational_recommendations?.summary?.watch_regions ?? '-'}</strong>
          </div>
          <div className="pilot-summary-stat">
            <span>Freigegebene Empfehlungen</span>
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
            <div className="pilot-section-label">Weitere priorisierte Regionen</div>
            {rankedRegions.map((row) => (
              <RankedRegionRow key={row.region_code || row.region_name} row={row} />
            ))}
          </div>
        )}

        {visibleRegions.length === 0 && (
          <div className="pilot-ranked-empty">
            Kein Regions-Output passt aktuell zum gewählten Stufen-Filter.
          </div>
        )}
      </section>

      <section className="pilot-section pilot-section--evidence">
        <div className="pilot-section__header">
          <div className="pilot-section__headline">
            <span className="pilot-kicker">Pilot-Evidenz und Freigabestatus</span>
            <h2>Pilot-Evidenz und Freigabestatus</h2>
            <p>
              Forecast-Evidenz bleibt als eigene Ebene sichtbar. Die kommerzielle Validierung bleibt davon getrennt und wird explizit ausgewiesen.
            </p>
          </div>
          <span className={badgeClassName('readiness', evidence?.scope_readiness || pilotReadout?.run_context?.scope_readiness)}>
            {evidence?.scope_readiness || pilotReadout?.run_context?.scope_readiness || 'NO_GO'}
          </span>
        </div>

        <div className="pilot-evidence-grid">
          <article className="pilot-evidence-card">
            <div className="pilot-section-label">Aktueller Freigabestatus</div>
            <div className="pilot-gate-list">
              {readinessRows.map((item) => (
                <div key={item.label} className="pilot-gate-row">
                  <span>{item.label}</span>
                  <strong className={badgeClassName('readiness', item.value)}>{item.value}</strong>
                </div>
              ))}
            </div>
            <div className="pilot-evidence-card__footer">
              <span>Validierungsstatus</span>
              <strong>{gateSnapshot?.validation_status || '-'}</strong>
            </div>
          </article>

          <article className="pilot-evidence-card">
            <div className="pilot-section-label">Kommerzielle Validierung</div>
            {heroBlockers.length > 0 ? (
              <ul className="pilot-blocker-list">
                {heroBlockers.slice(0, 6).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="pilot-muted-copy">Für diesen Scope sind aktuell keine weiteren kommerziellen Blocker ausgewiesen.</p>
            )}
            <div className="pilot-evidence-card__footer">
              <span>{budgetMode === 'validated_allocation' ? 'Kommerzieller Modus' : 'Aktueller Budgetmodus'}</span>
              <strong>{budgetModeLabel(budgetMode)}</strong>
            </div>
          </article>

          <article className="pilot-evidence-card">
            <div className="pilot-section-label">Aktueller Evaluationssieger</div>
            <div className="pilot-evaluation-highlight">
              <strong>{evidence?.evaluation?.selected_experiment_name || 'Aktuell liegt noch kein retained Winner vor.'}</strong>
              <span>{evidence?.evaluation?.calibration_mode || '-'}</span>
            </div>
            <div className="pilot-evaluation-meta">
              <div>
                <span>Freigabe</span>
                <strong>{evidence?.evaluation?.gate_outcome || '-'}</strong>
              </div>
              <div>
                <span>Beibehalten</span>
                <strong>{evidence?.evaluation?.retained ? 'Ja' : 'Nein'}</strong>
              </div>
              <div>
                <span>Erzeugt</span>
                <strong>{formatDateTime(evidence?.evaluation?.generated_at || null)}</strong>
              </div>
            </div>
          </article>
        </div>

        <div className="pilot-comparison-panel">
          <div className="pilot-section-label">Vergleichsmetriken</div>
          {evaluationRows.length > 0 ? (
            <div className="pilot-comparison-table-wrap">
              <table className="pilot-comparison-table">
                <thead>
                  <tr>
                    <th>Variante</th>
                    <th>precision_at_top3</th>
                    <th>activation_fp_rate</th>
                    <th>ece</th>
                    <th>brier</th>
                    <th>Freigabe</th>
                    <th>Beibehalten</th>
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
                      <td>{row.retained === true ? 'Ja' : row.retained === false ? 'Nein' : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="pilot-ranked-empty">
              Fuer diesen Scope ist aktuell keine archivierte Vergleichstabelle verfuegbar.
            </div>
          )}
        </div>

        {evidence?.legacy_context?.note && (
          <div className="pilot-legacy-note">
            <span className="pilot-section-label">Altpfad</span>
            <p>{evidence.legacy_context.note}</p>
            <small>Abschaltung: {evidence.legacy_context.sunset_date || '-'}</small>
          </div>
        )}
      </section>
    </div>
  );
};

export default PilotSurface;
