import React from 'react';
import { Link } from 'react-router-dom';

import CollapsibleSection from '../CollapsibleSection';
import { OPERATOR_LABELS } from '../../constants/operatorLabels';
import { COCKPIT_SEMANTICS, UI_COPY, additionalSuggestionsText, decisionStateLabel, marketComparisonStateLabel } from '../../lib/copy';
import {
  BacktestResponse,
  MediaDecisionResponse,
  MediaEvidenceResponse,
  RegionalBenchmarkResponse,
  RegionalPortfolioResponse,
  WaveRadarResponse,
} from '../../types/media';
import { WaveOutlookPanel, WaveSpreadPanel } from './BacktestVisuals';
import RegionalPortfolioPanel from './RegionalPortfolioPanel';
import {
  VIRUS_OPTIONS,
  businessValidationLabel,
  decisionScopeLabel,
  evidenceTierLabel,
  formatCurrency,
  formatDateTime,
  formatPercent,
  learningStateLabel,
  metricContractDisplayLabel,
  metricContractNote,
  primarySignalScore,
  readinessTone,
  truthLayerLabel,
  truthFreshnessLabel,
  workflowLabel,
} from './cockpitUtils';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  decision: MediaDecisionResponse | null;
  evidence: MediaEvidenceResponse | null;
  loading: boolean;
  waveOutlook: BacktestResponse | null;
  waveOutlookLoading: boolean;
  waveRadar: WaveRadarResponse | null;
  waveRadarLoading: boolean;
  regionalBenchmark: RegionalBenchmarkResponse | null;
  regionalPortfolio: RegionalPortfolioResponse | null;
  regionalPortfolioLoading: boolean;
  onOpenRecommendation: (id: string) => void;
  onOpenRegions: () => void;
  onOpenCampaigns: () => void;
  onFocusPortfolioOpportunity: (virus: string, regionCode: string) => void;
}

const DecisionView: React.FC<Props> = ({
  virus,
  onVirusChange,
  decision,
  evidence,
  loading,
  waveOutlook,
  waveOutlookLoading,
  waveRadar,
  waveRadarLoading,
  regionalBenchmark,
  regionalPortfolio,
  regionalPortfolioLoading,
  onOpenRecommendation,
  onOpenRegions,
  onOpenCampaigns,
  onFocusPortfolioOpportunity,
}) => {
  const weeklyDecision = decision?.weekly_decision;
  const latestMarket = decision?.backtest_summary?.latest_market;
  const latestCustomer = decision?.backtest_summary?.latest_customer;
  const sourceItems = evidence?.source_status?.items || [];
  const sourceSummary = evidence?.source_status;
  const topCard = decision?.top_recommendations?.[0] || null;
  const recommendations = decision?.top_recommendations || [];
  const topRegions = weeklyDecision?.top_regions || [];
  const isGo = String(weeklyDecision?.decision_state || '').toUpperCase() === 'GO';
  const readiness = latestMarket?.decision_metrics?.readiness_score_0_100;
  const primaryRegion = topCard?.decision_brief?.recommendation?.primary_region || topRegions[0]?.name;
  const horizonMin = topCard?.decision_brief?.horizon?.min_days;
  const horizonMax = topCard?.decision_brief?.horizon?.max_days;
  const topDrivers = weeklyDecision?.signal_stack_summary?.top_drivers || [];
  const driverGroups = weeklyDecision?.signal_stack_summary?.driver_groups || {};
  const mathStack = weeklyDecision?.signal_stack_summary?.math_stack;
  const decisionModeLabel = weeklyDecision?.decision_mode_label || weeklyDecision?.signal_stack_summary?.decision_mode_label || 'Regionalsignal';
  const decisionModeReason = weeklyDecision?.decision_mode_reason || weeklyDecision?.signal_stack_summary?.decision_mode_reason;
  const hiddenBacklog = decision?.campaign_summary?.hidden_backlog_cards || 0;
  const eventProbabilityRaw = weeklyDecision?.event_forecast?.event_probability;
  const eventProbabilityPct = eventProbabilityRaw == null
    ? null
    : (eventProbabilityRaw <= 1 ? eventProbabilityRaw * 100 : eventProbabilityRaw);
  const topRegionSignal = primarySignalScore(topRegions[0]);
  const eventProbabilityLabel = metricContractDisplayLabel(weeklyDecision?.field_contracts, 'event_probability', 'Event-Wahrscheinlichkeit');
  const signalScoreLabel = metricContractDisplayLabel(weeklyDecision?.field_contracts, 'signal_score', UI_COPY.signalScore);
  const eventProbabilityNote = metricContractNote(
    weeklyDecision?.field_contracts,
    'event_probability',
    'Beschreibt die kalibrierte Wahrscheinlichkeit für das definierte Forecast-Ereignis.',
  );
  const signalScoreNote = metricContractNote(
    weeklyDecision?.field_contracts,
    'signal_score',
    'Hilft beim Vergleichen und Priorisieren, ist aber keine Eintrittswahrscheinlichkeit.',
  );
  const learningState = learningStateLabel(weeklyDecision?.learning_state || weeklyDecision?.truth_gate?.learning_state);
  const businessGate = weeklyDecision?.business_gate || decision?.business_validation || evidence?.business_validation;
  const operatorContext = weeklyDecision?.operator_context || decision?.operator_context || evidence?.operator_context;
  const businessValidationStatus = businessValidationLabel(weeklyDecision?.business_readiness || businessGate?.validation_status);
  const businessEvidenceTier = evidenceTierLabel(weeklyDecision?.business_evidence_tier || businessGate?.evidence_tier);
  const decisionScope = decisionScopeLabel(businessGate?.decision_scope);
  const businessValidated = Boolean(businessGate?.validated_for_budget_activation);

  const heroSentence = weeklyDecision?.recommended_action
    || topCard?.decision_brief?.summary_sentence
    || (topRegions.length
      ? `Diese Woche ${isGo ? 'freigeben' : 'vorbereiten'}: Fokus auf ${topRegions
        .map((region) => region.name || region.code)
        .join(', ')}.`
      : 'Diese Woche die nationale Lage beobachten und regionale Signale priorisieren.');
  const horizonLabel = horizonMin && horizonMax
    ? `${horizonMin}-${horizonMax} Tagen`
    : (horizonMax || horizonMin)
      ? `${horizonMax || horizonMin} Tagen`
      : null;
  const heroLead = primaryRegion
    ? `${isGo ? 'Aktivieren' : 'Vorbereiten'} für ${primaryRegion}${horizonLabel ? ` in ${horizonLabel}` : ''}.`
    : (isGo ? 'Aktivieren, wo das Signal trägt.' : 'Vorbereiten, wo die Welle zuerst greift.');
  const shiftLabel = isGo && weeklyDecision?.budget_shift != null
    ? formatPercent(weeklyDecision.budget_shift as number)
    : 'Noch nicht freigegeben';
  const shiftNote = isGo
    ? 'Eine übergeordnete Budgetverschiebung ist freigegeben.'
    : 'Noch keine breite Umschichtung freigeben. Regionen weiter priorisieren.';

  const gateTone = readinessTone(isGo);

  const sourceFreshnessLabel = (value?: string | null): string => {
    const normalized = String(value || '').trim().toLowerCase();
    if (normalized === 'live') return 'aktuell';
    if (normalized === 'stale') return 'veraltet';
    if (normalized === 'no_data') return 'keine Daten';
    return value ? String(value) : '-';
  };

  if (loading && !decision) {
    return <div className="card decision-loading-card">Lade Entscheidungssystem...</div>;
  }

  return (
    <div className="page-stack decision-template-page">
      <section className="context-filter-rail decision-context-rail">
        <div className="section-heading">
          <span className="section-kicker">ViralFlux for GELO</span>
          <div className="decision-chip-rail">
            {VIRUS_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onVirusChange(option)}
                className={`tab-chip ${option === virus ? 'active' : ''}`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
        <div className="decision-chip-rail">
          <span className="step-chip step-chip-done">Letzte epidemiologische Woche {formatDateTime(weeklyDecision?.decision_window?.start)}</span>
          <span className="step-chip">Generiert {formatDateTime(decision?.generated_at)}</span>
          <span className="step-chip">{UI_COPY.marketComparison}: {marketComparisonStateLabel(weeklyDecision?.proxy_state)}</span>
          <span className="step-chip">{UI_COPY.customerData}: {truthLayerLabel(decision?.truth_coverage || latestCustomer)}</span>
          <span className="step-chip">{OPERATOR_LABELS.business_validation_gate}: {businessValidationStatus}</span>
          <span className="step-chip">Evidenz: {businessEvidenceTier}</span>
        </div>
      </section>

      <section className="card decision-header hero-card decision-hero-shell decision-card-lg">
        <div className="hero-grid">
          <div className="hero-main">
            <div className="hero-status-row">
              <span className="decision-status-pill" style={gateTone}>
                {decisionStateLabel(weeklyDecision?.decision_state)}
              </span>
              <span className="decision-meta-text">
                {topCard?.playbook_title || 'Wochenentscheidung'} · letzte epidemiologische Woche {weeklyDecision?.decision_window?.start ? new Date(weeklyDecision.decision_window.start).toLocaleDateString('de-DE') : '-'}
              </span>
              <span className="campaign-confidence-chip">{decisionModeLabel}</span>
            </div>
            <div className="section-heading decision-section-heading">
              <span className="section-kicker">Hero Decision Stage</span>
              <h1 className="hero-title">Wochenentscheidung: {heroLead}</h1>
              <p className="hero-context">{heroSentence}</p>
              <p className="hero-copy">
                {isGo
                  ? 'Die Daten sprechen für konkrete regionale Kampagnenvorschläge, die jetzt zur Freigabe bereitstehen.'
                  : decisionModeReason || 'Noch keine harte Aktivierung. Regionen weiter priorisieren und die stärksten Vorschläge zuerst prüfen.'}
              </p>
            </div>
            <div className="action-row">
              <button className="media-button" type="button" onClick={onOpenCampaigns}>Kampagnen prüfen</button>
              <button className="media-button secondary" type="button" onClick={onOpenRegions}>Regionen ansehen</button>
              <Link className="media-button secondary decision-button-link" to="/bericht">Bericht exportieren</Link>
            </div>
          </div>

          <div className="soft-panel aside-summary decision-card-md">
            <div>
              <div className="section-kicker">Confidence Strip</div>
              <div className="summary-headline">
                {weeklyDecision?.top_products?.[0] || topCard?.recommended_product || 'GELO Portfolio'}
              </div>
              <div className="summary-note">
                Top-Regionen: {topRegions.map((region) => region.name || region.code).join(', ') || 'National'} · {UI_COPY.stateLevelScope}
              </div>
            </div>
            <div className="decision-rail summary-grid">
              <div className="decision-summary-block decision-summary-block--sm">
                <div className="section-kicker decision-kicker-spaced">Nationaler Shift</div>
                <div className="summary-metric">{shiftLabel}</div>
                <div className="summary-note decision-note-tight">{shiftNote}</div>
              </div>
              <div className="decision-summary-block decision-summary-block--md">
                <div className="section-kicker decision-kicker-spaced">Wochenbudget</div>
                <div className="summary-metric">
                  {formatCurrency(topCard?.campaign_preview?.budget?.weekly_budget_eur)}
                </div>
                <div className="summary-note decision-note-tight">
                  {hiddenBacklog > 0 ? additionalSuggestionsText(hiddenBacklog) : 'Der Fokus liegt auf den nächsten prüfbaren Vorschlägen.'}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <RegionalPortfolioPanel
        currentVirus={virus}
        benchmark={regionalBenchmark}
        portfolio={regionalPortfolio}
        loading={regionalPortfolioLoading}
        onFocusOpportunity={onFocusPortfolioOpportunity}
      />

      <section className="cockpit-grid decision-workspace-grid">
        <div className="decision-primary-stack">
          <WaveOutlookPanel
            virus={virus}
            onVirusChange={onVirusChange}
            result={waveOutlook}
            loading={waveOutlookLoading}
          />

          <WaveSpreadPanel
            virus={virus}
            result={waveRadar}
            loading={waveRadarLoading}
            subtitle={`Hier siehst du den historischen Ausbreitungsweg für ${virus} in der zuletzt verfügbaren Saison. Das hilft bei der Einordnung, ersetzt aber nicht die aktuelle Wochenentscheidung.`}
          />
        </div>

        <div className="decision-secondary-stack">
          <CollapsibleSection title="Datenstand & Quellen" subtitle="Eingangswerte und deren Aktualität">
            <div className="review-chip-row decision-stack-top-sm">
              <span className="step-chip">
                Quellen aktuell: {sourceSummary ? `${sourceSummary.live_count}/${sourceSummary.total}` : '-'}
              </span>
              <span className="step-chip">
                Evidenz: {formatDateTime(evidence?.generated_at)}
              </span>
              <span className="step-chip">
                Kundendaten: {truthFreshnessLabel(decision?.truth_coverage?.truth_freshness_state || weeklyDecision?.truth_freshness_state)}
              </span>
            </div>
            <div className="decision-list-grid decision-stack-top-md">
              {sourceItems.length > 0 ? sourceItems.map((item) => (
                <div key={item.source_key} className="evidence-row">
                  <span>{item.label}</span>
                  <strong>
                    {sourceFreshnessLabel(item.freshness_state)} · {formatDateTime(item.last_updated)}
                  </strong>
                </div>
              )) : (
                <div className="soft-panel decision-panel-line">
                  Der genaue Datenstand der abgefragten Werte wird noch geladen.
                </div>
              )}
            </div>
          </CollapsibleSection>

          <div className="card subsection-card decision-card-md">
            <div className="section-heading decision-section-heading-tight">
              <h2 className="subsection-title">Was die Entscheidung trägt</h2>
              <p className="subsection-copy">
                Der Forecast zeigt, wo eine Welle wahrscheinlich entsteht. Der {OPERATOR_LABELS.business_validation_gate} entscheidet separat, ob PEIX daraus schon eine budgetwirksame GELO-Freigabe ableiten darf.
              </p>
            </div>
            <div className="review-chip-row decision-stack-top-sm">
              <span className="step-chip">Operator: {(operatorContext?.operator || 'peix').toUpperCase()}</span>
              <span className="step-chip">Truth-Partner: {(operatorContext?.truth_partner || 'gelo').toUpperCase()}</span>
              <span className="step-chip">{decisionScope}</span>
              <span className="step-chip">{UI_COPY.noCityForecast}</span>
            </div>
            <div className="metric-strip decision-stack-top-md">
              <div className="metric-box">
                <span>{OPERATOR_LABELS.business_validation_gate}</span>
                <strong>{businessValidationStatus}</strong>
              </div>
              <div className="metric-box">
                <span>Evidenz-Tier</span>
                <strong>{businessEvidenceTier}</strong>
              </div>
              <div className="metric-box">
                <span>Truth-Wochen</span>
                <strong>{businessGate?.coverage_weeks ?? decision?.truth_coverage?.coverage_weeks ?? 0}</strong>
              </div>
              <div className="metric-box">
                <span>Aktivierungszyklen</span>
                <strong>{businessGate?.activation_cycles ?? 0}</strong>
              </div>
              <div className="metric-box">
                <span>Holdout-Setup</span>
                <strong>{businessGate?.holdout_ready ? 'bereit' : 'offen'}</strong>
              </div>
              <div className="metric-box">
                <span>Budgetfreigabe</span>
                <strong>{businessValidated ? 'ja' : 'nein'}</strong>
              </div>
            </div>
            <div className="soft-panel decision-panel-message">
              <div className="decision-panel-message__title">
                {businessGate?.message || 'Die kommerzielle Validierung befindet sich noch im Aufbau.'}
              </div>
              {businessGate?.guidance && (
                <div className="decision-panel-message__body">
                  {businessGate.guidance}
                </div>
              )}
            </div>
          </div>

          <div className="metric-strip">
            <div className="metric-box">
              <span>System-Readiness</span>
              <strong>{readiness != null ? `${Math.round(readiness)}/100` : '-'}</strong>
            </div>
              <div className="metric-box">
                <span>{eventProbabilityLabel}</span>
                <strong>{formatPercent(eventProbabilityPct)}</strong>
            </div>
            <div className="metric-box">
              <span>{signalScoreLabel}</span>
              <strong>{formatPercent(topRegionSignal)}</strong>
            </div>
            <div className="metric-box">
              <span>Hit-Rate</span>
              <strong>{formatPercent(latestMarket?.decision_metrics?.hit_rate_pct || 0)}</strong>
            </div>
            <div className="metric-box">
              <span>Lernstand</span>
              <strong>{learningState}</strong>
            </div>
            <div className="metric-box">
              <span>False Alarms</span>
              <strong>{formatPercent(latestMarket?.decision_metrics?.false_alarm_rate_pct || 0)}</strong>
            </div>
          </div>

          <div className="card subsection-card decision-card-md">
            <div className="section-heading decision-section-heading-tight">
              <h2 className="subsection-title">Warum jetzt?</h2>
              <p className="subsection-copy">
                Die Entscheidung wird aus sichtbaren Signalen abgeleitet, nicht aus einer Black Box.
              </p>
            </div>
            <div className="soft-panel decision-panel-note">
              <strong className="decision-inline-strong">{eventProbabilityLabel}:</strong> {eventProbabilityNote} <strong className="decision-inline-strong">{signalScoreLabel}:</strong> {signalScoreNote}
              <div className="decision-note-tight">{COCKPIT_SEMANTICS.stateLevelScope.helper} {COCKPIT_SEMANTICS.noCityForecast.helper}</div>
            </div>
            <div className="decision-list-grid decision-stack-top-md">
              {(weeklyDecision?.why_now || []).map((reason) => (
                <div key={reason} className="soft-panel decision-panel-line">
                  {reason}
                </div>
              ))}
            </div>
          </div>

          <div className="card subsection-card decision-card-md">
            <div className="section-heading decision-section-heading-tight">
              <h2 className="subsection-title">Secondary Paths</h2>
              <p className="subsection-copy">
                Direkter Sprung in die nächste sinnvolle Aktion statt in eine lange Liste.
              </p>
            </div>
            {recommendations.length > 0 ? (recommendations.slice(0, 3)).map((card) => (
              <button
                key={card.id}
                type="button"
                onClick={() => onOpenRecommendation(card.id)}
                className="campaign-list-card"
              >
                <div className="decision-list-row">
                  <div>
                    <div className="decision-list-title">
                      {card.display_title || card.campaign_name || card.product}
                    </div>
                    <div className="decision-list-meta">
                      {card.region_codes_display?.join(', ') || card.region || 'National'} · {card.recommended_product || card.product}
                    </div>
                  </div>
                  <strong className="decision-list-value">
                    {isGo && card.is_publishable ? formatPercent(card.budget_shift_pct || 0) : workflowLabel(card.lifecycle_state || card.status)}
                  </strong>
                </div>
              </button>
            )) : (
              <div className="soft-panel decision-panel-line decision-stack-top-md">
                Noch keine Kampagnenvorschläge im Fokus. Öffne die Kampagnenansicht, um weitere Vorschläge zu sichten oder neue zu erzeugen.
              </div>
            )}
          </div>

          <CollapsibleSection title="Modell & Signaltreiber" subtitle="Epidemiologische Kerndaten und Versorgungskontext">
            <div className="review-chip-row decision-stack-top-sm">
              {Object.entries(driverGroups).map(([key, group]) => (
                <span key={key} className="step-chip">
                  {group.label} {formatPercent(group.contribution || 0)}
                </span>
              ))}
            </div>
            <div className="review-chip-row decision-stack-top-sm">
              {(mathStack?.base_models || []).map((label) => (
                <span key={label} className="step-chip">{label}</span>
              ))}
              {mathStack?.meta_learner && <span className="step-chip">{mathStack.meta_learner}</span>}
            </div>
            <div className="review-chip-row decision-stack-top-sm">
              {topDrivers.map((driver) => (
                <span key={driver.label} className="step-chip">
                  {driver.label} {formatPercent(driver.strength_pct || 0)}
                </span>
              ))}
            </div>
          </CollapsibleSection>
        </div>
      </section>

      {(weeklyDecision?.risk_flags || []).length > 0 && (
        <section className="card subsection-card decision-risk-shell decision-card-md">
          <div className="section-heading decision-section-heading-tight">
            <h2 className="subsection-title">Details bei Bedarf</h2>
            <p className="subsection-copy">
              Die Bewertung beruht auf Datenfrische, Marktvergleich, Kundendaten, Modellzustand und Freigabefähigkeit.
            </p>
          </div>
          <div className="decision-list-grid decision-stack-top-md">
            {(weeklyDecision?.risk_flags || []).map((flag) => (
              <div key={flag} className="evidence-row">
                <span>{flag}</span>
                <strong>{weeklyDecision?.decision_state}</strong>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default DecisionView;
