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

  if (loading && !view.hasData) {
    return (
      <OperatorSection
        kicker="PEIX x GELO Weekly Briefing"
        title="Was diese Woche zuerst geprüft werden sollte"
        description="Wir bauen gerade das Wochenbriefing auf. Gleich siehst du wieder den Fokus, die Alternativen und die Vertrauenslage."
        tone="muted"
        className="now-template-page operator-toolbar-shell"
      >
        <div className="now-briefing-skeleton" aria-label="Weekly Briefing wird geladen">
          <div className="workspace-note-card now-briefing-skeleton__block now-briefing-skeleton__block--hero" />
          <div className="workspace-note-card now-briefing-skeleton__block now-briefing-skeleton__block--secondary" />
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
        title="Was diese Woche zuerst geprüft werden sollte"
        description="Die Ansicht beantwortet zuerst: welche Maßnahme, in welchem Bundesland und mit welcher Vertrauenslage."
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
        {view.emptyState ? (
          <OperatorPanel
            eyebrow="Empfohlener Fokus diese Woche"
            title={view.emptyState.title}
            description={view.emptyState.body}
            tone="muted"
            className="now-briefing-hero now-briefing-hero--weak"
          >
            <div className="action-row">
              <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
                Evidenz prüfen
              </button>
              <button className="media-button secondary" type="button" onClick={() => onOpenRegions()}>
                Regionen öffnen
              </button>
            </div>
          </OperatorPanel>
        ) : heroRecommendation ? (
          <div className="now-briefing-stack">
            <OperatorPanel
              tone={heroRecommendation.state === 'strong' ? 'accent' : 'default'}
              className={`now-briefing-hero now-briefing-hero--${heroRecommendation.state}`}
            >
              <div className="now-briefing-hero__header">
                <div>
                  <span className="now-weekly-plan-card__label">Empfohlener Fokus diese Woche</span>
                  <h3 className="now-briefing-hero__title">{heroRecommendation.headline}</h3>
                </div>
                <div className="now-briefing-hero__pills">
                  <span className={`now-state-pill now-state-pill--${heroRecommendation.state}`}>
                    {heroRecommendation.stateLabel}
                  </span>
                  <span className="step-chip">{heroRecommendation.direction}</span>
                  <span className="step-chip">Bundesland-Level</span>
                  {view.supportState.label ? <span className="step-chip">{view.supportState.label}</span> : null}
                </div>
              </div>

              <p className="now-briefing-hero__copy">{heroRecommendation.whyNow}</p>

              <div className="now-briefing-hero__facts">
                <article className="workspace-note-card now-briefing-fact">
                  <span className="now-weekly-plan-card__label">Bundesland</span>
                  <strong>{heroRecommendation.region}</strong>
                  <p>Die Empfehlung bleibt bewusst auf Bundesland-Level.</p>
                </article>
                <article className="workspace-note-card now-briefing-fact">
                  <span className="now-weekly-plan-card__label">Kontext</span>
                  <strong>{heroRecommendation.context}</strong>
                  <p>{focusRegion?.budgetLabel && focusRegion.budgetLabel !== '-' ? `Budgetrahmen ${focusRegion.budgetLabel}` : 'Kein erfundener Budgetwert, nur vorhandener Kontext.'}</p>
                </article>
              </div>

              {heroRecommendation.actionHint ? (
                <div className="workspace-note-card now-briefing-callout">
                  <strong>{heroRecommendation.stateLabel}</strong>
                  <p>{heroRecommendation.actionHint}</p>
                </div>
              ) : null}

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

              {view.supportState.detail && !heroRecommendation.ctaDisabled ? (
                <p className="now-briefing-hero__help">{view.supportState.detail}</p>
              ) : null}
            </OperatorPanel>

            <OperatorPanel
              eyebrow="Danach im Blick"
              title="Die zwei nächsten Prüfpfade"
              description="Damit du Alternativen siehst, ohne wieder in ein gleichwertiges Dashboard zu rutschen."
              tone="muted"
              className="now-briefing-secondary"
            >
              <div className="now-briefing-secondary__list">
                {secondaryMoves.length > 0 ? secondaryMoves.map((region) => (
                  <button
                    type="button"
                    key={region.code}
                    onClick={() => onOpenRegions(region.code)}
                    className="campaign-list-card now-briefing-secondary__item"
                  >
                    <div className="now-briefing-secondary__item-copy">
                      <div className="now-briefing-secondary__item-title">{region.name}</div>
                      <div className="now-briefing-secondary__item-meta">
                        {region.stage} · {region.probabilityLabel}
                      </div>
                    </div>
                    <p>{region.reason}</p>
                  </button>
                )) : (
                  <div className="workspace-note-card now-briefing-secondary__empty">
                    Aktuell gibt es keine weiteren belastbaren Bundesländer für diese Woche.
                  </div>
                )}
              </div>
            </OperatorPanel>
          </div>
        ) : null}
      </OperatorSection>

      {!view.emptyState ? (
        <>
          <OperatorSection
            title="Was die Empfehlung trägt"
            description={trustSummary}
            tone="muted"
            className="workspace-status-panel now-briefing-trust"
          >
            <div className="now-trust-grid">
              {normalizedTrustChecks.map((item) => (
                <article
                  key={item.key}
                  className={`workspace-status-card workspace-status-card--${item.tone}`}
                >
                  <span className="workspace-status-card__question">{item.label}</span>
                  <strong>{item.value}</strong>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>

            <div className="workspace-status-panel__footer">
              <span>{heroRecommendation?.actionHint || view.supportState.detail || trustSummary}</span>
              <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
                Evidenz prüfen
              </button>
            </div>
          </OperatorSection>

          <div className="now-proof-stage now-briefing-support">
            <FocusRegionOutlookPanel
              prediction={focusPrediction}
              backtest={focusRegionBacktest}
              loading={focusRegionBacktestLoading}
              horizonDays={horizonDays}
            />
          </div>

          <CollapsibleSection
            title="Zweiter Blick"
            subtitle="Historie, offene Punkte und Hintergrund nur wenn du tiefer einsteigen möchtest."
          >
            <div className="workspace-two-column">
              <OperatorPanel
                title="Warum die Fokusregion vorne liegt"
                description="Hier stehen die zusätzlichen Begründungen hinter der Wochenempfehlung."
              >
                <div className="workspace-note-list">
                  <div className="workspace-note-card">{heroRecommendation?.context || view.primaryCampaignContext || 'Bundesland-Level-Kontext noch offen.'}</div>
                  {leadReasons.length > 0 ? leadReasons.map((reason) => (
                    <div key={reason} className="workspace-note-card">
                      {reason}
                    </div>
                  )) : (
                    <div className="workspace-note-card">Noch keine zusätzliche Kurzbegründung verfügbar.</div>
                  )}
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
