import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

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

    expect(screen.getByLabelText('Legende Bundeslandkarte')).toBeInTheDocument();
    expect(screen.getByText('Orientierungskarte Bundesland-Level')).toBeInTheDocument();
    expect(screen.getByText('Bundesland-Level. Kein City-Forecast. Die Flächenfarbe hilft bei Auswahl und Orientierung, ersetzt aber nicht die eigentliche Regionsentscheidung.')).toBeInTheDocument();

    const berlinButton = screen.getByRole('button', { name: /Berlin, Bundesland-Level/i });
    fireEvent.keyDown(berlinButton, { key: 'Enter' });

    expect(onSelectRegion).toHaveBeenCalledWith('BE');
  });
});
