import React, { useEffect, useState } from 'react';
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
} from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const VirusRadarPage: React.FC = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { setPageHeader, clearPageHeader, exportWeeklyReport, pdfLoading } = usePageHeader();
  const {
    virus,
    setVirus,
    brand,
    weeklyBudget,
    dataVersion,
    openRecommendation,
  } = useMediaWorkflow();
  const [horizonDays] = useState(7);
  const nowData = useNowPageData(virus, brand, horizonDays, weeklyBudget, dataVersion, toast);
  const regionsData = useRegionsPageData(virus, brand, dataVersion, toast);
  const campaignsData = useCampaignsPageData(virus, brand, dataVersion, toast);
  const evidenceData = useEvidencePageData(virus, brand, dataVersion, toast);

  useEffect(() => {
    setPageHeader({
      primaryAction: {
        label: pdfLoading ? 'Bericht wird erstellt...' : 'Wochenbericht exportieren',
        onClick: exportWeeklyReport,
        disabled: pdfLoading,
      },
      secondaryAction: {
        label: 'Kampagnen öffnen',
        onClick: () => navigate('/kampagnen'),
      },
    });

    return clearPageHeader;
  }, [clearPageHeader, exportWeeklyReport, navigate, pdfLoading, setPageHeader]);

  return (
    <AnimatedPage>
      <VirusRadarWorkspace
        virus={virus}
        onVirusChange={setVirus}
        horizonDays={horizonDays}
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
