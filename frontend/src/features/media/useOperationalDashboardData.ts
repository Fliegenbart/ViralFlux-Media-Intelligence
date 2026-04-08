import { useCallback, useEffect, useRef, useState } from 'react';

import {
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastResponse,
} from '../../types/media';
import { mediaApi } from './api';
import { noop, ToastLike } from './useMediaData.shared';

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
  const loadVersionRef = useRef(0);

  const loadOperationalDashboard = useCallback(async () => {
    const loadVersion = ++loadVersionRef.current;
    setLoading(true);
    const [forecastResult, allocationResult, recommendationResult] = await Promise.allSettled([
      mediaApi.getRegionalForecast(virus, horizonDays),
      mediaApi.getRegionalAllocation(virus, weeklyBudget, horizonDays),
      mediaApi.getRegionalCampaignRecommendations(virus, weeklyBudget, horizonDays),
    ]);

    if (loadVersionRef.current !== loadVersion) {
      return;
    }

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
    return () => {
      loadVersionRef.current += 1;
    };
  }, [dataVersion, loadOperationalDashboard]);

  return {
    forecast,
    allocation,
    campaignRecommendations,
    loading,
    loadOperationalDashboard,
  };
}
