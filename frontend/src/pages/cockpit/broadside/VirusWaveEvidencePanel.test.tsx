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

    expect(screen.getByText('Epidemiologische Beweislage')).toBeInTheDocument();
    expect(screen.getByText(/AMELAG-Frühsignal/)).toBeInTheDocument();
    expect(screen.getByText(/SurvStat-Bestätigung/)).toBeInTheDocument();
    expect(screen.getByText(/Budget diagnostic_only/)).toBeInTheDocument();
    expect(screen.getByText('AMELAG · Frühsignal')).toBeInTheDocument();
    expect(screen.getByText('SurvStat · Bestätigung')).toBeInTheDocument();

    expect(screen.queryByText('Virus Wave Evidence')).not.toBeInTheDocument();
    expect(screen.queryByText('Epidemiologische Evidenz vor Forecast und Budget')).not.toBeInTheDocument();
    expect(screen.queryByText('AMELAG · Early Signal')).not.toBeInTheDocument();
    expect(screen.queryByText('SurvStat · Confirmed Signal')).not.toBeInTheDocument();
  });
});
