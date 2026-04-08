import React, { useMemo, useState } from 'react';

import {
  useCampaignsPageData,
  useEvidencePageData,
  useNowPageData,
  useRegionsPageData,
} from '../../features/media/useMediaData';
import { RecommendationCard } from '../../types/media';
import GermanyMap from './GermanyMap';
import { ForecastChart } from './ForecastChart';
import { MapRegion } from './types';
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  statusTone,
} from './cockpitUtils';
import {
  OperatorPanel,
  OperatorSection,
} from './operator/OperatorPrimitives';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  horizonDays: number;
  nowData: ReturnType<typeof useNowPageData>;
  regionsData: ReturnType<typeof useRegionsPageData>;
  campaignsData: ReturnType<typeof useCampaignsPageData>;
  evidenceData: ReturnType<typeof useEvidencePageData>;
  onOpenRecommendation: (id: string) => void;
  onOpenRegions: (regionCode?: string) => void;
  onOpenCampaigns: () => void;
  onOpenEvidence: () => void;
}

type SignalPrediction = {
  event_probability_calibrated?: number | null;
  trend?: string | null;
} | null;

const VirusRadarWorkspace: React.FC<Props> = ({
  virus,
  onVirusChange,
  horizonDays,
  nowData,
  regionsData,
  campaignsData,
  evidenceData,
  onOpenRecommendation,
  onOpenRegions,
  onOpenCampaigns,
  onOpenEvidence,
}) => {
  const [selectedRegionCode, setSelectedRegionCode] = useState<string | null>(null);
  const heroRecommendation = nowData.view.heroRecommendation;
  const focusRegion = nowData.view.focusRegion;
  const sortedPredictions = [...(nowData.forecast?.predictions || [])].sort((left, right) => {
    const leftRank = Number(left.decision_rank ?? left.rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.decision_rank ?? right.rank ?? Number.MAX_SAFE_INTEGER);
    return leftRank - rightRank;
  });
  const topPrediction = (
    (focusRegion?.code
      ? sortedPredictions.find((item) => item.bundesland === focusRegion.code)
      : null)
    || sortedPredictions[0]
    || null
  );
  const mapRegions = useMemo<Record<string, MapRegion>>(() => {
    if (regionsData.regionsView?.map?.regions) {
      return regionsData.regionsView.map.regions;
    }

    const fallback: Record<string, MapRegion> = {};
    for (const item of nowData.forecast?.predictions || []) {
      fallback[item.bundesland] = {
        name: item.bundesland_name,
        avg_viruslast: item.current_known_incidence || 0,
        intensity: item.event_probability_calibrated || 0,
        trend: item.trend || '',
        change_pct: item.change_pct || 0,
        n_standorte: 0,
        signal_score: item.event_probability_calibrated || 0,
        impact_probability: item.event_probability_calibrated || 0,
        forecast_direction: item.trend || '',
        priority_rank: item.decision_rank ?? item.rank ?? undefined,
      };
    }
    return fallback;
  }, [nowData.forecast?.predictions, regionsData.regionsView?.map?.regions]);
  const regionLeaderboard = useMemo(() => {
    const regionRows = regionsData.regionsView?.map?.top_regions || [];
    if (regionRows.length > 0) return regionRows.slice(0, 5);

    return sortedPredictions.slice(0, 5).map((item) => ({
      code: item.bundesland,
      name: item.bundesland_name || item.bundesland,
      trend: item.trend || '',
      impact_probability: item.event_probability_calibrated || 0,
      signal_score: item.event_probability_calibrated || 0,
      recommendation_ref: undefined,
      tooltip: undefined,
    }));
  }, [regionsData.regionsView?.map?.top_regions, sortedPredictions]);
  const effectiveRegionCode = selectedRegionCode || focusRegion?.code || regionLeaderboard[0]?.code || null;
  const selectedRegion = effectiveRegionCode ? mapRegions[effectiveRegionCode] : null;
  const decisionHeadline = buildDecisionHeadline(heroRecommendation?.direction, heroRecommendation?.region || focusRegion?.name);
  const recommendationId = focusRegion?.recommendationId || regionLeaderboard[0]?.recommendation_ref?.card_id || null;
  const signalTiles = buildSignalTiles({
    workspaceStatus: nowData.workspaceStatus,
    evidence: evidenceData.evidence,
    campaigns: campaignsData.campaignsView,
    topPrediction,
  });
  const whyNowItems = buildWhyNowItems(nowData.view.reasons, evidenceData.evidence?.signal_stack?.summary?.top_drivers);
  const riskItems = buildRiskItems(nowData.workspaceStatus?.blockers, nowData.view.risks, evidenceData.evidence?.known_limits);
  const campaignCards = (campaignsData.campaignsView?.cards || []).slice(0, 3);
  const topActivation = regionsData.regionsView?.map?.activation_suggestions?.slice(0, 3) || [];
  const evidenceSummary = evidenceData.evidence?.truth_gate?.message
    || evidenceData.evidence?.business_validation?.guidance
    || nowData.workspaceStatus?.summary
    || 'Die Datensicht wird gerade aufgebaut.';
  const chartRegionName = topPrediction?.bundesland_name || focusRegion?.name || '';
  const dataTimestamp = formatDateTime(nowData.view.generatedAt);

  return (
    <div className="page-stack virus-radar-page">
      <OperatorSection
        title="Virus-Radar"
        description="Eine zentrale Entscheidungsseite für Media. Was jetzt wichtig ist, wo gehandelt werden sollte und welche Risiken oder Blocker noch sichtbar bleiben."
        tone="accent"
        className="virus-radar-shell"
      >
        <section className="virus-radar-hero" aria-label="Wochenentscheidung">
          <div className="virus-radar-hero__topline">
            <span className="virus-radar-hero__product">PEIX / GELO / VIRUS-RADAR</span>
            <div className="virus-radar-hero__topline-meta">
              <span>Stand {dataTimestamp}</span>
              <span>{focusRegion?.name || 'Fokus offen'}</span>
              <span>{nowData.workspaceStatus?.data_freshness || 'Datenlage offen'}</span>
            </div>
          </div>

          <div className="virus-radar-hero__copy-wrap">
            <div className="virus-radar-hero__copy">
              <div className="virus-radar-hero__eyebrow">Entscheidung diese Woche</div>
              <h2 className="virus-radar-hero__title">{decisionHeadline}</h2>
              <p className="virus-radar-hero__meta">
                {virus} · {topPrediction?.bundesland_name || focusRegion?.name || 'Bundesland offen'} · nächste {horizonDays} Tage · Stand {dataTimestamp}
              </p>
              <p className="virus-radar-hero__summary">
                {heroRecommendation?.whyNow || nowData.view.summary}
              </p>
              <div className="virus-radar-hero__stats">
                <div className="virus-radar-stat">
                  <span className="virus-radar-stat__label">Signal</span>
                  <strong className="virus-radar-stat__value">
                    {formatProbability(topPrediction?.event_probability_calibrated)}
                  </strong>
                </div>
                <div className="virus-radar-stat">
                  <span className="virus-radar-stat__label">Fokus</span>
                  <strong className="virus-radar-stat__value">{focusRegion?.name || 'Noch offen'}</strong>
                </div>
                <div className="virus-radar-stat">
                  <span className="virus-radar-stat__label">Datenlage</span>
                  <strong className="virus-radar-stat__value">{nowData.workspaceStatus?.data_freshness || 'Noch offen'}</strong>
                </div>
              </div>
              <div className="virus-radar-hero__actions">
                <button
                  type="button"
                  className="media-button"
                  onClick={() => recommendationId && onOpenRecommendation(recommendationId)}
                  disabled={!recommendationId}
                >
                  Empfehlung prüfen
                </button>
                <button type="button" className="media-button secondary" onClick={onOpenEvidence}>
                  Evidenz ansehen
                </button>
                <button type="button" className="media-button secondary" onClick={onOpenCampaigns}>
                  Kampagnen öffnen
                </button>
              </div>
            </div>

            <div className="virus-radar-hero__support">
              <div className="virus-radar-terminal-card">
                <span className="virus-radar-terminal-card__label">Decision Basis</span>
                <strong className="virus-radar-terminal-card__value">
                  {evidenceSummary}
                </strong>
                <span className="virus-radar-terminal-card__detail">
                  {recommendationId ? 'Empfehlung ist direkt öffnbar.' : 'Empfehlung wird noch konkretisiert.'}
                </span>
              </div>

              <div className="virus-radar-virus-switcher" aria-label="Virus wechseln">
                {['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'].map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => onVirusChange(option)}
                    className={`virus-radar-chip ${option === virus ? 'active' : ''}`}
                    aria-pressed={option === virus}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="virus-radar-strip-shell" aria-label="Schnellstatus">
          <div className="virus-radar-strip-shell__header">
            <span className="virus-radar-strip-shell__title">Radar-Tape</span>
            <span className="virus-radar-strip-shell__summary">
              Fünf schnelle Checks für Signal, Evidenz, Datenlage, Kampagnen-Reife und Blocker.
            </span>
          </div>
          <div className="virus-radar-strip">
            {signalTiles.map((tile) => (
              <div key={tile.label} className={`virus-radar-strip__item virus-radar-strip__item--${tile.tone}`}>
                <span className="virus-radar-strip__label">{tile.label}</span>
                <strong className="virus-radar-strip__value">{tile.value}</strong>
                <span className="virus-radar-strip__detail">{tile.detail}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="virus-radar-core-grid">
          <OperatorPanel
            eyebrow="Signal Map"
            title="Deutschland und Regionenleiter"
            description="Karte für Orientierung, Ranking für Reihenfolge. Ein Klick auf ein Bundesland setzt den Fokus."
            className="virus-radar-map-panel"
          >
            <div className="virus-radar-map-panel__body">
              <div className="virus-radar-map-panel__map">
                <GermanyMap
                  regions={mapRegions}
                  selectedRegion={effectiveRegionCode}
                  onSelectRegion={setSelectedRegionCode}
                  showProbability
                  topRegionCode={regionLeaderboard[0]?.code || null}
                />
              </div>

              <div className="virus-radar-ladder">
                <div className="virus-radar-ladder__header">
                  <span>Top-Regionen</span>
                  <button type="button" className="virus-radar-inline-link" onClick={() => onOpenRegions(effectiveRegionCode || undefined)}>
                    Regionenansicht
                  </button>
                </div>
                <div className="virus-radar-ladder__list">
                  {regionLeaderboard.map((row, index) => (
                    <button
                      key={row.code}
                      type="button"
                      className={`virus-radar-ladder__item ${effectiveRegionCode === row.code ? 'is-active' : ''}`}
                      onClick={() => {
                        setSelectedRegionCode(row.code);
                        onOpenRegions(row.code);
                      }}
                    >
                      <span className="virus-radar-ladder__rank">{String(index + 1).padStart(2, '0')}</span>
                      <span className="virus-radar-ladder__name">{row.name}</span>
                      <span className="virus-radar-ladder__probability">{formatProbability(row.impact_probability)}</span>
                    </button>
                  ))}
                </div>
                {selectedRegion ? (
                  <div className="virus-radar-ladder__detail">
                    <strong>{selectedRegion.name || effectiveRegionCode}</strong>
                    <span>Trend {selectedRegion.trend || 'noch offen'} · {formatPercent(Math.abs(selectedRegion.change_pct || 0), 1)} {(selectedRegion.change_pct || 0) >= 0 ? 'hoch' : 'runter'} zur Vorwoche</span>
                  </div>
                ) : null}
              </div>
            </div>
          </OperatorPanel>

          <div className="virus-radar-core-grid__rail">
            <OperatorPanel
              eyebrow="Activation Queue"
              title="Nächste Schritte nach Region"
              description="Welche Bundesländer als Nächstes in der Media-Prüfung landen sollten."
            >
              <div className="virus-radar-queue">
                {topActivation.length > 0 ? topActivation.map((item) => (
                  <div key={item.region} className="virus-radar-queue__item">
                    <div>
                      <strong>{item.region_name}</strong>
                      <span>{item.priority} · {formatProbability(item.impact_probability)}</span>
                    </div>
                    <span>{item.reason}</span>
                  </div>
                )) : (
                  <div className="virus-radar-empty">Noch keine regionale Reihenfolge vorhanden.</div>
                )}
              </div>
            </OperatorPanel>

            <OperatorPanel
              eyebrow="Campaign Readiness"
              title="Was kampagnenreif ist"
              description="Die wichtigsten Vorschläge, damit Analyse in Handlung übergeht."
            >
              <div className="virus-radar-campaigns">
                {campaignCards.length > 0 ? campaignCards.map((card) => (
                  <CampaignReadinessCard
                    key={card.id}
                    card={card}
                    onOpen={() => onOpenRecommendation(card.id)}
                  />
                )) : (
                  <div className="virus-radar-empty">Noch keine Kampagnenvorschläge sichtbar.</div>
                )}
              </div>
            </OperatorPanel>
          </div>
        </section>

        <section className="virus-radar-analysis-grid">
          <OperatorPanel
            eyebrow="Trend Board"
            title="Dynamik der Fokusregion"
            description="Nicht nur wo das Signal ist, sondern ob es sich stabil aufbaut."
          >
            <div className="virus-radar-trend">
              <ForecastChart
                timeline={nowData.focusRegionBacktest?.timeline || []}
                regionName={chartRegionName}
              />
              <div className="virus-radar-trend__summary">
                <strong>{chartRegionName || 'Fokusregion'}</strong>
                <span>
                  {topPrediction?.change_pct != null
                    ? `Veränderung zur Vorwoche: ${topPrediction.change_pct >= 0 ? '+' : ''}${topPrediction.change_pct.toFixed(1)}%`
                    : 'Verlauf wird gerade aufgebaut.'}
                </span>
              </div>
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Why Now"
            title="Was die Entscheidung trägt"
            description="Die wichtigsten Treiber in Klartext, damit man nicht erst mehrere Seiten lesen muss."
          >
            <div className="virus-radar-list">
              {whyNowItems.map((item) => (
                <div key={item} className="virus-radar-list__item">{item}</div>
              ))}
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Decision Risk"
            title="Was noch bremst"
            description="Unsicherheiten und Blocker bleiben sichtbar, damit die Entscheidung ehrlich bleibt."
          >
            <div className="virus-radar-list virus-radar-list--risk">
              {riskItems.map((item) => (
                <div key={item} className="virus-radar-list__item">{item}</div>
              ))}
            </div>
          </OperatorPanel>
        </section>
      </OperatorSection>
    </div>
  );
};

function buildDecisionHeadline(direction?: string | null, region?: string | null): string {
  const cleanDirection = String(direction || 'Prüfen').trim().toLowerCase();
  const cleanRegion = String(region || 'Dieses Bundesland').trim();

  if (cleanDirection.includes('aktiv')) return `${cleanRegion} jetzt priorisieren`;
  if (cleanDirection.includes('vorbereit')) return `${cleanRegion} jetzt vorbereiten`;
  if (cleanDirection.includes('beobacht')) return `${cleanRegion} eng beobachten`;
  return `${cleanRegion} jetzt prüfen`;
}

function formatProbability(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  const percent = value <= 1 ? value * 100 : value;
  return formatPercent(percent, 0);
}

function buildSignalTiles({
  workspaceStatus,
  evidence,
  campaigns,
  topPrediction,
}: {
  workspaceStatus: ReturnType<typeof useNowPageData>['workspaceStatus'];
  evidence: ReturnType<typeof useEvidencePageData>['evidence'];
  campaigns: ReturnType<typeof useCampaignsPageData>['campaignsView'];
  topPrediction: SignalPrediction;
}) {
  return [
    {
      label: 'Signalstärke',
      value: formatProbability(topPrediction?.event_probability_calibrated),
      detail: topPrediction?.trend ? `Trend ${topPrediction.trend}` : 'Trend wird eingeordnet',
      tone: scoreTone(topPrediction?.event_probability_calibrated),
    },
    {
      label: 'Evidenz',
      value: evidence?.truth_gate?.state || evidence?.business_validation?.validation_status || 'Noch offen',
      detail: evidence?.truth_gate?.message || 'Truth- und Business-Lage für diese Woche',
      tone: stateTone(evidence?.truth_gate?.passed ? 'success' : 'warning'),
    },
    {
      label: 'Datenfrische',
      value: workspaceStatus?.data_freshness || 'Noch offen',
      detail: workspaceStatus?.summary || 'Datenstand wird geladen',
      tone: stateTone(workspaceStatus?.data_freshness),
    },
    {
      label: 'Kampagnen-Reife',
      value: campaigns?.summary.publishable_cards != null ? String(campaigns.summary.publishable_cards) : '-',
      detail: campaigns?.summary.active_cards != null ? `${campaigns.summary.active_cards} aktive Vorschläge` : 'Noch keine Kampagnen geladen',
      tone: stateTone((campaigns?.summary.publishable_cards || 0) > 0 ? 'success' : 'warning'),
    },
    {
      label: 'Blocker',
      value: workspaceStatus?.blocker_count != null ? String(workspaceStatus.blocker_count) : '-',
      detail: workspaceStatus?.open_blockers || 'Keine offenen Blocker',
      tone: stateTone((workspaceStatus?.blocker_count || 0) > 0 ? 'danger' : 'success'),
    },
  ];
}

function buildWhyNowItems(
  reasons: string[],
  drivers?: Array<{ label: string; strength_pct: number }>,
): string[] {
  const driverLines = (drivers || []).slice(0, 2).map((driver) => `${driver.label} trägt aktuell ${formatPercent(driver.strength_pct, 0)} zum Signal bei.`);
  const combined = [...reasons.slice(0, 3), ...driverLines].filter(Boolean);
  return combined.length > 0 ? combined : ['Noch keine klare Kurzbegründung vorhanden.'];
}

function buildRiskItems(
  blockers?: string[],
  risks?: string[],
  knownLimits?: string[],
): string[] {
  const combined = [...(blockers || []), ...(risks || []), ...(knownLimits || [])].filter(Boolean);
  return combined.slice(0, 4).length > 0 ? combined.slice(0, 4) : ['Aktuell sind keine zusätzlichen Risiken dokumentiert.'];
}

function scoreTone(value?: number | null): 'success' | 'warning' | 'danger' | 'neutral' {
  if (value == null || Number.isNaN(value)) return 'neutral';
  const normalized = value <= 1 ? value : value / 100;
  if (normalized >= 0.7) return 'danger';
  if (normalized >= 0.4) return 'warning';
  return 'success';
}

function stateTone(value?: string | boolean | null): 'success' | 'warning' | 'danger' | 'neutral' {
  const normalized = String(value || '').toLowerCase();
  if (value === true) return 'success';
  if (normalized.includes('krit') || normalized.includes('block') || normalized.includes('offen') || normalized.includes('fehl')) {
    return 'danger';
  }
  if (normalized.includes('watch') || normalized.includes('warn') || normalized.includes('vorsicht') || normalized.includes('aufbau')) {
    return 'warning';
  }
  if (normalized.includes('ok') || normalized.includes('ready') || normalized.includes('aktuell') || normalized.includes('fresh') || normalized.includes('go')) {
    return 'success';
  }
  return 'neutral';
}

const CampaignReadinessCard: React.FC<{ card: RecommendationCard; onOpen: () => void }> = ({ card, onOpen }) => {
  const tone = statusTone(card.lifecycle_state || card.status_label || card.status);
  return (
    <button type="button" className="virus-radar-campaign-card" onClick={onOpen}>
      <div className="virus-radar-campaign-card__header">
        <strong>{card.display_title || card.campaign_name || card.region || 'Vorschlag'}</strong>
        <span style={{ background: tone.background, color: tone.color, border: tone.border }}>
          {card.lifecycle_state || card.status_label || card.status}
        </span>
      </div>
      <span>{card.reason || card.decision_brief?.summary_sentence || 'Noch keine Kurzbegründung vorhanden.'}</span>
      <div className="virus-radar-campaign-card__meta">
        <span>{card.region || 'Bundesland offen'}</span>
        <span>{formatCurrency(card.campaign_preview?.budget?.weekly_budget_eur)}</span>
      </div>
    </button>
  );
};

export default VirusRadarWorkspace;
