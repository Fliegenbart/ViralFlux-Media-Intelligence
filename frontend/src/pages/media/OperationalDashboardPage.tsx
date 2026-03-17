import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import OperationalDashboard from '../../components/cockpit/OperationalDashboard';
import { useToast } from '../../App';
import { useOperationalDashboardData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const OperationalDashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { virus, setVirus, weeklyBudget, dataVersion } = useMediaWorkflow();
  const [horizonDays, setHorizonDays] = useState(7);
  const {
    forecast,
    allocation,
    campaignRecommendations,
    loading,
  } = useOperationalDashboardData(virus, horizonDays, weeklyBudget, dataVersion, toast);

  return (
    <OperationalDashboard
      virus={virus}
      onVirusChange={setVirus}
      horizonDays={horizonDays}
      onHorizonChange={setHorizonDays}
      weeklyBudget={weeklyBudget}
      forecast={forecast}
      allocation={allocation}
      campaignRecommendations={campaignRecommendations}
      loading={loading}
      onOpenRegions={(regionCode) => navigate('/regionen', { state: regionCode ? { regionCode } : undefined })}
      onOpenCampaigns={() => navigate('/kampagnen')}
      onOpenEvidence={() => navigate('/evidenz')}
    />
  );
};

export default OperationalDashboardPage;
