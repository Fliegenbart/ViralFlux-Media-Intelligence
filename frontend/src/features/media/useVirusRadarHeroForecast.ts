import { useCallback, useEffect, useRef, useState } from 'react';

import { LatestForecastResponse } from '../../types/media';
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

    const forecastResults = await Promise.allSettled(
      VIRUS_RADAR_HERO_VIRUSES.map((virus) => mediaApi.getLatestForecast(virus)),
    );

    if (!isCurrentLoad()) return;

    const byVirus: Partial<Record<string, LatestForecastResponse | null>> = {};
    forecastResults.forEach((result, index) => {
      byVirus[VIRUS_RADAR_HERO_VIRUSES[index]] = result.status === 'fulfilled' ? result.value : null;
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
