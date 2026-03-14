import React from 'react';
import { useNavigate } from 'react-router-dom';

import DecisionView from '../../components/cockpit/DecisionView';
import { useToast } from '../../App';
import { useDecisionPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const DecisionPage: React.FC = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { virus, setVirus, brand, dataVersion, openRecommendation } = useMediaWorkflow();
  const {
    decision,
    decisionEvidence,
    decisionLoading,
    waveOutlook,
    waveOutlookLoading,
    regionalBenchmark,
    regionalPortfolio,
    regionalPortfolioLoading,
  } = useDecisionPageData(virus, brand, dataVersion, toast);

  return (
    <DecisionView
      virus={virus}
      onVirusChange={setVirus}
      decision={decision}
      evidence={decisionEvidence}
      loading={decisionLoading}
      waveOutlook={waveOutlook}
      waveOutlookLoading={waveOutlookLoading}
      regionalBenchmark={regionalBenchmark}
      regionalPortfolio={regionalPortfolio}
      regionalPortfolioLoading={regionalPortfolioLoading}
      onOpenRecommendation={(id) => openRecommendation(id, 'overlay')}
      onOpenRegions={() => navigate('/regionen')}
      onOpenCampaigns={() => navigate('/kampagnen')}
      onFocusPortfolioOpportunity={(nextVirus, regionCode) => {
        setVirus(nextVirus);
        navigate('/regionen', { state: { regionCode } });
      }}
    />
  );
};

export default DecisionPage;
