import React, { useMemo, useState } from 'react';

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
import { ForecastChart } from './ForecastChart';
import GermanyMap from './GermanyMap';
import Sparkline from './Sparkline';
import { MapRegion } from './types';
import { formatDateTime, VIRUS_OPTIONS } from './cockpitUtils';
import {
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

  // Build regions Record for GermanyMap from forecast predictions
  const mapRegions = useMemo<Record<string, MapRegion>>(() => {
    const regions: Record<string, MapRegion> = {};
    for (const pred of forecast?.predictions || []) {
      regions[pred.bundesland] = {
        name: pred.bundesland_name,
        avg_viruslast: pred.current_known_incidence || 0,
        intensity: pred.event_probability_calibrated || 0,
        trend: pred.trend || '',
        change_pct: pred.change_pct || 0,
        n_standorte: 0,
        signal_score: pred.event_probability_calibrated || 0,
        impact_probability: pred.event_probability_calibrated || 0,
        forecast_direction: pred.trend || '',
        priority_rank: pred.decision_rank ?? pred.rank ?? undefined,
      };
    }
    return regions;
  }, [forecast]);

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
  const [selectedRegionCode, setSelectedRegionCode] = useState<string | null>(null);
  const effectiveRegionCode = selectedRegionCode || focusPrediction?.bundesland || null;
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

  const regionState = (prob: string) => {
    const n = parseFloat(prob) / 100;
    if (n > 0.7) return 'critical';
    if (n > 0.4) return 'elevated';
    if (n > 0.1) return 'watch';
    return 'clear';
  };

  const heroState = (() => {
    const prob = focusPrediction?.event_probability_calibrated ?? 0;
    if (prob > 0.7) return 'critical';
    if (prob > 0.4) return 'elevated';
    if (prob > 0.1) return 'watch';
    return 'clear';
  })();

  if (loading && !view.hasData) {
    return (
      <OperatorSection
        title="Operative Klarheit wird aufgebaut"
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
        title="Fokus diese Woche"
        description="Was PEIX und GELO diese Woche tun sollten. Nächste Schritte, Trust und Detailansichten folgen darunter."
        tone="accent"
        className="now-workspace-shell"
      >
        {/* ── 1. Answer Hero — THE dominant element ── */}
        {focusPrediction ? (
          <div className="answer-hero" data-state={heroState}>
            <div className="answer-hero__signal">
              <span className="answer-hero__dot" />
              <span className="answer-hero__probability">
                {Math.round((focusPrediction?.event_probability_calibrated ?? 0) * 100)}%
              </span>
            </div>
            <h2 className="answer-hero__title">{decisionTitle}</h2>
            <p className="answer-hero__meta">
              {focusPrediction?.bundesland_name} · {virus} · nächste {focusPrediction?.horizon_days || horizonDays} Tage
              {focusPrediction?.change_pct != null && (
                <> · Trend: {focusPrediction.change_pct >= 0 ? '+' : ''}{focusPrediction.change_pct.toFixed(1)}%</>
              )}
            </p>
            <div className="answer-hero__actions">
              {heroRecommendation && !heroRecommendation.ctaDisabled && (
                <button type="button" className="media-button answer-hero__cta" onClick={() => {
                  if (focusRegion?.code) onOpenRegions(focusRegion.code);
                  else onOpenCampaigns();
                }}>
                  {heroRecommendation.actionLabel || 'Details öffnen'}
                </button>
              )}
              <div className="answer-hero__chips">
                {VIRUS_OPTIONS.map((option) => (
                  <button key={option} type="button" onClick={() => onVirusChange(option)}
                    className={`tab-chip ${option === virus ? 'active' : ''}`} aria-pressed={option === virus}>
                    {option}
                  </button>
                ))}
              </div>
            </div>
            <div className="now-next-step" aria-label="Nächster Schritt">
              <span className="now-next-step__label">Nächster Schritt</span>
              <div className="now-next-step__actions">
                <button
                  type="button"
                  className="media-button secondary now-next-step__button"
                  onClick={() => onOpenRegions(focusRegion?.code || undefined)}
                >
                  Regionen öffnen
                </button>
                <button
                  type="button"
                  className="media-button secondary now-next-step__button"
                  onClick={onOpenCampaigns}
                >
                  Kampagnen öffnen
                </button>
                <button
                  type="button"
                  className="media-button secondary now-next-step__button"
                  onClick={onOpenEvidence}
                >
                  Evidenz öffnen
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="answer-hero" data-state="clear">
            <div className="answer-hero__signal">
              <span className="answer-hero__dot" />
              <span className="answer-hero__probability">&mdash;</span>
            </div>
            <h2 className="answer-hero__title">Keine belastbare Aktion diese Woche</h2>
            <p className="answer-hero__meta">
              Keine Region zeigt ausreichende Signale für die nächsten {horizonDays} Tage.
            </p>
            <div className="answer-hero__actions">
              <button type="button" className="media-button secondary" onClick={onOpenEvidence}>Evidenz prüfen</button>
              <button type="button" className="media-button secondary" onClick={() => onOpenRegions()}>Regionen öffnen</button>
            </div>
          </div>
        )}

        {/* ── 2. Map + Chart (side by side) ── */}
        <div className="prediction-hero">
          <div className="prediction-hero__map">
            <GermanyMap
              regions={mapRegions}
              selectedRegion={effectiveRegionCode}
              onSelectRegion={setSelectedRegionCode}
              showProbability
              topRegionCode={sortedPredictions[0]?.bundesland || null}
            />
          </div>
          <div className="prediction-hero__chart">
            <ForecastChart
              timeline={focusRegionBacktest?.timeline || []}
              regionName={focusPrediction?.bundesland_name || ''}
            />
          </div>
        </div>
        <span className="now-data-timestamp">
          Datenstand {formatDateTime(view.generatedAt)} · {heroRecommendation?.stateLabel || 'Prüfung läuft'}
        </span>

        {/* ── 3. Trust as compact bar ── */}
        {confidenceItems.length > 0 && (
          <div className="trust-bar">
            {confidenceItems.map((item) => {
              const toneColor = item.tone === 'success' ? '#22c55e' : item.tone === 'warning' ? '#f97316' : '#94a3b8';
              return (
                <div key={item.key} className={`trust-bar__item trust-bar__item--${item.tone}`}>
                  <span className="trust-bar__label">{item.label}</span>
                  <span className="trust-bar__value">{item.value}</span>
                  <Sparkline data={[3, 5, 4, 6, 5, 7, 6]} color={toneColor} />
                </div>
              );
            })}
          </div>
        )}

        {/* ── 4. Secondary moves ── */}
        {secondaryMoves.length > 0 && (
          <div className="next-regions">
            <h3 className="next-regions__title">Nächste Regionen</h3>
            <div className="next-regions__list">
              {secondaryMoves.map((region, i) => (
                <button key={region.code} type="button" className="next-regions__item" data-state={regionState(region.probabilityLabel)} onClick={() => onOpenRegions(region.code)}>
                  <span className="next-regions__rank">{String(i + 1).padStart(2, '0')}</span>
                  <span className="next-regions__name">{region.name}</span>
                  <span className="next-regions__meta">{region.stage} · {region.probabilityLabel}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </OperatorSection>

      {/* ── 5. Collapsible Vertiefung (unchanged) ── */}
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
