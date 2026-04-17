import { useMemo } from 'react';
import useSWR from 'swr';
import type { ImpactPayload } from './impactTypes';

const IMPACT_URL = '/api/v1/media/cockpit/impact';
const REFRESH_INTERVAL_MS = 60 * 60 * 1000;

interface Options {
  virusTyp: string;
  /** Lead-time horizon; default 14 to match snapshot. */
  horizonDays?: number;
  leadTarget?: 'ATEMWEGSINDEX' | 'RKI_ARE' | 'SURVSTAT';
  client?: string;
  weeksBack?: number;
}

export interface UseImpactResult {
  data: ImpactPayload | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

async function fetcher(url: string): Promise<ImpactPayload> {
  const response = await fetch(url, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => '');
    const err = new Error(
      `Impact-Payload konnte nicht geladen werden (HTTP ${response.status}). ${detail}`.trim(),
    );
    (err as Error & { status?: number }).status = response.status;
    throw err;
  }
  return (await response.json()) as ImpactPayload;
}

export function useImpact(options: Options): UseImpactResult {
  const {
    virusTyp,
    horizonDays = 14,
    leadTarget = 'ATEMWEGSINDEX',
    client = 'GELO',
    weeksBack = 12,
  } = options;
  const url = useMemo(() => {
    const params = new URLSearchParams();
    params.set('virus_typ', virusTyp);
    params.set('horizon_days', String(horizonDays));
    params.set('lead_target', leadTarget);
    params.set('client', client);
    params.set('weeks_back', String(weeksBack));
    return `${IMPACT_URL}?${params.toString()}`;
  }, [virusTyp, horizonDays, leadTarget, client, weeksBack]);

  const { data, error, isLoading, mutate } = useSWR<ImpactPayload, Error>(
    url,
    fetcher,
    {
      refreshInterval: REFRESH_INTERVAL_MS,
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    },
  );

  return {
    data: data ?? null,
    loading: isLoading,
    error: error ?? null,
    reload: () => {
      void mutate();
    },
  };
}
