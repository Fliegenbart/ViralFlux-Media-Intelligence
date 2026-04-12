import { useCallback, useEffect, useRef, useState } from 'react';

import {
  RegionalBacktestResponse,
  RegionalForecastResponse,
} from '../../types/media';
import { mediaApi } from './api';
import {
  noop,
  sortRegionalPredictions,
  ToastLike,
} from './useMediaData.shared';

export interface TimegraphRegionOption {
  code: string;
  name: string;
}

export function useTimegraphPageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const horizonDays = 7;
  const [forecast, setForecast] = useState<RegionalForecastResponse | null>(null);
  const [regionalBacktest, setRegionalBacktest] = useState<RegionalBacktestResponse | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const loadVersionRef = useRef(0);

  const sortedPredictions = sortRegionalPredictions(forecast);
  const regionOptions: TimegraphRegionOption[] = sortedPredictions.map((item) => ({
    code: item.bundesland,
    name: item.bundesland_name || item.bundesland,
  }));
  const selectedPrediction = (
    (selectedRegion
      ? sortedPredictions.find((item) => item.bundesland === selectedRegion)
      : null)
    || sortedPredictions[0]
    || null
  );

  const loadTimegraph = useCallback(async () => {
    const loadVersion = loadVersionRef.current + 1;
    loadVersionRef.current = loadVersion;
    const isCurrentLoad = () => loadVersionRef.current === loadVersion;

    setLoading(true);
    setForecast(null);
    setRegionalBacktest(null);
    setBacktestLoading(false);

    try {
      const result = await mediaApi.getRegionalForecast(virus, horizonDays, brand);
      if (!isCurrentLoad()) return;
      const predictions = sortRegionalPredictions(result);
      setForecast(result);
      setSelectedRegion((current) => (
        current && predictions.some((item) => item.bundesland === current)
          ? current
          : predictions[0]?.bundesland || null
      ));
    } catch (error) {
      console.error('Timegraph forecast fetch failed', error);
      if (!isCurrentLoad()) return;
      setForecast(null);
      setSelectedRegion(null);
      toast('Der Zeitgraph konnte nicht geladen werden.', 'error');
    } finally {
      if (isCurrentLoad()) {
        setLoading(false);
      }
    }
  }, [brand, toast, virus]);

  useEffect(() => {
    loadTimegraph();
    return () => {
      loadVersionRef.current += 1;
    };
  }, [dataVersion, loadTimegraph]);

  useEffect(() => {
    let active = true;

    if (!selectedRegion) {
      setRegionalBacktest(null);
      setBacktestLoading(false);
      return () => {
        active = false;
      };
    }

    setBacktestLoading(true);
    setRegionalBacktest(null);

    mediaApi.getRegionalBacktest(virus, selectedRegion, horizonDays)
      .then((result) => {
        if (!active) return;
        setRegionalBacktest(result?.error ? null : result);
      })
      .catch((error) => {
        console.error('Timegraph regional backtest fetch failed', error);
        if (active) {
          setRegionalBacktest(null);
        }
      })
      .finally(() => {
        if (active) {
          setBacktestLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [dataVersion, selectedRegion, virus]);

  return {
    forecast,
    selectedRegion,
    setSelectedRegion,
    selectedPrediction,
    regionOptions,
    regionalBacktest,
    loading,
    backtestLoading,
    horizonDays,
  };
}
