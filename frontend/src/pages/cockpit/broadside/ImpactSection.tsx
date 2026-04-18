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

export const ImpactSection: React.FC<Props> = ({ snapshot }) => (
  <>
    <SectionHeader
      numeral="§ IV"
      kicker="Outcome-Loop · Honest-by-default"
      title={
        <>
          <em>Wirkung</em> &amp; Rückkopplung.
        </>
      }
      stamp={snapshot.isoWeek}
    />
    <div className="ex-section-body">
      <ImpactDrawerBody snapshot={snapshot} />
    </div>
  </>
);

export default ImpactSection;
