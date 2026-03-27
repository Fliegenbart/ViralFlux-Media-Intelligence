import React from 'react';

import {
  BacktestResponse,
  RegionalBacktestResponse,
  RegionalForecastResponse,
  WaveRadarResponse,
  WorkspaceStatusSummary,
} from '../../types/media';
import CollapsibleSection from '../CollapsibleSection';
import { NowPageViewModel } from '../../features/media/useMediaData';
import { FocusRegionOutlookPanel, WaveOutlookPanel, WaveSpreadPanel } from './BacktestVisuals';
import { formatDateTime, VIRUS_OPTIONS } from './cockpitUtils';
import {
  OperatorChipRail,
  OperatorPanel,
  OperatorSection,
  OperatorStat,
} from './operator/OperatorPrimitives';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  horizonDays: number;
  onHorizonChange: (value: number) => void;
  view: NowPageViewModel;
  workspaceStatus: WorkspaceStatusSummary | null;
  loading: boolean;
  forecast: RegionalForecastResponse | null;
  focusRegionBacktest: RegionalBacktestResponse | null;
  focusRegionBacktestLoading: boolean;
  waveOutlook: BacktestResponse | null;
  waveOutlookLoading: boolean;
  waveRadar: WaveRadarResponse | null;
  waveRadarLoading: boolean;
  onOpenRecommendation: (id: string) => void;
  onOpenRegions: (regionCode?: string) => void;
  onOpenCampaigns: () => void;
  onOpenEvidence: () => void;
}

const NowWorkspace: React.FC<Props> = ({
  virus,
  onVirusChange,
  horizonDays,
  onHorizonChange,
  view,
  workspaceStatus,
  loading,
  forecast,
  focusRegionBacktest,
  focusRegionBacktestLoading,
  waveOutlook,
  waveOutlookLoading,
  waveRadar,
  waveRadarLoading,
  onOpenRecommendation,
  onOpenRegions,
  onOpenCampaigns,
  onOpenEvidence,
}) => {
  const focusRegion = view.focusRegion;
  const proof = view.proof;
  const leadReasons = view.reasons.slice(0, 3);
  const relatedRegions = view.relatedRegions.slice(0, 2);
  const trustChecks = view.trustChecks.slice(0, 3);
  const mainActionLabel = view.primaryActionLabel || 'Kampagnen prüfen';
  const blockers = (workspaceStatus?.blockers?.length ? workspaceStatus.blockers : view.risks).slice(0, 3);
  const sortedPredictions = [...(forecast?.predictions || [])].sort((left, right) => {
    const leftRank = Number(left.decision_rank ?? left.rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.decision_rank ?? right.rank ?? Number.MAX_SAFE_INTEGER);
    return leftRank - rightRank;
  });
  const focusPrediction = (
    (focusRegion?.code
      ? sortedPredictions.find((item) => item.bundesland === focusRegion.code)
      : null)
    || sortedPredictions[0]
    || null
  );
  const nextStepTitle = view.primaryCampaignTitle && view.primaryCampaignTitle !== '-'
    ? view.primaryCampaignTitle
    : focusRegion?.name
      ? `${focusRegion.name} als nächster Schritt`
      : 'Nächsten Schritt prüfen';
  const nextStepDescription = view.primaryCampaignCopy && view.primaryCampaignCopy !== '-'
    ? view.primaryCampaignCopy
    : focusRegion?.reason
      ? focusRegion.reason
      : 'Hier starten wir mit dem nächsten sinnvollen Arbeitsschritt.';
  const nextStepContext = view.primaryCampaignContext && view.primaryCampaignContext !== '-'
    ? view.primaryCampaignContext
    : focusRegion?.name
      ? `${focusRegion.name} · ${focusRegion.stage || 'prüfen'}`
      : 'Nächster Arbeitsfall';
  const priorityNotes = [
    ...(proof?.proofPoints || []),
    ...leadReasons,
  ].slice(0, 4);
  const mainWhy = priorityNotes[0] || 'Hier steht gleich der wichtigste Grund.';
  const trustSummary = workspaceStatus?.summary || 'Hier siehst du den schnellen Vertrauenscheck.';
  const weeklyActionDetail = view.primaryCampaignContext && view.primaryCampaignContext !== '-'
    ? `${view.primaryCampaignContext} · ${nextStepDescription}`
    : nextStepDescription;
  const weeklyWhereDetail = focusRegion?.product && focusRegion.product !== '-'
    ? `Bundesland-Level · ${focusRegion.stage || 'Beobachten'} · ${focusRegion.product}`
    : `Bundesland-Level · ${focusRegion?.stage || 'Beobachten'}`;
  const weeklyWhyDetail = proof?.supportingText || focusRegion?.reason || 'Hier steht der wichtigste Grund für die Priorisierung.';
  const weeklyBudgetDetail = focusRegion?.probabilityLabel && focusRegion.probabilityLabel !== '-'
    ? `${horizonDays}-Tage-Fenster · Vorhersagesignal ${focusRegion.probabilityLabel}`
    : `${horizonDays}-Tage-Fenster · Vorhersagesignal noch offen`;

  if (loading && !view.hasData) {
    return (
      <OperatorSection
        kicker="PEIX x GELO Wochenplan"
        title="Was PEIX und GELO diese Woche tun sollten"
        description="Wir holen gerade die aktuelle Wochenplanung. Gleich siehst du wieder, welches Bundesland und welche Maßnahme vorne liegen."
        tone="muted"
        className="now-template-page operator-toolbar-shell"
      >
        <div className="workspace-note-card">Lade Wochenplanung...</div>
      </OperatorSection>
    );
  }

  return (
    <div className="page-stack now-template-page">
      <OperatorSection
        kicker="PEIX x GELO Wochenplan"
        title="Was PEIX und GELO diese Woche tun sollten"
        description="Die Ansicht beantwortet zuerst: Welche Maßnahme, in welchem Bundesland, und warum."
        tone="accent"
        className="operator-toolbar-shell"
      >
        <div className="now-toolbar">
          <OperatorChipRail className="review-chip-row">
            {VIRUS_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onVirusChange(option)}
                className={`tab-chip ${option === virus ? 'active' : ''}`}
              >
                {option}
              </button>
            ))}
            <span className="step-chip">Bundesland-Level</span>
          </OperatorChipRail>
          <span className="step-chip">Stand {formatDateTime(view.generatedAt)}</span>
        </div>

        <div className="now-command-grid">
          <div className="now-proof-stage">
            <FocusRegionOutlookPanel
              prediction={focusPrediction}
              backtest={focusRegionBacktest}
              loading={focusRegionBacktestLoading}
              horizonDays={horizonDays}
            />
          </div>

          <OperatorPanel
            eyebrow="Diese Woche zuerst"
            title={view.summary || proof?.headline || (focusRegion?.name ? `${focusRegion.name} steht gerade vorne` : 'Das ist der aktuelle Fokus')}
            description={view.note || proof?.supportingText || 'Hier steht der wichtigste Grund für den Fokus.'}
            tone="muted"
            className="now-command-rail"
          >
            <div className="now-weekly-plan-grid">
              <article className="workspace-note-card now-weekly-plan-card">
                <span className="now-weekly-plan-card__label">Was tun?</span>
                <strong>{nextStepTitle}</strong>
                <p>{weeklyActionDetail}</p>
              </article>
              <article className="workspace-note-card now-weekly-plan-card">
                <span className="now-weekly-plan-card__label">Wo zuerst?</span>
                <strong>{focusRegion?.name || '-'}</strong>
                <p>{weeklyWhereDetail}</p>
              </article>
              <article className="workspace-note-card now-weekly-plan-card">
                <span className="now-weekly-plan-card__label">Warum jetzt?</span>
                <strong>{mainWhy}</strong>
                <p>{weeklyWhyDetail}</p>
              </article>
              <article className="workspace-note-card now-weekly-plan-card">
                <span className="now-weekly-plan-card__label">Budgetrahmen</span>
                <strong>{focusRegion?.budgetLabel || '-'}</strong>
                <p>{weeklyBudgetDetail}</p>
              </article>
            </div>

            {proof?.cautionText ? (
              <div className="workspace-note-card now-action-brief">
                <strong>Wichtiger Hinweis zur Einordnung</strong>
                <span>Evidenz sichtbar halten</span>
                <p>{proof.cautionText}</p>
              </div>
            ) : null}

            <div className="action-row">
              <button
                className="media-button"
                type="button"
                onClick={() => (
                  view.primaryRecommendationId
                    ? onOpenRecommendation(view.primaryRecommendationId)
                    : onOpenCampaigns()
                )}
              >
                {mainActionLabel}
              </button>
              <button
                className="media-button secondary"
                type="button"
                onClick={() => onOpenRegions(focusRegion?.code || undefined)}
              >
                Bundesland öffnen
              </button>
              <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
                Evidenz prüfen
              </button>
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>

      {view.emptyState ? (
        <OperatorSection
          kicker="Was passiert gerade?"
          title={view.emptyState.title}
          description={view.emptyState.body}
          tone="muted"
        >
          <div className="action-row">
            <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
              Qualität prüfen
            </button>
            <button className="media-button secondary" type="button" onClick={() => onOpenRegions()}>
              Regionen öffnen
            </button>
          </div>
        </OperatorSection>
      ) : (
        <>
          <OperatorSection
            kicker="Kann ich der Entscheidung trauen?"
            title="Der schnelle Sicherheitscheck"
            description="Hier siehst du sofort, ob Forecast, Daten und Freigabe schon tragen."
            tone="muted"
            className="workspace-status-panel"
          >
            <div className="now-trust-grid">
              {trustChecks.map((item) => (
                <article
                  key={item.key}
                  className={`workspace-status-card workspace-status-card--${item.tone}`}
                >
                  <span className="workspace-status-card__question">{item.question}</span>
                  <strong>{item.value}</strong>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>

            <div className="workspace-status-panel__footer">
              <span>{trustSummary}</span>
              <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
                Evidenz öffnen
              </button>
            </div>
          </OperatorSection>

          <CollapsibleSection
            title="Weitere Details"
            subtitle="Nur wenn du tiefer einsteigen möchtest."
          >
            <div className="workspace-two-column">
              <OperatorPanel
                title={nextStepTitle}
                description={nextStepDescription}
              >
                <div className="workspace-note-list">
                  <div className="workspace-note-card">{nextStepContext}</div>
                  {relatedRegions.length > 0 ? relatedRegions.map((region) => (
                    <button
                      type="button"
                      key={region.code}
                      onClick={() => onOpenRegions(region.code)}
                      className="campaign-list-card"
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                        <div style={{ textAlign: 'left' }}>
                          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{region.name}</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                            {region.stage} · {region.probabilityLabel}
                          </div>
                        </div>
                      </div>
                    </button>
                  )) : null}
                </div>
              </OperatorPanel>

              <OperatorPanel
                title="Offene Punkte"
                description="Nur wenn noch etwas blockiert."
              >
                <div className="workspace-note-list">
                  {blockers.length > 0 ? blockers.map((risk) => (
                    <div key={risk} className="workspace-note-card">
                      {risk}
                    </div>
                  )) : (
                    <div className="workspace-note-card">Aktuell blockiert nichts.</div>
                  )}
                </div>
              </OperatorPanel>
            </div>

            <WaveOutlookPanel
              virus={virus}
              onVirusChange={onVirusChange}
              result={waveOutlook}
              loading={waveOutlookLoading}
              showVirusSelector={false}
              title="Bundesweiter Rückblick"
              subtitle={`Hier bleibt die bisherige bundesweite Validierung sichtbar. Sie ist nicht mehr die erste Kundenansicht, hilft aber weiter bei der fachlichen Einordnung von ${virus}.`}
            />

            <WaveSpreadPanel
              virus={virus}
              result={waveRadar}
              loading={waveRadarLoading}
              title="Hier beginnt die Welle"
              subtitle={`So hat sich ${virus} in der zuletzt verfügbaren Saison über Deutschland verteilt. Damit siehst du schneller, welche Regionen damals zuerst gefolgt sind.`}
            />

            <div className="workspace-two-column">
              <OperatorPanel title="Kennzahlen" description="Die wichtigsten Werte kurz zusammengefasst.">
                <div className="operator-stat-grid">
                  {(view.quality.length ? view.quality : [{ label: 'Qualität', value: 'Noch offen' }]).map((item) => (
                    <OperatorStat
                      key={item.label}
                      label={item.label}
                      value={item.value}
                      tone="muted"
                    />
                  ))}
                </div>
              </OperatorPanel>

              <OperatorPanel
                title="Weitere Hinweise"
                description="Hier stehen zusätzliche Punkte, die für die Einordnung hilfreich sind."
              >
                <div className="workspace-note-list">
                  {(view.reasons.length > 3 ? view.reasons.slice(3) : view.risks).map((item) => (
                    <div key={item} className="workspace-note-card">
                      {item}
                    </div>
                  ))}
                </div>
              </OperatorPanel>
            </div>
          </CollapsibleSection>
        </>
      )}
    </div>
  );
};

export default NowWorkspace;
