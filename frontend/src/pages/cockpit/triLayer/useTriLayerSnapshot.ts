import { useMemo } from 'react';
import useSWR from 'swr';

import type { TriLayerMode, TriLayerSnapshot } from './types';

const TRI_LAYER_SNAPSHOT_URL = '/api/v1/media/cockpit/tri-layer/snapshot';
const REFRESH_INTERVAL_MS = 60 * 60 * 1000;

export interface UseTriLayerSnapshotOptions {
  virusTyp?: string;
  horizonDays?: 3 | 7 | 14;
  brand?: string;
  client?: string;
  mode?: TriLayerMode;
}

export interface UseTriLayerSnapshotResult {
  snapshot: TriLayerSnapshot | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

async function triLayerFetcher(url: string): Promise<TriLayerSnapshot> {
  const response = await fetch(url, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const message = `HTTP ${response.status} — Tri-Layer-Snapshot nicht verfügbar`;
    const err = new Error(message);
    (err as Error & { status?: number }).status = response.status;
    throw err;
  }
  return (await response.json()) as TriLayerSnapshot;
}

export function useTriLayerSnapshot(
  options: UseTriLayerSnapshotOptions = {},
): UseTriLayerSnapshotResult {
  const {
    virusTyp = 'Influenza A',
    horizonDays = 7,
    brand = 'gelo',
    client = 'GELO',
    mode = 'research',
  } = options;

  const queryUrl = useMemo(() => {
    const params = new URLSearchParams();
    params.set('virus_typ', virusTyp);
    params.set('horizon_days', String(horizonDays));
    params.set('brand', brand);
    params.set('client', client);
    params.set('mode', mode);
    return `${TRI_LAYER_SNAPSHOT_URL}?${params.toString()}`;
  }, [virusTyp, horizonDays, brand, client, mode]);

  const { data, error, isLoading, mutate } = useSWR<TriLayerSnapshot, Error>(
    queryUrl,
    triLayerFetcher,
    {
      refreshInterval: REFRESH_INTERVAL_MS,
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    },
  );

  return {
    snapshot: data ?? null,
    loading: isLoading,
    error: error ?? null,
    reload: () => {
      void mutate();
    },
  };
}
