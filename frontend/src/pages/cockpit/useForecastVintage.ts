import { useMemo } from 'react';
import useSWR from 'swr';

/**
 * Hook für GET /api/v1/media/cockpit/forecast-vintage.
 *
 * Liefert historische Forecast-Runs (aus ml_forecasts) + aktuelle
 * predicted-vs-actual-Reconciliation (aus forecast_accuracy_log) für
 * den Vintage-Overlay in § III Forecast-Zeitreise.
 */

export interface VintagePoint {
  date: string;
  q50: number | null;
  q10: number | null;
  q90: number | null;
  horizon_days: number | null;
}

export interface VintageRun {
  run_date: string;
  anchor_date: string;
  anchor_value: number | null;
  num_points: number;
  points: VintagePoint[];
}

export interface ReconciliationPair {
  date: string;
  predicted: number | null;
  actual: number | null;
}

export interface Reconciliation {
  computed_at: string | null;
  window_days: number;
  samples: number;
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  correlation: number | null;
  drift_detected: boolean;
  pairs: ReconciliationPair[];
}

export interface ForecastVintagePayload {
  virus_typ: string;
  runs: VintageRun[];
  reconciliation: Reconciliation | null;
}

const URL_BASE = '/api/v1/media/cockpit/forecast-vintage';
const REFRESH_MS = 60 * 60 * 1000;

async function fetcher(url: string): Promise<ForecastVintagePayload> {
  const r = await fetch(url, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => '');
    const err = new Error(
      `Vintage-Payload konnte nicht geladen werden (HTTP ${r.status}). ${txt}`.trim(),
    );
    (err as Error & { status?: number }).status = r.status;
    throw err;
  }
  return (await r.json()) as ForecastVintagePayload;
}

export function useForecastVintage(virusTyp: string = 'Influenza A', runLimit = 5) {
  const url = useMemo(
    () =>
      `${URL_BASE}?virus_typ=${encodeURIComponent(virusTyp)}&run_limit=${runLimit}`,
    [virusTyp, runLimit],
  );
  const { data, error, isLoading, mutate } = useSWR<ForecastVintagePayload>(
    url,
    fetcher,
    { refreshInterval: REFRESH_MS, revalidateOnFocus: false, keepPreviousData: true },
  );
  return {
    data: data ?? null,
    loading: isLoading,
    error: (error as Error) ?? null,
    reload: () => { void mutate(); },
  };
}
