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
  const qualityStats = (view.quality.length ? view.quality : [{ label: 'Qualität', value: 'Noch offen' }]).slice(0, 4);
  const inlineNotes = [
    ...(view.supportState.detail ? [view.supportState.detail] : []),
    ...blockers.slice(0, 2),
  ].filter(Boolean);
  const heroNotes = inlineNotes.slice(0, 2);
  const confidenceItems = [
    normalizedTrustChecks[0] || { key: 'forecast', label: 'Belastbarkeit', value: 'Noch offen', detail: 'Die Vorhersage wird gerade neu eingeordnet.', tone: 'muted' },
    normalizedTrustChecks[1] || { key: 'evidence', label: 'Evidenz', value: 'Noch offen', detail: 'Die Evidenzlage wird gerade aktualisiert.', tone: 'muted' },
    normalizedTrustChecks[2] || { key: 'readiness', label: 'Einsatzreife', value: 'Noch offen', detail: 'Die operative Freigabe ist noch offen.', tone: 'muted' },
  ].slice(0, 3);
  const decisionTitle = buildDecisionTitle(heroRecommendation, focusRegion);
  const decisionContext = [
    heroRecommendation?.context || view.primaryCampaignContext || null,
    heroRecommendation?.region || focusRegion?.name || null,
    heroRecommendation?.stateLabel || null,
  ].filter(Boolean).join(' · ');
  const heroFacts = [
    {
      label: 'Empfohlene Aktion',
      value: heroRecommendation?.actionLabel || 'Noch offen',
      detail: heroRecommendation?.actionHint || heroSupportText || 'Die Richtung ist sichtbar, die Freigabe bleibt Teil der Bewertung.',
    },
    {
      label: 'Kontext',
      value: heroRecommendation?.context || view.primaryCampaignContext || 'Noch ohne Einordnung',
      detail: `Stand ${formatDateTime(view.generatedAt)}`,
    },
  ];
  const emptyStateSignals = [
    heroRecommendation?.stateLabel || 'Noch kein freigegebener Fokus',
    view.supportState.detail || 'Die Lage bleibt sichtbar, aber noch ohne belastbare Priorisierung.',
    blockers[0] || 'Der nächste sinnvolle Schritt ist die Prüfung von Evidenz oder Regionen.',
  ].filter(Boolean).slice(0, 3);

  if (loading && !view.hasData) {
    return (
      <OperatorSection
        kicker="Wochenplan"
        title="Operative Klarheit wird aufgebaut"
        description="Die Wochenlage, ihre Priorisierung und die belastbaren Prüfpfade werden gerade zusammengestellt."
        tone="muted"
        className="now-template-page now-workspace-shell"
      >
        <div className="now-briefing-skeleton" aria-label="Wochenüberblick wird geladen">
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
        kicker="Wochenplan"
        title="Fokus diese Woche"
        description="Eine klare Richtung zuerst. Vertrauen, Einordnung und weitere Optionen direkt darunter."
        tone="accent"
        className="now-workspace-shell"
      >
        <div className="now-toolbar">
          <div className="now-toolbar__intro">
            <span className="now-toolbar__eyebrow">Wochenlage</span>
            <div className="now-toolbar__heading">
              <strong>Diese Woche</strong>
              <span>Signal lesen, Fokus verstehen, nächsten Schritt sauber einordnen.</span>
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
            <strong>Datenstand {formatDateTime(view.generatedAt)}</strong>
            <span>
              {heroRecommendation?.stateLabel || 'Noch ohne belastbare Freigabe'}
              {' '}· Gilt auf Bundesland-Ebene, nicht für einzelne Städte.
            </span>
          </div>
        </div>
        {view.emptyState ? (
          <OperatorPanel
            eyebrow="Status"
            title={view.emptyState.title}
            description={view.emptyState.body}
            tone="muted"
            className="workspace-zone workspace-zone--hero now-briefing-hero now-briefing-hero--weak now-briefing-hero--empty"
          >
            <div className="now-briefing-empty__meta">
              <span>Noch keine belastbare Aktion</span>
              <span>{virus} · {horizonDays} Tage</span>
            </div>
            <div className="now-briefing-empty__body">
              <div className="now-briefing-empty__summary">
                <span className="now-weekly-plan-card__label">Fokus diese Woche</span>
                <strong>Es gibt erste Signale, aber noch keine belastbare Priorisierung für diese Woche.</strong>
                <p>Die Oberfläche bleibt bewusst zurückhaltend, solange Evidenz und Freigabe nicht ausreichen.</p>
              </div>
              <div className="now-briefing-empty__stage">
                <div className="workspace-note-card now-briefing-empty__signal">
                  <span className="now-weekly-plan-card__label">Was sichtbar bleibt</span>
                  <strong>{emptyStateSignals[0] || 'Noch kein freigegebener Fokus'}</strong>
                  <p>{emptyStateSignals[1] || 'Die Lage bleibt sichtbar, aber noch ohne belastbare Priorisierung.'}</p>
                </div>
                <div className="workspace-note-card now-briefing-empty__signal">
                  <span className="now-weekly-plan-card__label">Sinnvoller nächster Schritt</span>
                  <strong>Evidenz oder Regionen öffnen</strong>
                  <p>{emptyStateSignals[2] || 'Zuerst sollte geklärt werden, ob Evidenz oder Regionen bereits eine tragfähige Richtung zeigen.'}</p>
                </div>
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
            {heroNotes.length > 0 ? (
              <div className="now-inline-notes" aria-live="polite">
                {heroNotes.map((note) => (
                  <div key={note} className="now-inline-note">
                    <span className="material-symbols-outlined" aria-hidden="true">info</span>
                    <p>{note}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </OperatorPanel>
        ) : heroRecommendation ? (
          <div className="now-briefing-stack now-editorial-stage">
              <OperatorPanel
                tone={heroRecommendation.state === 'strong' ? 'accent' : 'default'}
                className={`workspace-zone workspace-zone--hero now-briefing-hero now-briefing-hero--${heroRecommendation.state}`}
              >
                <div className="now-briefing-hero__header">
                  <div>
                    <span className="now-weekly-plan-card__label">Empfohlene Aktion</span>
                    <h3 className="now-briefing-hero__title">{decisionTitle}</h3>
                    <div className="now-briefing-hero__meta">{decisionContext}</div>
                  </div>
                  <div className="now-briefing-hero__pills">
                    <span className={`now-state-pill now-state-pill--${heroRecommendation.state}`}>
                      {heroRecommendation.stateLabel}
                    </span>
                  </div>
                </div>

                <p className="now-briefing-hero__copy">{heroRecommendation.whyNow}</p>

                <div className="now-briefing-hero__facts">
                  {heroFacts.map((item) => (
                    <article key={item.label} className="workspace-note-card now-briefing-fact">
                      <span className="now-weekly-plan-card__label">{item.label}</span>
                      <strong>{item.value}</strong>
                      <p>{item.detail}</p>
                    </article>
                  ))}
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

                {focusRegion?.budgetLabel && focusRegion.budgetLabel !== '-' ? (
                  <p className="now-briefing-hero__help">Budgetrahmen {focusRegion.budgetLabel} · nur zur Einordnung, nicht als exakte Vorgabe.</p>
                ) : null}

                {heroNotes.length > 0 ? (
                  <div className="now-inline-notes" aria-live="polite">
                    {heroNotes.map((note) => (
                      <div key={note} className="now-inline-note">
                        <span className="material-symbols-outlined" aria-hidden="true">info</span>
                        <p>{note}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </OperatorPanel>

              <OperatorPanel
                eyebrow="Belastbarkeit"
                title="Warum wir das diese Woche vertreten können"
                description="Die Empfehlung bleibt nur dann oben, wenn Forecast, Evidenz und Einsatzreife gemeinsam tragen."
                tone="muted"
                className="workspace-zone workspace-zone--trust now-confidence-strip"
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

            <OperatorPanel
              eyebrow="Nächste Schritte"
              title="Was danach sinnvoll geprüft werden kann"
              description="Nur die nächsten belastbaren Optionen bleiben sichtbar. Alles andere bleibt bewusst im Hintergrund."
              tone="muted"
              className="workspace-zone workspace-zone--secondary now-briefing-secondary"
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
                    Aktuell gibt es keine weiteren belastbaren Regionen mit vergleichbarer Relevanz.
                  </div>
                )}
              </div>
            </OperatorPanel>
          </div>
        ) : null}
      </OperatorSection>

      {!view.emptyState ? (
        <>
          <CollapsibleSection
            className="workspace-zone workspace-zone--detail"
            title="Vertiefung (optional)"
            subtitle="Historie, Zusatzsignale und Qualitätsdetails nur öffnen, wenn die Wochenentscheidung tiefer geprüft werden soll."
          >
            <div className="workspace-two-column">
              <FocusRegionOutlookPanel
                prediction={focusPrediction}
                backtest={focusRegionBacktest}
                loading={focusRegionBacktestLoading}
                horizonDays={horizonDays}
              />

            <OperatorPanel
              title="Signalqualität und Kontext"
              description="Verdichteter Blick auf Qualität, Status und Einordnung der wichtigsten Signale."
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
              subtitle={`Die letzte verfügbare Saison hilft als Hintergrund, ersetzt aber nicht die aktuelle Vorhersage auf Bundesland-Ebene für ${virus}.`}
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
  if (normalized === 'reliability') return 'Sicherheit';
  if (normalized === 'readiness' || normalized === 'readiness / blocker') return 'Handlung & Blocker';
  return label || 'Einordnung';
}

function buildDecisionTitle(
  heroRecommendation?: NowPageViewModel['heroRecommendation'] | null,
  focusRegion?: NowPageViewModel['focusRegion'] | null,
): string {
  const direction = String(heroRecommendation?.direction || focusRegion?.stage || 'Prüfen').trim();
  const region = String(heroRecommendation?.region || focusRegion?.name || 'dieses Bundesland').trim();

  if (/aktiv/i.test(direction)) return `${region} jetzt priorisieren.`;
  if (/vorbereit/i.test(direction)) return `${region} jetzt vorbereiten.`;
  if (/beobacht/i.test(direction)) return `${region} eng beobachten.`;
  if (/halt/i.test(direction)) return `${region} stabil halten.`;
  return `${region} jetzt prüfen.`;
}
