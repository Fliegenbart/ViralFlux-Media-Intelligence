import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useToast } from '../../App';
import AnimatedPage from '../../components/AnimatedPage';
import { usePageHeader } from '../../components/AppLayout';
import NowWorkspace from '../../components/cockpit/NowWorkspace';
import { useNowPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const NowPage: React.FC = () => {
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
  const [horizonDays, setHorizonDays] = useState(7);
  const {
    loading,
    workspaceStatus,
    view,
    forecast,
    focusRegionBacktest,
    focusRegionBacktestLoading,
    waveOutlook,
    waveOutlookLoading,
    waveRadar,
    waveRadarLoading,
  } = useNowPageData(virus, brand, horizonDays, weeklyBudget, dataVersion, toast);

  useEffect(() => {
    setPageHeader({
      primaryAction: {
        label: pdfLoading ? 'Bericht wird erstellt...' : 'Wochenbericht exportieren',
        onClick: exportBriefingPdf,
        disabled: pdfLoading,
      },
      secondaryAction: {
        label: 'Zum Virus-Radar',
        onClick: () => navigate('/virus-radar'),
      },
    });

    return clearPageHeader;
  }, [clearPageHeader, exportBriefingPdf, navigate, pdfLoading, setPageHeader]);

  return (
    <AnimatedPage>
    <NowWorkspace
      virus={virus}
      onVirusChange={setVirus}
      horizonDays={horizonDays}
      onHorizonChange={setHorizonDays}
      view={view}
      workspaceStatus={workspaceStatus}
      loading={loading}
      forecast={forecast}
      focusRegionBacktest={focusRegionBacktest}
      focusRegionBacktestLoading={focusRegionBacktestLoading}
      waveOutlook={waveOutlook}
      waveOutlookLoading={waveOutlookLoading}
      waveRadar={waveRadar}
      waveRadarLoading={waveRadarLoading}
      onOpenRecommendation={(id) => openRecommendation(id, 'overlay')}
      onOpenRegions={(regionCode) => navigate('/regionen', { state: regionCode ? { regionCode } : undefined })}
      onOpenCampaigns={() => navigate('/kampagnen')}
      onOpenEvidence={() => navigate('/evidenz')}
    />
    </AnimatedPage>
  );
};

export default NowPage;
