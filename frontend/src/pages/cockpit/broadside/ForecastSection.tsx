import React from 'react';
import type { CockpitSnapshot } from '../types';
import SectionHeader from './SectionHeader';
import { ForecastDrawerBody } from '../exhibit/ForecastDrawer';

/**
 * § III — Forecast-Zeitreise.
 *
 * Scientific-atlas plate on paper: observed → HEUTE → forecast, with
 * three footer panels (Lesart / Lag-Rail / Kalibrierungs-Thermometer).
 *
 * The actual plate is exported as ForecastDrawerBody from the original
 * drawer module (the drawer wrapper is bypassed for the broadside).
 */

interface Props {
  snapshot: CockpitSnapshot;
}

export const ForecastSection: React.FC<Props> = ({ snapshot }) => (
  <>
    <SectionHeader
      numeral="§ III"
      kicker="Fan-Chart · Q10 / Q50 / Q90 · Notaufnahme-Spur"
      title={
        <>
          Die <em>Forecast-Zeitreise</em>.
        </>
      }
      stamp={snapshot.isoWeek}
    />
    <div className="ex-section-body">
      <ForecastDrawerBody snapshot={snapshot} />
    </div>
  </>
);

export default ForecastSection;
