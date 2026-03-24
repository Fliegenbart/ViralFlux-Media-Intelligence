import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useToast } from '../../App';
import NowWorkspace from '../../components/cockpit/NowWorkspace';
import { useNowPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const NowPage: React.FC = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
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
  } = useNowPageData(virus, brand, horizonDays, weeklyBudget, dataVersion, toast);

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
      onOpenRecommendation={(id) => openRecommendation(id, 'overlay')}
      onOpenRegions={(regionCode) => navigate('/regionen', { state: regionCode ? { regionCode } : undefined })}
      onOpenCampaigns={() => navigate('/kampagnen')}
      onOpenEvidence={() => navigate('/evidenz')}
    />
  );
};

export default NowPage;
