import { useCallback, useEffect, useState } from 'react';

/**
 * 2026-04-21 Media-Plan CSV integration hook.
 *
 * Exposes three actions:
 *   - ``upload(file, {dryRun})`` — POST multipart to /upload endpoint.
 *     Returns the parsed preview summary; committed=false when dryRun.
 *   - ``reload()`` — GET current plan rows for the client.
 *   - ``clear()`` — DELETE the client's plan.
 *
 * The hook keeps a local ``plan`` state (last successful GET) so the
 * upload modal can render "Aktueller Plan · N Zeilen · X € / Woche"
 * without an extra prop drill.
 */

export interface MediaPlanSummary {
  row_count: number;
  error_count: number;
  total_eur: number;
  iso_weeks: string[];
  bundesland_codes: string[];
  errors: Array<{ row: number; reason: string; [key: string]: unknown }>;
}

export interface MediaPlanUploadResult {
  ok: boolean;
  dry_run: boolean;
  committed: boolean;
  summary: MediaPlanSummary;
  commit?: { upload_id: string; inserted: number; client: string };
}

export interface MediaPlanRow {
  id: number;
  iso_week: string;
  iso_week_year: number;
  iso_week_number: number;
  bundesland_code: string | null;
  channel: string | null;
  eur_amount: number;
  upload_id: string;
  uploaded_at: string | null;
}

export interface MediaPlanState {
  client: string;
  row_count: number;
  total_eur: number;
  iso_weeks: string[];
  by_bundesland: Record<string, number>;
  rows: MediaPlanRow[];
}

interface UseMediaPlanParams {
  client?: string;
  autoLoad?: boolean;
}

export function useMediaPlan(params: UseMediaPlanParams = {}) {
  const { client = 'GELO', autoLoad = true } = params;

  const [plan, setPlan] = useState<MediaPlanState | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/media/cockpit/media-plan/current?client=${encodeURIComponent(client)}`,
        { credentials: 'include' },
      );
      if (!res.ok) {
        throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
      }
      const data: MediaPlanState = await res.json();
      setPlan(data);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    if (autoLoad) {
      reload();
    }
  }, [autoLoad, reload]);

  const upload = useCallback(
    async (file: File, opts: { dryRun?: boolean } = {}): Promise<MediaPlanUploadResult> => {
      const dry = opts.dryRun ?? false;
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(
        `/api/v1/media/cockpit/media-plan/upload?client=${encodeURIComponent(client)}&dry_run=${dry}`,
        {
          method: 'POST',
          body: form,
          credentials: 'include',
        },
      );
      if (!res.ok) {
        const text = await res.text();
        throw Object.assign(new Error(`HTTP ${res.status}: ${text}`), {
          status: res.status,
        });
      }
      const data: MediaPlanUploadResult = await res.json();
      if (data.committed) {
        // refresh local snapshot after successful commit
        void reload();
      }
      return data;
    },
    [client, reload],
  );

  const clear = useCallback(async () => {
    const res = await fetch(
      `/api/v1/media/cockpit/media-plan/current?client=${encodeURIComponent(client)}`,
      { method: 'DELETE', credentials: 'include' },
    );
    if (!res.ok) {
      throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
    }
    await reload();
  }, [client, reload]);

  return { plan, loading, error, reload, upload, clear };
}
