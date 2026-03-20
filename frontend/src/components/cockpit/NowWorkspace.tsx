import React from 'react';

import { WorkspaceStatusSummary } from '../../types/media';
import CollapsibleSection from '../CollapsibleSection';
import { NowPageViewModel } from '../../features/media/useMediaData';
import { formatDateTime, VIRUS_OPTIONS } from './cockpitUtils';
import WorkspaceStatusPanel from './WorkspaceStatusPanel';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  horizonDays: number;
  onHorizonChange: (value: number) => void;
  view: NowPageViewModel;
  workspaceStatus: WorkspaceStatusSummary | null;
  loading: boolean;
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
  onOpenRecommendation,
  onOpenRegions,
  onOpenCampaigns,
  onOpenEvidence,
}) => {
  const focusRegion = view.focusRegion;
  const leadReasons = view.reasons.slice(0, 3);
  const relatedRegions = view.relatedRegions.slice(0, 3);
  const mainActionLabel = view.primaryActionLabel || 'Kampagnen prüfen';

  if (loading && !view.hasData) {
    return (
      <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
        Lade klare Arbeitslage...
      </div>
    );
  }

  return (
    <div className="page-stack now-template-page">
      <section className="context-filter-rail">
        <div className="section-heading" style={{ marginBottom: 0 }}>
          <span className="section-kicker">Diese Woche zuerst</span>
          <h1 className="section-title">Klare Lage. Klare nächste Aktion.</h1>
          <p className="section-copy">
            Wir zeigen zuerst nur die wichtigste Entscheidung, warum sie gerade zählt und was der nächste sinnvolle Schritt ist.
          </p>
        </div>

        <div style={{ display: 'grid', gap: 12, justifyItems: 'start' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
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
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
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
          </div>

          <span className="step-chip">Stand {formatDateTime(view.generatedAt)}</span>
        </div>
      </section>

      {view.emptyState ? (
        <section className="card subsection-card" style={{ padding: 28 }}>
          <div className="section-heading" style={{ gap: 6 }}>
            <h2 className="subsection-title">{view.emptyState.title}</h2>
            <p className="subsection-copy">{view.emptyState.body}</p>
          </div>
          <div className="action-row">
            <button className="media-button secondary" type="button" onClick={onOpenEvidence}>Qualität prüfen</button>
            <button className="media-button secondary" type="button" onClick={() => onOpenRegions()}>Regionen öffnen</button>
          </div>
        </section>
      ) : (
        <>
          <section className="card subsection-card workspace-priority-card" style={{ padding: 28 }}>
            <div className="workspace-priority-grid">
              <div>
                <div className="section-heading" style={{ gap: 8 }}>
                  <span className="section-kicker">Hauptentscheidung</span>
                  <h2 className="section-title workspace-priority-card__title">{view.summary}</h2>
                  <p className="section-copy">{view.note}</p>
                </div>

                <div className="review-chip-row" style={{ marginTop: 14 }}>
                  <span className="step-chip">Fokus {focusRegion?.name || '-'}</span>
                  <span className="step-chip">{focusRegion?.stage || '-'}</span>
                  <span className="step-chip">{focusRegion?.probabilityLabel || '-'}</span>
                  <span className="step-chip">{focusRegion?.budgetLabel || '-'}</span>
                </div>

                <div className="action-row" style={{ marginTop: 20 }}>
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

              <aside className="soft-panel workspace-priority-card__aside">
                <div>
                  <div className="section-kicker">Warum jetzt?</div>
                  <div className="workspace-priority-card__reasons">
                    {(leadReasons.length ? leadReasons : ['Noch keine kurze Begründung verfügbar.']).map((reason) => (
                      <div key={reason} className="workspace-note-card">
                        {reason}
                      </div>
                    ))}
                  </div>
                </div>

                <div style={{ display: 'grid', gap: 10 }}>
                  <div className="evidence-row">
                    <span>Fokusregion</span>
                    <strong>{focusRegion?.name || '-'}</strong>
                  </div>
                  <div className="evidence-row">
                    <span>Produktfokus</span>
                    <strong>{focusRegion?.product || '-'}</strong>
                  </div>
                  <div className="evidence-row">
                    <span>Wahrscheinlichkeit</span>
                    <strong>{focusRegion?.probabilityLabel || '-'}</strong>
                  </div>
                  <div className="evidence-row">
                    <span>Budgethinweis</span>
                    <strong>{focusRegion?.budgetLabel || '-'}</strong>
                  </div>
                </div>
              </aside>
            </div>
          </section>

          <WorkspaceStatusPanel
            status={workspaceStatus}
            title="Wie sicher ist das?"
            intro="Diese vier Antworten helfen uns, ob wir direkt handeln oder erst noch etwas prüfen sollten."
          />

          <section className="workspace-two-column">
            <section className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Was danach wichtig wird</h2>
                <p className="subsection-copy">
                  Nach der Fokusregion sind das die nächsten sinnvollen Prüfpfade.
                </p>
              </div>
              <div style={{ display: 'grid', gap: 12 }}>
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
            </section>

            <section className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Was noch offen ist</h2>
                <p className="subsection-copy">
                  Diese Punkte sprechen für Vorsicht oder für einen kurzen zweiten Blick.
                </p>
              </div>
              <div className="workspace-note-list">
                {((workspaceStatus?.blockers?.length ? workspaceStatus.blockers : view.risks).slice(0, 4)).map((risk) => (
                  <div key={risk} className="workspace-note-card">
                    {risk}
                  </div>
                ))}
              </div>
            </section>
          </section>

          <CollapsibleSection
            title="Technische Details"
            subtitle="Nur für den zweiten Blick: zusätzliche Qualitätswerte, weitere Gründe und Detailhinweise."
          >
            <div className="workspace-two-column">
              <div className="soft-panel workspace-detail-panel">
                <div className="section-kicker">Qualitätswerte</div>
                <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
                  {(view.quality.length ? view.quality : [{ label: 'Qualität', value: 'Noch offen' }]).map((item) => (
                    <div key={item.label} className="evidence-row">
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                    </div>
                  ))}
                </div>
              </div>

              <div className="soft-panel workspace-detail-panel">
                <div className="section-kicker">Weitere Begründungen</div>
                <div className="workspace-note-list" style={{ marginTop: 12 }}>
                  {(view.reasons.length > 3 ? view.reasons.slice(3) : view.risks).map((item) => (
                    <div key={item} className="workspace-note-card">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </CollapsibleSection>
        </>
      )}
    </div>
  );
};

export default NowWorkspace;
