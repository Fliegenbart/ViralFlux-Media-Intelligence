import { useCallback, useEffect, useRef, useState } from 'react';

import { BacktestResponse } from '../../types/media';
import { mediaApi } from './api';
import {
  buildVirusRadarHeroForecastData,
  VirusRadarHeroForecastData,
  VIRUS_RADAR_HERO_VIRUSES,
} from './virusRadarHeroForecast';

const EMPTY_HERO_FORECAST = buildVirusRadarHeroForecastData({});
type ToastLike = (message: string, tone?: 'success' | 'error' | 'info') => void;
const noop: ToastLike = () => undefined;

export function useVirusRadarHeroForecast(
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [heroForecast, setHeroForecast] = useState<VirusRadarHeroForecastData>(EMPTY_HERO_FORECAST);
  const [loading, setLoading] = useState(false);
  const loadVersionRef = useRef(0);

  const loadHeroForecast = useCallback(async () => {
    const loadVersion = loadVersionRef.current + 1;
    loadVersionRef.current = loadVersion;
    const isCurrentLoad = () => loadVersionRef.current === loadVersion;

    setLoading(true);

    const decisionResults = await Promise.allSettled(
      VIRUS_RADAR_HERO_VIRUSES.map((virus) => mediaApi.getDecision(virus, brand)),
    );

    if (!isCurrentLoad()) return;

    const waveRuns = decisionResults.map((result, index) => ({
      virus: VIRUS_RADAR_HERO_VIRUSES[index],
      runId: result.status === 'fulfilled' ? result.value.wave_run_id || null : null,
    }));

    const backtestResults = await Promise.allSettled(
      waveRuns.map((entry) => (entry.runId ? mediaApi.getBacktestRun(entry.runId) : Promise.resolve(null))),
    );

    if (!isCurrentLoad()) return;

    const byVirus: Partial<Record<string, BacktestResponse | null>> = {};
    backtestResults.forEach((result, index) => {
      byVirus[waveRuns[index].virus] = result.status === 'fulfilled' ? result.value : null;
    });

    const nextHeroForecast = buildVirusRadarHeroForecastData(byVirus);
    setHeroForecast(nextHeroForecast);
    setLoading(false);

    if (!nextHeroForecast.availableViruses.length) {
      toast('Das gemeinsame 4-Virus-Lagebild konnte gerade nicht aufgebaut werden.', 'info');
    }
  }, [brand, toast]);

  useEffect(() => {
    loadHeroForecast();
    return () => {
      loadVersionRef.current += 1;
    };
  }, [dataVersion, loadHeroForecast]);

  return {
    heroForecast,
    loading,
    loadHeroForecast,
  };
}
