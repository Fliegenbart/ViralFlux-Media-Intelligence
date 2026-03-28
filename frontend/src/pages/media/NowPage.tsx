import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useToast } from '../../App';
import { usePageHeader } from '../../components/AppLayout';
import NowWorkspace from '../../components/cockpit/NowWorkspace';
import { useNowPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const NowPage: React.FC = () => {
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
      contextNote: 'Eine Richtung zuerst. Vertrauen und weitere Optionen direkt darunter.',
      primaryAction: {
        label: pdfLoading ? 'Bericht wird erstellt...' : 'Wochenbericht exportieren',
        onClick: exportWeeklyReport,
        disabled: pdfLoading,
      },
      secondaryAction: {
        label: 'Evidenz öffnen',
        onClick: () => navigate('/evidenz'),
      },
    });

    return clearPageHeader;
  }, [clearPageHeader, exportWeeklyReport, navigate, pdfLoading, setPageHeader]);

  return (
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
  );
};

export default NowPage;
