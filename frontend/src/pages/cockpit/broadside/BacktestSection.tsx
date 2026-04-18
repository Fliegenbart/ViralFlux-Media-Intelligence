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

export const BacktestSection: React.FC<Props> = ({ snapshot }) => {
  const badges: Array<{ label: string; tone: 'go' | 'watch' | 'neutral' | 'solid' | 'ochre' }> = [
    { label: 'Walk-forward', tone: 'neutral' },
    { label: 'Strict vintage', tone: 'neutral' },
    { label: 'Point-in-time', tone: 'ochre' },
  ];

  return (
    <>
      <SectionHeader
        numeral="§ V"
        kicker="Ranking-Validation · die Pitch-Geschichte"
        title={
          <>
            Hatten wir <em>recht</em>?
          </>
        }
        stamp={snapshot.isoWeek}
        badges={badges}
      />
      <div className="ex-section-body">
        <BacktestDrawerBody
          initialVirusTyp={snapshot.virusTyp || 'Influenza B'}
          hideTitle={true}
        />
      </div>
    </>
  );
};

export default BacktestSection;
