import { useCallback, useEffect, useRef, useState } from 'react';

import {
  BacktestResponse,
  MediaDecisionResponse,
  MediaEvidenceResponse,
  RegionalAllocationResponse,
  RegionalBacktestResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastResponse,
  WaveRadarResponse,
} from '../../types/media';
import { mediaApi } from './api';
import {
  buildNowPageViewModel,
  buildWorkspaceStatus,
  deriveNowFocusRegionCode,
  noop,
  ToastLike,
} from './useMediaData.shared';

export function useNowPageData(
  virus: string,
  brand: string,
  horizonDays: number,
  weeklyBudget: number,
  dataVersion: number,
  toast: ToastLike = noop,
  preferredFocusRegionCode: string | null = null,
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
      mediaApi.getRegionalForecast(virus, horizonDays, brand),
      mediaApi.getRegionalAllocation(virus, weeklyBudget, horizonDays, brand),
      mediaApi.getRegionalCampaignRecommendations(virus, weeklyBudget, horizonDays, 12, brand),
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

    const focusRegionCode = preferredFocusRegionCode || deriveNowFocusRegionCode(
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
  }, [brand, horizonDays, preferredFocusRegionCode, toast, virus, weeklyBudget]);

  useEffect(() => {
    loadNowPage();
    return () => {
      loadVersionRef.current += 1;
    };
  }, [dataVersion, loadNowPage]);

  const workspaceStatus = buildWorkspaceStatus(decision, evidence);

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
    workspaceStatus,
    view: buildNowPageViewModel(
      decision,
      evidence,
      forecast,
      allocation,
      campaignRecommendations,
      workspaceStatus,
      weeklyBudget,
      horizonDays,
    ),
  };
}
