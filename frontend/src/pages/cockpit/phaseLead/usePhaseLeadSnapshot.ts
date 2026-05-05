import { useMemo } from 'react';
import useSWR from 'swr';

import type { PhaseLeadSnapshot } from './types';

const PHASE_LEAD_SNAPSHOT_URL = '/api/v1/media/cockpit/phase-lead/snapshot';
const PHASE_LEAD_AGGREGATE_URL = '/api/v1/media/cockpit/phase-lead/aggregate';
const REFRESH_INTERVAL_MS = 60 * 60 * 1000;

export interface UsePhaseLeadSnapshotOptions {
  virusTyp?: string;
  windowDays?: number;
  nSamples?: number;
  maxIter?: number;
  regions?: string[];
}

export interface UsePhaseLeadSnapshotResult {
  snapshot: PhaseLeadSnapshot | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

async function phaseLeadFetcher(url: string): Promise<PhaseLeadSnapshot> {
  const response = await fetch(url, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const message = `HTTP ${response.status} — Phase-Lead-Snapshot nicht verfügbar`;
    const err = new Error(message);
    (err as Error & { status?: number }).status = response.status;
    throw err;
  }
  return (await response.json()) as PhaseLeadSnapshot;
}

export function usePhaseLeadSnapshot(
  options: UsePhaseLeadSnapshotOptions = {},
): UsePhaseLeadSnapshotResult {
  const {
    virusTyp = 'Influenza A',
    windowDays = 70,
    nSamples = 80,
    maxIter = 0,
    regions,
  } = options;

  const queryUrl = useMemo(() => {
    const params = new URLSearchParams();
    if (virusTyp === 'Gesamt') {
      params.set('window_days', String(windowDays));
      params.set('n_samples', String(nSamples));
      if (regions?.length) params.set('regions', regions.join(','));
      return `${PHASE_LEAD_AGGREGATE_URL}?${params.toString()}`;
    }
    params.set('virus_typ', virusTyp);
    params.set('window_days', String(windowDays));
    params.set('n_samples', String(nSamples));
    params.set('max_iter', String(maxIter));
    if (regions?.length) params.set('regions', regions.join(','));
    return `${PHASE_LEAD_SNAPSHOT_URL}?${params.toString()}`;
  }, [virusTyp, windowDays, nSamples, maxIter, regions]);

  const { data, error, isLoading, mutate } = useSWR<PhaseLeadSnapshot, Error>(
    queryUrl,
    phaseLeadFetcher,
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
