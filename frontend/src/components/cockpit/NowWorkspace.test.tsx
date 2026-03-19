import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import NowWorkspace from './NowWorkspace';
import { NowPageViewModel } from '../../features/media/useMediaData';

const noop = () => {};

function buildView(): NowPageViewModel {
  return {
    hasData: true,
    generatedAt: '2026-03-18T08:00:00Z',
    title: 'Aktivieren: Berlin',
    summary: 'Berlin ist diese Woche der klarste nächste Schritt.',
    note: 'Die nächste sinnvolle Aktion steht oben. Qualität und Risiken folgen darunter.',
    primaryActionLabel: 'Nächste Kampagne öffnen',
    primaryRecommendationId: 'rec-1',
    primaryCampaignTitle: 'Respiratory Core Demand',
    primaryCampaignContext: 'Berlin · Zu prüfen',
    primaryCampaignCopy: 'Die Kampagne ist der direkteste prüfbare nächste Schritt.',
    focusRegion: {
      code: 'BE',
      name: 'Berlin',
      stage: 'Aktivieren',
      reason: 'Berlin bündelt das stärkste Signal aus Forecast und Kontext.',
      product: 'GeloMyrtol forte',
      probabilityLabel: '81.0%',
      budgetLabel: '55.200 €',
      recommendationId: 'rec-1',
    },
    metrics: [
      { label: 'Freigabe', value: 'Freigeben', tone: 'success' },
      { label: 'Event-Wahrscheinlichkeit', value: '81.0%', tone: 'success' },
      { label: 'Empfohlenes Budget', value: '55.200 €', tone: 'neutral' },
      { label: 'Vertrauen', value: 'im Aufbau', tone: 'warning' },
    ],
    reasons: [
      'Das Signal liegt klar über der Aktivierungsschwelle.',
      'Die Fokusregion zeigt die stärkste Dynamik.',
    ],
    risks: [
      'Die Revision der Quelldaten bleibt sichtbar.',
    ],
    quality: [
      { label: 'Quellen aktuell', value: '6/7' },
      { label: 'Kundendaten', value: 'im Aufbau' },
      { label: 'Business-Gate', value: 'Holdout bereit' },
      { label: 'Evidenz', value: 'observational' },
    ],
    relatedRegions: [
      {
        code: 'BY',
        name: 'Bayern',
        stage: 'Vorbereiten',
        probabilityLabel: '54.0%',
        reason: 'Bayern ist der nächste sinnvolle Prüfpfad.',
      },
    ],
    emptyState: null,
  };
}

describe('NowWorkspace', () => {
  it('shows a focused hero with four metrics and quality follow-up', () => {
    render(
      <NowWorkspace
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        onHorizonChange={noop}
        view={buildView()}
        loading={false}
        onOpenRecommendation={noop}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    expect(screen.getByText('Klare Lage. Klare nächste Aktion.')).toBeInTheDocument();
    expect(screen.getByText('Aktivieren: Berlin')).toBeInTheDocument();
    expect(screen.getByText('Warum vertrauen wir dem?')).toBeInTheDocument();
    expect(screen.getByText('Qualität & Vertrauen')).toBeInTheDocument();
    expect(screen.getByText('Weitere Regionen')).toBeInTheDocument();
    expect(screen.getAllByTestId('now-metric')).toHaveLength(4);
  });

  it('opens the primary recommendation from the hero action', () => {
    const onOpenRecommendation = jest.fn();

    render(
      <NowWorkspace
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        onHorizonChange={noop}
        view={buildView()}
        loading={false}
        onOpenRecommendation={onOpenRecommendation}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Nächste Kampagne öffnen' }));

    expect(onOpenRecommendation).toHaveBeenCalledWith('rec-1');
  });
});
