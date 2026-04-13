import React, { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';

import RegionWorkbench from '../../components/cockpit/RegionWorkbench';
import { useToast } from '../../App';
import AnimatedPage from '../../components/AnimatedPage';
import { usePageHeader } from '../../components/AppLayout';
import { mediaApi } from '../../features/media/api';
import { useRegionsPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const RegionsPage: React.FC = () => {
  const location = useLocation();
  const { toast } = useToast();
  const { setPageHeader, clearPageHeader } = usePageHeader();
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

  const openOrCreateRegionCampaign = useCallback(async (regionCode: string) => {
    setRegionActionLoading(true);
    try {
      const data = await mediaApi.openRegionCampaign({
        region_code: regionCode,
        brand,
        product: 'Alle Produkte',
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
  }, [brand, campaignGoal, invalidateData, loadRegions, openRecommendation, toast, virus, weeklyBudget]);

  const focusRegionCode = selectedRegion || regionsView?.map?.top_regions?.[0]?.code || null;
  const focusRegion = focusRegionCode ? regionsView?.map?.regions?.[focusRegionCode] || null : null;
  const focusRecommendationId = focusRegion?.recommendation_ref?.card_id || null;
  const focusHasThinEvidence = hasThinRegionEvidence(focusRegion);

  useEffect(() => {
    const primaryAction = focusRecommendationId ? {
      label: 'Regionalen Vorschlag öffnen',
      onClick: () => openRecommendation(focusRecommendationId, 'overlay'),
    } : {
      label: regionActionLoading ? 'Regionale Maßnahme wird geprüft...' : 'Regionale Maßnahme prüfen',
      onClick: () => {
        if (focusRegionCode) {
          void openOrCreateRegionCampaign(focusRegionCode);
        }
      },
      disabled: regionActionLoading || !focusRegionCode || focusHasThinEvidence,
    };

    setPageHeader({
      primaryAction,
      secondaryAction: {
        label: 'Zum Virus-Radar',
        to: '/virus-radar',
      },
    });

    return clearPageHeader;
  }, [
    clearPageHeader,
    focusHasThinEvidence,
    focusRecommendationId,
    focusRegionCode,
    openOrCreateRegionCampaign,
    openRecommendation,
    regionActionLoading,
    setPageHeader,
  ]);

  return (
    <AnimatedPage>
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
    </AnimatedPage>
  );
};

export default RegionsPage;

function hasThinRegionEvidence(region?: {
  source_trace?: string[];
  signal_drivers?: Array<{ label: string; strength_pct: number }>;
  signal_score?: number;
  peix_score?: number;
  impact_probability?: number;
} | null): boolean {
  if (!region) return true;
  const sourceCount = region.source_trace?.length || 0;
  const driverCount = region.signal_drivers?.length || 0;
  const signalScore = region.signal_score ?? region.peix_score ?? region.impact_probability ?? 0;
  return signalScore <= 0 || (sourceCount < 2 && driverCount === 0);
}
