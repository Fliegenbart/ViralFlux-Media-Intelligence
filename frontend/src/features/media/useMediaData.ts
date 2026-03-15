import { useCallback, useEffect, useState } from 'react';

import { BacktestResponse, MediaCampaignsResponse, MediaDecisionResponse, MediaEvidenceResponse, MediaRegionsResponse, RegionalBenchmarkResponse, RegionalPortfolioResponse, TruthImportBatchDetailResponse, TruthImportResponse } from '../../types/media';
import { mediaApi } from './api';

function noop() {}

interface ToastLike {
  (message: string, type?: 'success' | 'error' | 'info'): void;
}

export function useDecisionPageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [decision, setDecision] = useState<MediaDecisionResponse | null>(null);
  const [decisionEvidence, setDecisionEvidence] = useState<MediaEvidenceResponse | null>(null);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [waveOutlook, setWaveOutlook] = useState<BacktestResponse | null>(null);
  const [waveOutlookLoading, setWaveOutlookLoading] = useState(false);
  const [regionalBenchmark, setRegionalBenchmark] = useState<RegionalBenchmarkResponse | null>(null);
  const [regionalPortfolio, setRegionalPortfolio] = useState<RegionalPortfolioResponse | null>(null);
  const [regionalPortfolioLoading, setRegionalPortfolioLoading] = useState(false);

  const loadDecision = useCallback(async () => {
    setDecisionLoading(true);
    setRegionalPortfolioLoading(true);
    let decisionLoaded = false;
    try {
      const decisionResult = await mediaApi.getDecision(virus, brand);
      setDecision(decisionResult);
      decisionLoaded = true;
    } catch (error) {
      console.error('Decision fetch failed', error);
      toast('Entscheidung konnte nicht geladen werden.', 'error');
    } finally {
      setDecisionLoading(false);
    }

    if (!decisionLoaded) {
      setRegionalPortfolioLoading(false);
      return;
    }

    Promise.allSettled([
      mediaApi.getEvidence(virus, brand),
      mediaApi.getRegionalBenchmark(),
      mediaApi.getRegionalPortfolio(),
    ]).then(([evidenceResult, benchmarkResult, portfolioResult]) => {
      if (evidenceResult.status === 'fulfilled') {
        setDecisionEvidence(evidenceResult.value);
      } else {
        console.error('Decision evidence fetch failed', evidenceResult.reason);
        setDecisionEvidence(null);
      }

      if (benchmarkResult.status === 'fulfilled') {
        setRegionalBenchmark(benchmarkResult.value);
      } else {
        console.error('Regional benchmark fetch failed', benchmarkResult.reason);
        setRegionalBenchmark(null);
      }

      if (portfolioResult.status === 'fulfilled') {
        setRegionalPortfolio(portfolioResult.value);
      } else {
        console.error('Regional portfolio fetch failed', portfolioResult.reason);
        setRegionalPortfolio(null);
      }
    }).finally(() => {
      setRegionalPortfolioLoading(false);
    });
  }, [brand, toast, virus]);

  useEffect(() => {
    loadDecision();
  }, [dataVersion, loadDecision]);

  useEffect(() => {
    const runId = decision?.wave_run_id;
    if (!runId) {
      setWaveOutlook(null);
      setWaveOutlookLoading(false);
      return;
    }

    let active = true;
    setWaveOutlookLoading(true);
    mediaApi.getBacktestRun(runId)
      .then((result) => {
        if (active) setWaveOutlook(result?.run_id ? result : null);
      })
      .catch((error) => {
        console.error('Market validation detail failed', error);
        if (active) setWaveOutlook(null);
      })
      .finally(() => {
        if (active) setWaveOutlookLoading(false);
      });

    return () => {
      active = false;
    };
  }, [decision?.wave_run_id]);

  return {
    decision,
    decisionEvidence,
    decisionLoading,
    loadDecision,
    waveOutlook,
    waveOutlookLoading,
    regionalBenchmark,
    regionalPortfolio,
    regionalPortfolioLoading,
  };
}

export function useRegionsPageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [regionsView, setRegionsView] = useState<MediaRegionsResponse | null>(null);
  const [regionsLoading, setRegionsLoading] = useState(false);

  const loadRegions = useCallback(async () => {
    setRegionsLoading(true);
    try {
      setRegionsView(await mediaApi.getRegions(virus, brand));
    } catch (error) {
      console.error('Regions fetch failed', error);
      toast('Regionen konnten nicht geladen werden.', 'error');
    } finally {
      setRegionsLoading(false);
    }
  }, [brand, toast, virus]);

  useEffect(() => {
    loadRegions();
  }, [dataVersion, loadRegions]);

  return {
    regionsView,
    regionsLoading,
    loadRegions,
  };
}

export function useCampaignsPageData(
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [campaignsView, setCampaignsView] = useState<MediaCampaignsResponse | null>(null);
  const [campaignsLoading, setCampaignsLoading] = useState(false);

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    try {
      setCampaignsView(await mediaApi.getCampaigns(brand));
    } catch (error) {
      console.error('Campaigns fetch failed', error);
      toast('Kampagnenvorschlaege konnten nicht geladen werden.', 'error');
    } finally {
      setCampaignsLoading(false);
    }
  }, [brand, toast]);

  useEffect(() => {
    loadCampaigns();
  }, [dataVersion, loadCampaigns]);

  return {
    campaignsView,
    campaignsLoading,
    loadCampaigns,
  };
}

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

  const loadEvidence = useCallback(async () => {
    setEvidenceLoading(true);
    try {
      setEvidence(await mediaApi.getEvidence(virus, brand));
    } catch (error) {
      console.error('Evidence fetch failed', error);
      toast('Evidenz konnte nicht geladen werden.', 'error');
    } finally {
      setEvidenceLoading(false);
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
        validateOnly ? 'Upload der Kundendaten validiert. Vorschau ist bereit.' : 'Kundendaten importiert und Evidenz aktualisiert.',
        'success',
      );
    } catch (error) {
      console.error('Truth upload failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Upload der Kundendaten fehlgeschlagen: ${message}`, 'error');
    } finally {
      setTruthActionLoading(false);
    }
  }, [brand, loadEvidence, loadTruthBatchDetail, toast]);

  useEffect(() => {
    loadEvidence();
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
