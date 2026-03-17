import React, { useState } from 'react';

import { useToast } from '../../App';
import PilotSurface from '../../components/cockpit/PilotSurface';
import { usePilotSurfaceData } from '../../features/media/usePilotSurfaceData';
import { PilotSurfaceScope, PilotSurfaceStageFilter } from '../../types/media';

const PilotPage: React.FC = () => {
  const { toast } = useToast();
  const [virus, setVirus] = useState('RSV A');
  const [horizonDays, setHorizonDays] = useState(7);
  const [scope, setScope] = useState<PilotSurfaceScope>('recommendation');
  const [stage, setStage] = useState<PilotSurfaceStageFilter>('ALL');

  const {
    forecast,
    allocation,
    campaignRecommendations,
    evidence,
    pilotReporting,
    loading,
  } = usePilotSurfaceData(
    {
      brand: 'gelo',
      virus,
      horizonDays,
      weeklyBudget: 120000,
      lookbackWeeks: 26,
    },
    toast,
  );

  return (
    <PilotSurface
      virus={virus}
      onVirusChange={setVirus}
      horizonDays={horizonDays}
      onHorizonChange={setHorizonDays}
      scope={scope}
      onScopeChange={setScope}
      stage={stage}
      onStageChange={setStage}
      weeklyBudget={120000}
      forecast={forecast}
      allocation={allocation}
      campaignRecommendations={campaignRecommendations}
      evidence={evidence}
      pilotReporting={pilotReporting}
      loading={loading}
    />
  );
};

export default PilotPage;
