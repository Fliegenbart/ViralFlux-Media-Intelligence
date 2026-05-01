import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import VirusWaveEvidencePanel from './VirusWaveEvidencePanel';

describe('VirusWaveEvidencePanel', () => {
  it('uses clear evidence-first cockpit language instead of internal labels', () => {
    render(
      <VirusWaveEvidencePanel
        snapshot={{
          virusWaveTruth: {
            status: 'active',
            amelag: { phase: 'rising', confidence: 0.72 },
            survstat: { phase: 'confirmed', confidence: 0.68 },
            alignment: {
              lead_lag_days: -9,
              alignment_score: 0.77,
              divergence_score: 0.12,
            },
            evidence: {
              confidence: 0.7,
              confidence_method: 'heuristic_v1',
              effective_weights: { amelag: 0.6, survstat: 0.4 },
            },
          },
        } as any}
      />,
    );

    expect(screen.getByText('Was wir sehen — und was uns fehlt')).toBeInTheDocument();
    expect(screen.getAllByText(/AMELAG-Frühsignal/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SurvStat-Bestätigung/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Budget-Gates separat/)).toBeInTheDocument();
    expect(screen.getAllByText('AMELAG-Frühsignal').length).toBeGreaterThan(0);
    expect(screen.getAllByText('SurvStat-Bestätigung').length).toBeGreaterThan(0);
    expect(screen.getByText('GELO Sell-Out')).toBeInTheDocument();
    expect(screen.getAllByText('Lebt schon.')).toHaveLength(2);
    expect(screen.getByText(/Wartet auf euch/)).toBeInTheDocument();

    expect(screen.queryByText('Virus Wave Evidence')).not.toBeInTheDocument();
    expect(screen.queryByText('Epidemiologische Evidenz vor Forecast und Budget')).not.toBeInTheDocument();
    expect(screen.queryByText('AMELAG · Early Signal')).not.toBeInTheDocument();
    expect(screen.queryByText('SurvStat · Confirmed Signal')).not.toBeInTheDocument();
    expect(screen.queryByText('nicht bewertet')).not.toBeInTheDocument();
  });
});
