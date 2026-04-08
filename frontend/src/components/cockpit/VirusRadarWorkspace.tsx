import React, { useMemo, useState } from 'react';

import {
  useCampaignsPageData,
  useEvidencePageData,
  useNowPageData,
  useRegionsPageData,
} from '../../features/media/useMediaData';
import { VirusRadarHeroForecastData } from '../../features/media/virusRadarHeroForecast';
import { RecommendationCard } from '../../types/media';
import GermanyMap from './GermanyMap';
import { ForecastChart } from './ForecastChart';
import { MultiVirusForecastChart } from './MultiVirusForecastChart';
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
  heroForecastLoading: boolean;
  heroForecast: VirusRadarHeroForecastData;
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

type RegionLeaderboardRow = {
  code: string;
  name: string;
  trend?: string;
  impact_probability?: number;
  signal_score?: number;
  recommendation_ref?: { card_id?: string } | null;
  tooltip?: unknown;
};

const VirusRadarWorkspace: React.FC<Props> = ({
  virus,
  onVirusChange,
  horizonDays,
  heroForecastLoading,
  heroForecast,
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
  const regionLeaderboard = useMemo<RegionLeaderboardRow[]>(() => {
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
  const activationByRegion = useMemo(() => {
    const entries = regionsData.regionsView?.map?.activation_suggestions || [];
    return new Map(entries.map((item) => [item.region, item] as const));
  }, [regionsData.regionsView?.map?.activation_suggestions]);
  const predictionByRegion = useMemo(() => {
    return new Map(sortedPredictions.map((item) => [item.bundesland, item] as const));
  }, [sortedPredictions]);
  const defaultHeroRegionCode = (
    regionsData.regionsView?.map?.activation_suggestions?.[0]?.region
    || regionsData.regionsView?.map?.top_regions?.[0]?.code
    || focusRegion?.code
    || regionLeaderboard[0]?.code
    || sortedPredictions[0]?.bundesland
    || null
  );
  const heroRegionLeaderboardEntry = defaultHeroRegionCode
    ? regionLeaderboard.find((row) => row.code === defaultHeroRegionCode) || null
    : null;
  const heroRegion = defaultHeroRegionCode ? mapRegions[defaultHeroRegionCode] || null : null;
  const heroActivation = defaultHeroRegionCode
    ? (regionsData.regionsView?.map?.activation_suggestions || []).find((item) => item.region === defaultHeroRegionCode) || null
    : null;
  const heroPrediction = (
    (defaultHeroRegionCode
      ? sortedPredictions.find((item) => item.bundesland === defaultHeroRegionCode)
      : null)
    || null
  );
  const heroRegionName = (
    heroRegion?.name
    || heroRegionLeaderboardEntry?.name
    || heroActivation?.region_name
    || heroPrediction?.bundesland_name
    || focusRegion?.name
    || heroRecommendation?.region
    || null
  );
  const heroSignalProbability = (
    heroPrediction?.event_probability_calibrated
    ?? heroRegion?.impact_probability
    ?? heroRegion?.signal_score
    ?? heroRegionLeaderboardEntry?.impact_probability
    ?? heroRegionLeaderboardEntry?.signal_score
    ?? null
  );
  const heroTrend = heroPrediction?.trend || heroRegion?.trend || heroRegionLeaderboardEntry?.trend || null;
  const heroChangePct = heroPrediction?.change_pct ?? heroRegion?.change_pct ?? null;
  const effectiveRegionCode = selectedRegionCode || defaultHeroRegionCode;
  const selectedRegion = effectiveRegionCode ? mapRegions[effectiveRegionCode] : null;
  const selectedActivation = effectiveRegionCode ? activationByRegion.get(effectiveRegionCode) || null : null;
  const selectedPrediction = effectiveRegionCode ? predictionByRegion.get(effectiveRegionCode) || null : null;
  const topVirusSummary = heroForecast.summaries[0] || null;
  const secondVirusSummary = heroForecast.summaries[1] || null;
  const heroHasData = heroForecast.availableViruses.length > 0;
  const heroIsLoading = heroForecastLoading && !heroHasData;
  const recommendationId = (
    heroRegionLeaderboardEntry?.recommendation_ref?.card_id
    || (
      defaultHeroRegionCode && defaultHeroRegionCode === focusRegion?.code
        ? focusRegion?.recommendationId
        : null
    )
    || regionLeaderboard[0]?.recommendation_ref?.card_id
    || null
  );
  const signalTiles = buildSignalTiles({
    workspaceStatus: nowData.workspaceStatus,
    evidence: evidenceData.evidence,
    campaigns: campaignsData.campaignsView,
    topPrediction: {
      event_probability_calibrated: heroSignalProbability,
      trend: heroTrend,
    },
  });
  const chartRegionName = heroRegionName || '';
  const selectedRegionStage = resolveRegionStage(
    selectedActivation?.priority,
    selectedPrediction?.decision_label,
    selectedRegion?.impact_probability ?? selectedRegion?.signal_score ?? null,
  );
  const selectedRegionStageTone = regionStageTone(selectedRegionStage);
  const selectedRegionDetail = buildRegionDetail({
    regionName: selectedRegion?.name || chartRegionName || effectiveRegionCode || 'Fokusregion',
    stage: selectedRegionStage,
    trend: selectedRegion?.trend || selectedPrediction?.trend || null,
    changePct: selectedRegion?.change_pct ?? selectedPrediction?.change_pct ?? null,
    impactProbability: selectedRegion?.impact_probability ?? selectedRegion?.signal_score ?? selectedPrediction?.event_probability_calibrated ?? null,
    reason: selectedActivation?.reason || selectedRegion?.priority_explanation || null,
  });
  const whyNowItems = buildWhyNowItems(nowData.view.reasons, evidenceData.evidence?.signal_stack?.summary?.top_drivers);
  const riskItems = buildRiskItems(nowData.workspaceStatus?.blockers, nowData.view.risks, evidenceData.evidence?.known_limits);
  const whyNowModel = buildWhyNowModel({
    regionName: chartRegionName,
    virus,
    items: whyNowItems,
  });
  const riskModel = buildRiskModel({
    regionName: chartRegionName,
    items: riskItems,
  });
  const campaignCards = (campaignsData.campaignsView?.cards || []).slice(0, 3);
  const topActivation = regionsData.regionsView?.map?.activation_suggestions?.slice(0, 3) || [];
  const dataTimestamp = formatDateTime(nowData.view.generatedAt);
  const trendInsight = buildTrendInsight({
    regionName: chartRegionName,
    changePct: heroChangePct,
    trend: heroTrend,
    virus,
    hasTimeline: (nowData.focusRegionBacktest?.timeline || []).length > 0,
  });
  const heroEyebrow = heroIsLoading
    ? 'Live-Lagebild wird geladen'
    : `Live-Lagebild · ${heroForecast.availableViruses.length} Viren`;
  const heroHeadlinePrimary = heroIsLoading
    ? 'Das gemeinsame 4-Virus-Lagebild wird geladen.'
    : heroForecast.headlinePrimary;
  const heroHeadlineSecondary = heroIsLoading
    ? 'Die 7-Tage-Prognose wird gerade aufgebaut.'
    : heroForecast.headlineSecondary;
  const heroSummary = heroIsLoading
    ? 'Die Prognosekurven werden im Hintergrund geladen. Sobald sie da sind, siehst du hier wieder das gemeinsame Lagebild der nächsten sieben Tage.'
    : heroForecast.summary;
  const heroPrimaryStat = heroIsLoading
    ? 'Wird geladen'
    : topVirusSummary
      ? `${topVirusSummary.virus} ${formatSignedPercent(topVirusSummary.deltaPct)}`
      : 'Noch offen';
  const heroSecondaryStat = heroIsLoading
    ? 'Wird geladen'
    : secondVirusSummary
      ? `${secondVirusSummary.virus} ${formatSignedPercent(secondVirusSummary.deltaPct)}`
      : 'Noch offen';

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
              <span>{heroRegionName || 'Fokus offen'}</span>
              <span>{nowData.workspaceStatus?.data_freshness || 'Datenlage offen'}</span>
            </div>
          </div>

          <div className="virus-radar-hero__eyebrow">
            <span className="virus-radar-hero__pulse" aria-hidden="true" />
            {heroEyebrow}
          </div>
          <h2 className="virus-radar-hero__headline">
            <span>{heroHeadlinePrimary}</span>
            <span className="virus-radar-hero__headline-accent">{heroHeadlineSecondary}</span>
          </h2>
          <p className="virus-radar-hero__summary virus-radar-hero__summary--lead">
            {heroSummary}
          </p>

          <div className="virus-radar-hero-chart-card">
            <div className="virus-radar-hero-chart-card__meta">
              <div className="virus-radar-hero-chart-card__legend">
                <div className="virus-radar-hero-chart-card__legend-item">
                  <span className="virus-radar-hero-chart-card__swatch virus-radar-hero-chart-card__swatch--influenza-a" />
                  Influenza A
                </div>
                <div className="virus-radar-hero-chart-card__legend-item">
                  <span className="virus-radar-hero-chart-card__swatch virus-radar-hero-chart-card__swatch--influenza-b" />
                  Influenza B
                </div>
                <div className="virus-radar-hero-chart-card__legend-item">
                  <span className="virus-radar-hero-chart-card__swatch virus-radar-hero-chart-card__swatch--sars-cov-2" />
                  SARS-CoV-2
                </div>
                <div className="virus-radar-hero-chart-card__legend-item">
                  <span className="virus-radar-hero-chart-card__swatch virus-radar-hero-chart-card__swatch--rsv-a" />
                  RSV A
                </div>
                <div className="virus-radar-hero-chart-card__legend-item virus-radar-hero-chart-card__legend-item--explain">
                  Heute = 100
                </div>
                <div className="virus-radar-hero-chart-card__legend-item virus-radar-hero-chart-card__legend-item--explain">
                  Forecast · {horizonDays} Tage
                </div>
              </div>
              <div className="virus-radar-hero-chart-card__stamp">
                <strong>Vier Viren im Vergleich</strong>
                <span>Stand {dataTimestamp}</span>
              </div>
            </div>
            <MultiVirusForecastChart
              data={heroForecast.chartData}
              className="virus-radar-hero-chart"
              loading={heroIsLoading}
            />
          </div>

          <div className="virus-radar-hero__footer">
            <div className="virus-radar-hero__stats">
              <div className="virus-radar-stat">
                <span className="virus-radar-stat__label">Stärkster Anstieg</span>
                <strong className="virus-radar-stat__value">{heroPrimaryStat}</strong>
              </div>
              <div className="virus-radar-stat">
                <span className="virus-radar-stat__label">Danach</span>
                <strong className="virus-radar-stat__value">{heroSecondaryStat}</strong>
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
            <div className="virus-radar-hero__support">
              <p className="virus-radar-hero__support-copy">
                {recommendationId
                  ? 'Oben siehst du das gemeinsame Virus-Lagebild. Die Karte, Regionen und Kampagnen darunter folgen weiter dem aktuell gewählten Virus.'
                  : 'Oben siehst du das gemeinsame Virus-Lagebild. Die konkrete Aktivierung wird darunter weiter nach Virus und Bundesland verdichtet.'}
              </p>

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
            description="Die Regionen-Leiter zeigt, wo diese Woche zuerst hingeschaut werden sollte. Die Karte bestätigt das räumliche Muster."
            className="virus-radar-map-panel"
          >
            <div className="virus-radar-map-panel__body">
              <div className="virus-radar-ladder">
                <div className="virus-radar-ladder__header">
                  <span>Wichtigste Regionen diese Woche</span>
                  <button type="button" className="virus-radar-inline-link" onClick={() => onOpenRegions(effectiveRegionCode || undefined)}>
                    Regionenansicht
                  </button>
                </div>
                <div className="virus-radar-ladder__focus">
                  <span className="virus-radar-ladder__focus-label">Fokusregion</span>
                  <div className="virus-radar-ladder__focus-head">
                    <strong>{selectedRegionDetail.regionName}</strong>
                    <span className={`virus-radar-ladder__stage virus-radar-ladder__stage--${selectedRegionStageTone}`}>
                      {selectedRegionStage}
                    </span>
                  </div>
                  <span className="virus-radar-ladder__focus-meta">
                    {selectedRegionDetail.meta}
                  </span>
                  <p className="virus-radar-ladder__focus-copy">
                    {selectedRegionDetail.copy}
                  </p>
                </div>
                <div className="virus-radar-ladder__list">
                  {regionLeaderboard.map((row, index) => (
                    <RegionLadderRow
                      key={row.code}
                      row={row}
                      index={index}
                      isActive={effectiveRegionCode === row.code}
                      stage={resolveRegionStage(
                        activationByRegion.get(row.code)?.priority,
                        predictionByRegion.get(row.code)?.decision_label,
                        row.impact_probability ?? row.signal_score ?? null,
                      )}
                      onSelect={() => {
                        setSelectedRegionCode(row.code);
                        onOpenRegions(row.code);
                      }}
                    />
                  ))}
                </div>
              </div>

              <div className="virus-radar-map-panel__map">
                <GermanyMap
                  regions={mapRegions}
                  selectedRegion={effectiveRegionCode}
                  onSelectRegion={setSelectedRegionCode}
                  showProbability
                  topRegionCode={regionLeaderboard[0]?.code || null}
                  variant="radar"
                />
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
              <div className="virus-radar-trend__lead">
                <div className="virus-radar-trend__narrative">
                  <span className="virus-radar-trend__eyebrow">Diese Woche</span>
                  <strong className={`virus-radar-trend__headline virus-radar-trend__headline--${trendInsight.tone}`}>
                    {trendInsight.headline}
                  </strong>
                  <p className="virus-radar-trend__copy">
                    {trendInsight.copy}
                  </p>
                </div>
                <div className={`virus-radar-trend__metric virus-radar-trend__metric--${trendInsight.tone}`}>
                  <span className="virus-radar-trend__metric-label">Zur Vorwoche</span>
                  <strong className="virus-radar-trend__metric-value">{trendInsight.metricValue}</strong>
                  <span className="virus-radar-trend__metric-detail">{trendInsight.metricDetail}</span>
                </div>
              </div>
              <ForecastChart
                timeline={nowData.focusRegionBacktest?.timeline || []}
                regionName={chartRegionName}
                className="virus-radar-trend__chart"
              />
              <div className="virus-radar-trend__summary">
                <strong>{chartRegionName || 'Fokusregion'}</strong>
                <span>{trendInsight.footer}</span>
              </div>
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Why Now"
            title="Was die Entscheidung trägt"
            description="Die wichtigsten Treiber in Klartext, damit man nicht erst mehrere Seiten lesen muss."
          >
            <div className="virus-radar-explain virus-radar-explain--why">
              <div className="virus-radar-explain__lead">
                <span className="virus-radar-explain__eyebrow">Kurz gesagt</span>
                <strong className="virus-radar-explain__headline">{whyNowModel.headline}</strong>
                <p className="virus-radar-explain__copy">{whyNowModel.copy}</p>
              </div>
              <div className="virus-radar-list virus-radar-list--detail">
                {whyNowModel.items.map((item, index) => (
                  <div key={`${item}-${index}`} className="virus-radar-list__item virus-radar-list__item--detail">
                    <span className="virus-radar-list__index">{String(index + 1).padStart(2, '0')}</span>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Decision Risk"
            title="Was noch bremst"
            description="Unsicherheiten und Blocker bleiben sichtbar, damit die Entscheidung ehrlich bleibt."
          >
            <div className="virus-radar-explain virus-radar-explain--risk">
              <div className="virus-radar-explain__lead virus-radar-explain__lead--risk">
                <span className="virus-radar-explain__eyebrow">Freigabe-Risiko</span>
                <strong className="virus-radar-explain__headline virus-radar-explain__headline--risk">{riskModel.headline}</strong>
                <p className="virus-radar-explain__copy">{riskModel.copy}</p>
              </div>
              <div className="virus-radar-list virus-radar-list--risk virus-radar-list--detail">
                {riskModel.items.map((item, index) => (
                  <div key={`${item}-${index}`} className="virus-radar-list__item virus-radar-list__item--detail">
                    <span className="virus-radar-list__index virus-radar-list__index--risk">{String(index + 1).padStart(2, '0')}</span>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          </OperatorPanel>
        </section>
      </OperatorSection>
    </div>
  );
};

function formatProbability(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  const percent = value <= 1 ? value * 100 : value;
  return formatPercent(percent, 0);
}

function formatSignedPercent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value >= 0 ? '+' : ''}${value.toFixed(0)}%`;
}

function formatSignedPercentPrecise(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

function buildTrendInsight({
  regionName,
  changePct,
  trend,
  virus,
  hasTimeline,
}: {
  regionName: string;
  changePct?: number | null;
  trend?: string | null;
  virus: string;
  hasTimeline: boolean;
}): {
  tone: 'rising' | 'falling' | 'steady' | 'pending';
  headline: string;
  copy: string;
  metricValue: string;
  metricDetail: string;
  footer: string;
} {
  if (!hasTimeline) {
    return {
      tone: 'pending',
      headline: 'Signal wird gerade aufgebaut.',
      copy: 'Sobald genügend Verlaufspunkte vorliegen, wird hier sichtbar, ob sich das Signal wirklich aufbaut oder wieder abkühlt.',
      metricValue: '-',
      metricDetail: regionName || 'Fokusregion',
      footer: `Der 7-Tage-Verlauf für ${virus} wird gerade geladen.`,
    };
  }

  const safeRegionName = regionName || 'Die Fokusregion';
  const roundedDelta = formatSignedPercentPrecise(changePct);
  const trendLabel = trend ? `Trend ${trend}` : 'Trend wird eingeordnet';

  if (changePct == null || Number.isNaN(changePct)) {
    return {
      tone: 'pending',
      headline: 'Verlauf sichtbar, Vorwochenvergleich noch offen.',
      copy: `${safeRegionName} ist bereits als Verlauf sichtbar. Der Vergleich zur Vorwoche wird nachgezogen, sobald der Referenzwert vollständig vorliegt.`,
      metricValue: '-',
      metricDetail: safeRegionName,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  if (changePct >= 25) {
    return {
      tone: 'rising',
      headline: 'Signal baut sich deutlich auf.',
      copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche und zieht damit klar an. Das spricht für erhöhte Aufmerksamkeit in dieser Woche.`,
      metricValue: roundedDelta,
      metricDetail: `${safeRegionName} · ${trendLabel}`,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  if (changePct >= 5) {
    return {
      tone: 'rising',
      headline: 'Signal zieht weiter an.',
      copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche. Der Ausschlag ist sichtbar, aber noch kein maximaler Peak.`,
      metricValue: roundedDelta,
      metricDetail: `${safeRegionName} · ${trendLabel}`,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  if (changePct <= -25) {
    return {
      tone: 'falling',
      headline: 'Signal fällt deutlich zurück.',
      copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche. Das spricht eher für Beobachten als für zusätzlichen Mediadrück in dieser Woche.`,
      metricValue: roundedDelta,
      metricDetail: `${safeRegionName} · ${trendLabel}`,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  if (changePct <= -5) {
    return {
      tone: 'falling',
      headline: 'Signal kühlt wieder ab.',
      copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche. Der Verlauf ist noch relevant, aber nicht mehr so scharf wie zuletzt.`,
      metricValue: roundedDelta,
      metricDetail: `${safeRegionName} · ${trendLabel}`,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  return {
    tone: 'steady',
    headline: 'Signal bleibt weitgehend stabil.',
    copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche. Der Verlauf verändert sich aktuell nur leicht und spricht eher für Beobachten als für einen harten Richtungswechsel.`,
    metricValue: roundedDelta,
    metricDetail: `${safeRegionName} · ${trendLabel}`,
    footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
  };
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

function buildWhyNowModel({
  regionName,
  virus,
  items,
}: {
  regionName: string;
  virus: string;
  items: string[];
}): {
  headline: string;
  copy: string;
  items: string[];
} {
  const safeRegion = regionName || 'Die Fokusregion';
  const primaryItem = items[0] || 'Noch keine klare Kurzbegründung vorhanden.';
  const detailItems = items.slice(1);

  return {
    headline: `${safeRegion} bleibt für ${virus} im Fokus.`,
    copy: primaryItem,
    items: detailItems.length > 0 ? detailItems : ['Weitere Treiber werden nachgeladen, sobald zusätzliche Evidenzpunkte vorliegen.'],
  };
}

function buildRiskModel({
  regionName,
  items,
}: {
  regionName: string;
  items: string[];
}): {
  headline: string;
  copy: string;
  items: string[];
} {
  const safeRegion = regionName || 'Die Fokusregion';
  const realItems = items.filter((item) => item && item !== 'Aktuell sind keine zusätzlichen Risiken dokumentiert.');

  if (realItems.length === 0) {
    return {
      headline: 'Aktuell keine harten Stopps sichtbar.',
      copy: `${safeRegion} hat derzeit keine zusätzlichen Risikohinweise. Beobachten bleibt sinnvoll, aber es gibt keinen klaren Showstopper.`,
      items: ['Die Freigabe bleibt trotzdem an die allgemeine Datenlage und Evidenz gekoppelt.'],
    };
  }

  const primaryItem = realItems[0];
  const detailItems = realItems.slice(1);
  const headline = realItems.length === 1
    ? 'Ein Prüfpunkt bleibt vor der Freigabe offen.'
    : `${realItems.length} Punkte bremsen die Freigabe noch.`;

  return {
    headline,
    copy: primaryItem,
    items: detailItems.length > 0 ? detailItems : ['Dieser Punkt sollte vor einer aktiven Budgetverschiebung noch geprüft werden.'],
  };
}

function resolveRegionStage(
  activationPriority?: string | null,
  decisionLabel?: string | null,
  probability?: number | null,
): string {
  const raw = String(activationPriority || decisionLabel || '').toLowerCase();
  if (raw.includes('aktiv') || raw.includes('activate')) return 'Aktivieren';
  if (raw.includes('vorbereit') || raw.includes('prepare') || raw.includes('halt')) return 'Vorbereiten';
  if (raw.includes('beobacht') || raw.includes('watch')) return 'Beobachten';

  if (probability == null || Number.isNaN(probability)) return 'Beobachten';
  const normalized = probability <= 1 ? probability : probability / 100;
  if (normalized >= 0.7) return 'Aktivieren';
  if (normalized >= 0.45) return 'Vorbereiten';
  return 'Beobachten';
}

function regionStageTone(stage: string): 'activate' | 'prepare' | 'watch' {
  if (stage === 'Aktivieren') return 'activate';
  if (stage === 'Vorbereiten') return 'prepare';
  return 'watch';
}

function buildRegionDetail({
  regionName,
  stage,
  trend,
  changePct,
  impactProbability,
  reason,
}: {
  regionName: string;
  stage: string;
  trend?: string | null;
  changePct?: number | null;
  impactProbability?: number | null;
  reason?: string | null;
}): {
  regionName: string;
  meta: string;
  copy: string;
} {
  const probabilityLabel = formatProbability(impactProbability);
  const deltaLabel = changePct == null || Number.isNaN(changePct)
    ? 'Vorwochenvergleich offen'
    : `${changePct >= 0 ? '+' : ''}${changePct.toFixed(1)}% zur Vorwoche`;
  const trendLabel = trend ? `Trend ${trend}` : 'Trend noch offen';

  return {
    regionName,
    meta: `${stage} · ${probabilityLabel} Signal · ${deltaLabel}`,
    copy: reason || `${regionName} steht aktuell weit oben im Ranking. ${trendLabel} und Signalscore sprechen für eine genauere Prüfung in dieser Woche.`,
  };
}

const RegionLadderRow: React.FC<{
  row: RegionLeaderboardRow;
  index: number;
  isActive: boolean;
  stage: string;
  onSelect: () => void;
}> = ({ row, index, isActive, stage, onSelect }) => {
  const tone = regionStageTone(stage);
  return (
    <button
      type="button"
      className={`virus-radar-ladder__item ${isActive ? 'is-active' : ''}`}
      onClick={onSelect}
    >
      <span className="virus-radar-ladder__rank">{String(index + 1).padStart(2, '0')}</span>
      <span className="virus-radar-ladder__main">
        <span className="virus-radar-ladder__name">{row.name}</span>
        <span className="virus-radar-ladder__subline">
          Trend {row.trend || 'offen'}
        </span>
      </span>
      <span className="virus-radar-ladder__meta">
        <span className={`virus-radar-ladder__stage virus-radar-ladder__stage--${tone}`}>{stage}</span>
        <span className="virus-radar-ladder__probability">{formatProbability(row.impact_probability ?? row.signal_score)}</span>
      </span>
    </button>
  );
};

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
