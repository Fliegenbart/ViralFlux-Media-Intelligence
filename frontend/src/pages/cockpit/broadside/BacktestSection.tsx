import React from 'react';
import type { CockpitSnapshot } from '../types';
import SectionHeader from './SectionHeader';
import { BacktestDrawerBody } from '../exhibit/BacktestDrawer';

/**
 * § V — Backtest.
 *
 * The pitch-story artifact. Virus switch + monument + comparison +
 * methodology stanza + per-BL roster + weekly hit barcode. Renders
 * the existing BacktestDrawerBody — no drawer chrome.
 *
 * hideTitle=true because the broadside's SectionHeader already carries
 * the §-numeral and title — no need to repeat the drawer's internal
 * title block.
 */

interface Props {
  snapshot: CockpitSnapshot;
}

export const BacktestSection: React.FC<Props> = ({ snapshot }) => (
  <>
    <SectionHeader
      numeral="§ V"
      kicker="Walk-forward · point-in-time · strict vintage"
      title={
        <>
          In wie vielen Wochen hatten wir <em>recht</em>?
        </>
      }
      stamp={snapshot.isoWeek}
    />
    <div className="ex-section-body">
      <BacktestDrawerBody
        initialVirusTyp={snapshot.virusTyp || 'Influenza B'}
        hideTitle={true}
      />
    </div>
  </>
);

export default BacktestSection;
