import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import CampaignStudio from '../../components/cockpit/CampaignStudio';
import AnimatedPage from '../../components/AnimatedPage';
import { usePageHeader } from '../../components/AppLayout';
import { mediaApi } from '../../features/media/api';
import { useCampaignsPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';
import { useToast } from '../../lib/appContext';
import { RecommendationCard } from '../../types/media/recommendations';

const CampaignsPage: React.FC = () => {
  const navigate = useNavigate();
  const { id: routeRecommendationId } = useParams<{ id?: string }>();
  const { toast } = useToast();
  const { setPageHeader, clearPageHeader } = usePageHeader();
  const {
    brand,
    setBrand,
    weeklyBudget,
    setWeeklyBudget,
    campaignGoal,
    setCampaignGoal,
    virus,
    dataVersion,
    invalidateData,
    openRecommendation,
    closeRecommendation,
    recommendationOverlayMode,
  } = useMediaWorkflow();
  const { campaignsView, campaignsLoading, loadCampaigns, workspaceStatus } = useCampaignsPageData(virus, brand, dataVersion, toast);
  const [generationLoading, setGenerationLoading] = useState(false);

  useEffect(() => {
    if (routeRecommendationId) {
      openRecommendation(routeRecommendationId, 'route');
      return;
    }
    if (recommendationOverlayMode === 'route') {
      closeRecommendation();
    }
  }, [closeRecommendation, openRecommendation, recommendationOverlayMode, routeRecommendationId]);

  const focusCard = (campaignsView?.cards || []).find((card) => (
    ['review', 'approve', 'sync'].includes(headerRecommendationLane(card))
  )) || campaignsView?.cards?.[0] || null;
  const focusActionLabel = focusCard ? headerCampaignActionLabel(focusCard) : null;

  const generateRecommendations = useCallback(async () => {
    setGenerationLoading(true);
    try {
      const data = await mediaApi.generateRecommendations({
        brand,
        product: 'Alle Produkte',
        campaign_goal: campaignGoal,
        weekly_budget: weeklyBudget,
        channel_pool: ['programmatic', 'social', 'search', 'ctv'],
        strategy_mode: 'PLAYBOOK_AI',
        max_cards: 8,
        virus_typ: virus,
      });
      toast(`${(data.cards || []).length} Vorschläge erstellt.`, 'success');
      invalidateData();
      await loadCampaigns();
    } catch (error) {
      console.error('Recommendation generation failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Erstellen fehlgeschlagen: ${message}`, 'error');
    } finally {
      setGenerationLoading(false);
    }
  }, [brand, campaignGoal, invalidateData, loadCampaigns, toast, virus, weeklyBudget]);

  useEffect(() => {
    setPageHeader({
      secondaryAction: {
        label: 'Zum Virus-Radar',
        to: '/virus-radar',
      },
      primaryAction: {
        label: focusCard
          ? focusActionLabel || 'Empfehlung prüfen'
          : (generationLoading ? 'Vorschläge werden erstellt...' : 'Vorschläge erstellen'),
        onClick: focusCard
          ? () => navigate(`/kampagnen/${focusCard.id}`)
          : generateRecommendations,
        disabled: generationLoading && !focusCard,
      },
    });

    return clearPageHeader;
  }, [clearPageHeader, focusActionLabel, focusCard, generateRecommendations, generationLoading, navigate, setPageHeader]);

  return (
    <AnimatedPage>
    <CampaignStudio
      campaignsView={campaignsView}
      virus={virus}
      brand={brand}
      budget={weeklyBudget}
      goal={campaignGoal}
      workspaceStatus={workspaceStatus}
      loading={campaignsLoading}
      generationLoading={generationLoading}
      onBrandChange={setBrand}
      onBudgetChange={setWeeklyBudget}
      onGoalChange={setCampaignGoal}
      onGenerate={generateRecommendations}
      onOpenRecommendation={(id) => {
        navigate(`/kampagnen/${id}`);
      }}
    />
    </AnimatedPage>
  );
};

export default CampaignsPage;

function headerCampaignActionLabel(card: RecommendationCard): string {
  const lane = headerRecommendationLane(card);
  if ((card.publish_blockers || []).length > 0) return 'Blocker prüfen';
  if (lane === 'sync') return 'Übergabe vorbereiten';
  if (lane === 'approve') return 'Zur Freigabe öffnen';
  if (lane === 'live') return 'Aktiven Fall öffnen';
  return 'Empfehlung prüfen';
}

function headerRecommendationLane(card: RecommendationCard): 'prepare' | 'review' | 'approve' | 'sync' | 'live' {
  const lifecycle = String(card.lifecycle_state || '').toUpperCase();
  if (lifecycle === 'LIVE') return 'live';
  if (lifecycle === 'SYNC_READY') return 'sync';
  if (lifecycle === 'APPROVE') return 'approve';
  if (lifecycle === 'REVIEW') return 'review';
  if (lifecycle === 'EXPIRED' || lifecycle === 'ARCHIVED') return 'prepare';

  const status = String(card.status || '').toUpperCase();
  if (status === 'ACTIVATED') return 'live';
  if (status === 'APPROVED') return 'sync';
  if (status === 'READY') return 'approve';
  if (status === 'NEW' || status === 'URGENT') return 'review';
  if (String(card.mapping_status || '').toLowerCase() === 'needs_review') return 'review';
  return 'prepare';
}
