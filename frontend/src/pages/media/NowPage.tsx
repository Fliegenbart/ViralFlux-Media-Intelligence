import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import AnimatedPage from '../../components/AnimatedPage';
import { usePageHeader } from '../../components/AppLayout';
import NowWorkspace from '../../components/cockpit/NowWorkspace';
import { useNowPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';
import { useToast } from '../../lib/appContext';

const NowPage: React.FC = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { setPageHeader, clearPageHeader } = usePageHeader();
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
  const heroRecommendation = view?.heroRecommendation;
  const focusRegionCode = view?.focusRegion?.code || undefined;
  const primaryRecommendationId = view?.primaryRecommendationId || null;

  useEffect(() => {
    const primaryAction = primaryRecommendationId && !heroRecommendation?.ctaDisabled ? {
      label: heroRecommendation?.actionLabel || view?.primaryActionLabel || 'Top-Empfehlung prüfen',
      onClick: () => openRecommendation(primaryRecommendationId, 'overlay'),
    } : focusRegionCode ? {
      label: 'Fokusregion öffnen',
      onClick: () => navigate('/regionen', { state: { regionCode: focusRegionCode } }),
    } : {
      label: 'Kampagnen öffnen',
      onClick: () => navigate('/kampagnen'),
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
    focusRegionCode,
    heroRecommendation?.actionLabel,
    heroRecommendation?.ctaDisabled,
    navigate,
    openRecommendation,
    primaryRecommendationId,
    setPageHeader,
    view?.primaryActionLabel,
  ]);

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
