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

function metricToneClass(tone: 'success' | 'warning' | 'neutral') {
  if (tone === 'success') return 'now-status-pill now-status-pill--success';
  if (tone === 'warning') return 'now-status-pill now-status-pill--warning';
  return 'now-status-pill';
}

function extractPercent(value?: string | null): number {
  if (!value) return 0;
  const normalized = value.replace(',', '.').replace(/[^\d.]/g, '');
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
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
  const focusProbability = extractPercent(focusRegion?.probabilityLabel);
  const pageLead = view.note || 'Hier steht nur das, was für diese Woche wirklich zählt. Alles Weitere ordnen wir darunter.';
  const spotlightLead = focusRegion?.reason || view.note || 'Hier bündelt sich aktuell das stärkste Signal.';
  const primaryCampaignLabel = view.primaryRecommendationId ? 'Nächste Kampagne' : 'Kampagnenvorschlag';

  const prioritizedRegions = [
    ...(focusRegion ? [{
      key: focusRegion.code,
      rank: '01',
      name: focusRegion.name,
      detail: focusRegion.reason,
      stage: focusRegion.stage,
      value: focusRegion.probabilityLabel,
      accent: 'primary',
      intensity: Math.max(32, Math.min(96, focusProbability || 78)),
    }] : []),
    ...view.relatedRegions.slice(0, 2).map((region, index) => ({
      key: region.code,
      rank: `0${index + 2}`,
      name: region.name,
      detail: region.reason,
      stage: region.stage,
      value: region.probabilityLabel,
      accent: index === 0 ? 'secondary' : 'tertiary',
      intensity: Math.max(22, Math.min(88, extractPercent(region.probabilityLabel) || (60 - index * 10))),
    })),
  ];

  const updateItems = [
    ...view.quality.slice(0, 3).map((item, index) => ({
      key: `quality-${index}`,
      icon: 'verified',
      title: item.label,
      body: item.value,
      meta: 'Qualität',
    })),
    ...view.risks.slice(0, 2).map((risk, index) => ({
      key: `risk-${index}`,
      icon: 'warning',
      title: index === 0 ? 'Offener Prüfpunkt' : 'Weiterer Hinweis',
      body: risk,
      meta: 'Risiko',
    })),
  ];

  if (loading && !view.hasData) {
    return (
      <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
        Lade klare Arbeitslage...
      </div>
    );
  }

  return (
    <div className="page-stack now-template-page">
      <section className="now-page-header">
        <div className="now-page-header__copy">
          <span className="now-page-header__kicker">Live Intelligence Engine</span>
          <h1 className="now-page-header__title">Klare Lage. Klare nächste Aktion.</h1>
          <p className="now-page-header__text">
            {pageLead}
          </p>
        </div>

        <div className="now-page-header__controls">
          <div className="now-filter-shell">
            <span className="now-filter-shell__label">Virus</span>
            <div className="now-filter-shell__chips">
              {VIRUS_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => onVirusChange(option)}
                  className={`now-filter-chip ${option === virus ? 'active' : ''}`}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>

          <div className="now-filter-shell">
            <span className="now-filter-shell__label">Horizont</span>
            <div className="now-filter-shell__chips">
              {HORIZON_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => onHorizonChange(option)}
                  className={`now-filter-chip ${option === horizonDays ? 'active' : ''}`}
                >
                  {option} Tage
                </button>
              ))}
            </div>
          </div>

          <div className="now-live-status">
            <span className="now-live-status__dot" aria-hidden="true" />
            <span>Stand {formatDateTime(view.generatedAt)}</span>
          </div>
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
          <section className="now-metrics-grid">
            {view.metrics.map((metric) => (
              <div className="card now-metric-card" key={metric.label} data-testid="now-metric">
                <div className="now-metric-card__top">
                  <span className="now-metric-card__icon material-symbols-outlined" aria-hidden="true">
                    {metric.tone === 'success' ? 'trending_up' : metric.tone === 'warning' ? 'warning' : 'insights'}
                  </span>
                  <span className={metricToneClass(metric.tone || 'neutral')}>{metric.value}</span>
                </div>
                <span className="now-metric-card__label">{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </section>

          <section className="now-template-layout">
            <div className="now-template-main">
              <section className="card now-spotlight-card">
                <div className="now-spotlight-card__header">
                  <div>
                    <span className="now-section-kicker">Aktuelle Lage</span>
                    <h2 className="now-spotlight-card__title">{view.title}</h2>
                    <p className="now-spotlight-card__subtitle">{spotlightLead}</p>
                  </div>

                  <div className="now-spotlight-card__status">
                    <span className={metricToneClass(primaryMetric?.tone || 'neutral')}>
                      {primaryMetric?.value || 'Arbeitslage'}
                    </span>
                    <span className="campaign-confidence-chip">{focusRegion?.stage || 'Fokus aktiv'}</span>
                  </div>
                </div>

                <div className="now-spotlight-card__badges">
                  <span className="step-chip">Fokus {focusRegion?.name || '-'}</span>
                  <span className="step-chip">{focusRegion?.stage || '-'}</span>
                  <span className="step-chip">{focusRegion?.probabilityLabel || '-'}</span>
                  <span className="step-chip">Stand {formatDateTime(view.generatedAt)}</span>
                </div>

                <div className="now-spotlight-card__content">
                  <div className="now-spotlight-card__story">
                    <div className="now-story-intro">
                      <span className="now-story-intro__label">Wo wir jetzt hinschauen</span>
                      <p className="now-story-intro__copy">
                        {focusRegion?.name
                          ? `${focusRegion.name} steht im Mittelpunkt der aktuellen Wochenentscheidung.`
                          : 'Die aktuelle Wochenentscheidung bündelt die stärkste Lage direkt hier.'}
                      </p>
                    </div>

                    <p className="now-spotlight-card__copy">{view.summary}</p>

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
                      <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
                        Warum vertrauen wir dem?
                      </button>
                      <button
                        className="media-button secondary"
                        type="button"
                        onClick={() => onOpenRegions(focusRegion?.code || undefined)}
                      >
                        Fokusregion öffnen
                      </button>
                    </div>

                    <div className="now-proof-strip">
                      <div className="section-kicker">Darum schauen wir genau hier hin</div>
                      <div className="now-proof-strip__items">
                        {(leadingReasons.length ? leadingReasons : ['Noch keine Kurzbegründung verfügbar.']).map((reason) => (
                          <div key={reason} className="soft-panel now-proof-card">
                            {reason}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <aside className="soft-panel now-focus-panel">
                    <div>
                      <div className="section-kicker">Fokusregion</div>
                      <div className="summary-headline">{focusRegion?.name || '-'}</div>
                      <div className="summary-note">{focusRegion?.reason || 'Noch keine kurze Einordnung verfügbar.'}</div>
                    </div>

                    <div className="now-focus-panel__grid">
                      <div>
                        <div className="section-kicker">Status</div>
                        <div className="summary-metric">{focusRegion?.stage || '-'}</div>
                      </div>
                      <div>
                        <div className="section-kicker">Produkt</div>
                        <div className="summary-note">{focusRegion?.product || '-'}</div>
                      </div>
                      <div>
                        <div className="section-kicker">Wahrscheinlichkeit</div>
                        <div className="summary-note">{focusRegion?.probabilityLabel || '-'}</div>
                      </div>
                      <div>
                        <div className="section-kicker">Budget</div>
                        <div className="summary-note">{focusRegion?.budgetLabel || '-'}</div>
                      </div>
                    </div>

                    <div className="soft-panel now-focus-panel__campaign">
                      <div className="section-kicker">{primaryCampaignLabel}</div>
                      <div className="now-focus-panel__campaign-title">{view.primaryCampaignTitle}</div>
                      <div className="summary-note">{view.primaryCampaignContext}</div>
                      <p className="campaign-focus-copy">{view.primaryCampaignCopy}</p>
                    </div>
                  </aside>
                </div>
              </section>

              <section className="now-priority-section">
                <div className="now-priority-section__header">
                  <h3>Wohin schauen wir als Nächstes?</h3>
                  <button className="now-inline-link" type="button" onClick={() => onOpenRegions()}>
                    Vollständige Analyse
                  </button>
                </div>

                <div className="now-priority-list">
                  {(prioritizedRegions.length ? prioritizedRegions : [{
                    key: 'placeholder',
                    rank: '01',
                    name: 'Noch keine priorisierte Region',
                    detail: 'Sobald eine klare Fokusregion vorliegt, erscheint sie hier im Dashboard.',
                    stage: 'Offen',
                    value: '-',
                    accent: 'primary',
                    intensity: 24,
                  }]).map((item) => (
                    <button
                      type="button"
                      key={item.key}
                      className="card now-priority-card"
                      onClick={() => onOpenRegions(item.key && item.key !== 'placeholder' ? String(item.key) : undefined)}
                    >
                      <div className="now-priority-card__rank">{item.rank}</div>
                      <div className="now-priority-card__copy">
                        <h4>{item.name}</h4>
                        <p>{item.detail}</p>
                      </div>
                      <div className="now-priority-card__bars" aria-hidden="true">
                        {[0.42, 0.6, 0.34, 0.76, 0.92, item.intensity / 100].map((value, index) => (
                          <span
                            key={`${item.key}-${index}`}
                            className={`now-priority-card__bar now-priority-card__bar--${item.accent}`}
                            style={{ height: `${Math.max(22, Math.round(value * 48))}px` }}
                          />
                        ))}
                      </div>
                      <div className="now-priority-card__meta">
                        <strong>{item.value}</strong>
                        <span>{item.stage}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </section>

              <section className="now-map-card">
                <div className="now-map-card__content">
                  <h3>Regionale Dynamik</h3>
                  <p>
                    Die Fläche bündelt die Bewegung hinter der Wochenlage. Links steht die Fokusregion, darunter die nächsten Prüfpfade und rechts die kompakten Hinweise für den zweiten Blick.
                  </p>
                  <button
                    className="now-map-card__button"
                    type="button"
                    onClick={() => onOpenRegions(focusRegion?.code ? String(focusRegion.code) : undefined)}
                  >
                    Regionen im Detail
                  </button>
                </div>
                <div className="now-map-card__visual" aria-hidden="true">
                  <span style={{ height: 92 }} />
                  <span style={{ height: 148 }} />
                  <span style={{ height: 118 }} />
                  <span style={{ height: 176 }} />
                </div>
              </section>
            </div>

            <aside className="card now-live-feed">
              <div className="now-live-feed__header">
                <h3>Prüfhinweise</h3>
                <span className="now-live-feed__badge">Live</span>
              </div>

              <div className="now-live-feed__items">
                {(updateItems.length ? updateItems : [{
                  key: 'empty',
                  icon: 'info',
                  title: 'Noch keine Hinweise',
                  body: 'Sobald neue Qualitäts- oder Risiko-Hinweise vorliegen, erscheinen sie hier.',
                  meta: 'Status',
                }]).map((item, index) => (
                  <div key={item.key} className={`now-live-feed__item ${index > 0 ? 'now-live-feed__item--muted' : ''}`}>
                    <div className="now-live-feed__avatar">
                      <span className="material-symbols-outlined" aria-hidden="true">{item.icon}</span>
                    </div>
                    <div className="now-live-feed__copy">
                      <div className="now-live-feed__item-top">
                        <strong>{item.title}</strong>
                        <span>{item.meta}</span>
                      </div>
                      <p>{item.body}</p>
                    </div>
                  </div>
                ))}
              </div>

              <button className="now-live-feed__button" type="button" onClick={onOpenEvidence}>
                Alle Qualitätsdetails ansehen
              </button>
            </aside>
          </section>

          <section className="now-secondary-grid">
            <div className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Warum jetzt?</h2>
                <p className="subsection-copy">
                  Die stärksten Gründe für die aktuelle Wochenentscheidung.
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
