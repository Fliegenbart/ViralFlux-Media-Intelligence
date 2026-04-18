import React from 'react';
import type { CockpitSnapshot } from '../types';
import SectionHeader from './SectionHeader';
import { ImpactDrawerBody } from '../exhibit/ImpactDrawer';

/**
 * § IV — Wirkung & Feedback-Loop.
 *
 * Recent weeks roster + pipeline status + three monuments. Reuses the
 * drawer body unchanged; the broadside just wraps it with its own
 * section header.
 */

interface Props {
  snapshot: CockpitSnapshot;
}

export const ImpactSection: React.FC<Props> = ({ snapshot }) => {
  const mediaConnected = snapshot.mediaPlan?.connected === true;
  const badges: Array<{ label: string; tone: 'go' | 'watch' | 'neutral' | 'solid' | 'ochre' }> = [
    {
      label: mediaConnected ? 'Plan verbunden' : 'Plan fehlt',
      tone: mediaConnected ? 'go' : 'watch',
    },
    { label: 'Honest-by-default', tone: 'neutral' },
  ];

  return (
    <>
      <SectionHeader
        numeral="§ IV"
        kicker="Outcome-Loop · was wurde empfohlen, was geschah"
        title={
          <>
            <em>Wirkung</em> &amp; Rückkopplung
          </>
        }
        stamp={snapshot.isoWeek}
        badges={badges}
      />
      <div className="ex-section-body">
        <ImpactDrawerBody snapshot={snapshot} />
      </div>
    </>
  );
};

export default ImpactSection;
