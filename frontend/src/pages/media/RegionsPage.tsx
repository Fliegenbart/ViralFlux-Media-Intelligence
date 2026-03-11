import React, { useEffect, useState } from 'react';

import RegionWorkbench from '../../components/cockpit/RegionWorkbench';
import { useToast } from '../../App';
import { mediaApi } from '../../features/media/api';
import { useRegionsPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const RegionsPage: React.FC = () => {
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
  const { regionsView, regionsLoading, loadRegions } = useRegionsPageData(virus, brand, dataVersion, toast);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [regionActionLoading, setRegionActionLoading] = useState(false);

  useEffect(() => {
    if (!selectedRegion && regionsView?.map?.top_regions?.[0]?.code) {
      setSelectedRegion(regionsView.map.top_regions[0].code);
    }
  }, [regionsView?.map?.top_regions, selectedRegion]);

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
        toast(data.action === 'reused' ? 'Vorhandenes Kampagnenpaket geöffnet.' : 'Regionale Kampagne erzeugt.', 'success');
        openRecommendation(data.card_id, 'overlay');
      }
    } catch (error) {
      console.error('Region campaign failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Regionenaktion fehlgeschlagen: ${message}`, 'error');
    } finally {
      setRegionActionLoading(false);
    }
  };

  return (
    <RegionWorkbench
      virus={virus}
      onVirusChange={setVirus}
      regionsView={regionsView}
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
