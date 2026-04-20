import { useMemo } from 'react';
import useSWR from 'swr';

/**
 * SWR hooks für die Data-Office Seite.
 *
 * Read-only Endpoints (Template, Batch-Liste, Batch-Detail, Coverage,
 * Evidenz) laufen über das Cockpit-Gate (Passwort `peix26`) — gleiche
 * Auth wie der Rest vom /cockpit.
 *
 * Der POST /outcomes/import bleibt admin-only und wird hier NICHT als
 * Hook abgedeckt; das Upload-UI ruft `fetch` direkt auf und behandelt
 * 403-Responses explizit ("Admin-Login erforderlich").
 */

// -----------------------------------------------------------------
// Types — spiegeln backend/app/api/media_routes_outcomes.py
// -----------------------------------------------------------------

export interface OutcomeImportBatch {
  batch_id: string;
  brand: string;
  source_label: string | null;
  source_system: string | null;
  external_batch_id: string | null;
  ingestion_mode: string | null;
  file_name: string | null;
  status: string;
  rows_total: number | null;
  rows_valid: number | null;
  rows_imported: number | null;
  rows_rejected: number | null;
  rows_duplicate: number | null;
  week_min: string | null;
  week_max: string | null;
  created_at?: string | null;
  imported_at?: string | null;
  coverage_after_import?: {
    coverage_weeks?: number | null;
    latest_week?: string | null;
    regions_covered?: number | null;
    products_covered?: number | null;
  } | null;
}

export interface OutcomeImportBatchesResponse {
  brand: string;
  batches: OutcomeImportBatch[];
}

export interface OutcomeBatchDetail {
  batch_id: string;
  brand: string;
  status: string;
  rows_total: number | null;
  rows_imported: number | null;
  rows_rejected: number | null;
  issues: Array<{
    row_number?: number | null;
    severity: string;
    code: string;
    message: string;
    field?: string | null;
  }>;
  records: any[];
  coverage_after_import?: any;
}

export interface TruthCoverageRow {
  region_code: string;
  region_name?: string | null;
  product: string;
  coverage_weeks: number;
  first_week: string | null;
  last_week: string | null;
  row_count: number;
}

export interface TruthCoverageResponse {
  brand: string;
  virus_typ: string;
  coverage_weeks: number;
  latest_week: string | null;
  regions_covered: number;
  products_covered: number;
  per_region_product?: TruthCoverageRow[];
  window?: { start: string | null; end: string | null };
  [k: string]: any;
}

// -----------------------------------------------------------------
// Fetcher — credentials: include so the cockpit-gate cookie is sent.
// -----------------------------------------------------------------
async function jsonFetcher<T>(url: string): Promise<T> {
  const r = await fetch(url, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => '');
    const err = new Error(
      `HTTP ${r.status} bei ${url}${txt ? `: ${txt.slice(0, 200)}` : ''}`,
    );
    (err as Error & { status?: number }).status = r.status;
    throw err;
  }
  return (await r.json()) as T;
}

// -----------------------------------------------------------------
// Hooks
// -----------------------------------------------------------------

export function useOutcomeImportBatches(brand: string = 'GELO', limit = 20) {
  const url = useMemo(
    () =>
      `/api/v1/media/outcomes/import-batches?brand=${encodeURIComponent(brand)}&limit=${limit}`,
    [brand, limit],
  );
  const { data, error, isLoading, mutate } = useSWR<OutcomeImportBatchesResponse>(
    url,
    jsonFetcher,
    { refreshInterval: 60_000, revalidateOnFocus: false },
  );
  return {
    data: data ?? null,
    loading: isLoading,
    error: (error as Error) ?? null,
    reload: () => { void mutate(); },
  };
}

export function useOutcomeBatchDetail(batchId: string | null) {
  const url = batchId
    ? `/api/v1/media/outcomes/import-batches/${encodeURIComponent(batchId)}`
    : null;
  const { data, error, isLoading, mutate } = useSWR<OutcomeBatchDetail>(
    url,
    jsonFetcher,
    { revalidateOnFocus: false },
  );
  return {
    data: data ?? null,
    loading: isLoading,
    error: (error as Error) ?? null,
    reload: () => { void mutate(); },
  };
}

export function useTruthCoverage(brand: string = 'GELO', virusTyp: string = 'Influenza A') {
  const url = useMemo(
    () =>
      `/api/v1/media/outcomes/coverage?brand=${encodeURIComponent(brand)}&virus_typ=${encodeURIComponent(virusTyp)}`,
    [brand, virusTyp],
  );
  const { data, error, isLoading, mutate } = useSWR<TruthCoverageResponse>(
    url,
    jsonFetcher,
    { refreshInterval: 300_000, revalidateOnFocus: false },
  );
  return {
    data: data ?? null,
    loading: isLoading,
    error: (error as Error) ?? null,
    reload: () => { void mutate(); },
  };
}

// -----------------------------------------------------------------
// Upload — CSV-Payload an POST /outcomes/import. Admin-only, kein SWR.
// -----------------------------------------------------------------

export interface OutcomeImportResult {
  batch_id?: string | null;
  brand?: string | null;
  status?: string;
  rows_total?: number | null;
  rows_valid?: number | null;
  rows_imported?: number | null;
  rows_rejected?: number | null;
  rows_duplicate?: number | null;
  issues?: Array<{
    row_number?: number | null;
    severity: string;
    code: string;
    message: string;
    field?: string | null;
  }>;
  [k: string]: any;
}

export interface UploadOutcomeArgs {
  brand: string;
  sourceLabel: string;
  csvPayload: string;
  fileName?: string;
  replaceExisting?: boolean;
  validateOnly?: boolean;
}

export async function uploadOutcomeCsv(
  args: UploadOutcomeArgs,
): Promise<{ ok: true; result: OutcomeImportResult } | { ok: false; status: number; message: string }> {
  const r = await fetch('/api/v1/media/outcomes/import', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      brand: args.brand,
      source_label: args.sourceLabel,
      file_name: args.fileName ?? null,
      replace_existing: args.replaceExisting ?? false,
      validate_only: args.validateOnly ?? false,
      csv_payload: args.csvPayload,
      records: [],
    }),
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => '');
    let message = txt;
    try {
      const parsed = JSON.parse(txt);
      message = parsed.detail ?? parsed.message ?? txt;
    } catch {
      // keep raw text
    }
    return { ok: false, status: r.status, message: String(message).slice(0, 500) };
  }
  const result = (await r.json()) as OutcomeImportResult;
  return { ok: true, result };
}

// ----------------------------------------------------------------
// Delete batch — admin-only. The batch row stays in history with
// status='deleted'; the underlying MediaOutcomeRecords attributed to
// the batch are removed so Truth-Coverage and § IV reflect the
// corrected data set.
// ----------------------------------------------------------------

export interface DeleteBatchResult {
  batch_id: string;
  status: string;
  rows_deleted: number;
}

export async function deleteOutcomeBatch(
  batchId: string,
): Promise<
  | { ok: true; result: DeleteBatchResult }
  | { ok: false; status: number; message: string }
> {
  const r = await fetch(
    `/api/v1/media/outcomes/import-batches/${encodeURIComponent(batchId)}`,
    {
      method: 'DELETE',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    },
  );
  if (!r.ok) {
    const txt = await r.text().catch(() => '');
    let message = txt;
    try {
      const parsed = JSON.parse(txt);
      message = parsed.detail ?? parsed.message ?? txt;
    } catch {
      // keep raw text
    }
    return { ok: false, status: r.status, message: String(message).slice(0, 500) };
  }
  const result = (await r.json()) as DeleteBatchResult;
  return { ok: true, result };
}
