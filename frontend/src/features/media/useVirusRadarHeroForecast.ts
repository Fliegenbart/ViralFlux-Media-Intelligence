import { useCallback, useEffect, useRef, useState } from 'react';

import { mediaApi } from './api';
import {
  buildVirusRadarHeroForecastData,
  VirusRadarHeroForecastData,
} from './virusRadarHeroForecast';

const EMPTY_HERO_FORECAST = buildVirusRadarHeroForecastData(undefined);
type ToastLike = (message: string, tone?: 'success' | 'error' | 'info') => void;
const noop: ToastLike = () => undefined;

export function useVirusRadarHeroForecast(
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [heroForecast, setHeroForecast] = useState<VirusRadarHeroForecastData>(EMPTY_HERO_FORECAST);
  const [loading, setLoading] = useState(true);
  const loadVersionRef = useRef(0);

  const loadHeroForecast = useCallback(async () => {
    const loadVersion = loadVersionRef.current + 1;
    loadVersionRef.current = loadVersion;
    const isCurrentLoad = () => loadVersionRef.current === loadVersion;

    setLoading(true);
    try {
      const portfolio = await mediaApi.getRegionalPortfolio('Influenza A', 4);

      if (!isCurrentLoad()) return;

      const nextHeroForecast = buildVirusRadarHeroForecastData(portfolio);
      setHeroForecast(nextHeroForecast);

      if (!nextHeroForecast.availableViruses.length) {
        toast('Das gemeinsame 4-Virus-Lagebild konnte gerade nicht aufgebaut werden.', 'info');
      }
    } catch (error) {
      if (!isCurrentLoad()) return;
      setHeroForecast(EMPTY_HERO_FORECAST);
      toast('Das gemeinsame 4-Virus-Lagebild konnte gerade nicht geladen werden.', 'info');
    } finally {
      if (isCurrentLoad()) {
        setLoading(false);
      }
    }
  }, [toast]);

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
