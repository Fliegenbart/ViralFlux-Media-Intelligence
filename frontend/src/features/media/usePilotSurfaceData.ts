import { useCallback, useEffect, useState } from 'react';

import { PilotReadoutResponse } from '../../types/media';
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
  dataVersion?: number;
}

export function usePilotSurfaceData(
  {
    brand,
    virus,
    horizonDays,
    weeklyBudget,
    dataVersion = 0,
  }: PilotSurfaceInput,
  toast: ToastLike = noop,
) {
  const [pilotReadout, setPilotReadout] = useState<PilotReadoutResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadSurface = useCallback(async () => {
    setLoading(true);
    try {
      const result = await mediaApi.getPilotReadout({
        brand,
        virus,
        horizonDays,
        weeklyBudgetEur: weeklyBudget,
      });
      setPilotReadout(result);
    } catch (error) {
      console.error('Pilot readout fetch failed', error);
      setPilotReadout(null);
      toast('Die Wochenübersicht konnte gerade nicht geladen werden.', 'error');
    } finally {
      setLoading(false);
    }
  }, [brand, horizonDays, toast, virus, weeklyBudget]);

  useEffect(() => {
    loadSurface();
  }, [dataVersion, loadSurface]);

  return {
    pilotReadout,
    loading,
    loadSurface,
  };
}
