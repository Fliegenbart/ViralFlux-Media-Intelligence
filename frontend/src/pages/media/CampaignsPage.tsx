import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import CampaignStudio from '../../components/cockpit/CampaignStudio';
import { useToast } from '../../App';
import {
  PageChromeMobileToggle,
  PageChromeUtilityMenu,
  usePageHeader,
} from '../../components/AppLayout';
import { mediaApi } from '../../features/media/api';
import { useCampaignsPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

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

  const generateRecommendations = useCallback(async () => {
    setGenerationLoading(true);
    try {
      const data = await mediaApi.generateRecommendations({
        brand,
        product: 'Alle Gelo-Produkte',
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
      chromeMode: 'hidden',
    });

    return clearPageHeader;
  }, [clearPageHeader, setPageHeader]);

  const headerActions = (
    <div className="operator-page-actions" aria-label="Kampagnenaktionen">
      <PageChromeMobileToggle />
      <button
        type="button"
        className="operator-page-action operator-page-action--secondary"
        onClick={() => navigate('/jetzt')}
      >
        Zum Wochenplan
      </button>
      <button
        type="button"
        className="operator-page-action operator-page-action--primary"
        onClick={generateRecommendations}
        disabled={generationLoading}
      >
        {generationLoading ? 'Vorschläge werden erstellt...' : 'Vorschläge erstellen'}
      </button>
      <PageChromeUtilityMenu />
    </div>
  );

  return (
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
      headerActions={headerActions}
    />
  );
};

export default CampaignsPage;
