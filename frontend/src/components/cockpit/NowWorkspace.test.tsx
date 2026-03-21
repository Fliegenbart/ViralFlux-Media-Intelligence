import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import NowWorkspace from './NowWorkspace';
import { NowPageViewModel } from '../../features/media/useMediaData';
import { WorkspaceStatusSummary } from '../../types/media';

const noop = () => {};

function buildView(): NowPageViewModel {
  return {
    hasData: true,
    generatedAt: '2026-03-18T08:00:00Z',
    title: 'Aktivieren: Berlin',
    summary: 'Berlin ist diese Woche der klarste nächste Schritt.',
    note: 'Die nächste sinnvolle Aktion steht oben. Qualität und Risiken folgen darunter.',
    proof: {
      headline: 'Wir sehen im 7-Tage-Fenster das früheste relevante Signal aktuell in Berlin.',
      supportingText: 'Die Vorhersage spricht im Moment klar dafür, dass die nächste relevante Welle dort zuerst anzieht.',
      proofPoints: ['7 Tage Vorhersage', 'Berlin zeigt aktuell das früheste relevante Signal.'],
      cautionText: 'Die Lage bleibt nachvollziehbar, aber keine Vorhersage ist eine Garantie.',
      assertive: true,
    },
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
      { label: 'Freigabestatus', value: 'Holdout bereit' },
      { label: 'Belegstufe', value: 'beobachtend' },
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

function buildWorkspaceStatus(): WorkspaceStatusSummary {
  return {
    forecast_status: 'Freigabe bereit',
    data_freshness: 'Aktuell',
    customer_data_status: 'im Aufbau',
    open_blockers: '1 offen',
    last_import_at: '2026-03-17T08:00:00Z',
    blocker_count: 1,
    blockers: ['Die Revision der Quelldaten bleibt sichtbar.'],
    summary: 'Vor dem nächsten Schritt sollten wir zuerst die offenen Punkte prüfen.',
    items: [
      {
        key: 'forecast_status',
        question: 'Ist der Forecast stabil?',
        value: 'Freigabe bereit',
        detail: 'Monitoring Stabil · Forecast aktuell',
        tone: 'success',
      },
      {
        key: 'data_freshness',
        question: 'Sind die Daten frisch?',
        value: 'Aktuell',
        detail: '6/7 Quellen aktuell',
        tone: 'success',
      },
      {
        key: 'customer_data_status',
        question: 'Sind Kundendaten verbunden?',
        value: 'im Aufbau',
        detail: '24 Wochen verbunden',
        tone: 'warning',
      },
      {
        key: 'open_blockers',
        question: 'Gibt es offene Blocker?',
        value: '1 offen',
        detail: 'Die Revision der Quelldaten bleibt sichtbar.',
        tone: 'warning',
      },
    ],
  };
}

describe('NowWorkspace', () => {
  it('shows one main decision, the trust block and the next region flow', () => {
    render(
      <NowWorkspace
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        onHorizonChange={noop}
        view={buildView()}
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        waveOutlook={null}
        waveOutlookLoading={false}
        onOpenRecommendation={noop}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    expect(screen.getByText('Warum wir frueher sehen, was kommt')).toBeInTheDocument();
    expect(screen.getByText('Verlauf der Welle')).toBeInTheDocument();
    expect(screen.getByText('Wir sehen im 7-Tage-Fenster das früheste relevante Signal aktuell in Berlin.')).toBeInTheDocument();
    expect(screen.getByText('Wie sicher ist das?')).toBeInTheDocument();
    expect(screen.getByText('Als Nächstes prüfen')).toBeInTheDocument();
    expect(screen.getByText('Was wir noch prüfen')).toBeInTheDocument();
    expect(screen.getByText('Weitere Details')).toBeInTheDocument();
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
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        waveOutlook={null}
        waveOutlookLoading={false}
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
