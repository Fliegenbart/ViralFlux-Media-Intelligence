import { OPERATOR_LABELS } from '../../constants/operatorLabels';
import { decisionStateLabel } from '../../lib/copy';
import { buildPredictionNarrative } from '../../lib/plainLanguage';
import {
  MediaDecisionResponse,
  MediaEvidenceResponse,
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastResponse,
  StructuredReasonItem,
  WorkspaceStatusSummary,
} from '../../types/media';
import {
  businessValidationLabel,
  evidenceTierLabel,
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
} from '../../components/cockpit/evidence/evidenceUtils';
import {
  NowPageBriefingTrustItem,
  NowPageViewModel,
} from './useMediaData.types';
import { sortRegionalPredictions } from './useMediaData.utils';
import {
  buildNowPageNote,
  businessTrustTone,
  cleanCopy,
  deriveBriefingState,
  explainedEntries,
  findReasonMentioningRegion,
  firstCleanText,
  forecastStatusTone,
  preferredReasonEntries,
  probabilityPercent,
  regionSignalSentence,
  stageLabel,
  stageTone,
  textMentionsRegion,
  uniqueText,
} from './nowPageViewModel.utils';

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
  const sortedPredictions = sortRegionalPredictions(forecast);
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
    probabilityPercent(focusPrediction?.event_probability ?? weeklyDecision?.event_forecast?.event_probability),
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
    'Portfolio-Fokus',
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
          ? formatPercent(probabilityPercent(relatedPrediction.event_probability), 1)
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
      probabilityLabel: formatPercent(probabilityPercent(item.event_probability), 1),
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
