import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useToast } from '../App';
import {
  BacktestResponse,
  ConnectorCatalogItem,
  PreparedSyncPayload,
  RecommendationCard,
  RecommendationDetail,
} from '../types/media';
import CampaignStudio from '../components/cockpit/CampaignStudio';
import DecisionView from '../components/cockpit/DecisionView';
import EvidencePanel from '../components/cockpit/EvidencePanel';
import RecommendationDrawer from '../components/cockpit/RecommendationDrawer';
import RegionWorkbench from '../components/cockpit/RegionWorkbench';
import { CockpitResponse, MediaCockpitView } from '../components/cockpit/types';

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
  const [cockpit, setCockpit] = useState<CockpitResponse | null>(null);
  const [cockpitLoading, setCockpitLoading] = useState(true);

  const [recommendations, setRecommendations] = useState<RecommendationCard[]>([]);
  const [recommendationsLoading, setRecommendationsLoading] = useState(true);
  const [generationLoading, setGenerationLoading] = useState(false);

  const [brand, setBrand] = useState('gelo');
  const [weeklyBudget, setWeeklyBudget] = useState(120000);
  const [campaignGoal, setCampaignGoal] = useState('Top-of-Mind vor Erkältungswelle');

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
  const needsCampaignList = view === 'campaigns';
  const needsConnectorCatalog = view === 'campaigns' || Boolean(detail);
  const needsMarketValidation = view === 'decision' || view === 'evidence';
  const needsCustomerValidation = view === 'evidence';

  const displayedRecommendations = useMemo(
    () => (
      needsCampaignList && recommendations.length > 0
        ? recommendations
        : sortRecommendations(cockpit?.recommendations?.cards || [])
    ),
    [cockpit?.recommendations?.cards, needsCampaignList, recommendations],
  );

  const loadCockpit = useCallback(async () => {
    setCockpitLoading(true);
    try {
      const qs = new URLSearchParams({ virus_typ: virus });
      const data = await fetchJson<CockpitResponse>(`/api/v1/media/cockpit?${qs.toString()}`, undefined, 12000);
      setCockpit(data);
    } catch (error) {
      console.error('Cockpit fetch failed', error);
      toast('Cockpit konnte nicht geladen werden.', 'error');
    } finally {
      setCockpitLoading(false);
    }
  }, [toast, virus]);

  const loadRecommendations = useCallback(async () => {
    setRecommendationsLoading(true);
    try {
      const qs = new URLSearchParams({ limit: '120', with_campaign_preview: 'true' });
      const data = await fetchJson<{ cards?: RecommendationCard[] }>(`/api/v1/media/recommendations/list?${qs.toString()}`, undefined, 12000);
      setRecommendations(sortRecommendations(data.cards || []));
    } catch (error) {
      console.error('Recommendation list failed', error);
      toast('Kampagnenpakete konnten nicht geladen werden.', 'error');
    } finally {
      setRecommendationsLoading(false);
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
    loadCockpit();
  }, [loadCockpit]);

  useEffect(() => {
    if (!needsCampaignList) {
      setRecommendationsLoading(false);
      return;
    }
    loadRecommendations();
  }, [loadRecommendations, needsCampaignList]);

  useEffect(() => {
    if (!needsConnectorCatalog) return;
    loadConnectors();
  }, [loadConnectors, needsConnectorCatalog]);

  useEffect(() => {
    if (!needsMarketValidation) {
      setMarketValidationLoading(false);
      return;
    }
    const marketRunId = cockpit?.backtest_summary?.latest_market?.run_id;
    if (!marketRunId) {
      setMarketValidation(null);
      setMarketValidationLoading(false);
      return;
    }
    loadBacktestRun(marketRunId, setMarketValidation, setMarketValidationLoading, 'Market validation');
  }, [cockpit?.backtest_summary?.latest_market?.run_id, loadBacktestRun, needsMarketValidation]);

  useEffect(() => {
    if (!needsCustomerValidation) {
      setCustomerValidationLoading(false);
      return;
    }
    const customerRunId = cockpit?.backtest_summary?.latest_customer?.run_id;
    if (!customerRunId) {
      setCustomerValidation(null);
      setCustomerValidationLoading(false);
      return;
    }
    loadBacktestRun(customerRunId, setCustomerValidation, setCustomerValidationLoading, 'Customer validation');
  }, [cockpit?.backtest_summary?.latest_customer?.run_id, loadBacktestRun, needsCustomerValidation]);

  useEffect(() => {
    if (!selectedRegion && cockpit?.map?.top_regions?.[0]?.code) {
      setSelectedRegion(cockpit.map.top_regions[0].code);
    }
  }, [cockpit?.map?.top_regions, selectedRegion]);

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

      const cards = sortRecommendations(data.cards || []);
      setRecommendations(cards);
      toast(`${cards.length} Kampagnenpakete erzeugt.`, 'success');
      await loadCockpit();
    } catch (error) {
      console.error('Recommendation generation failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Generierung fehlgeschlagen: ${message}`, 'error');
    } finally {
      setGenerationLoading(false);
    }
  }, [brand, campaignGoal, loadCockpit, toast, virus, weeklyBudget]);

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

      if (needsCampaignList) {
        await loadRecommendations();
      }
      await loadCockpit();

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
  }, [brand, campaignGoal, loadCockpit, loadRecommendations, needsCampaignList, openRecommendation, toast, virus, weeklyBudget]);

  const advanceStatus = useCallback(async (id: string, nextStatus: string) => {
    setStatusUpdating(true);
    try {
      const data = await fetchJson<{ new_status?: string }>(`/api/v1/media/recommendations/${encodeURIComponent(id)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus }),
      }, 12000);

      setRecommendations((current) => sortRecommendations(
        current.map((card) => (
          card.id === id
            ? { ...card, status: data.new_status || nextStatus, status_label: data.new_status || nextStatus }
            : card
        )),
      ));
      toast(`Status auf ${data.new_status || nextStatus} gesetzt.`, 'success');
      await openRecommendation(id, false);
    } catch (error) {
      console.error('Status update failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Statuswechsel fehlgeschlagen: ${message}`, 'error');
    } finally {
      setStatusUpdating(false);
    }
  }, [openRecommendation, toast]);

  const regenerateAI = useCallback(async (id: string) => {
    setRegenerating(true);
    try {
      const data = await fetchJson<RecommendationDetail>(`/api/v1/media/recommendations/${encodeURIComponent(id)}/regenerate-ai`, {
        method: 'POST',
      }, 30000);

      setDetail(data);
      setRecommendations((current) => sortRecommendations(
        current.map((card) => (
          card.id === id
            ? {
              ...card,
              campaign_name: data.campaign_name || card.campaign_name,
              campaign_preview: data.campaign_preview || card.campaign_preview,
              ai_generation_status: data.ai_generation_status || card.ai_generation_status,
            }
            : card
        )),
      ));
      toast('Qwen-Plan aktualisiert.', 'success');
    } catch (error) {
      console.error('AI regeneration failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Qwen-Regeneration fehlgeschlagen: ${message}`, 'error');
    } finally {
      setRegenerating(false);
    }
  }, [toast]);

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

  return (
    <>
      {view === 'decision' && (
        <DecisionView
          virus={virus}
          onVirusChange={setVirus}
          cockpit={cockpit}
          loading={cockpitLoading}
          recommendations={displayedRecommendations}
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
          cockpit={cockpit}
          loading={cockpitLoading}
          selectedRegion={selectedRegion}
          onSelectRegion={setSelectedRegion}
          onOpenRecommendation={(id) => openRecommendation(id, false)}
          onGenerateRegionCampaign={openOrCreateRegionCampaign}
          regionActionLoading={regionActionLoading}
        />
      )}

      {view === 'campaigns' && (
        <CampaignStudio
          cards={displayedRecommendations}
          virus={virus}
          brand={brand}
          budget={weeklyBudget}
          goal={campaignGoal}
          loading={recommendationsLoading}
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
          cockpit={cockpit}
          loading={cockpitLoading}
          marketValidation={marketValidation}
          marketValidationLoading={marketValidationLoading}
          customerValidation={customerValidation}
          customerValidationLoading={customerValidationLoading}
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
