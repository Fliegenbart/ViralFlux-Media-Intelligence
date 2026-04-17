import { useMemo } from 'react';
import useSWR from 'swr';
import type { CockpitSnapshot } from './types';

/**
 * Hook that fetches a CockpitSnapshot from the backend.
 *
 * Backend endpoint: GET /api/v1/media/cockpit/snapshot
 * (see app/api/media_routes_cockpit_snapshot.py)
 *
 * History: this hook used to return a hard-coded fixture (GELO_SNAPSHOT).
 * After the 2026-04-16 math audit (~/peix-math-audit.md) we switched to
 * real backend data. No silent fixture fallback — if the endpoint fails
 * we return `error` so the UI can render an explicit warning.
 */

export interface UseCockpitSnapshotOptions {
  /** Backend virus_typ query parameter. */
  virusTyp?: string;
  /**
   * Lead-time horizon for the headline story. Default 14 days — that is the
   * horizon at which the backtest against Notaufnahme-Aktivität shows the
   * strongest honest lead. Accepted: 7, 14, 21.
   */
  horizonDays?: number;
  /**
   * Truth target for the lead-time claim. Default `ATEMWEGSINDEX`
   * (Notaufnahme-Syndromsurveillance). Set to `RKI_ARE` to reproduce the
   * pre-2026-04-17 "vs Meldewesen" story.
   */
  leadTarget?: 'ATEMWEGSINDEX' | 'RKI_ARE' | 'SURVSTAT';
  /** Client label, cosmetic. */
  client?: string;
  /** Brand passthrough for the regional forecast service. */
  brand?: string;
}

export interface UseCockpitSnapshotResult {
  snapshot: CockpitSnapshot | null;
  loading: boolean;
  error: Error | null;
  /** Call to force a refresh. */
  reload: () => void;
}

const SNAPSHOT_URL = '/api/v1/media/cockpit/snapshot';
const REFRESH_INTERVAL_MS = 60 * 60 * 1000; // 1 hour

async function snapshotFetcher(url: string): Promise<CockpitSnapshot> {
  const response = await fetch(url, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    // Keep the 401 path terse — the gate component recognises it by the
    // status property and pattern-matches the HTTP code in the message
    // as a fallback, so we include both.
    const message = `HTTP ${response.status} — Cockpit-Snapshot nicht verfügbar`;
    const err = new Error(message);
    (err as Error & { status?: number }).status = response.status;
    throw err;
  }
  return (await response.json()) as CockpitSnapshot;
}

export function useCockpitSnapshot(
  options: UseCockpitSnapshotOptions = {},
): UseCockpitSnapshotResult {
  const {
    virusTyp = 'Influenza A',
    horizonDays = 14,
    leadTarget = 'ATEMWEGSINDEX',
    client = 'GELO',
    brand,
  } = options;

  const queryUrl = useMemo(() => {
    const params = new URLSearchParams();
    params.set('virus_typ', virusTyp);
    params.set('horizon_days', String(horizonDays));
    params.set('lead_target', leadTarget);
    params.set('client', client);
    if (brand) params.set('brand', brand);
    return `${SNAPSHOT_URL}?${params.toString()}`;
  }, [virusTyp, horizonDays, leadTarget, client, brand]);

  const { data, error, isLoading, mutate } = useSWR<CockpitSnapshot, Error>(
    queryUrl,
    snapshotFetcher,
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
