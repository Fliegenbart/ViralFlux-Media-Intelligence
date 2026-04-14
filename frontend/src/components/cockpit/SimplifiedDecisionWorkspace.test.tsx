import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import SimplifiedDecisionWorkspace from './SimplifiedDecisionWorkspace';

jest.mock('./cockpitUtils', () => ({
  __esModule: true,
  formatDateTime: (value?: string | null) => value || '-',
}));

jest.mock('./BacktestVisuals', () => ({
  __esModule: true,
  FocusRegionOutlookPanel: ({ title, subtitle }: { title?: string; subtitle?: string }) => (
    <div>
      <div>{title || 'Verlauf bisher und Prognose'}</div>
      {subtitle ? <div>{subtitle}</div> : null}
    </div>
  ),
}));

describe('SimplifiedDecisionWorkspace', () => {
  it('renders one answer, one graph, three facts, and collapsed details', () => {
    const onPrimaryAction = jest.fn();

    const { container } = render(
      <SimplifiedDecisionWorkspace
        view={{
          hasData: true,
          generatedAt: '2026-04-14T08:00:00Z',
          title: 'Decision',
          summary: 'Sachsen zeigt aktuell die staerkste Dynamik.',
          note: '',
          proof: null,
          primaryActionLabel: 'Empfehlung pruefen',
          primaryRecommendationId: 'rec-1',
          heroRecommendation: {
            headline: 'Budget erhoehen',
            actionLabel: 'Empfehlung pruefen',
            direction: 'Budget erhoehen',
            region: 'Sachsen',
            regionCode: 'SN',
            context: 'Influenza A',
            whyNow: 'Der Verlauf steigt und die Prognose zeigt weiter nach oben.',
            state: 'strong',
            stateLabel: 'Bereit fuer Review',
            actionHint: null,
            ctaDisabled: false,
          },
          secondaryMoves: [
            { code: 'HH', name: 'Hamburg', stage: 'Beobachten', probabilityLabel: '38%', reason: 'Noch nicht stark genug.' },
          ],
          briefingTrust: {
            summary: 'Forecast und Datenlage tragen die Empfehlung.',
            items: [
              { key: 'reliability', label: 'Belastbarkeit', value: 'Mittel', detail: 'Die Prognose ist brauchbar.', tone: 'warning' },
            ],
          },
          supportState: { stale: false, label: null, detail: null },
          primaryCampaignTitle: '',
          primaryCampaignContext: '',
          primaryCampaignCopy: '',
          focusRegion: {
            code: 'SN',
            name: 'Sachsen',
            stage: 'Aktivieren',
            reason: 'Die Dynamik ist am staerksten.',
            product: 'GELO',
            probabilityLabel: '81%',
            budgetLabel: '55.000 EUR',
            recommendationId: 'rec-1',
          },
          metrics: [],
          trustChecks: [],
          reasons: ['Sachsen fuehrt Forecast und Signal an.'],
          risks: ['Kundendaten sind noch im Aufbau.'],
          quality: [],
          relatedRegions: [],
          emptyState: null,
        } as any}
        forecast={{
          predictions: [
            {
              bundesland: 'SN',
              bundesland_name: 'Sachsen',
              event_probability: 0.81,
              change_pct: 12.4,
              trend: 'steigend',
            },
          ],
        } as any}
        focusRegionBacktest={null}
        focusRegionBacktestLoading={false}
        horizonDays={9}
        primaryActionLabel="Empfehlung pruefen"
        onPrimaryAction={onPrimaryAction}
      />,
    );

    expect(container.firstElementChild).toHaveClass('decision-home');
    expect(screen.getByText('Diese Woche Budget in Sachsen erhoehen.')).toBeInTheDocument();
    expect(screen.getByText('Verlauf bisher und Prognose')).toBeInTheDocument();
    expect(screen.getByText('Links siehst du den bisherigen Verlauf, rechts die naechsten 7 Tage.')).toBeInTheDocument();
    expect(screen.getByText('Region')).toBeInTheDocument();
    expect(screen.getByText('Trend')).toBeInTheDocument();
    expect(screen.getByText('Vertrauen')).toBeInTheDocument();
    expect(screen.getByText('Datenstand 2026-04-14T08:00:00Z')).toBeInTheDocument();
    expect(screen.queryByText('Sachsen fuehrt Forecast und Signal an.')).not.toBeInTheDocument();

    expect(screen.getByText('Diese Woche Budget in Sachsen erhoehen.').closest('.decision-home__hero--go')?.className)
      .toBe('decision-home__hero decision-home__hero--go');
    expect(screen.getByLabelText('Kernfakten').className).toBe('decision-home__facts');

    fireEvent.click(screen.getByRole('button', { name: /Warum glauben wir das/i }));
    expect(screen.getByText('Sachsen fuehrt Forecast und Signal an.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Empfehlung pruefen' }));
    expect(onPrimaryAction).toHaveBeenCalledTimes(1);
  });

  it('keeps the fallback action clickable when the live recommendation is blocked', () => {
    const onPrimaryAction = jest.fn();

    render(
      <SimplifiedDecisionWorkspace
        view={{
          hasData: true,
          generatedAt: '2026-04-14T08:00:00Z',
          title: 'Decision',
          summary: 'Berlin bleibt ein Beobachtungsfall.',
          note: '',
          proof: null,
          primaryActionLabel: 'Empfehlung pruefen',
          primaryRecommendationId: null,
          heroRecommendation: {
            headline: 'Beobachten',
            actionLabel: 'Empfehlung pruefen',
            direction: 'Beobachten',
            region: 'Berlin',
            regionCode: 'BE',
            context: 'Influenza A',
            whyNow: 'Es gibt erste Signale, aber noch keine Freigabe.',
            state: 'guarded',
            stateLabel: 'Pruefen',
            actionHint: null,
            ctaDisabled: true,
          },
          secondaryMoves: [],
          briefingTrust: {
            summary: 'Noch vorsichtig.',
            items: [],
          },
          supportState: { stale: false, label: null, detail: null },
          primaryCampaignTitle: '',
          primaryCampaignContext: '',
          primaryCampaignCopy: '',
          focusRegion: {
            code: 'BE',
            name: 'Berlin',
            stage: 'Beobachten',
            reason: 'Noch zu frueh.',
            product: 'GELO',
            probabilityLabel: '44%',
            budgetLabel: '20.000 EUR',
            recommendationId: null,
          },
          metrics: [],
          trustChecks: [],
          reasons: [],
          risks: [],
          quality: [],
          relatedRegions: [],
          emptyState: null,
        } as any}
        forecast={null}
        focusRegionBacktest={null}
        focusRegionBacktestLoading={false}
        horizonDays={7}
        primaryActionLabel="Details ansehen"
        onPrimaryAction={onPrimaryAction}
      />,
    );

    const fallbackButton = screen.getByRole('button', { name: 'Details ansehen' });
    expect(fallbackButton).toBeEnabled();

    fireEvent.click(fallbackButton);
    expect(onPrimaryAction).toHaveBeenCalledTimes(1);
  });

  it('shows the honest empty state instead of a fabricated recommendation', () => {
    render(
      <SimplifiedDecisionWorkspace
        view={{
          hasData: false,
          generatedAt: '2026-04-14T08:00:00Z',
          title: 'Decision',
          summary: '',
          note: '',
          proof: null,
          primaryActionLabel: 'Empfehlung pruefen',
          primaryRecommendationId: null,
          heroRecommendation: null,
          secondaryMoves: [],
          briefingTrust: {
            summary: '',
            items: [],
          },
          supportState: { stale: false, label: null, detail: null },
          primaryCampaignTitle: '',
          primaryCampaignContext: '',
          primaryCampaignCopy: '',
          focusRegion: null,
          metrics: [],
          trustChecks: [],
          reasons: [],
          risks: [],
          quality: [],
          relatedRegions: [],
          emptyState: {
            title: 'Für diesen Scope ist noch kein regionales Modell verfügbar.',
            body: 'Wechsle Virus oder Zeitraum oder prüfe die Qualität.',
          },
        } as any}
        forecast={null}
        focusRegionBacktest={null}
        focusRegionBacktestLoading={false}
        horizonDays={7}
        primaryActionLabel="Details ansehen"
        onPrimaryAction={jest.fn()}
      />,
    );

    expect(screen.getByText('Für diesen Scope ist noch kein regionales Modell verfügbar.')).toBeInTheDocument();
    expect(screen.getByText('Wechsle Virus oder Zeitraum oder prüfe die Qualität.')).toBeInTheDocument();
    expect(screen.queryByText('Diese Woche dieser Region weiter beobachten.')).not.toBeInTheDocument();
  });
});
