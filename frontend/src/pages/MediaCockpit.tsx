import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useToast } from '../App';
import CampaignStudio from '../components/cockpit/CampaignStudio';
import DecisionView from '../components/cockpit/DecisionView';
import EvidencePanel from '../components/cockpit/EvidencePanel';
import RecommendationDrawer from '../components/cockpit/RecommendationDrawer';
import RegionWorkbench from '../components/cockpit/RegionWorkbench';
import { MediaCockpitView } from '../components/cockpit/types';
import {
  BacktestResponse,
  ConnectorCatalogItem,
  MediaCampaignsResponse,
  MediaDecisionResponse,
  MediaEvidenceResponse,
  MediaRegionsResponse,
  PreparedSyncPayload,
  RecommendationCard,
  RecommendationDetail,
  TruthImportBatchDetailResponse,
  TruthImportResponse,
} from '../types/media';

interface Props {
  view: MediaCockpitView;
}

async function fetchJson<T>(url: string, init?: RequestInit, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error((data as { detail?: string; error?: string }).detail || (data as { error?: string }).error || `HTTP ${response.status}`);
    }
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('timeout');
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function sortRecommendations(cards: RecommendationCard[]): RecommendationCard[] {
  return [...cards].sort((a, b) => {
    const publishableDelta = Number(Boolean(b.is_publishable)) - Number(Boolean(a.is_publishable));
    if (publishableDelta !== 0) return publishableDelta;
    const urgencyDelta = Number(b.urgency_score || 0) - Number(a.urgency_score || 0);
    if (urgencyDelta !== 0) return urgencyDelta;
    return Number(b.confidence || 0) - Number(a.confidence || 0);
  });
}

const MediaCockpit: React.FC<Props> = ({ view }) => {
  const navigate = useNavigate();
  const { id: routeRecommendationId } = useParams<{ id?: string }>();
  const { toast } = useToast();

  const [virus, setVirus] = useState('Influenza A');
  const [brand, setBrand] = useState('gelo');
  const [weeklyBudget, setWeeklyBudget] = useState(120000);
  const [campaignGoal, setCampaignGoal] = useState('Top-of-Mind vor Erkältungswelle');

  const [decision, setDecision] = useState<MediaDecisionResponse | null>(null);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [regionsView, setRegionsView] = useState<MediaRegionsResponse | null>(null);
  const [regionsLoading, setRegionsLoading] = useState(false);
  const [campaignsView, setCampaignsView] = useState<MediaCampaignsResponse | null>(null);
  const [campaignsLoading, setCampaignsLoading] = useState(false);
  const [evidenceView, setEvidenceView] = useState<MediaEvidenceResponse | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [truthPreview, setTruthPreview] = useState<TruthImportResponse | null>(null);
  const [truthBatchDetail, setTruthBatchDetail] = useState<TruthImportBatchDetailResponse | null>(null);
  const [truthActionLoading, setTruthActionLoading] = useState(false);
  const [truthBatchDetailLoading, setTruthBatchDetailLoading] = useState(false);

  const [generationLoading, setGenerationLoading] = useState(false);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [regionActionLoading, setRegionActionLoading] = useState(false);

  const [detail, setDetail] = useState<RecommendationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const [connectorCatalog, setConnectorCatalog] = useState<ConnectorCatalogItem[]>([]);
  const [syncPreview, setSyncPreview] = useState<PreparedSyncPayload | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);

  const [marketValidation, setMarketValidation] = useState<BacktestResponse | null>(null);
  const [marketValidationLoading, setMarketValidationLoading] = useState(false);
  const [customerValidation, setCustomerValidation] = useState<BacktestResponse | null>(null);
  const [customerValidationLoading, setCustomerValidationLoading] = useState(false);

  const needsConnectorCatalog = view === 'campaigns' || Boolean(detail);

  const loadDecision = useCallback(async () => {
    setDecisionLoading(true);
    try {
      const qs = new URLSearchParams({ virus_typ: virus, brand });
      const data = await fetchJson<MediaDecisionResponse>(`/api/v1/media/decision?${qs.toString()}`, undefined, 12000);
      setDecision(data);
    } catch (error) {
      console.error('Decision fetch failed', error);
      toast('Entscheidung konnte nicht geladen werden.', 'error');
    } finally {
      setDecisionLoading(false);
    }
  }, [brand, toast, virus]);

  const loadRegions = useCallback(async () => {
    setRegionsLoading(true);
    try {
      const qs = new URLSearchParams({ virus_typ: virus, brand });
      const data = await fetchJson<MediaRegionsResponse>(`/api/v1/media/regions?${qs.toString()}`, undefined, 12000);
      setRegionsView(data);
    } catch (error) {
      console.error('Regions fetch failed', error);
      toast('Regionen konnten nicht geladen werden.', 'error');
    } finally {
      setRegionsLoading(false);
    }
  }, [brand, toast, virus]);

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    try {
      const qs = new URLSearchParams({ brand, limit: '120' });
      const data = await fetchJson<MediaCampaignsResponse>(`/api/v1/media/campaigns?${qs.toString()}`, undefined, 12000);
      setCampaignsView({
        ...data,
        cards: sortRecommendations(data.cards || []),
      });
    } catch (error) {
      console.error('Campaigns fetch failed', error);
      toast('Kampagnenpakete konnten nicht geladen werden.', 'error');
    } finally {
      setCampaignsLoading(false);
    }
  }, [brand, toast]);

  const loadEvidence = useCallback(async () => {
    setEvidenceLoading(true);
    try {
      const qs = new URLSearchParams({ virus_typ: virus, brand });
      const data = await fetchJson<MediaEvidenceResponse>(`/api/v1/media/evidence?${qs.toString()}`, undefined, 12000);
      setEvidenceView(data);
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
      const data = await fetchJson<TruthImportBatchDetailResponse>(`/api/v1/media/outcomes/import-batches/${encodeURIComponent(batchId)}`, undefined, 12000);
      setTruthBatchDetail(data);
    } catch (error) {
      console.error('Truth batch detail failed', error);
      toast('Import-Detail konnte nicht geladen werden.', 'error');
    } finally {
      setTruthBatchDetailLoading(false);
    }
  }, [toast]);

  const loadConnectors = useCallback(async () => {
    try {
      const data = await fetchJson<{ connectors?: ConnectorCatalogItem[] }>('/api/v1/media/connectors/catalog', undefined, 8000);
      setConnectorCatalog(data.connectors || []);
    } catch (error) {
      console.error('Connector catalog failed', error);
    }
  }, []);

  const loadBacktestRun = useCallback(async (
    runId: string,
    setResult: React.Dispatch<React.SetStateAction<BacktestResponse | null>>,
    setLoading: React.Dispatch<React.SetStateAction<boolean>>,
    errorLabel: string,
  ) => {
    setLoading(true);
    try {
      const data = await fetchJson<BacktestResponse>(`/api/v1/backtest/runs/${encodeURIComponent(runId)}`, undefined, 12000);
      if (!data?.run_id) {
        throw new Error('Run nicht gefunden');
      }
      setResult(data);
    } catch (error) {
      console.error(`${errorLabel} detail failed`, error);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view === 'decision') {
      loadDecision();
      return;
    }
    if (view === 'regions') {
      loadRegions();
      return;
    }
    if (view === 'campaigns') {
      loadCampaigns();
      return;
    }
    if (view === 'evidence') {
      loadEvidence();
    }
  }, [loadCampaigns, loadDecision, loadEvidence, loadRegions, view]);

  useEffect(() => {
    if (!needsConnectorCatalog) return;
    loadConnectors();
  }, [loadConnectors, needsConnectorCatalog]);

  useEffect(() => {
    const runId = view === 'decision'
      ? decision?.wave_run_id
      : evidenceView?.proxy_validation?.run_id;
    if (!runId) {
      setMarketValidation(null);
      setMarketValidationLoading(false);
      return;
    }
    loadBacktestRun(runId, setMarketValidation, setMarketValidationLoading, 'Market validation');
  }, [decision?.wave_run_id, evidenceView?.proxy_validation?.run_id, loadBacktestRun, view]);

  useEffect(() => {
    if (view !== 'evidence') {
      setCustomerValidation(null);
      setCustomerValidationLoading(false);
      return;
    }
    const customerRunId = evidenceView?.truth_validation?.run_id;
    if (!customerRunId) {
      setCustomerValidation(null);
      setCustomerValidationLoading(false);
      return;
    }
    loadBacktestRun(customerRunId, setCustomerValidation, setCustomerValidationLoading, 'Customer validation');
  }, [evidenceView?.truth_validation?.run_id, loadBacktestRun, view]);

  useEffect(() => {
    if (view !== 'evidence') {
      setTruthPreview(null);
      setTruthBatchDetail(null);
      return;
    }
    const latestBatchId = evidenceView?.truth_snapshot?.latest_batch?.batch_id;
    if (!latestBatchId) {
      setTruthBatchDetail(null);
      return;
    }
    loadTruthBatchDetail(latestBatchId);
  }, [evidenceView?.truth_snapshot?.latest_batch?.batch_id, loadTruthBatchDetail, view]);

  useEffect(() => {
    if (!selectedRegion && regionsView?.map?.top_regions?.[0]?.code) {
      setSelectedRegion(regionsView.map.top_regions[0].code);
    }
  }, [regionsView?.map?.top_regions, selectedRegion]);

  const openRecommendation = useCallback(async (id: string, updateRoute = view === 'campaigns') => {
    if (!id) return;
    if (updateRoute) {
      navigate(`/kampagnen/${id}`);
    }
    setDetailLoading(true);
    setSyncPreview(null);
    try {
      const data = await fetchJson<RecommendationDetail>(`/api/v1/media/recommendations/${encodeURIComponent(id)}`, undefined, 12000);
      setDetail(data);
    } catch (error) {
      console.error('Recommendation detail failed', error);
      toast('Kampagnendetail konnte nicht geladen werden.', 'error');
    } finally {
      setDetailLoading(false);
    }
  }, [navigate, toast, view]);

  useEffect(() => {
    if (view === 'campaigns' && routeRecommendationId) {
      openRecommendation(routeRecommendationId, false);
    }
  }, [openRecommendation, routeRecommendationId, view]);

  const closeRecommendation = useCallback(() => {
    setDetail(null);
    setSyncPreview(null);
    if (routeRecommendationId) {
      navigate('/kampagnen');
    }
  }, [navigate, routeRecommendationId]);

  const refreshCoreViews = useCallback(async () => {
    await Promise.all([
      loadDecision(),
      loadRegions(),
      loadCampaigns(),
      loadEvidence(),
    ]);
  }, [loadCampaigns, loadDecision, loadEvidence, loadRegions]);

  const generateRecommendations = useCallback(async () => {
    setGenerationLoading(true);
    try {
      const data = await fetchJson<{ cards?: RecommendationCard[] }>('/api/v1/media/recommendations/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brand,
          product: 'Alle Gelo-Produkte',
          campaign_goal: campaignGoal,
          weekly_budget: weeklyBudget,
          channel_pool: ['programmatic', 'social', 'search', 'ctv'],
          strategy_mode: 'PLAYBOOK_AI',
          max_cards: 8,
          virus_typ: virus,
        }),
      }, 30000);

      toast(`${(data.cards || []).length} Kampagnenpakete erzeugt.`, 'success');
      await refreshCoreViews();
    } catch (error) {
      console.error('Recommendation generation failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Generierung fehlgeschlagen: ${message}`, 'error');
    } finally {
      setGenerationLoading(false);
    }
  }, [brand, campaignGoal, refreshCoreViews, toast, virus, weeklyBudget]);

  const openOrCreateRegionCampaign = useCallback(async (regionCode: string) => {
    setRegionActionLoading(true);
    try {
      const data = await fetchJson<{ action?: string; card_id?: string }>('/api/v1/media/recommendations/open-region', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_code: regionCode,
          brand,
          product: 'Alle Gelo-Produkte',
          campaign_goal: campaignGoal,
          weekly_budget: weeklyBudget,
          virus_typ: virus,
        }),
      }, 30000);

      await refreshCoreViews();

      if (data.card_id) {
        toast(data.action === 'reused' ? 'Vorhandenes Kampagnenpaket geöffnet.' : 'Regionale Kampagne erzeugt.', 'success');
        await openRecommendation(data.card_id, false);
      }
    } catch (error) {
      console.error('Region campaign failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Regionenaktion fehlgeschlagen: ${message}`, 'error');
    } finally {
      setRegionActionLoading(false);
    }
  }, [brand, campaignGoal, openRecommendation, refreshCoreViews, toast, virus, weeklyBudget]);

  const advanceStatus = useCallback(async (id: string, nextStatus: string) => {
    setStatusUpdating(true);
    try {
      const data = await fetchJson<{ new_status?: string }>(`/api/v1/media/recommendations/${encodeURIComponent(id)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus }),
      }, 12000);

      toast(`Status auf ${data.new_status || nextStatus} gesetzt.`, 'success');
      await refreshCoreViews();
      await openRecommendation(id, false);
    } catch (error) {
      console.error('Status update failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Statuswechsel fehlgeschlagen: ${message}`, 'error');
    } finally {
      setStatusUpdating(false);
    }
  }, [openRecommendation, refreshCoreViews, toast]);

  const regenerateAI = useCallback(async (id: string) => {
    setRegenerating(true);
    try {
      const data = await fetchJson<RecommendationDetail>(`/api/v1/media/recommendations/${encodeURIComponent(id)}/regenerate-ai`, {
        method: 'POST',
      }, 30000);

      setDetail(data);
      await refreshCoreViews();
      toast('Qwen-Plan aktualisiert.', 'success');
    } catch (error) {
      console.error('AI regeneration failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Qwen-Regeneration fehlgeschlagen: ${message}`, 'error');
    } finally {
      setRegenerating(false);
    }
  }, [refreshCoreViews, toast]);

  const prepareSync = useCallback(async (id: string, connectorKey: string) => {
    setSyncLoading(true);
    try {
      const data = await fetchJson<PreparedSyncPayload>(`/api/v1/media/recommendations/${encodeURIComponent(id)}/prepare-sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connector_key: connectorKey }),
      }, 12000);
      setSyncPreview(data);
      setConnectorCatalog(data.available_connectors || connectorCatalog);
      toast('Connector-Preview vorbereitet.', 'success');
    } catch (error) {
      console.error('Prepare sync failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Sync-Preview fehlgeschlagen: ${message}`, 'error');
    } finally {
      setSyncLoading(false);
    }
  }, [connectorCatalog, toast]);

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
      const data = await fetchJson<TruthImportResponse>('/api/v1/media/outcomes/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brand,
          source_label: sourceLabel,
          replace_existing: replaceExisting,
          validate_only: validateOnly,
          file_name: file.name,
          csv_payload: csvPayload,
        }),
      }, 30000);

      setTruthPreview(data);
      if (data.batch_id) {
        await loadTruthBatchDetail(data.batch_id);
      }
      await Promise.all([loadEvidence(), loadDecision()]);
      toast(
        validateOnly ? 'Truth-Upload validiert. Vorschau ist bereit.' : 'Truth-Daten importiert und Evidenz aktualisiert.',
        'success',
      );
    } catch (error) {
      console.error('Truth upload failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Truth-Upload fehlgeschlagen: ${message}`, 'error');
    } finally {
      setTruthActionLoading(false);
    }
  }, [brand, loadDecision, loadEvidence, loadTruthBatchDetail, toast]);

  return (
    <>
      {view === 'decision' && (
        <DecisionView
          virus={virus}
          onVirusChange={setVirus}
          decision={decision}
          loading={decisionLoading}
          waveOutlook={marketValidation}
          waveOutlookLoading={marketValidationLoading}
          onOpenRecommendation={(id) => openRecommendation(id, false)}
          onOpenRegions={() => navigate('/regionen')}
          onOpenCampaigns={() => navigate('/kampagnen')}
        />
      )}

      {view === 'regions' && (
        <RegionWorkbench
          virus={virus}
          onVirusChange={setVirus}
          regionsView={regionsView}
          loading={regionsLoading}
          selectedRegion={selectedRegion}
          onSelectRegion={setSelectedRegion}
          onOpenRecommendation={(id) => openRecommendation(id, false)}
          onGenerateRegionCampaign={openOrCreateRegionCampaign}
          regionActionLoading={regionActionLoading}
        />
      )}

      {view === 'campaigns' && (
        <CampaignStudio
          campaignsView={campaignsView}
          virus={virus}
          brand={brand}
          budget={weeklyBudget}
          goal={campaignGoal}
          loading={campaignsLoading}
          generationLoading={generationLoading}
          onBrandChange={setBrand}
          onBudgetChange={setWeeklyBudget}
          onGoalChange={setCampaignGoal}
          onGenerate={generateRecommendations}
          onOpenRecommendation={(id) => openRecommendation(id, true)}
        />
      )}

      {view === 'evidence' && (
        <EvidencePanel
          evidence={evidenceView}
          loading={evidenceLoading}
          marketValidation={marketValidation}
          marketValidationLoading={marketValidationLoading}
          customerValidation={customerValidation}
          customerValidationLoading={customerValidationLoading}
          truthPreview={truthPreview}
          truthBatchDetail={truthBatchDetail}
          truthActionLoading={truthActionLoading}
          truthBatchDetailLoading={truthBatchDetailLoading}
          onSubmitTruthCsv={submitTruthCsv}
          onLoadTruthBatchDetail={loadTruthBatchDetail}
        />
      )}

      <RecommendationDrawer
        detail={detail}
        loading={detailLoading}
        connectorCatalog={connectorCatalog}
        syncPreview={syncPreview}
        syncLoading={syncLoading}
        statusUpdating={statusUpdating}
        regenerating={regenerating}
        onClose={closeRecommendation}
        onAdvanceStatus={advanceStatus}
        onRegenerateAI={regenerateAI}
        onPrepareSync={prepareSync}
      />
    </>
  );
};

export default MediaCockpit;
