import React from 'react';

import { formatDateTime, VIRUS_OPTIONS } from './cockpitUtils';
import { NowPageViewModel } from '../../features/media/useMediaData';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  horizonDays: number;
  onHorizonChange: (value: number) => void;
  view: NowPageViewModel;
  loading: boolean;
  onOpenRecommendation: (id: string) => void;
  onOpenRegions: (regionCode?: string) => void;
  onOpenCampaigns: () => void;
  onOpenEvidence: () => void;
}

const HORIZON_OPTIONS = [3, 5, 7];

function toneStyle(tone: 'success' | 'warning' | 'neutral'): React.CSSProperties {
  if (tone === 'success') {
    return {
      background: 'rgba(5, 150, 105, 0.12)',
      color: 'var(--status-success)',
      border: '1px solid rgba(5, 150, 105, 0.22)',
    };
  }

  if (tone === 'warning') {
    return {
      background: 'rgba(245, 158, 11, 0.12)',
      color: 'var(--status-warning)',
      border: '1px solid rgba(245, 158, 11, 0.24)',
    };
  }

  return {
    background: 'rgba(10, 132, 255, 0.10)',
    color: 'var(--status-info)',
    border: '1px solid rgba(10, 132, 255, 0.2)',
  };
}

const NowWorkspace: React.FC<Props> = ({
  virus,
  onVirusChange,
  horizonDays,
  onHorizonChange,
  view,
  loading,
  onOpenRecommendation,
  onOpenRegions,
  onOpenCampaigns,
  onOpenEvidence,
}) => {
  const focusRegion = view.focusRegion;
  const primaryMetric = view.metrics[0];
  const leadingReasons = view.reasons.slice(0, 3);

  if (loading && !view.hasData) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade klare Arbeitslage...</div>;
  }

  return (
    <div className="page-stack">
      <section className="context-filter-rail now-toolbar">
        <div className="section-heading">
          <span className="section-kicker">Jetzt</span>
          <h1 className="section-title">Klare Lage. Klare nächste Aktion.</h1>
          <p className="section-copy">
            Oben steht nur das, was für diese Woche zählt. Begründung, Qualität und Risiken folgen darunter.
          </p>
        </div>

        <div className="now-toolbar__controls">
          <div className="ops-filter-group">
            <span className="ops-filter-label">Virus</span>
            <div className="review-chip-row">
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
          </div>

          <div className="ops-filter-group">
            <span className="ops-filter-label">Horizont</span>
            <div className="review-chip-row">
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
          </div>
        </div>

        <div className="review-chip-row">
          <span className="step-chip">Stand {formatDateTime(view.generatedAt)}</span>
          <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
            Warum vertrauen wir dem?
          </button>
        </div>
      </section>

      {view.emptyState ? (
        <section className="card subsection-card" style={{ padding: 28 }}>
          <div className="section-heading" style={{ gap: 6 }}>
            <h2 className="subsection-title">{view.emptyState.title}</h2>
            <p className="subsection-copy">{view.emptyState.body}</p>
          </div>
          <div className="action-row">
            <button className="media-button secondary" type="button" onClick={onOpenEvidence}>Evidenz prüfen</button>
            <button className="media-button secondary" type="button" onClick={() => onOpenRegions()}>Regionen öffnen</button>
          </div>
        </section>
      ) : (
        <>
          <section className="card hero-card now-dashboard-hero" style={{ padding: 32 }}>
            <div className="hero-grid now-hero-grid">
              <div className="hero-main">
                <div className="hero-status-row">
                  <span
                    style={{
                      ...toneStyle(primaryMetric?.tone || 'neutral'),
                      padding: '8px 12px',
                      borderRadius: 999,
                      fontSize: 12,
                      fontWeight: 800,
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                    }}
                  >
                    {primaryMetric?.value || 'Arbeitslage'}
                  </span>
                  {focusRegion && <span className="campaign-confidence-chip">{focusRegion.stage}</span>}
                  <span className="campaign-confidence-chip">Fokus {focusRegion?.name || '-'}</span>
                  <span className="campaign-confidence-chip">Stand {formatDateTime(view.generatedAt)}</span>
                </div>

                <div className="section-heading" style={{ gap: 12 }}>
                  <span className="section-kicker">Aktuelle Lage</span>
                  <h2 className="hero-title">{view.title}</h2>
                  <p className="hero-context">{view.summary}</p>
                  <p className="hero-copy">{view.note}</p>
                </div>

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
                    {view.primaryActionLabel}
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

                <div className="now-proof-strip">
                  <div className="section-kicker">Wichtigste Gründe</div>
                  <div className="now-proof-strip__items">
                    {(leadingReasons.length ? leadingReasons : ['Noch keine Kurzbegründung verfügbar.']).map((reason) => (
                      <div key={reason} className="soft-panel now-proof-card">
                        {reason}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <aside className="soft-panel aside-summary now-focus-card" style={{ padding: 24 }}>
                <div>
                  <div className="section-kicker">Fokusregion</div>
                  <div className="summary-headline">{focusRegion?.name || '-'}</div>
                  <div className="summary-note">{focusRegion?.reason || 'Noch keine kurze Einordnung verfügbar.'}</div>
                </div>

                <div className="summary-grid now-focus-card__grid">
                  <div>
                    <div className="section-kicker" style={{ marginBottom: 6 }}>Stage</div>
                    <div className="summary-metric" style={{ fontSize: '1.45rem' }}>{focusRegion?.stage || '-'}</div>
                  </div>
                  <div>
                    <div className="section-kicker" style={{ marginBottom: 6 }}>Produkt</div>
                    <div className="summary-note" style={{ marginTop: 0 }}>{focusRegion?.product || '-'}</div>
                  </div>
                  <div>
                    <div className="section-kicker" style={{ marginBottom: 6 }}>Wahrscheinlichkeit</div>
                    <div className="summary-note" style={{ marginTop: 0 }}>{focusRegion?.probabilityLabel || '-'}</div>
                  </div>
                  <div>
                    <div className="section-kicker" style={{ marginBottom: 6 }}>Budget</div>
                    <div className="summary-note" style={{ marginTop: 0 }}>{focusRegion?.budgetLabel || '-'}</div>
                  </div>
                </div>

                <div className="soft-panel now-focus-card__campaign" style={{ padding: 16 }}>
                  <div className="section-kicker">Nächste Kampagne</div>
                  <div style={{ marginTop: 8, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {view.primaryCampaignTitle}
                  </div>
                  <div style={{ marginTop: 6, fontSize: 13, color: 'var(--text-muted)' }}>
                    {view.primaryCampaignContext}
                  </div>
                  <p className="campaign-focus-copy" style={{ marginTop: 10 }}>
                    {view.primaryCampaignCopy}
                  </p>
                </div>
              </aside>
            </div>
          </section>

          <section className="now-metrics-grid">
            {view.metrics.map((metric) => (
              <div className="card now-metric-card" key={metric.label} data-testid="now-metric">
                <div className="now-metric-card__top">
                  <span className="now-metric-card__label">{metric.label}</span>
                  <span
                    className={`now-metric-card__dot now-metric-card__dot--${metric.tone || 'neutral'}`}
                    aria-hidden="true"
                  />
                </div>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </section>

          <section className="now-secondary-grid">
            <div className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Warum jetzt?</h2>
                <p className="subsection-copy">
                  Die wichtigsten Gründe für die aktuelle Priorisierung.
                </p>
              </div>
              <div className="now-callout-list">
                {(view.reasons.length ? view.reasons : ['Noch keine Begründungen verfügbar.']).map((reason) => (
                  <div key={reason} className="soft-panel now-callout-card">
                    {reason}
                  </div>
                ))}
              </div>
            </div>

            <div className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Qualität & Vertrauen</h2>
                <p className="subsection-copy">
                  Diese Punkte helfen beim schnellen Gegencheck, ohne die Hauptsicht zu überladen.
                </p>
              </div>
              <div className="now-quality-list">
                {(view.quality.length ? view.quality : [{ label: 'Qualität', value: 'Noch offen' }]).map((item) => (
                  <div key={item.label} className="evidence-row">
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
            </div>

            <div className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Weitere Regionen</h2>
                <p className="subsection-copy">
                  Nach der Fokusregion sind das die nächsten sinnvollen Prüfpfade.
                </p>
              </div>
              <div className="now-region-list">
                {view.relatedRegions.length > 0 ? view.relatedRegions.map((region) => (
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
                  <div className="soft-panel now-callout-card">Aktuell gibt es keine weiteren priorisierten Regionen.</div>
                )}
              </div>
            </div>

            <div className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Risiken</h2>
                <p className="subsection-copy">
                  Diese Punkte sprechen für Vorsicht oder für einen zweiten Blick.
                </p>
              </div>
              <div className="now-callout-list">
                {(view.risks.length ? view.risks : ['Aktuell gibt es keine offenen Risiken im Fokus.']).map((risk) => (
                  <div key={risk} className="soft-panel now-callout-card">
                    {risk}
                  </div>
                ))}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
};

export default NowWorkspace;
