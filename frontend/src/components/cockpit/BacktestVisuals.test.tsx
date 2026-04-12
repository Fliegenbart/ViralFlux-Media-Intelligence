import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import {
  FocusRegionOutlookPanel,
  WaveSpreadPanel,
  WaveOutlookPanel,
  buildValidationRows,
  detectWaveMarkers,
  getWaveFreshnessHint,
} from './BacktestVisuals';
import { BacktestResponse } from '../../types/media';

jest.mock('./cockpitUtils', () => ({
  VIRUS_OPTIONS: ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'],
  formatDateShort: (value?: string | null) => {
    if (!value) return '-';
    const iso = String(value).slice(0, 10);
    const [year, month, day] = iso.split('-');
    return `${day}.${month}.${year}`;
  },
  formatDateTime: () => '04.04.2026 · 08:00',
  formatPercent: (value: number) => `${Math.round(value)}%`,
}));

jest.mock('recharts', () => {
  const ReactLib = require('react');

  const passthrough = ({ children }: { children?: React.ReactNode }) => ReactLib.createElement(ReactLib.Fragment, null, children);
  const empty = () => null;

  return {
    ResponsiveContainer: passthrough,
    ComposedChart: passthrough,
    CartesianGrid: empty,
    Legend: empty,
    Line: empty,
    ReferenceArea: empty,
    ReferenceLine: empty,
    Tooltip: empty,
    XAxis: empty,
    YAxis: empty,
    Area: empty,
  };
});

jest.mock('./HistoricalWaveMap', () => ({
  __esModule: true,
  default: ({ onSelectBundesland }: { onSelectBundesland: (bundesland: string) => void }) => (
    <div>
      <button type="button" data-testid="historical-wave-map-BE" onClick={() => onSelectBundesland('Berlin')}>
        HistoricalWaveMap Berlin
      </button>
      <button type="button" data-testid="historical-wave-map-BB" onClick={() => onSelectBundesland('Brandenburg')}>
        HistoricalWaveMap Brandenburg
      </button>
    </div>
  ),
}));

function buildResult(chartData: BacktestResponse['chart_data']): BacktestResponse {
  return {
    virus_typ: 'Influenza A',
    target_source: 'RKI_ARE',
    target_label: 'RKI ARE',
    chart_data: chartData,
  };
}

describe('wave outlook markers', () => {
  it('uses the last observed actual point even when trailing date slots are empty', () => {
    const rows = buildValidationRows(buildResult([
      { date: '2026-01-12', real_qty: 1561, predicted_qty: 1089 },
      { date: '2026-01-19', real_qty: 1613, predicted_qty: 1566 },
      { date: '2026-01-26', real_qty: 1939, predicted_qty: 2006 },
      { date: '2026-02-02', real_qty: 2055, predicted_qty: 2101 },
      { date: '2026-02-09', real_qty: 1894, predicted_qty: 1979 },
      { date: '2026-02-16', real_qty: 1700, predicted_qty: 2197 },
      { date: '2026-02-23', real_qty: 1632, predicted_qty: 2235 },
      { date: '2026-03-02' },
      { date: '2026-03-09' },
      { date: '2026-03-16' },
    ]), 36);

    const markers = detectWaveMarkers(rows);
    const hint = getWaveFreshnessHint(rows, markers, new Date('2026-03-13T00:00:00Z'));

    expect(rows[markers.lastObservedIndex]?.date).toBe('2026-02-23');
    expect(rows[markers.lastValuedIndex]?.date).toBe('2026-02-23');
    expect(rows[markers.peakIndex]?.date).toBe('2026-02-23');
    expect(hint).toContain('23.02.2026');
    expect(markers.narrative).not.toContain('Jetzt');
  });

  it('keeps projected data after the last observation in the peak narrative', () => {
    const rows = buildValidationRows(buildResult([
      { date: '2026-03-03', real_qty: 120, predicted_qty: 118 },
      { date: '2026-03-10', real_qty: 140, predicted_qty: 142 },
      { date: '2026-03-17', forecast_qty: 175, predicted_qty: 176 },
      { date: '2026-03-24', forecast_qty: 210, predicted_qty: 208 },
      { date: '2026-03-31', forecast_qty: 150, predicted_qty: 152 },
    ]), 36);

    const markers = detectWaveMarkers(rows);

    expect(markers.hasProjectedDataAfterObservation).toBe(true);
    expect(rows[markers.lastObservedIndex]?.date).toBe('2026-03-10');
    expect(rows[markers.peakIndex]?.date).toBe('2026-03-24');
    expect(markers.narrative).toContain('letzte beobachtete Stand stammt vom 10.03.2026');
    expect(markers.narrative).toContain('24.03.2026');
  });

  it('explains when only historical values exist and no further filled points are available', () => {
    const rows = buildValidationRows(buildResult([
      { date: '2026-01-12', real_qty: 90 },
      { date: '2026-01-19', real_qty: 110 },
      { date: '2026-01-26', real_qty: 105 },
      { date: '2026-02-02', real_qty: 98 },
      { date: '2026-02-09' },
      { date: '2026-02-16' },
    ]), 36);

    const markers = detectWaveMarkers(rows);

    expect(markers.hasProjectedDataAfterObservation).toBe(false);
    expect(markers.narrative).toContain('02.02.2026');
    expect(markers.narrative).toContain('keine weiteren befüllten Punkte');
  });

  it('returns an empty-state narrative for missing rows', () => {
    const markers = detectWaveMarkers([]);

    expect(markers.lastObservedIndex).toBe(-1);
    expect(markers.narrative).toBe('Noch keine Kurve verfügbar.');
    expect(getWaveFreshnessHint([], markers)).toBeNull();
  });
});

describe('WaveOutlookPanel', () => {
  it('renders the last observed label, chart semantics and freshness hint instead of claiming this is today', () => {
    const result = buildResult([
      { date: '2026-01-12', real_qty: 1561, predicted_qty: 1089 },
      { date: '2026-01-19', real_qty: 1613, predicted_qty: 1566 },
      { date: '2026-01-26', real_qty: 1939, predicted_qty: 2006 },
      { date: '2026-02-02', real_qty: 2055, predicted_qty: 2101 },
      { date: '2026-02-09', real_qty: 1894, predicted_qty: 1979 },
      { date: '2026-02-16', real_qty: 1700, predicted_qty: 2197 },
      { date: '2026-02-23', real_qty: 1632, predicted_qty: 2235 },
      { date: '2026-03-02' },
      { date: '2026-03-09' },
    ]);

    render(
      <WaveOutlookPanel
        virus="Influenza A"
        onVirusChange={() => {}}
        result={result}
        loading={false}
      />,
    );

    expect(screen.getByText('Historischer Markt-Rückblick')).toBeInTheDocument();
    expect(screen.getByText('Letzter Ist-Wert')).toBeInTheDocument();
    expect(screen.getByText('Chart-Konventionen Markt-Rückblick')).toBeInTheDocument();
    expect(screen.getByText('Truth / Ist-Wert')).toBeInTheDocument();
    expect(screen.getByText('Forecast / Ausblick')).toBeInTheDocument();
    expect(screen.getByText('Achsen-Hinweis:')).toBeInTheDocument();
    expect(screen.getByText(/Letzte Beobachtung: 23.02.2026/)).toBeInTheDocument();
    expect(screen.queryByText('Wir stehen hier')).not.toBeInTheDocument();
  });
});

describe('WaveSpreadPanel', () => {
  it('renders the historical start region and spread order', () => {
    render(
      <WaveSpreadPanel
        virus="Influenza A"
        loading={false}
        result={{
          disease: 'Influenza, saisonal',
          season: '2025/2026',
          summary: {
            first_onset: { bundesland: 'Berlin', date: '2025-11-10' },
            last_onset: { bundesland: 'Bayern', date: '2025-12-15' },
            spread_days: 35,
            regions_affected: 12,
            regions_total: 16,
          },
          regions: [
            { bundesland: 'Berlin', wave_start: '2025-11-10', wave_rank: 1 },
            { bundesland: 'Brandenburg', wave_start: '2025-11-17', wave_rank: 2 },
            { bundesland: 'Sachsen', wave_start: '2025-11-24', wave_rank: 3 },
          ],
        }}
      />,
    );

    expect(screen.getByText('Historische Ausbreitungsreihenfolge')).toBeInTheDocument();
    expect(screen.getByText(/Berlin war in der letzten verfügbaren Saison der erste sichtbare Startpunkt/)).toBeInTheDocument();
    expect(screen.getByText('Saison 2025/2026')).toBeInTheDocument();
    expect(screen.getByText('Brandenburg')).toBeInTheDocument();
    expect(screen.getByText('7 Tage nach dem ersten Start sichtbar geworden.')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('historical-wave-map-BB'));

    expect(screen.getByText('Ausgewählte Region')).toBeInTheDocument();
    expect(screen.getByText(/Brandenburg lag in dieser Saison auf Rang 2 der sichtbaren Ausbreitung/)).toBeInTheDocument();
  });
});

describe('FocusRegionOutlookPanel', () => {
  it('renders the focus-region headline with forecast semantics, labels and target sentence', () => {
    render(
      <FocusRegionOutlookPanel
        horizonDays={7}
        loading={false}
        prediction={{
          bundesland: 'BE',
          bundesland_name: 'Berlin',
          virus_typ: 'Influenza A',
          as_of_date: '2026-03-18 00:00:00',
          target_date: '2026-03-25',
          target_week_start: '2026-03-23',
          target_window_days: [7],
          horizon_days: 7,
          event_probability: 0.81,
          expected_target_incidence: 165,
          current_known_incidence: 110,
          prediction_interval: { lower: 150, upper: 185 },
          change_pct: 18,
          trend: 'up',
          last_data_date: '2026-03-17 00:00:00',
          quality_gate: { overall_passed: true, calibration_passed: false },
          source_coverage: { sample_coverage_pct: 0.72 },
        }}
        backtest={{
          bundesland: 'BE',
          bundesland_name: 'Berlin',
          timeline: [
            {
              bundesland: 'BE',
              bundesland_name: 'Berlin',
              as_of_date: '2026-03-10T00:00:00',
              target_date: '2026-03-17T00:00:00',
              horizon_days: 7,
              current_known_incidence: 110,
              expected_target_incidence: 121,
            },
          ],
        }}
      />,
    );

    expect(screen.getByText('Forecast zur Fokusregion')).toBeInTheDocument();
    expect(screen.getByText('Chart-Konventionen Forecast')).toBeInTheDocument();
    expect(screen.getByText('Truth / Ist-Wert')).toBeInTheDocument();
    expect(screen.getByText('Unsicherheitsintervall')).toBeInTheDocument();
    expect(screen.getByText('Quality Gate')).toBeInTheDocument();
    expect(screen.getByText('Kalibrierung')).toBeInTheDocument();
    expect(screen.getByText('Sample Coverage')).toBeInTheDocument();
    expect(screen.getByText('Bundesland-Level')).toBeInTheDocument();
    expect(screen.getByText(/Kein\s+Signal-Score/)).toBeInTheDocument();
    expect(screen.getByText(/In 7 Tagen erwarten wir für Berlin einen Viruslage-Wert von ca. 165,0/)).toBeInTheDocument();
    expect(screen.getByText(/Letzter bestätigter Ist-Wert vom 17.03.2026/)).toBeInTheDocument();
    expect(screen.getByText(/Die Richtung ist/)).toBeInTheDocument();
  });

  it('renders a restrained empty state when no forecast data is available', () => {
    render(
      <FocusRegionOutlookPanel
        horizonDays={7}
        loading={false}
        prediction={null}
        backtest={null}
      />,
    );

    expect(screen.getByText('Noch kein aktiver Forecast oder regionaler Rückblick für dieses Bundesland verfügbar.')).toBeInTheDocument();
  });
});
