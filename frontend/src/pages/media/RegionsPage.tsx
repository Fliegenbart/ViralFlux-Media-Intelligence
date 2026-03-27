import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';

import RegionWorkbench from '../../components/cockpit/RegionWorkbench';
import { useToast } from '../../App';
import { mediaApi } from '../../features/media/api';
import { useRegionsPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const RegionsPage: React.FC = () => {
  const location = useLocation();
  const { toast } = useToast();
  const {
    virus,
    setVirus,
    brand,
    weeklyBudget,
    campaignGoal,
    dataVersion,
    invalidateData,
    openRecommendation,
  } = useMediaWorkflow();
  const { regionsView, regionsLoading, loadRegions, workspaceStatus } = useRegionsPageData(virus, brand, dataVersion, toast);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [regionActionLoading, setRegionActionLoading] = useState(false);

  useEffect(() => {
    if (!selectedRegion && regionsView?.map?.top_regions?.[0]?.code) {
      setSelectedRegion(regionsView.map.top_regions[0].code);
    }
  }, [regionsView?.map?.top_regions, selectedRegion]);

  useEffect(() => {
    const regionCode = (location.state as { regionCode?: string } | null)?.regionCode;
    if (regionCode) {
      setSelectedRegion(regionCode);
    }
  }, [location.state]);

  const openOrCreateRegionCampaign = async (regionCode: string) => {
    setRegionActionLoading(true);
    try {
      const data = await mediaApi.openRegionCampaign({
        region_code: regionCode,
        brand,
        product: 'Alle Gelo-Produkte',
        campaign_goal: campaignGoal,
        weekly_budget: weeklyBudget,
        virus_typ: virus,
      });
      invalidateData();
      await loadRegions();
      if (data.card_id) {
        toast(data.action === 'reused' ? 'Vorhandener Vorschlag geöffnet.' : 'Neuer Vorschlag erstellt.', 'success');
        openRecommendation(data.card_id, 'overlay');
      }
    } catch (error) {
      console.error('Region campaign failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Aktion fehlgeschlagen: ${message}`, 'error');
    } finally {
      setRegionActionLoading(false);
    }
  };

  return (
    <RegionWorkbench
      virus={virus}
      onVirusChange={setVirus}
      regionsView={regionsView}
      workspaceStatus={workspaceStatus}
      loading={regionsLoading}
      selectedRegion={selectedRegion}
      onSelectRegion={setSelectedRegion}
      onOpenRecommendation={(id) => openRecommendation(id, 'overlay')}
      onGenerateRegionCampaign={openOrCreateRegionCampaign}
      regionActionLoading={regionActionLoading}
    />
  );
};

export default RegionsPage;
