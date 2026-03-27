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
  const heroRecommendation = view.heroRecommendation;
  const heroSupportText = [view.supportState.label, view.supportState.detail].filter(Boolean).join(' · ');
  const leadReasons = view.reasons.slice(0, 3);
  const secondaryMoves = view.secondaryMoves.slice(0, 2);
  const trustChecks = view.briefingTrust.items.slice(0, 3);
  const normalizedTrustChecks = trustChecks.map((item) => ({
    ...item,
    label: briefingTrustLabel(item.label),
  }));
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
  const trustSummary = view.briefingTrust.summary || workspaceStatus?.summary || 'Hier siehst du den schnellen Vertrauenscheck.';
  const heroMetrics = [
    { label: 'Entscheidung', value: heroRecommendation?.direction || 'Noch offen' },
    { label: 'Bundesland', value: heroRecommendation?.region || focusRegion?.name || 'Noch offen' },
    { label: 'Kontext', value: heroRecommendation?.context || view.primaryCampaignContext || 'Noch ohne Einordnung' },
  ];
  const qualityStats = (view.quality.length ? view.quality : [{ label: 'Qualität', value: 'Noch offen' }]).slice(0, 4);
  const inlineNotes = [
    ...(view.supportState.detail ? [view.supportState.detail] : []),
    ...blockers.slice(0, 2),
  ].filter(Boolean);
  const confidenceItems = [
    normalizedTrustChecks[0] || { key: 'forecast', label: 'Belastbarkeit', value: 'Noch offen', detail: 'Forecast wird aufgebaut', tone: 'muted' },
    normalizedTrustChecks[1] || { key: 'evidence', label: 'Evidenz', value: 'Noch offen', detail: 'Datenlage wird aktualisiert', tone: 'muted' },
    normalizedTrustChecks[2] || { key: 'readiness', label: 'Einsatzreife', value: 'Noch offen', detail: 'Freigabe steht noch aus', tone: 'muted' },
  ].slice(0, 3);
  const emptyStateSignals = [
    heroRecommendation?.stateLabel || 'Noch kein freigegebener Fokus',
    view.supportState.detail || 'Die Wochenlage bleibt sichtbar, aber noch ohne belastbare Entscheidung.',
    blockers[0] || 'Der nächste Schritt ist zuerst Evidenz oder Regionen zu prüfen.',
  ].filter(Boolean).slice(0, 3);

  if (loading && !view.hasData) {
    return (
      <OperatorSection
        kicker="PEIX x GELO Weekly Briefing"
        title="Wochenplan wird aufgebaut"
        description="Der Fokusfall, die Einordnung und die Prüfpfade werden gerade zusammengestellt."
        tone="muted"
        className="now-template-page now-workspace-shell"
      >
        <div className="now-briefing-skeleton" aria-label="Weekly Briefing wird geladen">
          <div className="now-briefing-skeleton__hero-row">
            <div className="workspace-note-card now-briefing-skeleton__block now-briefing-skeleton__block--hero" />
            <div className="workspace-note-card now-briefing-skeleton__block now-briefing-skeleton__block--aside" />
          </div>
          <div className="now-briefing-skeleton__trust">
            <div className="workspace-note-card now-briefing-skeleton__block" />
            <div className="workspace-note-card now-briefing-skeleton__block" />
            <div className="workspace-note-card now-briefing-skeleton__block" />
          </div>
        </div>
      </OperatorSection>
    );
  }

  return (
    <div className="page-stack now-template-page">
      <OperatorSection
        kicker="PEIX x GELO Weekly Briefing"
        title="Wochenplan: nächster klarer Schritt"
        description="Eine Hauptentscheidung, kurze Vertrauenslage und zwei Folgepfade."
        tone="accent"
        className="now-workspace-shell"
      >
        <div className="now-toolbar">
          <div className="now-toolbar__intro">
            <span className="now-toolbar__eyebrow">Arbeitsfilter</span>
            <div className="now-toolbar__heading">
              <strong>Virus-Kontext</strong>
              <span>Wählt den Arbeitskontext für diese Woche.</span>
            </div>
          </div>
          <OperatorChipRail className="review-chip-row now-toolbar__rail">
            {VIRUS_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onVirusChange(option)}
                className={`tab-chip ${option === virus ? 'active' : ''}`}
                aria-pressed={option === virus}
              >
                {option}
              </button>
            ))}
          </OperatorChipRail>
          <div className="workspace-note-card now-toolbar-note">
            <strong>Stand {formatDateTime(view.generatedAt)}</strong>
            <span>
              Bundesland-Level, {heroRecommendation?.stateLabel || 'ohne belastbare Freigabe'}.
              {' '}
              {view.supportState.label || 'Keine künstliche City-Präzision.'}
            </span>
          </div>
        </div>
        {view.emptyState ? (
          <OperatorPanel
            eyebrow="Status"
            title={view.emptyState.title}
            description={view.emptyState.body}
            tone="muted"
            className="now-briefing-hero now-briefing-hero--weak now-briefing-hero--empty"
          >
            <div className="now-briefing-empty__meta">
              <span>Fokusfall noch offen</span>
              <span>{virus} · h{horizonDays}</span>
            </div>
            <div className="now-briefing-empty__body">
              <div className="now-briefing-empty__summary">
                <span className="now-weekly-plan-card__label">Was fehlt gerade?</span>
                <strong>Noch keine belastbare Kombination aus Regionalsignal, Qualität und Freigabe.</strong>
                <p>Du siehst den Status klar und kannst direkt mit Evidenz oder Regionen weitermachen.</p>
              </div>
              <div className="now-briefing-empty__signals">
                {emptyStateSignals.map((item) => (
                  <div key={item} className="workspace-note-card now-briefing-empty__signal">
                    {item}
                  </div>
                ))}
              </div>
            </div>
            <div className="action-row">
              <button className="media-button" type="button" onClick={onOpenEvidence}>
                Evidenz prüfen
              </button>
              <button className="media-button secondary" type="button" onClick={() => onOpenRegions()}>
                Regionen öffnen
              </button>
            </div>
            {inlineNotes.length > 0 ? (
              <div className="now-inline-notes" aria-live="polite">
                {inlineNotes.map((note) => (
                  <div key={note} className="now-inline-note">
                    <span className="material-symbols-outlined" aria-hidden="true">info</span>
                    <p>{note}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </OperatorPanel>
        ) : heroRecommendation ? (
          <div className="now-briefing-stack">
            <div className="now-command-stage">
              <OperatorPanel
                tone={heroRecommendation.state === 'strong' ? 'accent' : 'default'}
                className={`now-briefing-hero now-briefing-hero--${heroRecommendation.state}`}
              >
                <div className="now-briefing-hero__header">
                  <div>
                    <span className="now-weekly-plan-card__label">Hero Decision Stage</span>
                    <h3 className="now-briefing-hero__title">{heroRecommendation.headline}</h3>
                    <div className="now-briefing-hero__meta">
                      {heroRecommendation.direction} · {heroRecommendation.region}
                    </div>
                  </div>
                  <div className="now-briefing-hero__pills">
                    <span className={`now-state-pill now-state-pill--${heroRecommendation.state}`}>
                      {heroRecommendation.stateLabel}
                    </span>
                  </div>
                </div>

                <p className="now-briefing-hero__copy">{heroRecommendation.whyNow}</p>

                <div className="now-briefing-hero__metrics">
                  {heroMetrics.map((item) => (
                    <div key={item.label} className="now-briefing-hero__metric">
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                    </div>
                  ))}
                </div>

                <div className="now-briefing-hero__facts">
                  <article className="workspace-note-card now-briefing-fact">
                    <span className="now-weekly-plan-card__label">Budgetrahmen</span>
                    <strong>{focusRegion?.budgetLabel && focusRegion.budgetLabel !== '-' ? focusRegion.budgetLabel : 'Noch offen'}</strong>
                    <p>Nur als Bundesland-Kontext, nicht als Scheingenauigkeit.</p>
                  </article>
                  <article className="workspace-note-card now-briefing-fact">
                    <span className="now-weekly-plan-card__label">Warum jetzt</span>
                    <strong>{heroRecommendation.stateLabel}</strong>
                    <p>{heroRecommendation.actionHint || heroSupportText || 'Die Einordnung bleibt sichtbar, aber mit kontrollierter Vorsicht.'}</p>
                  </article>
                </div>

                <div className="action-row">
                  <button
                    className="media-button"
                    type="button"
                    disabled={heroRecommendation.ctaDisabled}
                    onClick={() => (
                      view.primaryRecommendationId
                        ? onOpenRecommendation(view.primaryRecommendationId)
                        : onOpenCampaigns()
                    )}
                  >
                    {heroRecommendation.actionLabel}
                  </button>
                  <button
                    className="media-button secondary"
                    type="button"
                    onClick={() => onOpenRegions(heroRecommendation.regionCode || focusRegion?.code || undefined)}
                  >
                    Bundesland öffnen
                  </button>
                  <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
                    Evidenz prüfen
                  </button>
                </div>

                {heroSupportText ? (
                  <p className="now-briefing-hero__help">{heroSupportText}</p>
                ) : null}

                {inlineNotes.length > 0 ? (
                  <div className="now-inline-notes" aria-live="polite">
                    {inlineNotes.map((note) => (
                      <div key={note} className="now-inline-note">
                        <span className="material-symbols-outlined" aria-hidden="true">info</span>
                        <p>{note}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </OperatorPanel>

              <OperatorPanel
                eyebrow="Secondary Paths"
                title="Danach prüfen"
                description="Zwei nachrangige Pfade nach dem Fokusfall."
                tone="muted"
                className="now-briefing-secondary"
              >
                <div className="now-briefing-secondary__list">
                  {secondaryMoves.length > 0 ? secondaryMoves.map((region, index) => (
                    <button
                      type="button"
                      key={region.code}
                      onClick={() => onOpenRegions(region.code)}
                      className="campaign-list-card now-briefing-secondary__item"
                    >
                      <div className="now-briefing-secondary__index">0{index + 1}</div>
                      <div className="now-briefing-secondary__item-copy">
                        <div className="now-briefing-secondary__item-title">{region.name}</div>
                        <div className="now-briefing-secondary__item-meta">
                          {region.stage} · {region.probabilityLabel}
                        </div>
                        <p>{region.reason}</p>
                      </div>
                    </button>
                  )) : (
                    <div className="workspace-note-card now-briefing-secondary__empty">
                      Aktuell gibt es keine weiteren belastbaren Bundesländer für diese Woche.
                    </div>
                  )}
                </div>
              </OperatorPanel>
            </div>

            <OperatorPanel
              eyebrow="Confidence Strip"
              title="Vertrauenslage auf einen Blick"
              description={trustSummary}
              tone="muted"
              className="now-confidence-strip"
            >
              <div className="now-trust-grid">
                {confidenceItems.map((item) => (
                  <article key={item.key} className={`workspace-status-card workspace-status-card--${item.tone}`}>
                    <span className="workspace-status-card__question">{item.label}</span>
                    <strong>{item.value}</strong>
                    <p>{item.detail}</p>
                  </article>
                ))}
              </div>
            </OperatorPanel>
          </div>
        ) : null}
      </OperatorSection>

      {!view.emptyState ? (
        <>
          <CollapsibleSection
            title="Details bei Bedarf"
            subtitle="Historie und zusätzliche Signale nur dann öffnen, wenn du den Fokusfall tiefer prüfen willst."
          >
            <div className="workspace-two-column">
              <FocusRegionOutlookPanel
                prediction={focusPrediction}
                backtest={focusRegionBacktest}
                loading={focusRegionBacktestLoading}
                horizonDays={horizonDays}
              />

              <OperatorPanel
                title="Signal und Qualität"
                description="Kompakter Zustand der wichtigsten Qualitäts- und Kontextsignale."
              >
                <div className="operator-stat-grid">
                  {qualityStats.map((item) => (
                    <OperatorStat
                      key={item.label}
                      label={item.label}
                      value={item.value}
                      tone="muted"
                    />
                  ))}
                </div>
              </OperatorPanel>
            </div>

            <div className="workspace-two-column">
              <OperatorPanel
                title="Was noch bremsen kann"
                description="Nur die Punkte, die vor dem nächsten Schritt bewusst sichtbar bleiben sollen."
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

              <OperatorPanel
                title="Weitere Hinweise"
                description="Zusätzliche Hinweise, die hilfreich sind, aber nicht die Hauptentscheidung führen."
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

            <WaveOutlookPanel
              virus={virus}
              onVirusChange={onVirusChange}
              result={waveOutlook}
              loading={waveOutlookLoading}
              showVirusSelector={false}
              title="Historischer Markt-Rückblick"
              subtitle={`Das ist der zweite Blick auf ${virus}. Die Karte zeigt die letzte validierte bundesweite Entwicklung und bleibt Hintergrund für die aktuelle Wochenentscheidung.`}
            />

            <WaveSpreadPanel
              virus={virus}
              result={waveRadar}
              loading={waveRadarLoading}
              title="Historische Ausbreitungsreihenfolge"
              subtitle={`Die letzte verfügbare Saison hilft als Hintergrund, ersetzt aber nicht den aktuellen Forecast auf Bundesland-Level für ${virus}.`}
            />
          </CollapsibleSection>
        </>
      ) : null}
    </div>
  );
};

export default NowWorkspace;

function briefingTrustLabel(label?: string | null): string {
  const normalized = String(label || '').trim().toLowerCase();
  if (normalized === 'reliability') return 'Belastbarkeit';
  if (normalized === 'readiness' || normalized === 'readiness / blocker') return 'Einsatzreife & Blocker';
  return label || 'Einordnung';
}
