import React, { useState } from 'react';

import { useToast } from '../../App';
import PilotSurface from '../../components/cockpit/PilotSurface';
import { usePilotSurfaceData } from '../../features/media/usePilotSurfaceData';
import { PilotSurfaceScope, PilotSurfaceStageFilter } from '../../types/media';

const PilotPage: React.FC = () => {
  const { toast } = useToast();
  const [virus, setVirus] = useState('RSV A');
  const [horizonDays, setHorizonDays] = useState(7);
  const [scope, setScope] = useState<PilotSurfaceScope>('forecast');
  const [stage, setStage] = useState<PilotSurfaceStageFilter>('ALL');

  const {
    pilotReadout,
    loading,
  } = usePilotSurfaceData(
    {
      brand: 'gelo',
      virus,
      horizonDays,
      weeklyBudget: 120000,
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
      pilotReadout={pilotReadout}
      loading={loading}
    />
  );
};

export default PilotPage;
