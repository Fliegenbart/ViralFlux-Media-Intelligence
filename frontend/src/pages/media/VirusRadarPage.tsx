import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useToast } from '../../App';
import AnimatedPage from '../../components/AnimatedPage';
import { usePageHeader } from '../../components/AppLayout';
import VirusRadarWorkspace from '../../components/cockpit/VirusRadarWorkspace';
import {
  useCampaignsPageData,
  useEvidencePageData,
  useNowPageData,
  useRegionsPageData,
  useVirusRadarHeroForecast,
} from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const VirusRadarPage: React.FC = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { setPageHeader, clearPageHeader, exportBriefingPdf, pdfLoading } = usePageHeader();
  const {
    virus,
    setVirus,
    brand,
    weeklyBudget,
    dataVersion,
    openRecommendation,
  } = useMediaWorkflow();
  const [horizonDays] = useState(7);
  const regionsData = useRegionsPageData(virus, brand, dataVersion, toast);
  const heroForecastData = useVirusRadarHeroForecast(brand, dataVersion, toast);
  const preferredHeroRegionCode = useMemo(() => (
    regionsData.regionsView?.map?.activation_suggestions?.[0]?.region
    || regionsData.regionsView?.map?.top_regions?.[0]?.code
    || regionsData.regionsView?.top_regions?.[0]?.code
    || null
  ), [regionsData.regionsView]);
  const nowData = useNowPageData(
    virus,
    brand,
    horizonDays,
    weeklyBudget,
    dataVersion,
    toast,
    preferredHeroRegionCode,
  );
  const campaignsData = useCampaignsPageData(virus, brand, dataVersion, toast);
  const evidenceData = useEvidencePageData(virus, brand, dataVersion, toast);

  useEffect(() => {
    setPageHeader({
      primaryAction: {
        label: pdfLoading ? 'Bericht wird erstellt...' : 'Wochenbericht exportieren',
        onClick: exportBriefingPdf,
        disabled: pdfLoading,
      },
      secondaryAction: {
        label: 'Regionen öffnen',
        to: '/regionen',
      },
    });

    return clearPageHeader;
  }, [clearPageHeader, exportBriefingPdf, navigate, pdfLoading, setPageHeader]);

  return (
    <AnimatedPage>
      <VirusRadarWorkspace
        virus={virus}
        onVirusChange={setVirus}
        horizonDays={horizonDays}
        heroForecastLoading={heroForecastData.loading}
        heroForecast={heroForecastData.heroForecast}
        nowData={nowData}
        regionsData={regionsData}
        campaignsData={campaignsData}
        evidenceData={evidenceData}
        onOpenRecommendation={(id) => openRecommendation(id, 'overlay')}
        onOpenRegions={(regionCode) => navigate('/regionen', { state: regionCode ? { regionCode } : undefined })}
        onOpenCampaigns={() => navigate('/kampagnen')}
        onOpenEvidence={() => navigate('/evidenz')}
      />
    </AnimatedPage>
  );
};

export default VirusRadarPage;
