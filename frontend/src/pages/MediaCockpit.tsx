import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useToast } from '../App';
import {
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

  const displayedRecommendations = useMemo(
    () => (recommendations.length > 0 ? recommendations : sortRecommendations(cockpit?.recommendations?.cards || [])),
    [cockpit?.recommendations?.cards, recommendations],
  );

  const loadCockpit = useCallback(async () => {
    setCockpitLoading(true);
    try {
      const qs = new URLSearchParams({ virus_typ: virus });
      const res = await fetch(`/api/v1/media/cockpit?${qs.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
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
      const res = await fetch(`/api/v1/media/recommendations/list?${qs.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
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
      const res = await fetch('/api/v1/media/connectors/catalog');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setConnectorCatalog(data.connectors || []);
    } catch (error) {
      console.error('Connector catalog failed', error);
    }
  }, []);

  useEffect(() => {
    loadCockpit();
  }, [loadCockpit]);

  useEffect(() => {
    loadRecommendations();
  }, [loadRecommendations]);

  useEffect(() => {
    loadConnectors();
  }, [loadConnectors]);

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
      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
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
      const res = await fetch('/api/v1/media/recommendations/generate', {
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
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

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
      const res = await fetch('/api/v1/media/recommendations/open-region', {
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
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

      await loadRecommendations();
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
  }, [brand, campaignGoal, loadCockpit, loadRecommendations, openRecommendation, toast, virus, weeklyBudget]);

  const advanceStatus = useCallback(async (id: string, nextStatus: string) => {
    setStatusUpdating(true);
    try {
      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

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
      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}/regenerate-ai`, {
        method: 'POST',
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

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
      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}/prepare-sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connector_key: connectorKey }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
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
