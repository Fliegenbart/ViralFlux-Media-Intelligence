import { useCallback, useEffect, useRef, useState } from 'react';

import { decisionStateLabel } from '../../lib/copy';
import { buildPredictionNarrative, explainInPlainGerman } from '../../lib/plainLanguage';
import {
  BacktestResponse,
  MediaCampaignsResponse,
  MediaDecisionResponse,
  MediaEvidenceResponse,
  MediaRegionsResponse,
  RegionalAllocationResponse,
  RegionalBacktestResponse,
  RegionalBenchmarkResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastResponse,
  RegionalPortfolioResponse,
  StructuredReasonItem,
  TruthImportBatchDetailResponse,
  TruthImportResponse,
  WaveRadarResponse,
  PredictionNarrative,
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
import { mediaApi } from './api';
import { WorkspaceStatusSummary } from '../../types/media';

function noop() {}

interface ToastLike {
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

export interface NowPageViewModel {
  hasData: boolean;
  generatedAt: string | null;
  title: string;
  summary: string;
  note: string;
  proof: PredictionNarrative | null;
  primaryActionLabel: string;
  primaryRecommendationId: string | null;
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

function deriveNowFocusRegionCode(
  decision: MediaDecisionResponse | null,
  forecast: RegionalForecastResponse | null,
  allocation: RegionalAllocationResponse | null,
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null,
): string | null {
  const weeklyDecision = decision?.weekly_decision;
  const topCard = decision?.top_recommendations?.[0] || null;
  const sortedPredictions = [...(forecast?.predictions || [])].sort((left, right) => {
    const leftRank = Number(left.decision_rank ?? left.rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.decision_rank ?? right.rank ?? Number.MAX_SAFE_INTEGER);
    return leftRank - rightRank;
  });
  return weeklyDecision?.top_regions?.[0]?.code
    || campaignRecommendations?.recommendations?.[0]?.bundesland
    || campaignRecommendations?.recommendations?.[0]?.region
    || topCard?.region_codes?.[0]
    || allocation?.recommendations?.[0]?.bundesland
    || sortedPredictions[0]?.bundesland
    || null;
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

function buildWorkspaceStatus(
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
  const lastImportAt = truthStatus?.last_imported_at
    || evidence?.truth_snapshot?.latest_batch?.uploaded_at
    || decision?.weekly_decision?.truth_last_imported_at
    || null;

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
  const customerDetail = truthStatus
    ? `${truthStatus.coverage_weeks ?? 0} Wochen verbunden${lastImportAt ? ` · letzter Import ${formatDateTime(lastImportAt)}` : ''}`
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

function buildNowPageViewModel(
  decision: MediaDecisionResponse | null,
  evidence: MediaEvidenceResponse | null,
  forecast: RegionalForecastResponse | null,
  allocation: RegionalAllocationResponse | null,
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null,
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
    'Deutschland',
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

  const hasData = Boolean(
    decision
    || evidence
    || sortedPredictions.length
    || (allocation?.recommendations || []).length
    || (campaignRecommendations?.recommendations || []).length,
  );

  const emptyMessage = cleanCopy(forecast?.message || allocation?.message || campaignRecommendations?.message);
  const emptyState = hasData ? null : {
    title: forecast?.status === 'no_model'
      ? 'Für diesen Scope ist noch kein regionales Modell verfügbar.'
      : 'Für diesen Scope liegen gerade keine belastbaren Arbeitsdaten vor.',
    body: emptyMessage || 'Wechsle Virus oder Zeitraum oder prüfe die Qualität.',
  };

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

  return {
    hasData,
    generatedAt: decision?.generated_at || forecast?.generated_at || allocation?.generated_at || campaignRecommendations?.generated_at || evidence?.generated_at || null,
    title: `${focusStage}: ${focusRegionName}`,
    summary: focusAlignedSummary,
    note: proof?.supportingText || buildNowPageNote(focusStage),
    proof,
    primaryActionLabel: topCard?.id ? 'Nächste Kampagne öffnen' : 'Kampagnen prüfen',
    primaryRecommendationId: topCard?.id || null,
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
        label: 'Freigabestatus',
        value: decisionState,
        tone: stageTone(weeklyDecision?.decision_state),
      },
      {
        label: 'Vorhersagesignal',
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
        tone: sourceSummary ? (sourceAttentionCount > 0 ? 'warning' : 'success') : 'neutral',
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
        label: 'Freigabestatus',
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

export function useNowPageData(
  virus: string,
  brand: string,
  horizonDays: number,
  weeklyBudget: number,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [decision, setDecision] = useState<MediaDecisionResponse | null>(null);
  const [evidence, setEvidence] = useState<MediaEvidenceResponse | null>(null);
  const [forecast, setForecast] = useState<RegionalForecastResponse | null>(null);
  const [allocation, setAllocation] = useState<RegionalAllocationResponse | null>(null);
  const [campaignRecommendations, setCampaignRecommendations] = useState<RegionalCampaignRecommendationsResponse | null>(null);
  const [focusRegionBacktest, setFocusRegionBacktest] = useState<RegionalBacktestResponse | null>(null);
  const [focusRegionBacktestLoading, setFocusRegionBacktestLoading] = useState(false);
  const [waveOutlook, setWaveOutlook] = useState<BacktestResponse | null>(null);
  const [waveOutlookLoading, setWaveOutlookLoading] = useState(false);
  const [waveRadar, setWaveRadar] = useState<WaveRadarResponse | null>(null);
  const [waveRadarLoading, setWaveRadarLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const loadVersionRef = useRef(0);

  const loadNowPage = useCallback(async () => {
    const loadVersion = loadVersionRef.current + 1;
    loadVersionRef.current = loadVersion;
    const isCurrentLoad = () => loadVersionRef.current === loadVersion;

    setLoading(true);
    setForecast(null);
    setAllocation(null);
    setCampaignRecommendations(null);
    setFocusRegionBacktest(null);
    setFocusRegionBacktestLoading(false);
    setWaveOutlook(null);
    setWaveOutlookLoading(false);
    setWaveRadar(null);
    setWaveRadarLoading(false);

    const [decisionResult, evidenceResult] = await Promise.allSettled([
      mediaApi.getDecision(virus, brand),
      mediaApi.getEvidence(virus, brand),
    ]);

    if (!isCurrentLoad()) return;

    if (decisionResult.status === 'fulfilled') {
      setDecision(decisionResult.value);
    } else {
      console.error('Now page decision fetch failed', decisionResult.reason);
      setDecision(null);
      toast('Die Wochenentscheidung konnte nicht geladen werden.', 'error');
    }

    if (evidenceResult.status === 'fulfilled') {
      setEvidence(evidenceResult.value);
    } else {
      console.error('Now page evidence fetch failed', evidenceResult.reason);
      setEvidence(null);
      toast('Die Qualitätsdaten konnten nicht geladen werden.', 'error');
    }

    setLoading(false);

    if (!isCurrentLoad()) return;

    let proofGraphFailed = false;
    let backgroundLoadFailed = false;
    const waveRunId = decisionResult.status === 'fulfilled' ? decisionResult.value.wave_run_id : null;

    if (waveRunId) {
      setWaveOutlookLoading(true);
      const waveOutlookResult = await mediaApi.getBacktestRun(waveRunId)
        .then((value) => ({ status: 'fulfilled' as const, value }))
        .catch((reason) => ({ status: 'rejected' as const, reason }));

      if (!isCurrentLoad()) return;

      if (waveOutlookResult.status === 'fulfilled') {
        setWaveOutlook(waveOutlookResult.value?.run_id ? waveOutlookResult.value : null);
      } else {
        console.error('Now page wave outlook fetch failed', waveOutlookResult.reason);
        setWaveOutlook(null);
        proofGraphFailed = true;
      }
      setWaveOutlookLoading(false);
    }

    setWaveRadarLoading(true);
    const [forecastResult, allocationResult, recommendationResult, waveRadarResult] = await Promise.allSettled([
      mediaApi.getRegionalForecast(virus, horizonDays),
      mediaApi.getRegionalAllocation(virus, weeklyBudget, horizonDays),
      mediaApi.getRegionalCampaignRecommendations(virus, weeklyBudget, horizonDays),
      mediaApi.getWaveRadar(virus),
    ]);

    if (!isCurrentLoad()) return;

    if (forecastResult.status === 'fulfilled') {
      setForecast(forecastResult.value);
    } else {
      console.error('Now page forecast fetch failed', forecastResult.reason);
      setForecast(null);
      backgroundLoadFailed = true;
    }

    if (allocationResult.status === 'fulfilled') {
      setAllocation(allocationResult.value);
    } else {
      console.error('Now page allocation fetch failed', allocationResult.reason);
      setAllocation(null);
      backgroundLoadFailed = true;
    }

    if (recommendationResult.status === 'fulfilled') {
      setCampaignRecommendations(recommendationResult.value);
    } else {
      console.error('Now page recommendation fetch failed', recommendationResult.reason);
      setCampaignRecommendations(null);
      backgroundLoadFailed = true;
    }

    if (waveRadarResult.status === 'fulfilled' && !waveRadarResult.value?.error) {
      setWaveRadar(waveRadarResult.value);
    } else {
      if (waveRadarResult.status === 'rejected') {
        console.error('Now page wave radar fetch failed', waveRadarResult.reason);
      }
      setWaveRadar(null);
    }
    setWaveRadarLoading(false);

    const focusRegionCode = deriveNowFocusRegionCode(
      decisionResult.status === 'fulfilled' ? decisionResult.value : null,
      forecastResult.status === 'fulfilled' ? forecastResult.value : null,
      allocationResult.status === 'fulfilled' ? allocationResult.value : null,
      recommendationResult.status === 'fulfilled' ? recommendationResult.value : null,
    );

    if (focusRegionCode) {
      setFocusRegionBacktestLoading(true);
      const regionalBacktestResult = await mediaApi.getRegionalBacktest(virus, focusRegionCode, horizonDays)
        .then((value) => ({ status: 'fulfilled' as const, value }))
        .catch((reason) => ({ status: 'rejected' as const, reason }));

      if (!isCurrentLoad()) return;

      if (regionalBacktestResult.status === 'fulfilled' && !regionalBacktestResult.value?.error) {
        setFocusRegionBacktest(regionalBacktestResult.value);
      } else {
        if (regionalBacktestResult.status === 'rejected') {
          console.error('Now page focus region backtest fetch failed', regionalBacktestResult.reason);
        }
        setFocusRegionBacktest(null);
      }
      setFocusRegionBacktestLoading(false);
    }

    if (proofGraphFailed) {
      toast('Der Verlaufsgraph konnte nicht geladen werden. Die Wochenlage bleibt trotzdem sichtbar.', 'info');
    }

    if (backgroundLoadFailed) {
      toast('Ein Teil der Regionaldaten laedt laenger als erwartet. Die Wochenlage bleibt trotzdem sichtbar.', 'info');
    }
  }, [brand, horizonDays, toast, virus, weeklyBudget]);

  useEffect(() => {
    loadNowPage();
    return () => {
      loadVersionRef.current += 1;
    };
  }, [dataVersion, loadNowPage]);

  return {
    decision,
    evidence,
    forecast,
    allocation,
    campaignRecommendations,
    focusRegionBacktest,
    focusRegionBacktestLoading,
    waveOutlook,
    waveOutlookLoading,
    waveRadar,
    waveRadarLoading,
    loading,
    loadNowPage,
    workspaceStatus: buildWorkspaceStatus(decision, evidence),
    view: buildNowPageViewModel(decision, evidence, forecast, allocation, campaignRecommendations, weeklyBudget, horizonDays),
  };
}

export function useDecisionPageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [decision, setDecision] = useState<MediaDecisionResponse | null>(null);
  const [decisionEvidence, setDecisionEvidence] = useState<MediaEvidenceResponse | null>(null);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [waveOutlook, setWaveOutlook] = useState<BacktestResponse | null>(null);
  const [waveOutlookLoading, setWaveOutlookLoading] = useState(false);
  const [waveRadar, setWaveRadar] = useState<WaveRadarResponse | null>(null);
  const [waveRadarLoading, setWaveRadarLoading] = useState(false);
  const [regionalBenchmark, setRegionalBenchmark] = useState<RegionalBenchmarkResponse | null>(null);
  const [regionalPortfolio, setRegionalPortfolio] = useState<RegionalPortfolioResponse | null>(null);
  const [regionalPortfolioLoading, setRegionalPortfolioLoading] = useState(false);

  const loadDecision = useCallback(async () => {
    setDecisionLoading(true);
    setRegionalPortfolioLoading(true);
    setWaveRadar(null);
    setWaveRadarLoading(false);
    let decisionLoaded = false;
    try {
      const decisionResult = await mediaApi.getDecision(virus, brand);
      setDecision(decisionResult);
      decisionLoaded = true;
    } catch (error) {
      console.error('Decision fetch failed', error);
      toast('Entscheidung konnte nicht geladen werden.', 'error');
    } finally {
      setDecisionLoading(false);
    }

    if (!decisionLoaded) {
      setWaveRadarLoading(false);
      setRegionalPortfolioLoading(false);
      return;
    }

    setWaveRadarLoading(true);
    Promise.allSettled([
      mediaApi.getEvidence(virus, brand),
      mediaApi.getRegionalBenchmark(),
      mediaApi.getRegionalPortfolio(),
      mediaApi.getWaveRadar(virus),
    ]).then(([evidenceResult, benchmarkResult, portfolioResult, waveRadarResult]) => {
      if (evidenceResult.status === 'fulfilled') {
        setDecisionEvidence(evidenceResult.value);
      } else {
        console.error('Decision evidence fetch failed', evidenceResult.reason);
        setDecisionEvidence(null);
      }

      if (benchmarkResult.status === 'fulfilled') {
        setRegionalBenchmark(benchmarkResult.value);
      } else {
        console.error('Regional benchmark fetch failed', benchmarkResult.reason);
        setRegionalBenchmark(null);
      }

      if (portfolioResult.status === 'fulfilled') {
        setRegionalPortfolio(portfolioResult.value);
      } else {
        console.error('Regional portfolio fetch failed', portfolioResult.reason);
        setRegionalPortfolio(null);
      }

      if (waveRadarResult.status === 'fulfilled' && !waveRadarResult.value?.error) {
        setWaveRadar(waveRadarResult.value);
      } else {
        if (waveRadarResult.status === 'rejected') {
          console.error('Wave radar fetch failed', waveRadarResult.reason);
        }
        setWaveRadar(null);
      }
    }).finally(() => {
      setWaveRadarLoading(false);
      setRegionalPortfolioLoading(false);
    });
  }, [brand, toast, virus]);

  useEffect(() => {
    loadDecision();
  }, [dataVersion, loadDecision]);

  useEffect(() => {
    const runId = decision?.wave_run_id;
    if (!runId) {
      setWaveOutlook(null);
      setWaveOutlookLoading(false);
      return;
    }

    let active = true;
    setWaveOutlookLoading(true);
    mediaApi.getBacktestRun(runId)
      .then((result) => {
        if (active) setWaveOutlook(result?.run_id ? result : null);
      })
      .catch((error) => {
        console.error('Market validation detail failed', error);
        if (active) setWaveOutlook(null);
      })
      .finally(() => {
        if (active) setWaveOutlookLoading(false);
      });

    return () => {
      active = false;
    };
  }, [decision?.wave_run_id]);

  return {
    decision,
    decisionEvidence,
    decisionLoading,
    loadDecision,
    waveOutlook,
    waveOutlookLoading,
    waveRadar,
    waveRadarLoading,
    regionalBenchmark,
    regionalPortfolio,
    regionalPortfolioLoading,
  };
}

export function useRegionsPageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [regionsView, setRegionsView] = useState<MediaRegionsResponse | null>(null);
  const [regionsLoading, setRegionsLoading] = useState(false);
  const [workspaceStatus, setWorkspaceStatus] = useState<WorkspaceStatusSummary | null>(null);

  const loadRegions = useCallback(async () => {
    setRegionsLoading(true);
    const [regionsResult, evidenceResult] = await Promise.allSettled([
      mediaApi.getRegions(virus, brand),
      mediaApi.getEvidence(virus, brand),
    ]);

    if (regionsResult.status === 'fulfilled') {
      setRegionsView(regionsResult.value);
    } else {
      console.error('Regions fetch failed', regionsResult.reason);
      setRegionsView(null);
      toast('Regionen konnten nicht geladen werden.', 'error');
    }

    if (evidenceResult.status === 'fulfilled') {
      setWorkspaceStatus(buildWorkspaceStatus(null, evidenceResult.value));
    } else {
      console.error('Regions evidence fetch failed', evidenceResult.reason);
      setWorkspaceStatus(null);
      toast('Der Qualitätsstatus für Regionen konnte nicht geladen werden.', 'error');
    }

    setRegionsLoading(false);
  }, [brand, toast, virus]);

  useEffect(() => {
    loadRegions();
  }, [dataVersion, loadRegions]);

  return {
    regionsView,
    regionsLoading,
    loadRegions,
    workspaceStatus,
  };
}

export function useCampaignsPageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [campaignsView, setCampaignsView] = useState<MediaCampaignsResponse | null>(null);
  const [campaignsLoading, setCampaignsLoading] = useState(false);
  const [workspaceStatus, setWorkspaceStatus] = useState<WorkspaceStatusSummary | null>(null);

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    const [campaignsResult, evidenceResult] = await Promise.allSettled([
      mediaApi.getCampaigns(brand),
      mediaApi.getEvidence(virus, brand),
    ]);

    if (campaignsResult.status === 'fulfilled') {
      setCampaignsView(campaignsResult.value);
    } else {
      console.error('Campaigns fetch failed', campaignsResult.reason);
      setCampaignsView(null);
      toast('Kampagnenvorschläge konnten nicht geladen werden.', 'error');
    }

    if (evidenceResult.status === 'fulfilled') {
      setWorkspaceStatus(buildWorkspaceStatus(null, evidenceResult.value));
    } else {
      console.error('Campaigns evidence fetch failed', evidenceResult.reason);
      setWorkspaceStatus(null);
      toast('Der Qualitätsstatus für Kampagnen konnte nicht geladen werden.', 'error');
    }

    setCampaignsLoading(false);
  }, [brand, toast, virus]);

  useEffect(() => {
    loadCampaigns();
  }, [dataVersion, loadCampaigns]);

  return {
    campaignsView,
    campaignsLoading,
    loadCampaigns,
    workspaceStatus,
  };
}

export function useEvidencePageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [evidence, setEvidence] = useState<MediaEvidenceResponse | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [truthPreview, setTruthPreview] = useState<TruthImportResponse | null>(null);
  const [truthBatchDetail, setTruthBatchDetail] = useState<TruthImportBatchDetailResponse | null>(null);
  const [truthActionLoading, setTruthActionLoading] = useState(false);
  const [truthBatchDetailLoading, setTruthBatchDetailLoading] = useState(false);
  const [marketValidation, setMarketValidation] = useState<BacktestResponse | null>(null);
  const [marketValidationLoading, setMarketValidationLoading] = useState(false);
  const [customerValidation, setCustomerValidation] = useState<BacktestResponse | null>(null);
  const [customerValidationLoading, setCustomerValidationLoading] = useState(false);

  const loadEvidence = useCallback(async () => {
    setEvidenceLoading(true);
    try {
      setEvidence(await mediaApi.getEvidence(virus, brand));
    } catch (error) {
      console.error('Evidence fetch failed', error);
      toast('Qualität konnte nicht geladen werden.', 'error');
    } finally {
      setEvidenceLoading(false);
    }
  }, [brand, toast, virus]);

  const loadTruthBatchDetail = useCallback(async (batchId: string) => {
    if (!batchId) return;
    setTruthBatchDetailLoading(true);
    try {
      setTruthBatchDetail(await mediaApi.getTruthImportBatchDetail(batchId));
    } catch (error) {
      console.error('Truth batch detail failed', error);
      toast('Import-Detail konnte nicht geladen werden.', 'error');
    } finally {
      setTruthBatchDetailLoading(false);
    }
  }, [toast]);

  const submitTruthCsv = useCallback(async ({
    file,
    sourceLabel,
    replaceExisting,
    validateOnly,
  }: {
    file: File;
    sourceLabel: string;
    replaceExisting: boolean;
    validateOnly: boolean;
  }) => {
    setTruthActionLoading(true);
    try {
      const csvPayload = await file.text();
      const result = await mediaApi.importTruthCsv({
        brand,
        source_label: sourceLabel,
        replace_existing: replaceExisting,
        validate_only: validateOnly,
        file_name: file.name,
        csv_payload: csvPayload,
      });
      setTruthPreview(result);
      if (result.batch_id) {
        await loadTruthBatchDetail(result.batch_id);
      }
      await loadEvidence();
      toast(
        validateOnly ? 'Kundendaten geprüft. Die Vorschau ist bereit.' : 'Kundendaten importiert und Qualität aktualisiert.',
        'success',
      );
    } catch (error) {
      console.error('Truth upload failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Import der Kundendaten fehlgeschlagen: ${message}`, 'error');
    } finally {
      setTruthActionLoading(false);
    }
  }, [brand, loadEvidence, loadTruthBatchDetail, toast]);

  useEffect(() => {
    loadEvidence();
  }, [dataVersion, loadEvidence]);

  useEffect(() => {
    if (!evidence?.truth_snapshot?.latest_batch?.batch_id) {
      setTruthBatchDetail(null);
      return;
    }
    loadTruthBatchDetail(evidence.truth_snapshot.latest_batch.batch_id);
  }, [evidence?.truth_snapshot?.latest_batch?.batch_id, loadTruthBatchDetail]);

  useEffect(() => {
    const runId = evidence?.proxy_validation?.run_id;
    if (!runId) {
      setMarketValidation(null);
      setMarketValidationLoading(false);
      return;
    }

    let active = true;
    setMarketValidationLoading(true);
    mediaApi.getBacktestRun(runId)
      .then((result) => {
        if (active) setMarketValidation(result?.run_id ? result : null);
      })
      .catch((error) => {
        console.error('Market validation detail failed', error);
        if (active) setMarketValidation(null);
      })
      .finally(() => {
        if (active) setMarketValidationLoading(false);
      });

    return () => {
      active = false;
    };
  }, [evidence?.proxy_validation?.run_id]);

  useEffect(() => {
    const runId = evidence?.truth_validation?.run_id;
    if (!runId) {
      setCustomerValidation(null);
      setCustomerValidationLoading(false);
      return;
    }

    let active = true;
    setCustomerValidationLoading(true);
    mediaApi.getBacktestRun(runId)
      .then((result) => {
        if (active) setCustomerValidation(result?.run_id ? result : null);
      })
      .catch((error) => {
        console.error('Customer validation detail failed', error);
        if (active) setCustomerValidation(null);
      })
      .finally(() => {
        if (active) setCustomerValidationLoading(false);
      });

    return () => {
      active = false;
    };
  }, [evidence?.truth_validation?.run_id]);

  return {
    evidence,
    evidenceLoading,
    loadEvidence,
    workspaceStatus: buildWorkspaceStatus(null, evidence),
    marketValidation,
    marketValidationLoading,
    customerValidation,
    customerValidationLoading,
    truthPreview,
    truthBatchDetail,
    truthActionLoading,
    truthBatchDetailLoading,
    loadTruthBatchDetail,
    submitTruthCsv,
  };
}

export function useOperationalDashboardData(
  virus: string,
  horizonDays: number,
  weeklyBudget: number,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [forecast, setForecast] = useState<RegionalForecastResponse | null>(null);
  const [allocation, setAllocation] = useState<RegionalAllocationResponse | null>(null);
  const [campaignRecommendations, setCampaignRecommendations] = useState<RegionalCampaignRecommendationsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadOperationalDashboard = useCallback(async () => {
    setLoading(true);
    const [forecastResult, allocationResult, recommendationResult] = await Promise.allSettled([
      mediaApi.getRegionalForecast(virus, horizonDays),
      mediaApi.getRegionalAllocation(virus, weeklyBudget, horizonDays),
      mediaApi.getRegionalCampaignRecommendations(virus, weeklyBudget, horizonDays),
    ]);

    if (forecastResult.status === 'fulfilled') {
      setForecast(forecastResult.value);
    } else {
      console.error('Regional forecast fetch failed', forecastResult.reason);
      setForecast(null);
      toast('Die regionale Vorhersage konnte nicht geladen werden.', 'error');
    }

    if (allocationResult.status === 'fulfilled') {
      setAllocation(allocationResult.value);
    } else {
      console.error('Regional allocation fetch failed', allocationResult.reason);
      setAllocation(null);
      toast('Budgetallokation konnte nicht geladen werden.', 'error');
    }

    if (recommendationResult.status === 'fulfilled') {
      setCampaignRecommendations(recommendationResult.value);
    } else {
      console.error('Campaign recommendations fetch failed', recommendationResult.reason);
      setCampaignRecommendations(null);
      toast('Kampagnenempfehlungen konnten nicht geladen werden.', 'error');
    }

    setLoading(false);
  }, [horizonDays, toast, virus, weeklyBudget]);

  useEffect(() => {
    loadOperationalDashboard();
  }, [dataVersion, loadOperationalDashboard]);

  return {
    forecast,
    allocation,
    campaignRecommendations,
    loading,
    loadOperationalDashboard,
  };
}
