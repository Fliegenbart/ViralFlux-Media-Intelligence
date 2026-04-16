import React, { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import '../../styles/peix.css';

import Masthead from '../../components/cockpit/peix/Masthead';
import CockpitTabs, { type TabId } from '../../components/cockpit/peix/CockpitTabs';
import DecisionPage from './DecisionPage';
import AtlasPage from './AtlasPage';
import TimelinePage from './TimelinePage';
import { useCockpitSnapshot } from './useCockpitSnapshot';

/**
 * Self-contained shell that bypasses the existing MediaShell/AppLayout.
 * This is deliberate: the cockpit needs its own editorial chrome.
 *
 * Mounted at route /cockpit (see App.tsx diff in docs/README_peix.md).
 */
export const CockpitShell: React.FC = () => {
  const { snapshot, loading } = useCockpitSnapshot();
  const [tab, setTab] = useState<TabId>('decision');

  if (loading || !snapshot) {
    return (
      <div className="peix">
        <div className="peix-shell" style={{ padding: 80, textAlign: 'center' }}>
          <span className="peix-kicker">loading cockpit…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="peix">
      <div className="peix-shell">
        <Masthead
          client={snapshot.client}
          virusLabel={snapshot.virusLabel}
          isoWeek={snapshot.isoWeek}
          generatedAt={snapshot.generatedAt}
        />
        <CockpitTabs active={tab} onChange={setTab} />

        <AnimatePresence mode="wait">
          {tab === 'decision' && <DecisionPage key="decision" snapshot={snapshot} />}
          {tab === 'atlas'    && <AtlasPage    key="atlas"    snapshot={snapshot} />}
          {tab === 'timeline' && <TimelinePage key="timeline" snapshot={snapshot} />}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default CockpitShell;
