import { OPERATOR_LABELS } from '../../constants/operatorLabels';
import { decisionStateLabel } from '../../lib/copy';
import { buildPredictionNarrative, explainInPlainGerman } from '../../lib/plainLanguage';
import {
  MediaDecisionResponse,
  MediaEvidenceResponse,
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastPrediction,
  RegionalForecastResponse,
  StructuredReasonItem,
  PredictionNarrative,
  WorkspaceStatusSummary,
} from '../../types/media';
import {
  businessValidationLabel,
  evidenceTierLabel,
  formatDateTime,
  formatCurrency,
  formatPercent,
  truthFreshnessLabel,
  truthLayerLabel,
  workflowLabel,
} from '../../components/cockpit/cockpitUtils';
import {
  monitoringStatusLabel,
  numberFromUnknown,
  readinessGateLabel,
  sanitizeEvidenceCopy,
} from '../../components/cockpit/evidence/evidenceUtils';

export function noop() {}

export interface ToastLike {
  (message: string, type?: 'success' | 'error' | 'info'): void;
}

export interface NowPageMetric {
  label: string;
  value: string;
  tone: 'success' | 'warning' | 'neutral';
}

export interface NowPageTrustCheck {
  key: 'forecast' | 'data' | 'business';
  question: string;
  value: string;
  detail: string;
  tone: 'success' | 'warning' | 'neutral';
}

export interface NowPageFocusRegion {
  code: string | null;
  name: string;
  stage: string;
  reason: string;
  product: string;
  probabilityLabel: string;
  budgetLabel: string;
  recommendationId: string | null;
}

export interface NowPageRelatedRegion {
  code: string;
  name: string;
  stage: string;
  probabilityLabel: string;
  reason: string;
}

export type NowPageRecommendationState = 'strong' | 'guarded' | 'weak' | 'blocked';

export interface NowPageHeroRecommendation {
  headline: string;
  actionLabel: string;
  direction: string;
  region: string;
  regionCode: string | null;
  context: string;
  whyNow: string;
  state: NowPageRecommendationState;
  stateLabel: string;
  actionHint: string | null;
  ctaDisabled: boolean;
}

export interface NowPageSecondaryMove {
  code: string;
  name: string;
  stage: string;
  probabilityLabel: string;
  reason: string;
}

export interface NowPageBriefingTrustItem {
  key: 'reliability' | 'evidence' | 'readiness';
  label: string;
  value: string;
  detail: string;
  tone: 'success' | 'warning' | 'neutral';
}

export interface NowPageBriefingTrust {
  summary: string;
  items: NowPageBriefingTrustItem[];
}

export interface NowPageSupportState {
  stale: boolean;
  label: string | null;
  detail: string | null;
}

export interface NowPageViewModel {
  hasData: boolean;
  generatedAt: string | null;
  title: string;
  summary: string;
  note: string;
  proof: PredictionNarrative | null;
  primaryActionLabel: string;
  primaryRecommendationId: string | null;
  heroRecommendation: NowPageHeroRecommendation | null;
  secondaryMoves: NowPageSecondaryMove[];
  briefingTrust: NowPageBriefingTrust;
  supportState: NowPageSupportState;
  primaryCampaignTitle: string;
  primaryCampaignContext: string;
  primaryCampaignCopy: string;
  focusRegion: NowPageFocusRegion | null;
  metrics: NowPageMetric[];
  trustChecks: NowPageTrustCheck[];
  reasons: string[];
  risks: string[];
  quality: Array<{ label: string; value: string }>;
  relatedRegions: NowPageRelatedRegion[];
  emptyState: {
    title: string;
    body: string;
  } | null;
}

export function deriveNowFocusRegionCode(
  decision: MediaDecisionResponse | null,
  forecast: RegionalForecastResponse | null,
  allocation: RegionalAllocationResponse | null,
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null,
): string | null {
  const weeklyDecision = decision?.weekly_decision;
  const topCard = decision?.top_recommendations?.[0] || null;
  const sortedPredictions = sortRegionalPredictions(forecast);
  return weeklyDecision?.top_regions?.[0]?.code
    || campaignRecommendations?.recommendations?.[0]?.bundesland
    || campaignRecommendations?.recommendations?.[0]?.region
    || topCard?.region_codes?.[0]
    || allocation?.recommendations?.[0]?.bundesland
    || sortedPredictions[0]?.bundesland
    || null;
}

export function sortRegionalPredictions(
  forecast: RegionalForecastResponse | null | undefined,
): RegionalForecastPrediction[] {
  return [...(forecast?.predictions || [])].sort((left, right) => {
    const leftRank = Number(left.decision_rank ?? left.rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.decision_rank ?? right.rank ?? Number.MAX_SAFE_INTEGER);
    return leftRank - rightRank;
  });
}

function uniqueText(values: Array<string | null | undefined>, limit = 4): string[] {
  const seen = new Set<string>();

  return values
    .map((value) => String(value || '').trim())
    .filter((value) => {
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    })
    .slice(0, limit);
}

function explainedEntries(
  values: Array<string | StructuredReasonItem | null | undefined>,
  limit = 4,
): string[] {
  const seen = new Set<string>();
  return values
    .map((value) => explainInPlainGerman(value))
    .filter((value) => {
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    })
    .slice(0, limit);
}

function preferredReasonEntries(
  details?: StructuredReasonItem[] | null,
  fallback?: string[] | null,
): Array<string | StructuredReasonItem> {
  if (details && details.length > 0) return details;
  return fallback || [];
}

function findReasonMentioningRegion(
  values: Array<string | StructuredReasonItem | null | undefined>,
  regionName?: string | null,
): string {
  const normalizedRegion = explainInPlainGerman(regionName).toLowerCase();
  return explainedEntries(values, values.length || 4).find((item) => (
    normalizedRegion ? item.toLowerCase().includes(normalizedRegion) : false
  )) || '';
}

function cleanCopy(value?: string | StructuredReasonItem | null): string {
  return explainInPlainGerman(value);
}

function firstCleanText(...values: Array<string | StructuredReasonItem | null | undefined>): string {
  return values.map((value) => cleanCopy(value)).find(Boolean) || '-';
}

function textMentionsRegion(text: string, regionName?: string | null): boolean {
  const cleanedRegionName = cleanCopy(regionName);
  if (!text || !cleanedRegionName || cleanedRegionName === '-') return false;
  return text.toLowerCase().includes(cleanedRegionName.toLowerCase());
}

function regionTrendLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'rising' || normalized === 'up' || normalized === 'steigend') return 'steigend';
  if (normalized === 'falling' || normalized === 'down' || normalized === 'fallend') return 'fallend';
  if (normalized === 'flat' || normalized === 'stabil') return 'stabil';
  return normalized || '';
}

function regionSignalSentence(
  regionName?: string | null,
  signalScore?: number | null,
  trend?: string | null,
): string {
  const cleanedName = cleanCopy(regionName);
  const roundedScore = signalScore == null || Number.isNaN(signalScore) ? null : Math.round(signalScore);
  const trendLabel = regionTrendLabel(trend);

  if (cleanedName && roundedScore != null && trendLabel) {
    return `${cleanedName} zeigt mit ${roundedScore}/100 aktuell die größte Dynamik, der Trend wirkt ${trendLabel}.`;
  }
  if (cleanedName && roundedScore != null) {
    return `${cleanedName} liegt mit ${roundedScore}/100 im Wochenvergleich klar vorne.`;
  }
  return '';
}

function buildNowPageNote(stage: string): string {
  if (stage === 'Aktivieren') {
    return 'Du kannst hier direkt in den nächsten Schritt gehen. Die wichtigsten Hinweise stehen direkt darunter.';
  }
  if (stage === 'Vorbereiten') {
    return 'Die Lage ist wichtig, aber noch nicht ganz freigegeben. Unten siehst du sofort, was du prüfen solltest.';
  }
  return 'Im Moment geht es vor allem um Beobachtung. Du siehst trotzdem direkt, welche Region zuerst wichtig wird und was noch offen ist.';
}

function probabilityPercent(value?: number | null): number | null {
  if (value == null || Number.isNaN(value)) return null;
  return value <= 1 ? value * 100 : value;
}

function stageLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'activate' || normalized === 'go') return 'Aktivieren';
  if (normalized === 'prepare') return 'Vorbereiten';
  return 'Beobachten';
}

function stageTone(value?: string | null): 'success' | 'warning' | 'neutral' {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'activate' || normalized === 'go') return 'success';
  if (normalized === 'prepare') return 'warning';
  return 'neutral';
}

function forecastStatusTone(value: string): 'success' | 'warning' | 'neutral' {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'stabil' || normalized === 'freigabe bereit') return 'success';
  if (normalized === 'beobachten') return 'warning';
  return 'neutral';
}

function customerStatusTone(value: string): 'success' | 'warning' | 'neutral' {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'belastbar') return 'success';
  if (normalized === 'im aufbau' || normalized === 'erste signale') return 'warning';
  return 'neutral';
}

function businessTrustTone(value: string): 'success' | 'warning' | 'neutral' {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'bereit') return 'success';
  if (normalized === 'im aufbau') return 'warning';
  return 'neutral';
}

function recommendationStateLabel(state: NowPageRecommendationState): string {
  if (state === 'strong') return 'Bereit für Review';
  if (state === 'guarded') return 'Mit Vorsicht prüfen';
  if (state === 'weak') return 'Noch keine belastbare Empfehlung';
  return 'Vor Review blockiert';
}

function deriveBriefingState({
  hasRegionalModel,
  hasActionableRecommendation,
  forecastTone,
  dataTone,
  businessTone,
  workspaceStatus,
  dataFreshnessValue,
}: {
  hasRegionalModel: boolean;
  hasActionableRecommendation: boolean;
  forecastTone: 'success' | 'warning' | 'neutral';
  dataTone: 'success' | 'warning' | 'neutral';
  businessTone: 'success' | 'warning' | 'neutral';
  workspaceStatus: WorkspaceStatusSummary | null;
  dataFreshnessValue: string;
}): {
  state: NowPageRecommendationState;
  stateLabel: string;
  actionHint: string | null;
  summary: string;
  stale: boolean;
  staleLabel: string | null;
  staleDetail: string | null;
} {
  const blockers = workspaceStatus?.blockers || [];
  const hasBlockers = (workspaceStatus?.blocker_count || 0) > 0 || blockers.length > 0;
  const stale = workspaceStatus?.data_freshness === 'Beobachten' || dataFreshnessValue === 'Beobachten';
  const strongSignals = forecastTone === 'success' && dataTone === 'success' && businessTone === 'success';
  const weakSignals = !hasRegionalModel
    || !hasActionableRecommendation
    || (forecastTone === 'neutral' && dataTone !== 'success' && businessTone === 'neutral');

  const state: NowPageRecommendationState = hasBlockers
    ? 'blocked'
    : strongSignals
      ? 'strong'
      : weakSignals
        ? 'weak'
        : 'guarded';

  const stateLabel = recommendationStateLabel(state);
  const actionHint = state === 'blocked'
    ? blockers[0] || 'Vor dem Review liegt noch mindestens ein offener Blocker vor.'
    : state === 'weak'
      ? 'Die Richtung ist sichtbar, aber die Datenlage reicht noch nicht für eine belastbare Wochenempfehlung.'
      : state === 'guarded'
        ? 'Die Empfehlung ist prüfbar, sollte aber noch mit Evidenz und Freigabe gespiegelt werden.'
        : null;
  const summary = state === 'blocked'
    ? 'Die Empfehlung ist sichtbar, aber vor dem Review liegen noch offene Punkte auf dem Tisch.'
    : state === 'strong'
      ? 'Forecast, Datenlage und Freigabe tragen die Empfehlung aktuell klar genug für den nächsten Review.'
      : state === 'weak'
        ? 'Es gibt erste Richtungen, aber noch keine wirklich belastbare Wochenempfehlung.'
        : 'Die Empfehlung ist vorhanden, braucht aber noch einen vorsichtigen Blick auf Evidenz und Freigabe.';

  return {
    state,
    stateLabel,
    actionHint,
    summary,
    stale,
    staleLabel: stale ? 'Daten nicht ganz frisch' : null,
    staleDetail: stale
      ? workspaceStatus?.items.find((item) => item.key === 'data_freshness')?.detail || 'Die Datenbasis braucht noch einen kurzen Frische-Check.'
      : null,
  };
}

export function buildWorkspaceStatus(
  decision: MediaDecisionResponse | null,
  evidence: MediaEvidenceResponse | null,
): WorkspaceStatusSummary | null {
  if (!decision && !evidence) return null;

  const truthStatus = decision?.truth_coverage
    || evidence?.truth_snapshot?.coverage
    || evidence?.truth_coverage
    || null;
  const sourceSummary = evidence?.source_status || null;
  const sourceItems = sourceSummary?.items || [];
  const sourceAttentionCount = sourceItems.filter((item) => String(item.status_color || '').toLowerCase() !== 'green').length;
  const forecastStatus = evidence?.forecast_monitoring?.forecast_readiness
    ? readinessGateLabel(evidence.forecast_monitoring.forecast_readiness)
    : monitoringStatusLabel(
      evidence?.forecast_monitoring?.monitoring_status
      || decision?.weekly_decision?.forecast_state
      || decision?.weekly_decision?.decision_state,
    );
  const dataFreshness = sourceSummary
    ? (sourceAttentionCount > 0 ? 'Beobachten' : 'Aktuell')
    : 'Unbekannt';
  const customerDataStatus = truthLayerLabel(truthStatus);
  const hasCustomerTruthData = Boolean((truthStatus?.coverage_weeks || 0) > 0);
  const rawLastImportAt = truthStatus?.last_imported_at
    || evidence?.truth_snapshot?.latest_batch?.uploaded_at
    || decision?.weekly_decision?.truth_last_imported_at
    || null;
  const lastImportAt = hasCustomerTruthData ? rawLastImportAt : null;

  const blockers = uniqueText([
    ...(decision?.weekly_decision?.risk_flags || []),
    decision?.weekly_decision?.truth_risk_flag,
    evidence?.truth_gate?.guidance,
    evidence?.business_validation?.guidance,
    evidence?.business_validation?.message,
    ...(evidence?.forecast_monitoring?.alerts || []),
    evidence?.truth_snapshot?.analyst_note,
  ].map((item) => cleanCopy(sanitizeEvidenceCopy(item))), 4);

  const blockerCount = blockers.length;
  const openBlockers = blockerCount > 0 ? `${blockerCount} offen` : 'Keine';
  const sourceDetail = sourceSummary
    ? `${sourceSummary.live_count || 0}/${sourceSummary.total || 0} Quellen aktuell${sourceAttentionCount > 0 ? `, ${sourceAttentionCount} mit Prüfbedarf` : ''}`
    : 'Noch kein Quellenstatus verfügbar.';
  const customerDetail = hasCustomerTruthData
    ? `${truthStatus?.coverage_weeks ?? 0} Wochen verbunden${lastImportAt ? ` · letzter Import ${formatDateTime(lastImportAt)}` : ''}`
    : 'Noch keine Kundendaten verbunden.';
  const forecastDetail = evidence?.forecast_monitoring
    ? `Prüfung ${monitoringStatusLabel(evidence.forecast_monitoring.monitoring_status)} · Vorhersage ${truthFreshnessLabel(evidence.forecast_monitoring.freshness_status)}`
    : 'Noch kein detaillierter Monitoring-Status verfügbar.';

  return {
    forecast_status: forecastStatus,
    data_freshness: dataFreshness,
    customer_data_status: customerDataStatus,
    open_blockers: openBlockers,
    last_import_at: lastImportAt,
    blocker_count: blockerCount,
    blockers,
    summary: blockerCount > 0
      ? 'Vor dem nächsten Schritt sollten wir zuerst die offenen Punkte prüfen.'
      : 'Die Lage ist klar genug für den nächsten sinnvollen Schritt.',
    items: [
      {
        key: 'forecast_status',
        question: 'Ist die Vorhersage stabil?',
        value: forecastStatus,
        detail: forecastDetail,
        tone: forecastStatusTone(forecastStatus),
      },
      {
        key: 'data_freshness',
        question: 'Sind die Daten frisch?',
        value: dataFreshness,
        detail: sourceDetail,
        tone: sourceSummary ? (sourceAttentionCount > 0 ? 'warning' : 'success') : 'neutral',
      },
      {
        key: 'customer_data_status',
        question: 'Sind Kundendaten verbunden?',
        value: customerDataStatus,
        detail: customerDetail,
        tone: customerStatusTone(customerDataStatus),
      },
      {
        key: 'open_blockers',
        question: 'Gibt es offene Blocker?',
        value: openBlockers,
        detail: blockerCount > 0 ? blockers[0] : 'Aktuell gibt es keine offenen Blocker.',
        tone: blockerCount > 0 ? 'warning' : 'success',
      },
    ],
  };
}

export function buildNowPageViewModel(
  decision: MediaDecisionResponse | null,
  evidence: MediaEvidenceResponse | null,
  forecast: RegionalForecastResponse | null,
  allocation: RegionalAllocationResponse | null,
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null,
  workspaceStatus: WorkspaceStatusSummary | null,
  weeklyBudget: number,
  horizonDays: number,
): NowPageViewModel {
  const weeklyDecision = decision?.weekly_decision;
  const topCard = decision?.top_recommendations?.[0] || null;
  const sortedPredictions = [...(forecast?.predictions || [])].sort((left, right) => {
    const leftRank = Number(left.decision_rank ?? left.rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.decision_rank ?? right.rank ?? Number.MAX_SAFE_INTEGER);
    return leftRank - rightRank;
  });
  const leadPrediction = sortedPredictions[0] || null;
  const leadAllocation = allocation?.recommendations?.[0] || null;
  const leadCampaign = campaignRecommendations?.recommendations?.[0] || null;
  const topRegion = weeklyDecision?.top_regions?.[0] || null;

  const findPredictionForRegion = (code?: string | null, name?: string | null) => sortedPredictions.find((item) => (
    (code && item.bundesland === code)
    || (name && item.bundesland_name === name)
  )) || null;
  const findCampaignForRegion = (code?: string | null, name?: string | null) => (
    campaignRecommendations?.recommendations?.find((item) => (
      (code && (item.bundesland === code || item.region === code))
      || (name && item.region_name === name)
    )) || null
  );
  const findAllocationForRegion = (code?: string | null, name?: string | null) => (
    allocation?.recommendations?.find((item) => (
      (code && item.bundesland === code)
      || (name && item.bundesland_name === name)
    )) || null
  );

  const focusRegionCode = topRegion?.code
    || leadCampaign?.bundesland
    || leadCampaign?.region
    || topCard?.region_codes?.[0]
    || leadAllocation?.bundesland
    || leadPrediction?.bundesland
    || null;
  const focusRegionName = firstCleanText(
    topRegion?.name,
    topCard?.decision_brief?.recommendation?.primary_region,
    leadCampaign?.region_name,
    leadAllocation?.bundesland_name,
    leadPrediction?.bundesland_name,
  );
  const focusPrediction = findPredictionForRegion(focusRegionCode, focusRegionName) || leadPrediction;
  const focusCampaign = findCampaignForRegion(focusRegionCode, focusRegionName) || leadCampaign;
  const focusAllocation = findAllocationForRegion(focusRegionCode, focusRegionName) || leadAllocation;
  const focusStageValue = weeklyDecision?.action_stage
    || weeklyDecision?.decision_state
    || focusCampaign?.activation_level
    || focusAllocation?.recommended_activation_level
    || focusPrediction?.decision_label
    || 'Watch';
  const focusStage = stageLabel(focusStageValue);
  const focusProbabilityLabel = formatPercent(
    probabilityPercent(focusPrediction?.event_probability_calibrated ?? weeklyDecision?.event_forecast?.event_probability),
    1,
  );
  const focusBudgetLabel = formatCurrency(
    topCard?.campaign_preview?.budget?.weekly_budget_eur
    ?? focusCampaign?.suggested_budget_amount
    ?? focusAllocation?.suggested_budget_amount
    ?? weeklyBudget,
  );
  const focusReason = firstCleanText(
    (weeklyDecision?.why_now || []).find((item) => String(item || '').includes(focusRegionName)),
    regionSignalSentence(focusRegionName, topRegion?.signal_score, topRegion?.trend),
    findReasonMentioningRegion([
      ...preferredReasonEntries(
        focusCampaign?.recommendation_rationale?.why_details,
        focusCampaign?.recommendation_rationale?.why,
      ),
    ], focusRegionName),
    topCard?.decision_brief?.summary_sentence,
    focusPrediction?.decision?.explanation_summary_detail,
    focusPrediction?.decision?.explanation_summary,
    focusPrediction?.reason_trace?.why_details?.[0],
    focusPrediction?.reason_trace?.why?.[0],
    focusAllocation?.uncertainty_summary,
    'Hier sehen wir aktuell die größte Dynamik.',
  );
  const focusProduct = firstCleanText(
    topCard?.recommended_product,
    focusCampaign?.products?.[0],
    focusCampaign?.recommended_product_cluster?.products?.[0],
    focusCampaign?.recommended_product_cluster?.label,
    focusAllocation?.products?.[0],
    weeklyDecision?.top_products?.[0],
    'GELO Portfolio',
  );
  const decisionState = decisionStateLabel(weeklyDecision?.decision_state);
  const trustValue = truthLayerLabel(decision?.truth_coverage || evidence?.truth_coverage || evidence?.truth_snapshot?.coverage);
  const businessValue = businessValidationLabel(
    weeklyDecision?.business_readiness
    || decision?.business_validation?.validation_status
    || evidence?.business_validation?.validation_status,
  );
  const evidenceValue = evidenceTierLabel(
    weeklyDecision?.business_evidence_tier
    || decision?.business_validation?.evidence_tier
    || evidence?.business_validation?.evidence_tier,
  );
  const sourceSummary = evidence?.source_status;
  const sourceItems = sourceSummary?.items || [];
  const sourceAttentionCount = sourceItems.filter((item) => String(item.status_color || '').toLowerCase() !== 'green').length;
  const dataFreshnessValue = sourceSummary ? (sourceAttentionCount > 0 ? 'Beobachten' : 'Aktuell') : 'Unklar';
  const dataFreshnessTone = sourceSummary ? (sourceAttentionCount > 0 ? 'warning' : 'success') : 'neutral';
  const dataFreshnessDetail = sourceSummary
    ? `${sourceSummary.live_count || 0}/${sourceSummary.total || 0} Quellen aktuell${sourceAttentionCount > 0 ? `, ${sourceAttentionCount} mit Prüfbedarf` : ''}`
    : 'Noch kein Quellenstatus verfügbar.';
  const businessValidation = weeklyDecision?.business_gate || decision?.business_validation || evidence?.business_validation || null;
  const businessTrustValue = businessValidation?.validated_for_budget_activation
    ? 'Bereit'
    : (
      businessValidation?.truth_ready
      || (businessValidation?.coverage_weeks || 0) > 0
      || (businessValidation?.activation_cycles || 0) > 0
      || Boolean(businessValidation?.holdout_ready)
      || Boolean(businessValidation?.lift_metrics_available)
    )
      ? 'Im Aufbau'
      : 'Noch nicht';
  const businessTrustDetail = firstCleanText(
    cleanCopy(businessValidation?.guidance),
    cleanCopy(businessValidation?.message),
    businessValue !== '-' && evidenceValue !== '-' ? `${businessValue} · ${evidenceValue}` : businessValue,
    'Für eine echte Budgetfreigabe fehlt noch die kommerzielle Absicherung.',
  );
  const primaryCampaignRegionName = firstCleanText(
    topCard?.decision_brief?.recommendation?.primary_region,
    leadCampaign?.region_name,
    focusRegionName,
  );
  const primaryCampaignProduct = firstCleanText(
    topCard?.recommended_product,
    leadCampaign?.products?.[0],
    leadCampaign?.recommended_product_cluster?.products?.[0],
    leadCampaign?.recommended_product_cluster?.label,
    focusProduct,
  );
  const primaryCampaignTitle = firstCleanText(
    primaryCampaignProduct !== '-' && primaryCampaignRegionName !== '-'
      ? `${primaryCampaignProduct} in ${primaryCampaignRegionName}`
      : '',
    topCard?.display_title,
    topCard?.campaign_name,
    'Kampagnenvorschlag prüfen',
  );
  const primaryCampaignContext = firstCleanText(
    topCard?.region_codes_display?.length
      ? `${topCard.region_codes_display.join(', ')} · ${workflowLabel(topCard?.lifecycle_state || topCard?.status)}`
      : '',
    leadCampaign?.timeline,
    `${primaryCampaignRegionName} · ${stageLabel(leadCampaign?.activation_level || focusStageValue)}`,
  );
  const leadCampaignNarrative = uniqueText([
    ...explainedEntries(preferredReasonEntries(
      leadCampaign?.recommendation_rationale?.why_details,
      leadCampaign?.recommendation_rationale?.why,
    )),
    ...explainedEntries(preferredReasonEntries(
      leadCampaign?.recommendation_rationale?.guardrail_details,
      leadCampaign?.recommendation_rationale?.guardrails,
    )),
    leadCampaign?.timeline,
    ...explainedEntries(preferredReasonEntries(
      leadCampaign?.recommendation_rationale?.evidence_note_details,
      leadCampaign?.recommendation_rationale?.evidence_notes,
    )),
  ].map((item) => cleanCopy(item)), 2).join(' ');
  const primaryCampaignCopy = topCard?.id
    ? firstCleanText(
      topCard?.decision_brief?.summary_sentence,
      topCard?.reason,
      leadCampaignNarrative,
      'Der nächste prüfbare Kampagnenvorschlag liegt bereit.',
    )
    : firstCleanText(
      leadCampaignNarrative,
      topCard?.reason,
      topCard?.decision_brief?.summary_sentence,
      'Der nächste prüfbare Kampagnenvorschlag liegt bereit.',
    );

  const forecastProofStatus = evidence?.forecast_monitoring?.forecast_readiness
    ? readinessGateLabel(evidence.forecast_monitoring.forecast_readiness)
    : monitoringStatusLabel(
      evidence?.forecast_monitoring?.monitoring_status
      || weeklyDecision?.forecast_state
      || weeklyDecision?.decision_state,
    );
  const leadDays = numberFromUnknown(
    evidence?.forecast_monitoring?.latest_backtest?.lead_lag?.effective_lead_days,
  );
  const forecastTrustDetail = firstCleanText(
    leadDays && leadDays > 0 ? `Der letzte Marktvergleich zeigt rund ${leadDays} Tage Vorlauf.` : '',
    evidence?.forecast_monitoring
      ? `Prüfung ${monitoringStatusLabel(evidence.forecast_monitoring.monitoring_status)} · Vorhersage ${truthFreshnessLabel(evidence.forecast_monitoring.freshness_status)}`
      : '',
    cleanCopy(weeklyDecision?.decision_mode_reason),
    'Noch kein detaillierter Forecast-Status verfügbar.',
  );

  const reasons = uniqueText([
    ...(weeklyDecision?.why_now || []),
    focusCampaign?.recommendation_rationale?.why_details?.[0],
    focusCampaign?.recommendation_rationale?.why?.[0],
    focusPrediction?.decision?.explanation_summary_detail,
    focusPrediction?.decision?.explanation_summary,
    focusPrediction?.reason_trace?.why_details?.[0],
    focusPrediction?.reason_trace?.why?.[0],
    regionSignalSentence(focusRegionName, topRegion?.signal_score, topRegion?.trend),
  ].map((item) => cleanCopy(item)), 4);

  const risks = uniqueText([
    ...(weeklyDecision?.risk_flags || []),
    focusPrediction?.decision?.uncertainty_summary_detail,
    focusPrediction?.uncertainty_summary,
    ...(focusPrediction?.reason_trace?.uncertainty_details || []),
    ...(focusPrediction?.reason_trace?.uncertainty || []),
    focusAllocation?.uncertainty_summary,
    ...explainedEntries(
      Array.isArray(focusAllocation?.reason_trace)
        ? []
        : preferredReasonEntries(
          (focusAllocation?.reason_trace as { uncertainty_details?: StructuredReasonItem[] } | undefined)?.uncertainty_details,
          ((focusAllocation?.reason_trace as { uncertainty?: string[] } | undefined)?.uncertainty || []),
        ),
    ),
    ...(Array.isArray(focusAllocation?.reason_trace)
      ? []
      : ((focusAllocation?.reason_trace as { uncertainty?: string[] } | undefined)?.uncertainty || [])),
    evidence?.truth_snapshot?.truth_gate?.guidance,
    decision?.business_validation?.guidance,
  ].map((item) => cleanCopy(item)), 4);

  const decisionRelatedRegions = (weeklyDecision?.top_regions || [])
    .filter((item) => item.code !== focusRegionCode && item.name !== focusRegionName)
    .slice(0, 3)
    .map((item, index) => {
      const relatedPrediction = findPredictionForRegion(item.code, item.name);
      return {
        code: item.code || relatedPrediction?.bundesland || item.name || `region-${index + 1}`,
        name: firstCleanText(item.name, relatedPrediction?.bundesland_name),
        stage: stageLabel(relatedPrediction?.decision_label || focusStageValue),
        probabilityLabel: relatedPrediction
          ? formatPercent(probabilityPercent(relatedPrediction.event_probability_calibrated), 1)
          : item.signal_score != null
            ? `${Math.round(item.signal_score)}/100`
            : '-',
        reason: firstCleanText(
          regionSignalSentence(item.name, item.signal_score, item.trend),
          relatedPrediction?.reason_trace?.why_details?.[0],
          relatedPrediction?.reason_trace?.why?.[0],
          relatedPrediction?.decision?.explanation_summary_detail,
          relatedPrediction?.decision?.explanation_summary,
          relatedPrediction?.uncertainty_summary,
          'Weitere regionale Priorität für diese Woche.',
        ),
      };
    });

  const forecastRelatedRegions = sortedPredictions
    .filter((item) => item.bundesland !== focusRegionCode && item.bundesland_name !== focusRegionName)
    .slice(0, 3)
    .map((item) => ({
      code: item.bundesland,
      name: cleanCopy(item.bundesland_name),
      stage: stageLabel(item.decision_label),
      probabilityLabel: formatPercent(probabilityPercent(item.event_probability_calibrated), 1),
      reason: firstCleanText(
        item.reason_trace?.why_details?.[0],
        item.reason_trace?.why?.[0],
        item.decision?.explanation_summary_detail,
        item.decision?.explanation_summary,
        item.uncertainty_summary,
        'Weitere regionale Priorität für diese Woche.',
      ),
    }));

  const relatedRegions = decisionRelatedRegions.length > 0 ? decisionRelatedRegions : forecastRelatedRegions;
  const hasFocusRegion = Boolean(focusRegionCode || (focusRegionName && focusRegionName !== '-'));
  const hasActionableRecommendation = Boolean(
    topCard?.id
    || focusCampaign
    || focusAllocation
    || focusPrediction
    || weeklyDecision?.recommended_action
    || hasFocusRegion,
  );
  const stateSnapshot = deriveBriefingState({
    hasRegionalModel: hasFocusRegion || Boolean(sortedPredictions.length),
    hasActionableRecommendation,
    forecastTone: forecastStatusTone(forecastProofStatus),
    dataTone: dataFreshnessTone,
    businessTone: businessTrustTone(businessTrustValue),
    workspaceStatus,
    dataFreshnessValue,
  });

  const hasData = Boolean(
    decision
    || evidence
    || sortedPredictions.length
    || (allocation?.recommendations || []).length
    || (campaignRecommendations?.recommendations || []).length,
  );

  const emptyMessage = cleanCopy(forecast?.message || allocation?.message || campaignRecommendations?.message);
  const emptyState = !hasData ? {
    title: forecast?.status === 'no_model'
      ? 'Für diesen Scope ist noch kein regionales Modell verfügbar.'
      : 'Für diesen Scope liegen gerade keine belastbaren Arbeitsdaten vor.',
    body: emptyMessage || 'Wechsle Virus oder Zeitraum oder prüfe die Qualität.',
  } : (!hasFocusRegion && forecast?.status === 'no_model') ? {
    title: 'Für dieses Wochenbriefing liegt noch kein regionales Modell vor.',
    body: emptyMessage || 'Sobald der Forecast wieder Bundesland-Signale liefert, erscheint hier auch die nächste regionale Empfehlung.',
  } : (!hasActionableRecommendation) ? {
    title: 'Noch keine belastbare Wochenempfehlung.',
    body: sourceSummary
      ? 'Die Datenlage zeigt erste Signale, reicht aber noch nicht für einen klaren Fokus auf Bundesland-Level.'
      : 'Es fehlen noch belastbare Regional- und Qualitätsdaten für einen klaren Wochenfokus.',
  } : null;

  const cleanedDecisionSummary = cleanCopy(weeklyDecision?.recommended_action);
  const proof = focusRegionName
    ? buildPredictionNarrative({
      horizonDays,
      regionName: focusRegionName,
      forecastStatus: forecastProofStatus,
      proofPoints: uniqueText([
        `${horizonDays} Tage Vorhersagefenster.`,
        `${focusRegionName} zeigt aktuell die größte Dynamik.`,
        leadDays && leadDays > 0 ? `Der letzte Marktvergleich zeigt rund ${leadDays} Tage Vorlauf.` : null,
        sourceSummary ? `${sourceSummary.live_count || 0}/${sourceSummary.total || 0} Quellen sind aktuell.` : null,
        reasons[0],
      ], 3),
    })
    : null;
  const focusAlignedSummary = proof?.headline || (
    textMentionsRegion(cleanedDecisionSummary, focusRegionName)
      ? cleanedDecisionSummary
      : firstCleanText(
        `${focusRegionName} steht diese Woche im Mittelpunkt. ${focusReason}`,
        cleanedDecisionSummary,
        topCard?.decision_brief?.summary_sentence,
        `Die stärkste nächste Aktion liegt aktuell in ${focusRegionName}.`,
      )
  );
  const heroHeadline = firstCleanText(
    textMentionsRegion(primaryCampaignTitle, focusRegionName)
      ? primaryCampaignTitle
      : primaryCampaignTitle !== '-' && focusRegionName !== '-'
        ? `${primaryCampaignTitle} in ${focusRegionName}`
        : '',
    cleanedDecisionSummary,
    focusRegionName !== '-' ? `${focusRegionName} zuerst priorisieren` : '',
    'Wochenfokus vorbereiten',
  );
  const heroContext = firstCleanText(
    focusRegionName !== '-' && focusProduct !== '-'
      ? `${focusRegionName} · ${focusProduct}`
      : '',
    focusRegionName !== '-' ? `${focusRegionName} · ${focusStage}` : '',
    primaryCampaignContext,
    'Bundesland-Level',
  );
  const heroWhyNow = firstCleanText(
    reasons[0],
    focusReason,
    proof?.supportingText,
    primaryCampaignCopy,
    'Hier zeigt sich aktuell der stärkste nächste Schritt für diese Woche.',
  );
  const secondaryMoves = relatedRegions.slice(0, 2).map((region) => ({
    code: region.code,
    name: region.name,
    stage: region.stage,
    probabilityLabel: region.probabilityLabel,
    reason: region.reason,
  }));
  const briefingTrustItems: NowPageBriefingTrustItem[] = [
    {
      key: 'reliability',
      label: 'Reliability',
      value: forecastProofStatus,
      detail: forecastTrustDetail,
      tone: forecastStatusTone(forecastProofStatus),
    },
    {
      key: 'evidence',
      label: 'Daten & Evidenz',
      value: dataFreshnessValue,
      detail: firstCleanText(
        dataFreshnessDetail,
        trustValue !== '-' ? `Kundendaten ${trustValue}` : '',
        evidenceValue !== '-' ? `Belegstufe ${evidenceValue}` : '',
      ),
      tone: dataFreshnessTone,
    },
    {
      key: 'readiness',
      label: 'Readiness / Blocker',
      value: workspaceStatus?.open_blockers && workspaceStatus.open_blockers !== 'Keine'
        ? workspaceStatus.open_blockers
        : businessTrustValue,
      detail: workspaceStatus?.blocker_count
        ? workspaceStatus.blockers[0]
        : businessTrustDetail,
      tone: workspaceStatus?.blocker_count ? 'warning' : businessTrustTone(businessTrustValue),
    },
  ];

  return {
    hasData,
    generatedAt: decision?.generated_at || forecast?.generated_at || allocation?.generated_at || campaignRecommendations?.generated_at || evidence?.generated_at || null,
    title: focusRegionName !== '-' ? `${focusStage}: ${focusRegionName}` : 'Wochenbriefing',
    summary: focusAlignedSummary,
    note: proof?.supportingText || buildNowPageNote(focusStage),
    proof,
    primaryActionLabel: 'Top-Empfehlung prüfen',
    primaryRecommendationId: topCard?.id || null,
    heroRecommendation: hasData ? {
      headline: heroHeadline,
      actionLabel: 'Top-Empfehlung prüfen',
      direction: focusStage,
      region: focusRegionName !== '-' ? focusRegionName : 'Bundesland noch offen',
      regionCode: focusRegionCode,
      context: heroContext,
      whyNow: heroWhyNow,
      state: stateSnapshot.state,
      stateLabel: stateSnapshot.stateLabel,
      actionHint: stateSnapshot.actionHint,
      ctaDisabled: stateSnapshot.state === 'blocked',
    } : null,
    secondaryMoves,
    briefingTrust: {
      summary: stateSnapshot.summary,
      items: briefingTrustItems,
    },
    supportState: {
      stale: stateSnapshot.stale,
      label: stateSnapshot.staleLabel,
      detail: stateSnapshot.staleDetail,
    },
    primaryCampaignTitle,
    primaryCampaignContext,
    primaryCampaignCopy,
    focusRegion: focusRegionName ? {
      code: focusRegionCode,
      name: focusRegionName,
      stage: focusStage,
      reason: focusReason,
      product: focusProduct,
      probabilityLabel: focusProbabilityLabel,
      budgetLabel: focusBudgetLabel,
      recommendationId: topCard?.id || null,
    } : null,
    metrics: [
      {
        label: OPERATOR_LABELS.business_validation_gate,
        value: decisionState,
        tone: stageTone(weeklyDecision?.decision_state),
      },
      {
        label: OPERATOR_LABELS.forecast_event_probability,
        value: focusProbabilityLabel,
        tone: stageTone(focusStageValue),
      },
      {
        label: 'Empfohlenes Wochenbudget',
        value: focusBudgetLabel,
        tone: 'neutral',
      },
      {
        label: 'Kundendatenbasis',
        value: trustValue,
        tone: trustValue === 'belastbar' ? 'success' : trustValue === 'im Aufbau' ? 'warning' : 'neutral',
      },
    ],
    trustChecks: [
      {
        key: 'forecast',
        question: 'Kann ich der Vorhersage trauen?',
        value: forecastProofStatus,
        detail: forecastTrustDetail,
        tone: forecastStatusTone(forecastProofStatus),
      },
      {
        key: 'data',
        question: 'Sind die Daten frisch genug?',
        value: dataFreshnessValue,
        detail: dataFreshnessDetail,
        tone: dataFreshnessTone,
      },
      {
        key: 'business',
        question: 'Ist eine Business-Freigabe schon drin?',
        value: businessTrustValue,
        detail: businessTrustDetail,
        tone: businessTrustTone(businessTrustValue),
      },
    ],
    reasons: reasons.length > 0 ? reasons : ['Noch keine kurze Begründung verfügbar.'],
    risks: risks.length > 0 ? risks : ['Aktuell sind keine zusätzlichen Risikohinweise hinterlegt.'],
    quality: [
      {
        label: 'Quellen aktuell',
        value: sourceSummary ? `${sourceSummary.live_count || 0}/${sourceSummary.total || 0}` : '-',
      },
      {
        label: 'Kundendaten',
        value: trustValue,
      },
      {
        label: OPERATOR_LABELS.business_validation_gate,
        value: businessValue,
      },
      {
        label: 'Belegstufe',
        value: evidenceValue,
      },
    ],
    relatedRegions,
    emptyState,
  };
}
