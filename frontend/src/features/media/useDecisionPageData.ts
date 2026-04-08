import { useCallback, useEffect, useRef, useState } from 'react';

import {
  BacktestResponse,
  MediaDecisionResponse,
  MediaEvidenceResponse,
  RegionalBenchmarkResponse,
  RegionalPortfolioResponse,
  WaveRadarResponse,
} from '../../types/media';
import { mediaApi } from './api';
import { noop, ToastLike } from './useMediaData.shared';

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
  const loadVersionRef = useRef(0);

  const loadDecision = useCallback(async () => {
    const loadVersion = loadVersionRef.current + 1;
    loadVersionRef.current = loadVersion;
    const isCurrentLoad = () => loadVersionRef.current === loadVersion;

    setDecisionLoading(true);
    setRegionalPortfolioLoading(true);
    setWaveRadar(null);
    setWaveRadarLoading(false);
    let decisionLoaded = false;
    try {
      const decisionResult = await mediaApi.getDecision(virus, brand);
      if (!isCurrentLoad()) return;
      setDecision(decisionResult);
      decisionLoaded = true;
    } catch (error) {
      console.error('Decision fetch failed', error);
      if (!isCurrentLoad()) return;
      toast('Entscheidung konnte nicht geladen werden.', 'error');
    } finally {
      if (isCurrentLoad()) {
        setDecisionLoading(false);
      }
    }

    if (!decisionLoaded) {
      if (isCurrentLoad()) {
        setWaveRadarLoading(false);
        setRegionalPortfolioLoading(false);
      }
      return;
    }

    setWaveRadarLoading(true);
    Promise.allSettled([
      mediaApi.getEvidence(virus, brand),
      mediaApi.getRegionalBenchmark(),
      mediaApi.getRegionalPortfolio(),
      mediaApi.getWaveRadar(virus),
    ]).then(([evidenceResult, benchmarkResult, portfolioResult, waveRadarResult]) => {
      if (!isCurrentLoad()) return;

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
      if (isCurrentLoad()) {
        setWaveRadarLoading(false);
        setRegionalPortfolioLoading(false);
      }
    });
  }, [brand, toast, virus]);

  useEffect(() => {
    loadDecision();
    return () => {
      loadVersionRef.current += 1;
    };
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
