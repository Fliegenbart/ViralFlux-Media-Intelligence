import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

jest.mock('./cockpitUtils', () => ({
  formatPercent: (value: number, digits = 0) => `${value.toFixed(digits)}%`,
  formatSignalScore: (value: number, digits = 0) => {
    const normalized = value <= 1 ? value * 100 : value;
    return `${normalized.toFixed(digits)}/100`;
  },
  primarySignalScore: (region: { signal_score?: number | null; impact_probability?: number | null }) => (
    region.signal_score ?? region.impact_probability ?? 0
  ),
}));

import GermanyMap from './GermanyMap';

jest.mock('d3-geo', () => ({
  geoMercator: () => ({
    fitSize: () => ({}),
  }),
  geoPath: () => {
    const pathBuilder = () => 'M0,0L10,0L10,10Z';
    pathBuilder.centroid = () => [10, 10];
    return pathBuilder;
  },
}));

describe('GermanyMap', () => {
  it('supports keyboard selection and exposes the state-level legend', () => {
    const onSelectRegion = jest.fn();

    render(
      <GermanyMap
        regions={{
          BE: {
            name: 'Berlin',
            trend: 'steigend',
            change_pct: 12,
            signal_score: 0.82,
            signal_drivers: [{ label: 'ARE', strength_pct: 62 }],
            source_trace: ['RKI', 'Abwasser'],
          } as any,
        }}
        selectedRegion={null}
        onSelectRegion={onSelectRegion}
      />,
    );

    expect(screen.getByLabelText('Legende')).toBeInTheDocument();
    expect(screen.getByText('Stark')).toBeInTheDocument();
    expect(screen.getByText('Keine Evidenz')).toBeInTheDocument();
    const berlinButton = screen.getByRole('button', { name: /Berlin, Bundesland-Level/i });
    fireEvent.keyDown(berlinButton, { key: 'Enter' });

    expect(onSelectRegion).toHaveBeenCalledWith('BE');
  });

  it('renders a calmer radar focus state and only highlights the top signal percentage', () => {
    render(
      <GermanyMap
        variant="radar"
        regions={{
          MV: {
            name: 'Mecklenburg-Vorpommern',
            trend: 'steigend',
            change_pct: 199.1,
            signal_score: 0.55,
            impact_probability: 0.55,
            signal_drivers: [{ label: 'ARE', strength_pct: 62 }],
            source_trace: ['RKI', 'Abwasser'],
          } as any,
          BW: {
            name: 'Baden-Württemberg',
            trend: 'steigend',
            change_pct: 78,
            signal_score: 0.49,
            impact_probability: 0.49,
            signal_drivers: [{ label: 'ARE', strength_pct: 48 }],
            source_trace: ['RKI', 'Abwasser'],
          } as any,
        }}
        selectedRegion={null}
        onSelectRegion={() => undefined}
        showProbability
        topRegionCode="MV"
      />,
    );

    expect(screen.getByLabelText('Kartenfokus')).toHaveTextContent('Stärkstes Signal auf der Karte');
    expect(screen.getByText('Mecklenburg-Vorpommern')).toBeInTheDocument();
    expect(screen.getByText('Top-Region')).toBeInTheDocument();
    expect(screen.getByText('55%')).toBeInTheDocument();
    expect(screen.queryByText('49%')).not.toBeInTheDocument();
  });

  it('labels hovered peix map values as signal score instead of wave probability', () => {
    render(
      <GermanyMap
        regions={{
          BE: {
            name: 'Berlin',
            trend: 'steigend',
            change_pct: 12,
            signal_score: 0.82,
            impact_probability: 0.82,
            signal_drivers: [{ label: 'ARE', strength_pct: 62 }],
            source_trace: ['RKI', 'Abwasser'],
          } as any,
        }}
        selectedRegion={null}
        onSelectRegion={() => undefined}
      />,
    );

    fireEvent.mouseEnter(screen.getByRole('button', { name: /Berlin, Bundesland-Level/i }));

    expect(screen.getByText('82/100 Signalwert')).toBeInTheDocument();
    expect(screen.queryByText(/Wellenwahrscheinlichkeit/i)).not.toBeInTheDocument();
  });
});
