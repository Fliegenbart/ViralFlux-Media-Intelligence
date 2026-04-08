import { useCallback, useEffect, useRef, useState } from 'react';

import {
  BacktestResponse,
  MediaEvidenceResponse,
  TruthImportBatchDetailResponse,
  TruthImportResponse,
} from '../../types/media';
import { mediaApi } from './api';
import {
  buildWorkspaceStatus,
  noop,
  ToastLike,
} from './useMediaData.shared';

export function useEvidencePageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [evidence, setEvidence] = useState<MediaEvidenceResponse | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [truthPreview, setTruthPreview] = useState<TruthImportResponse | null>(null);
  const [truthBatchDetail, setTruthBatchDetail] = useState<TruthImportBatchDetailResponse | null>(null);
  const [truthActionLoading, setTruthActionLoading] = useState(false);
  const [truthBatchDetailLoading, setTruthBatchDetailLoading] = useState(false);
  const [marketValidation, setMarketValidation] = useState<BacktestResponse | null>(null);
  const [marketValidationLoading, setMarketValidationLoading] = useState(false);
  const [customerValidation, setCustomerValidation] = useState<BacktestResponse | null>(null);
  const [customerValidationLoading, setCustomerValidationLoading] = useState(false);
  const loadVersionRef = useRef(0);

  const loadEvidence = useCallback(async () => {
    const loadVersion = ++loadVersionRef.current;
    setEvidenceLoading(true);
    try {
      const result = await mediaApi.getEvidence(virus, brand);
      if (loadVersionRef.current !== loadVersion) return;
      setEvidence(result);
    } catch (error) {
      console.error('Evidence fetch failed', error);
      if (loadVersionRef.current !== loadVersion) return;
      toast('Qualität konnte nicht geladen werden.', 'error');
    } finally {
      if (loadVersionRef.current === loadVersion) {
        setEvidenceLoading(false);
      }
    }
  }, [brand, toast, virus]);

  const loadTruthBatchDetail = useCallback(async (batchId: string) => {
    if (!batchId) return;
    setTruthBatchDetailLoading(true);
    try {
      setTruthBatchDetail(await mediaApi.getTruthImportBatchDetail(batchId));
    } catch (error) {
      console.error('Truth batch detail failed', error);
      toast('Import-Detail konnte nicht geladen werden.', 'error');
    } finally {
      setTruthBatchDetailLoading(false);
    }
  }, [toast]);

  const submitTruthCsv = useCallback(async ({
    file,
    sourceLabel,
    replaceExisting,
    validateOnly,
  }: {
    file: File;
    sourceLabel: string;
    replaceExisting: boolean;
    validateOnly: boolean;
  }) => {
    setTruthActionLoading(true);
    try {
      const csvPayload = await file.text();
      const result = await mediaApi.importTruthCsv({
        brand,
        source_label: sourceLabel,
        replace_existing: replaceExisting,
        validate_only: validateOnly,
        file_name: file.name,
        csv_payload: csvPayload,
      });
      setTruthPreview(result);
      if (result.batch_id) {
        await loadTruthBatchDetail(result.batch_id);
      }
      await loadEvidence();
      toast(
        validateOnly ? 'Kundendaten geprüft. Die Vorschau ist bereit.' : 'Kundendaten importiert und Qualität aktualisiert.',
        'success',
      );
    } catch (error) {
      console.error('Truth upload failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Import der Kundendaten fehlgeschlagen: ${message}`, 'error');
    } finally {
      setTruthActionLoading(false);
    }
  }, [brand, loadEvidence, loadTruthBatchDetail, toast]);

  useEffect(() => {
    loadEvidence();
    return () => {
      loadVersionRef.current += 1;
    };
  }, [dataVersion, loadEvidence]);

  useEffect(() => {
    if (!evidence?.truth_snapshot?.latest_batch?.batch_id) {
      setTruthBatchDetail(null);
      return;
    }
    loadTruthBatchDetail(evidence.truth_snapshot.latest_batch.batch_id);
  }, [evidence?.truth_snapshot?.latest_batch?.batch_id, loadTruthBatchDetail]);

  useEffect(() => {
    const runId = evidence?.proxy_validation?.run_id;
    if (!runId) {
      setMarketValidation(null);
      setMarketValidationLoading(false);
      return;
    }

    let active = true;
    setMarketValidationLoading(true);
    mediaApi.getBacktestRun(runId)
      .then((result) => {
        if (active) setMarketValidation(result?.run_id ? result : null);
      })
      .catch((error) => {
        console.error('Market validation detail failed', error);
        if (active) setMarketValidation(null);
      })
      .finally(() => {
        if (active) setMarketValidationLoading(false);
      });

    return () => {
      active = false;
    };
  }, [evidence?.proxy_validation?.run_id]);

  useEffect(() => {
    const runId = evidence?.truth_validation?.run_id;
    if (!runId) {
      setCustomerValidation(null);
      setCustomerValidationLoading(false);
      return;
    }

    let active = true;
    setCustomerValidationLoading(true);
    mediaApi.getBacktestRun(runId)
      .then((result) => {
        if (active) setCustomerValidation(result?.run_id ? result : null);
      })
      .catch((error) => {
        console.error('Customer validation detail failed', error);
        if (active) setCustomerValidation(null);
      })
      .finally(() => {
        if (active) setCustomerValidationLoading(false);
      });

    return () => {
      active = false;
    };
  }, [evidence?.truth_validation?.run_id]);

  return {
    evidence,
    evidenceLoading,
    loadEvidence,
    workspaceStatus: buildWorkspaceStatus(null, evidence),
    marketValidation,
    marketValidationLoading,
    customerValidation,
    customerValidationLoading,
    truthPreview,
    truthBatchDetail,
    truthActionLoading,
    truthBatchDetailLoading,
    loadTruthBatchDetail,
    submitTruthCsv,
  };
}
