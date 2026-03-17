import { useCallback, useEffect, useState } from 'react';

import {
  MediaEvidenceResponse,
  PilotReportingResponse,
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastResponse,
} from '../../types/media';
import { mediaApi } from './api';

function noop() {}

interface ToastLike {
  (message: string, type?: 'success' | 'error' | 'info'): void;
}

export interface PilotSurfaceInput {
  brand: string;
  virus: string;
  horizonDays: number;
  weeklyBudget: number;
  lookbackWeeks?: number;
  dataVersion?: number;
}

export function usePilotSurfaceData(
  {
    brand,
    virus,
    horizonDays,
    weeklyBudget,
    lookbackWeeks = 26,
    dataVersion = 0,
  }: PilotSurfaceInput,
  toast: ToastLike = noop,
) {
  const [forecast, setForecast] = useState<RegionalForecastResponse | null>(null);
  const [allocation, setAllocation] = useState<RegionalAllocationResponse | null>(null);
  const [campaignRecommendations, setCampaignRecommendations] = useState<RegionalCampaignRecommendationsResponse | null>(null);
  const [evidence, setEvidence] = useState<MediaEvidenceResponse | null>(null);
  const [pilotReporting, setPilotReporting] = useState<PilotReportingResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadSurface = useCallback(async () => {
    setLoading(true);
    const [forecastResult, allocationResult, recommendationResult, evidenceResult, reportingResult] = await Promise.allSettled([
      mediaApi.getRegionalForecast(virus, horizonDays),
      mediaApi.getRegionalAllocation(virus, weeklyBudget, horizonDays),
      mediaApi.getRegionalCampaignRecommendations(virus, weeklyBudget, horizonDays),
      mediaApi.getEvidence(virus, brand),
      mediaApi.getPilotReporting({
        brand,
        lookbackWeeks,
        includeDraft: false,
      }),
    ]);

    if (forecastResult.status === 'fulfilled') {
      setForecast(forecastResult.value);
    } else {
      console.error('Pilot forecast fetch failed', forecastResult.reason);
      setForecast(null);
      toast('Forecast konnte für die Pilot-Ansicht nicht geladen werden.', 'error');
    }

    if (allocationResult.status === 'fulfilled') {
      setAllocation(allocationResult.value);
    } else {
      console.error('Pilot allocation fetch failed', allocationResult.reason);
      setAllocation(null);
      toast('Allocation konnte für die Pilot-Ansicht nicht geladen werden.', 'error');
    }

    if (recommendationResult.status === 'fulfilled') {
      setCampaignRecommendations(recommendationResult.value);
    } else {
      console.error('Pilot campaign recommendations fetch failed', recommendationResult.reason);
      setCampaignRecommendations(null);
      toast('Campaign Recommendations konnten für die Pilot-Ansicht nicht geladen werden.', 'error');
    }

    if (evidenceResult.status === 'fulfilled') {
      setEvidence(evidenceResult.value);
    } else {
      console.error('Pilot evidence fetch failed', evidenceResult.reason);
      setEvidence(null);
      toast('Evidenz konnte für die Pilot-Ansicht nicht geladen werden.', 'error');
    }

    if (reportingResult.status === 'fulfilled') {
      setPilotReporting(reportingResult.value);
    } else {
      console.error('Pilot reporting fetch failed', reportingResult.reason);
      setPilotReporting(null);
      toast('Pilot-Evidence konnte für die Pilot-Ansicht nicht geladen werden.', 'error');
    }

    setLoading(false);
  }, [brand, horizonDays, lookbackWeeks, toast, virus, weeklyBudget]);

  useEffect(() => {
    loadSurface();
  }, [dataVersion, loadSurface]);

  return {
    forecast,
    allocation,
    campaignRecommendations,
    evidence,
    pilotReporting,
    loading,
    loadSurface,
  };
}
