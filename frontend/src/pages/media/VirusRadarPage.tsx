import React, { useCallback, useEffect, useState } from 'react';

import { useToast } from '../../App';
import AnimatedPage from '../../components/AnimatedPage';
import { usePageHeader } from '../../components/AppLayout';
import SimplifiedDecisionWorkspace from '../../components/cockpit/SimplifiedDecisionWorkspace';
import { useNowPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const VirusRadarPage: React.FC = () => {
  const { toast } = useToast();
  const { clearPageHeader } = usePageHeader();
  const {
    virus,
    brand,
    weeklyBudget,
    dataVersion,
    openRecommendation,
  } = useMediaWorkflow();
  const [horizonDays] = useState(7);
  const nowData = useNowPageData(virus, brand, horizonDays, weeklyBudget, dataVersion, toast);
  const liveRecommendationId = nowData.view.primaryRecommendationId;
  const canOpenLiveRecommendation = Boolean(liveRecommendationId && !nowData.view.heroRecommendation?.ctaDisabled);
  const primaryActionLabel = canOpenLiveRecommendation
    ? nowData.view.heroRecommendation?.actionLabel || 'Empfehlung pruefen'
    : 'Details ansehen';

  const handlePrimaryAction = useCallback(async () => {
    if (canOpenLiveRecommendation && liveRecommendationId) {
      openRecommendation(liveRecommendationId, 'overlay');
      return;
    }

    document.getElementById('main-content')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [canOpenLiveRecommendation, liveRecommendationId, openRecommendation]);

  useEffect(() => {
    clearPageHeader();
    return clearPageHeader;
  }, [clearPageHeader]);

  return (
    <AnimatedPage>
      <SimplifiedDecisionWorkspace
        view={nowData.view}
        forecast={nowData.forecast}
        focusRegionBacktest={nowData.focusRegionBacktest}
        focusRegionBacktestLoading={nowData.focusRegionBacktestLoading}
        horizonDays={horizonDays}
        primaryActionLabel={primaryActionLabel}
        onPrimaryAction={handlePrimaryAction}
      />
    </AnimatedPage>
  );
};

export default VirusRadarPage;
