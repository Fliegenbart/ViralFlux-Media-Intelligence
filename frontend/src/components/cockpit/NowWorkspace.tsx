import React from 'react';

import { BacktestResponse, WorkspaceStatusSummary } from '../../types/media';
import CollapsibleSection from '../CollapsibleSection';
import { NowPageViewModel } from '../../features/media/useMediaData';
import { WaveOutlookPanel } from './BacktestVisuals';
import { formatDateTime, VIRUS_OPTIONS } from './cockpitUtils';
import WorkspaceStatusPanel from './WorkspaceStatusPanel';
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
  waveOutlook: BacktestResponse | null;
  waveOutlookLoading: boolean;
  onOpenRecommendation: (id: string) => void;
  onOpenRegions: (regionCode?: string) => void;
  onOpenCampaigns: () => void;
  onOpenEvidence: () => void;
}

const HORIZON_OPTIONS = [3, 5, 7];

const NowWorkspace: React.FC<Props> = ({
  virus,
  onVirusChange,
  horizonDays,
  onHorizonChange,
  view,
  workspaceStatus,
  loading,
  waveOutlook,
  waveOutlookLoading,
  onOpenRecommendation,
  onOpenRegions,
  onOpenCampaigns,
  onOpenEvidence,
}) => {
  const focusRegion = view.focusRegion;
  const proof = view.proof;
  const leadReasons = view.reasons.slice(0, 3);
  const relatedRegions = view.relatedRegions.slice(0, 3);
  const mainActionLabel = view.primaryActionLabel || 'Kampagnen prüfen';

  if (loading && !view.hasData) {
    return (
      <OperatorSection
        kicker="Diese Woche im Blick"
        title="Wo die nächste virale Welle zuerst anzieht"
        description="Wir holen gerade die aktuelle Wochenlage. Gleich siehst du wieder das wichtigste Signal zuerst."
        tone="muted"
        className="now-template-page operator-toolbar-shell"
      >
        <div className="workspace-note-card">Lade Wochenlage...</div>
      </OperatorSection>
    );
  }

  return (
    <div className="page-stack now-template-page">
      <OperatorSection
        kicker="Proof"
        title="Warum wir frueher sehen, was kommt"
        description="Ganz oben steht der sichtbare Verlauf der Welle. Erst danach kommt die Entscheidung fuer diese Woche."
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
          </OperatorChipRail>

          <OperatorChipRail className="review-chip-row">
            {HORIZON_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onHorizonChange(option)}
                className={`tab-chip ${option === horizonDays ? 'active' : ''}`}
              >
                {option} Tage
              </button>
            ))}
          </OperatorChipRail>

          <span className="step-chip">Stand {formatDateTime(view.generatedAt)}</span>
        </div>

        <div className="now-proof-stage">
          <WaveOutlookPanel
            virus={virus}
            onVirusChange={onVirusChange}
            result={waveOutlook}
            loading={waveOutlookLoading}
            showVirusSelector={false}
          />
        </div>
      </OperatorSection>

      {view.emptyState ? (
        <OperatorSection
          kicker="Keine Wochenlage"
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
            kicker="Hauptentscheidung"
            title={proof?.headline || view.summary}
            description={proof?.supportingText || view.note}
            tone="accent"
            className="now-hero-shell"
          >
            <div className="workspace-priority-grid now-hero-grid">
              <div className="now-focus-card">
                {proof?.proofPoints?.length ? (
                  <div className="workspace-note-list">
                    {proof.proofPoints.map((point) => (
                      <div key={point} className="workspace-note-card">
                        {point}
                      </div>
                    ))}
                  </div>
                ) : null}

                {proof?.cautionText ? (
                  <p className="subsection-copy" style={{ margin: 0 }}>
                    {proof.cautionText}
                  </p>
                ) : null}

                <OperatorChipRail className="review-chip-row">
                  <span className="step-chip">Fokus {focusRegion?.name || '-'}</span>
                  <span className="step-chip">{focusRegion?.stage || '-'}</span>
                  <span className="step-chip">{focusRegion?.probabilityLabel || '-'}</span>
                  <span className="step-chip">{focusRegion?.budgetLabel || '-'}</span>
                </OperatorChipRail>

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
                    Fokusregion öffnen
                  </button>
                  <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
                    Qualität prüfen
                  </button>
                </div>
              </div>

              <OperatorPanel
                eyebrow="Warum wir das sagen"
                title={focusRegion?.name ? `${focusRegion.name} im Detail` : 'Frühester Startpunkt'}
                description={
                  focusRegion
                    ? `Aktueller Status: ${focusRegion.stage || 'nicht klassifiziert'}`
                    : 'Sobald die Fokusregion feststeht, sammeln wir hier die kurzen Belege.'
                }
                tone="muted"
                className="workspace-priority-card__aside"
              >
                <div className="workspace-priority-card__reasons">
                  {(leadReasons.length ? leadReasons : ['Noch keine kurze Begründung verfügbar.']).map((reason) => (
                    <div key={reason} className="workspace-note-card">
                      {reason}
                    </div>
                  ))}
                </div>

                <div className="operator-stat-grid">
                  <OperatorStat
                    label="Fokusregion"
                    value={focusRegion?.name || '-'}
                    meta={focusRegion?.stage || 'noch nicht ausgewählt'}
                    tone="accent"
                  />
                  <OperatorStat
                    label="Produktfokus"
                    value={focusRegion?.product || '-'}
                    meta="für die nächste Aktion"
                  />
                  <OperatorStat
                    label="Vorhersagesignal"
                    value={focusRegion?.probabilityLabel || '-'}
                    meta="frühestes relevantes Signal"
                  />
                  <OperatorStat
                    label="Budgethinweis"
                    value={focusRegion?.budgetLabel || '-'}
                    meta="für den nächsten Arbeitsschritt"
                  />
                </div>
              </OperatorPanel>
            </div>
          </OperatorSection>

          <WorkspaceStatusPanel
            status={workspaceStatus}
            title="Wie sicher ist das?"
            intro="Diese vier Antworten helfen uns, ob wir direkt handeln oder erst noch etwas prüfen sollten."
          />

          <section className="workspace-two-column">
            <OperatorPanel
              title="Als Nächstes prüfen"
              description="Nach der Fokusregion sind das die nächsten Regionen, die wir prüfen sollten."
            >
              <div className="workspace-note-list">
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
                    <p className="campaign-focus-copy" style={{ marginTop: 10 }}>{region.reason}</p>
                  </button>
                )) : (
                  <div className="workspace-note-card">Aktuell gibt es keine weiteren priorisierten Regionen.</div>
                )}
              </div>
            </OperatorPanel>

            <OperatorPanel
              title="Was wir noch prüfen"
              description="Diese Punkte bremsen noch oder brauchen einen kurzen zweiten Blick."
            >
              <div className="workspace-note-list">
                {((workspaceStatus?.blockers?.length ? workspaceStatus.blockers : view.risks).slice(0, 4)).map((risk) => (
                  <div key={risk} className="workspace-note-card">
                    {risk}
                  </div>
                ))}
              </div>
            </OperatorPanel>
          </section>

          <CollapsibleSection
            title="Weitere Details"
            subtitle="Nur für den zweiten Blick: zusätzliche Gründe, Qualitätswerte und Hinweise."
          >
            <div className="workspace-two-column">
              <OperatorPanel title="Qualitätswerte" description="Die wichtigsten Qualitätswerte auf einen Blick.">
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
                title="Weitere Begründungen"
                description="Die längeren Gründe bleiben hier gesammelt und leicht aufklappbar."
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
