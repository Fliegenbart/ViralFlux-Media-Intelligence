import { useMemo } from 'react';
import useSWR from 'swr';
import type { BacktestPayload } from './backtestTypes';

/**
 * Hook for GET /api/v1/media/cockpit/backtest — Drawer V pitch-story.
 *
 * Walks over the snapshot / impact hook conventions: includes credentials,
 * surfaces HTTP status on the Error, 1h refresh cadence (backtest data
 * changes only when a fresh regional retrain lands, never faster).
 */

const BACKTEST_URL = '/api/v1/media/cockpit/backtest';
const REFRESH_INTERVAL_MS = 60 * 60 * 1000;

interface Options {
  virusTyp?: string;
  horizonDays?: number;
  weeksToSurface?: number;
}

export interface UseBacktestResult {
  data: BacktestPayload | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

async function fetcher(url: string): Promise<BacktestPayload> {
  const response = await fetch(url, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => '');
    const err = new Error(
      `Backtest-Payload konnte nicht geladen werden (HTTP ${response.status}). ${detail}`.trim(),
    );
    (err as Error & { status?: number }).status = response.status;
    throw err;
  }
  return (await response.json()) as BacktestPayload;
}

export function useBacktest(options: Options = {}): UseBacktestResult {
  const virusTyp = options.virusTyp ?? 'Influenza A';
  const horizonDays = options.horizonDays ?? 7;
  const weeksToSurface = options.weeksToSurface ?? 52;

  const url = useMemo(() => {
    const p = new URLSearchParams({
      virus_typ: virusTyp,
      horizon_days: String(horizonDays),
      weeks_to_surface: String(weeksToSurface),
    });
    return `${BACKTEST_URL}?${p.toString()}`;
  }, [virusTyp, horizonDays, weeksToSurface]);

  const { data, error, mutate, isLoading } = useSWR<BacktestPayload>(url, fetcher, {
    refreshInterval: REFRESH_INTERVAL_MS,
    revalidateOnFocus: false,
    keepPreviousData: true,
  });

  return {
    data: data ?? null,
    loading: isLoading,
    error: (error as Error) ?? null,
    reload: () => {
      mutate();
    },
  };
}
