import { useCallback, useEffect, useState } from 'react';

import { decisionStateLabel } from '../../lib/copy';
import {
  BacktestResponse,
  MediaCampaignsResponse,
  MediaDecisionResponse,
  MediaEvidenceResponse,
  MediaRegionsResponse,
  RegionalAllocationResponse,
  RegionalBenchmarkResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastResponse,
  RegionalPortfolioResponse,
  TruthImportBatchDetailResponse,
  TruthImportResponse,
} from '../../types/media';
import {
  businessValidationLabel,
  evidenceTierLabel,
  formatCurrency,
  formatPercent,
  truthLayerLabel,
  workflowLabel,
} from '../../components/cockpit/cockpitUtils';
import { mediaApi } from './api';

function noop() {}

interface ToastLike {
  (message: string, type?: 'success' | 'error' | 'info'): void;
}

export interface NowPageMetric {
  label: string;
  value: string;
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
  primaryActionLabel: string;
  primaryRecommendationId: string | null;
  primaryCampaignTitle: string;
  primaryCampaignContext: string;
  primaryCampaignCopy: string;
  focusRegion: NowPageFocusRegion | null;
  metrics: NowPageMetric[];
  reasons: string[];
  risks: string[];
  quality: Array<{ label: string; value: string }>;
  relatedRegions: NowPageRelatedRegion[];
  emptyState: {
    title: string;
    body: string;
  } | null;
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

function firstNonEmpty(...values: Array<string | null | undefined>): string {
  return values.map((value) => String(value || '').trim()).find(Boolean) || '-';
}

function buildNowPageViewModel(
  decision: MediaDecisionResponse | null,
  evidence: MediaEvidenceResponse | null,
  forecast: RegionalForecastResponse | null,
  allocation: RegionalAllocationResponse | null,
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null,
  weeklyBudget: number,
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
  const topRegion = weeklyDecision?.top_regions?.[0];

  const focusRegionCode = leadPrediction?.bundesland || leadAllocation?.bundesland || leadCampaign?.region || topRegion?.code || null;
  const focusRegionName = firstNonEmpty(
    leadCampaign?.region_name,
    leadAllocation?.bundesland_name,
    leadPrediction?.bundesland_name,
    topRegion?.name,
    topCard?.decision_brief?.recommendation?.primary_region,
    'Deutschland',
  );
  const focusStageValue = leadCampaign?.activation_level
    || leadAllocation?.recommended_activation_level
    || leadPrediction?.decision_label
    || weeklyDecision?.action_stage
    || weeklyDecision?.decision_state
    || 'Watch';
  const focusStage = stageLabel(focusStageValue);
  const focusProbabilityLabel = formatPercent(
    probabilityPercent(leadPrediction?.event_probability_calibrated ?? weeklyDecision?.event_forecast?.event_probability),
    1,
  );
  const focusBudgetLabel = formatCurrency(
    topCard?.campaign_preview?.budget?.weekly_budget_eur
    || leadCampaign?.suggested_budget_amount
    || leadAllocation?.suggested_budget_amount
    || weeklyBudget,
  );
  const focusReason = firstNonEmpty(
    weeklyDecision?.recommended_action,
    topCard?.decision_brief?.summary_sentence,
    leadCampaign?.recommendation_rationale?.why?.[0],
    leadPrediction?.decision?.explanation_summary,
    leadPrediction?.reason_trace?.why?.[0],
    leadAllocation?.uncertainty_summary,
    'Hier bündelt sich aktuell das stärkste Signal.',
  );
  const focusProduct = firstNonEmpty(
    topCard?.recommended_product,
    leadCampaign?.recommended_product_cluster?.label,
    leadAllocation?.products?.[0],
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
  const primaryCampaignTitle = firstNonEmpty(
    topCard?.display_title,
    topCard?.campaign_name,
    topCard?.recommended_product,
    leadCampaign?.recommended_product_cluster?.label,
    'Kampagnenvorschlag prüfen',
  );
  const primaryCampaignContext = firstNonEmpty(
    `${topCard?.region_codes_display?.join(', ') || focusRegionName} · ${workflowLabel(topCard?.lifecycle_state || topCard?.status)}`,
    `${focusRegionName} · ${focusStage}`,
  );
  const primaryCampaignCopy = firstNonEmpty(
    topCard?.decision_brief?.summary_sentence,
    topCard?.reason,
    leadCampaign?.recommendation_rationale?.why?.[0],
    'Der nächste prüfbare Kampagnenvorschlag liegt bereit.',
  );

  const reasons = uniqueText([
    ...(weeklyDecision?.why_now || []),
    topCard?.decision_brief?.summary_sentence,
    leadCampaign?.recommendation_rationale?.why?.[0],
    leadPrediction?.decision?.explanation_summary,
    leadPrediction?.reason_trace?.why?.[0],
  ], 4);

  const risks = uniqueText([
    ...(weeklyDecision?.risk_flags || []),
    leadPrediction?.uncertainty_summary,
    ...(leadPrediction?.reason_trace?.uncertainty || []),
    leadAllocation?.uncertainty_summary,
    ...(Array.isArray(leadAllocation?.reason_trace)
      ? []
      : ((leadAllocation?.reason_trace as { uncertainty?: string[] } | undefined)?.uncertainty || [])),
    evidence?.truth_snapshot?.truth_gate?.guidance,
  ], 4);

  const relatedRegions = sortedPredictions
    .filter((item) => item.bundesland !== focusRegionCode)
    .slice(0, 3)
    .map((item) => ({
      code: item.bundesland,
      name: item.bundesland_name,
      stage: stageLabel(item.decision_label),
      probabilityLabel: formatPercent(probabilityPercent(item.event_probability_calibrated), 1),
      reason: firstNonEmpty(
        item.reason_trace?.why?.[0],
        item.decision?.explanation_summary,
        item.uncertainty_summary,
        'Weitere regionale Priorität für diese Woche.',
      ),
    }));

  const hasData = Boolean(
    decision
    || evidence
    || sortedPredictions.length
    || (allocation?.recommendations || []).length
    || (campaignRecommendations?.recommendations || []).length,
  );

  const emptyMessage = forecast?.message || allocation?.message || campaignRecommendations?.message;
  const emptyState = hasData ? null : {
    title: forecast?.status === 'no_model'
      ? 'Für diesen Scope ist noch kein regionales Modell verfügbar.'
      : 'Für diesen Scope liegen gerade keine belastbaren Arbeitsdaten vor.',
    body: emptyMessage || 'Wechsle Virus oder Horizont oder prüfe die Datenqualität im Evidenz-Bereich.',
  };

  return {
    hasData,
    generatedAt: decision?.generated_at || forecast?.generated_at || allocation?.generated_at || campaignRecommendations?.generated_at || evidence?.generated_at || null,
    title: `${focusStage}: ${focusRegionName}`,
    summary: firstNonEmpty(
      weeklyDecision?.recommended_action,
      topCard?.decision_brief?.summary_sentence,
      `Die stärkste nächste Aktion liegt aktuell in ${focusRegionName}.`,
    ),
    note: topCard?.is_publishable
      ? 'Die nächste sinnvolle Aktion ist oben sichtbar. Begründung, Qualität und Risiken folgen darunter.'
      : 'Die nächste sinnvolle Aktion ist oben sichtbar. Erst prüfen, dann freigeben.',
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
        label: 'Freigabe',
        value: decisionState,
        tone: stageTone(weeklyDecision?.decision_state),
      },
      {
        label: 'Event-Wahrscheinlichkeit',
        value: focusProbabilityLabel,
        tone: stageTone(focusStageValue),
      },
      {
        label: 'Empfohlenes Budget',
        value: focusBudgetLabel,
        tone: 'neutral',
      },
      {
        label: 'Vertrauen',
        value: trustValue,
        tone: trustValue === 'belastbar' ? 'success' : trustValue === 'im Aufbau' ? 'warning' : 'neutral',
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
        label: 'Business-Gate',
        value: businessValue,
      },
      {
        label: 'Evidenz',
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
  const [loading, setLoading] = useState(false);

  const loadNowPage = useCallback(async () => {
    setLoading(true);

    const [
      decisionResult,
      evidenceResult,
      forecastResult,
      allocationResult,
      recommendationResult,
    ] = await Promise.allSettled([
      mediaApi.getDecision(virus, brand),
      mediaApi.getEvidence(virus, brand),
      mediaApi.getRegionalForecast(virus, horizonDays),
      mediaApi.getRegionalAllocation(virus, weeklyBudget, horizonDays),
      mediaApi.getRegionalCampaignRecommendations(virus, weeklyBudget, horizonDays),
    ]);

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

    if (forecastResult.status === 'fulfilled') {
      setForecast(forecastResult.value);
    } else {
      console.error('Now page forecast fetch failed', forecastResult.reason);
      setForecast(null);
      toast('Der regionale Forecast konnte nicht geladen werden.', 'error');
    }

    if (allocationResult.status === 'fulfilled') {
      setAllocation(allocationResult.value);
    } else {
      console.error('Now page allocation fetch failed', allocationResult.reason);
      setAllocation(null);
      toast('Die Budgetallokation konnte nicht geladen werden.', 'error');
    }

    if (recommendationResult.status === 'fulfilled') {
      setCampaignRecommendations(recommendationResult.value);
    } else {
      console.error('Now page recommendation fetch failed', recommendationResult.reason);
      setCampaignRecommendations(null);
      toast('Die Kampagnenempfehlungen konnten nicht geladen werden.', 'error');
    }

    setLoading(false);
  }, [brand, horizonDays, toast, virus, weeklyBudget]);

  useEffect(() => {
    loadNowPage();
  }, [dataVersion, loadNowPage]);

  return {
    decision,
    evidence,
    forecast,
    allocation,
    campaignRecommendations,
    loading,
    loadNowPage,
    view: buildNowPageViewModel(decision, evidence, forecast, allocation, campaignRecommendations, weeklyBudget),
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
  const [regionalBenchmark, setRegionalBenchmark] = useState<RegionalBenchmarkResponse | null>(null);
  const [regionalPortfolio, setRegionalPortfolio] = useState<RegionalPortfolioResponse | null>(null);
  const [regionalPortfolioLoading, setRegionalPortfolioLoading] = useState(false);

  const loadDecision = useCallback(async () => {
    setDecisionLoading(true);
    setRegionalPortfolioLoading(true);
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
      setRegionalPortfolioLoading(false);
      return;
    }

    Promise.allSettled([
      mediaApi.getEvidence(virus, brand),
      mediaApi.getRegionalBenchmark(),
      mediaApi.getRegionalPortfolio(),
    ]).then(([evidenceResult, benchmarkResult, portfolioResult]) => {
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
    }).finally(() => {
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

  const loadRegions = useCallback(async () => {
    setRegionsLoading(true);
    try {
      setRegionsView(await mediaApi.getRegions(virus, brand));
    } catch (error) {
      console.error('Regions fetch failed', error);
      toast('Regionen konnten nicht geladen werden.', 'error');
    } finally {
      setRegionsLoading(false);
    }
  }, [brand, toast, virus]);

  useEffect(() => {
    loadRegions();
  }, [dataVersion, loadRegions]);

  return {
    regionsView,
    regionsLoading,
    loadRegions,
  };
}

export function useCampaignsPageData(
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [campaignsView, setCampaignsView] = useState<MediaCampaignsResponse | null>(null);
  const [campaignsLoading, setCampaignsLoading] = useState(false);

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    try {
      setCampaignsView(await mediaApi.getCampaigns(brand));
    } catch (error) {
      console.error('Campaigns fetch failed', error);
      toast('Kampagnenvorschlaege konnten nicht geladen werden.', 'error');
    } finally {
      setCampaignsLoading(false);
    }
  }, [brand, toast]);

  useEffect(() => {
    loadCampaigns();
  }, [dataVersion, loadCampaigns]);

  return {
    campaignsView,
    campaignsLoading,
    loadCampaigns,
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
      toast('Evidenz konnte nicht geladen werden.', 'error');
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
        validateOnly ? 'Upload der Kundendaten validiert. Vorschau ist bereit.' : 'Kundendaten importiert und Evidenz aktualisiert.',
        'success',
      );
    } catch (error) {
      console.error('Truth upload failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Upload der Kundendaten fehlgeschlagen: ${message}`, 'error');
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
      toast('Regionaler Forecast konnte nicht geladen werden.', 'error');
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
      toast('Campaign Recommendations konnten nicht geladen werden.', 'error');
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
