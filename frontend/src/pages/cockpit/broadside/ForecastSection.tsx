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

export const ForecastSection: React.FC<Props> = ({ snapshot }) => {
  const cov80 = snapshot.modelStatus?.intervalCoverage80Pct ?? null;
  const bestLag = snapshot.modelStatus?.lead?.bestLagDays ?? null;
  const calibrationMode = snapshot.modelStatus?.calibrationMode;
  const horizonDays = snapshot.modelStatus?.horizonDays ?? 14;

  const badges: Array<{ label: string; tone: 'go' | 'watch' | 'neutral' | 'solid' | 'ochre' }> = [
    { label: `Q10–Q90 · ${horizonDays}d`, tone: 'neutral' },
    {
      label:
        calibrationMode === 'calibrated'
          ? 'Kalibriert'
          : calibrationMode === 'heuristic'
            ? 'Heuristisch'
            : 'Ungemessen',
      tone: calibrationMode === 'calibrated' ? 'go' : 'watch',
    },
  ];
  if (bestLag !== null) {
    badges.push({
      label: bestLag >= 0 ? `+${bestLag} d Lead` : `${bestLag} d Lag`,
      tone: bestLag >= 0 ? 'go' : 'watch',
    });
  }
  if (cov80 !== null) {
    badges.push({
      label: `Coverage ${cov80.toFixed(0)} %`,
      tone: Math.abs(cov80 - 80) <= 5 ? 'go' : 'watch',
    });
  }

  return (
    <>
      <SectionHeader
        numeral="§ III"
        kicker="Fan-Chart · Beobachtung trifft Prognose"
        title={
          <>
            Die <em>Forecast-Zeitreise</em>
          </>
        }
        stamp={snapshot.isoWeek}
        badges={badges}
      />
      <div className="ex-section-body">
        <ForecastDrawerBody snapshot={snapshot} />
      </div>
    </>
  );
};

export default ForecastSection;
