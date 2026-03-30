import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import RegionMap, { RegionMapRegion } from './RegionMap';

const ALL_REGIONS: RegionMapRegion[] = [
  { region_id: 'DE-SH', region_name: 'Schleswig-Holstein', decision_stage: 'watch', signal_score: 0.12 },
  { region_id: 'DE-HH', region_name: 'Hamburg', decision_stage: 'watch', signal_score: 0.15 },
  { region_id: 'DE-MV', region_name: 'Mecklenburg-Vorpommern', decision_stage: 'prepare', signal_score: 0.51 },
  { region_id: 'DE-HB', region_name: 'Bremen', decision_stage: 'watch', signal_score: 0.19 },
  { region_id: 'DE-NI', region_name: 'Niedersachsen', decision_stage: 'prepare', signal_score: 0.48 },
  { region_id: 'DE-BB', region_name: 'Brandenburg', decision_stage: 'watch', signal_score: 0.23 },
  { region_id: 'DE-BE', region_name: 'Berlin', decision_stage: 'activate', signal_score: 0.84 },
  { region_id: 'DE-ST', region_name: 'Sachsen-Anhalt', decision_stage: 'watch', signal_score: 0.27 },
  { region_id: 'DE-NW', region_name: 'Nordrhein-Westfalen', decision_stage: 'activate', signal_score: 0.72 },
  { region_id: 'DE-HE', region_name: 'Hessen', decision_stage: 'prepare', signal_score: 0.53 },
  { region_id: 'DE-TH', region_name: 'Thüringen', decision_stage: 'watch', signal_score: 0.24 },
  { region_id: 'DE-SN', region_name: 'Sachsen', decision_stage: 'prepare', signal_score: 0.49 },
  { region_id: 'DE-RP', region_name: 'Rheinland-Pfalz', decision_stage: 'watch', signal_score: 0.18 },
  { region_id: 'DE-SL', region_name: 'Saarland', decision_stage: 'watch', signal_score: 0.11 },
  { region_id: 'DE-BW', region_name: 'Baden-Württemberg', decision_stage: 'prepare', signal_score: 0.55 },
  { region_id: 'DE-BY', region_name: 'Bayern', decision_stage: 'watch', signal_score: 0.31 },
];

describe('RegionMap', () => {
  it('renders all 16 Bundesländer as interactive paths', () => {
    render(
      <RegionMap
        regions={ALL_REGIONS}
        selectedRegion={null}
        onRegionClick={() => {}}
      />,
    );

    expect(screen.getByRole('img', { name: 'Deutschlandkarte mit Bundesländern' })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(16);
  });

  it('fires onRegionClick with the correct region_id', () => {
    const onRegionClick = jest.fn();

    render(
      <RegionMap
        regions={ALL_REGIONS}
        selectedRegion={null}
        onRegionClick={onRegionClick}
      />,
    );

    fireEvent.click(screen.getByTestId('region-map-DE-BE'));

    expect(onRegionClick).toHaveBeenCalledWith('DE-BE');
  });

  it('assigns the correct stage colors to activate, prepare and watch', () => {
    render(
      <RegionMap
        regions={ALL_REGIONS}
        selectedRegion="DE-BE"
        onRegionClick={() => {}}
      />,
    );

    expect(screen.getByTestId('region-map-DE-BE')).toHaveAttribute('fill', 'rgba(220, 38, 38, 0.15)');
    expect(screen.getByTestId('region-map-DE-MV')).toHaveAttribute('fill', 'rgba(217, 119, 6, 0.12)');
    expect(screen.getByTestId('region-map-DE-SH')).toHaveAttribute('fill', 'rgba(5, 150, 105, 0.08)');
  });
});
