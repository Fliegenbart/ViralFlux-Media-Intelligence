import React, { useMemo, useState } from 'react';

import {
  useCampaignsPageData,
  useEvidencePageData,
  useNowPageData,
  useRegionsPageData,
} from '../../features/media/useMediaData';
import {
  VIRUS_RADAR_HERO_COLORS,
  VIRUS_RADAR_HERO_VIRUSES,
  VirusRadarHeroForecastData,
} from '../../features/media/virusRadarHeroForecast';
import { RecommendationCard } from '../../types/media';
import GermanyMap from './GermanyMap';
import { ForecastChart } from './ForecastChart';
import { MultiVirusForecastChart } from './MultiVirusForecastChart';
import { MapRegion } from './types';
import {
  formatCurrency,
  formatDateTime,
  statusTone,
} from './cockpitUtils';
import {
  OperatorPanel,
  OperatorSection,
} from './operator/OperatorPrimitives';
import {
  buildActivationQueueModel,
  buildCampaignReadinessModel,
  buildRegionDetail,
  buildRiskItems,
  buildRiskModel,
  buildSignalTiles,
  buildTrendInsight,
  buildWhyNowItems,
  buildWhyNowModel,
  formatProbability,
  formatSignedPercent,
  regionStageTone,
  resolveRegionStage,
} from './virusRadarWorkspace.utils';
import type { SignalPrediction } from './virusRadarWorkspace.utils';

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
  const heroHasData = heroForecast.availableViruses.length > 0;
  const heroIsLoading = heroForecastLoading && !heroHasData;
  const selectedHeroVirus = (
    (heroHasData && heroForecast.availableViruses.includes(virus) ? virus : null)
    || topVirusSummary?.virus
    || heroForecast.availableViruses[0]
    || VIRUS_RADAR_HERO_VIRUSES[0]
  );
  const selectedHeroSummary = heroForecast.summaries.find((item) => item.virus === selectedHeroVirus) || null;
  const selectedHeroColor = VIRUS_RADAR_HERO_COLORS[selectedHeroVirus] || '#1f7a66';
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
  const activationQueueModel = buildActivationQueueModel(topActivation);
  const campaignReadinessModel = buildCampaignReadinessModel({
    cards: campaignCards,
    publishableCards: campaignsData.campaignsView?.summary?.publishable_cards,
    activeCards: campaignsData.campaignsView?.summary?.active_cards,
  });
  const dataTimestamp = formatDateTime(nowData.view.generatedAt);
  const trendInsight = buildTrendInsight({
    regionName: chartRegionName,
    changePct: heroChangePct,
    trend: heroTrend,
    virus,
    hasTimeline: (nowData.focusRegionBacktest?.timeline || []).length > 0,
  });
  const heroEyebrow = heroIsLoading
    ? 'Virus-Verlauf wird geladen'
    : `Virus-Verlauf · ${selectedHeroVirus}`;
  const heroHeadlinePrimary = heroIsLoading
    ? 'Der Verlauf wird geladen.'
    : `${selectedHeroVirus} · letzte Wochen und nächste ${horizonDays} Tage.`;
  const heroHeadlineSecondary = heroIsLoading
    ? 'Die Prognose wird gerade aufgebaut.'
    : 'Durchgezogen siehst du die letzten Wochen, gestrichelt die Prognose.';
  const heroSummary = heroIsLoading
    ? 'Der Verlauf wird im Hintergrund geladen. Sobald die Daten da sind, siehst du hier wieder die letzten Wochen plus die 7-Tage-Prognose.'
    : selectedHeroSummary
      ? `${selectedHeroVirus} wird aktuell für die nächsten ${horizonDays} Tage bei ${formatSignedPercent(selectedHeroSummary.deltaPct)} erwartet. Der Graph basiert auf den letzten vorhandenen Wochenwerten und der aktuellen Prognose, nicht auf erfundenen Demo-Daten.`
      : 'Sobald frische Kurven vorliegen, siehst du hier wieder die letzten Wochen plus die 7-Tage-Prognose.';
  const heroPrimaryStat = heroIsLoading
    ? 'Wird geladen'
    : selectedHeroSummary
      ? formatSignedPercent(selectedHeroSummary.deltaPct)
      : 'Noch offen';
  const heroSecondaryStat = heroIsLoading
    ? 'Wird geladen'
    : selectedHeroSummary
      ? selectedHeroSummary.direction
      : 'Noch offen';

  return (
    <div className="page-stack virus-radar-page">
      <OperatorSection
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
                  <span className="virus-radar-hero-chart-card__swatch virus-radar-hero-chart-card__swatch--actual" />
                  Letzte Wochen
                </div>
                <div className="virus-radar-hero-chart-card__legend-item">
                  <span
                    className="virus-radar-hero-chart-card__swatch virus-radar-hero-chart-card__swatch--forecast"
                    style={{ background: selectedHeroColor }}
                  />
                  Nächste 7 Tage
                </div>
                <div className="virus-radar-hero-chart-card__legend-item virus-radar-hero-chart-card__legend-item--explain">
                  Heute = 100
                </div>
              </div>
              <div className="virus-radar-hero-chart-card__stamp">
                <strong>{selectedHeroVirus}</strong>
                <span>Stand {dataTimestamp}</span>
              </div>
            </div>
            <MultiVirusForecastChart
              data={heroForecast.chartData}
              selectedVirus={selectedHeroVirus}
              className="virus-radar-hero-chart"
              loading={heroIsLoading}
            />
            <div className="virus-radar-hero-chart-card__footer">
              <span className="virus-radar-hero-chart-card__hint">
                Links siehst du die letzten Wochen, rechts die nächsten 7 Tage. Alle Werte sind auf Heute = 100 normiert, damit die Richtung sauber vergleichbar bleibt.
              </span>
              <div className="virus-radar-virus-switcher virus-radar-virus-switcher--hero" aria-label="Virus im Verlauf wechseln">
                {VIRUS_RADAR_HERO_VIRUSES.map((option) => (
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

          <div className="virus-radar-hero__footer">
            <div className="virus-radar-hero__stats">
              <div className="virus-radar-stat">
                <span className="virus-radar-stat__label">7-Tage-Delta</span>
                <strong className="virus-radar-stat__value">{heroPrimaryStat}</strong>
              </div>
              <div className="virus-radar-stat">
                <span className="virus-radar-stat__label">Tendenz</span>
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
                  ? 'Oben siehst du immer den Verlauf des ausgewählten Virus. Die Karte, Regionen und Kampagnen darunter folgen demselben Virus.'
                  : 'Oben siehst du immer den Verlauf des ausgewählten Virus. Die konkrete Aktivierung wird darunter weiter nach Virus und Bundesland verdichtet.'}
              </p>
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
              title="Wer als Nächstes dran ist"
              description="Die nächste Reihenfolge für die Media-Prüfung."
            >
              <div className="virus-radar-secondary-lead virus-radar-secondary-lead--queue">
                <span className="virus-radar-secondary-lead__eyebrow">Kurz gesagt</span>
                <strong className="virus-radar-secondary-lead__headline">{activationQueueModel.headline}</strong>
                <p className="virus-radar-secondary-lead__copy">{activationQueueModel.copy}</p>
              </div>
              <div className="virus-radar-queue">
                {topActivation.length > 0 ? topActivation.map((item, index) => (
                  <div key={item.region} className="virus-radar-queue__item">
                    <div className="virus-radar-queue__item-head">
                      <span className="virus-radar-queue__rank">{String(index + 1).padStart(2, '0')}</span>
                      <div className="virus-radar-queue__item-copy">
                        <strong>{item.region_name}</strong>
                        <span>{formatProbability(item.impact_probability)} Signal · {item.priority}</span>
                      </div>
                      <span className={`virus-radar-ladder__stage virus-radar-ladder__stage--${regionStageTone(item.priority)}`}>
                        {item.priority}
                      </span>
                    </div>
                    <span className="virus-radar-queue__reason">{item.reason}</span>
                  </div>
                )) : (
                  <div className="virus-radar-empty">Noch keine Reihenfolge sichtbar.</div>
                )}
              </div>
            </OperatorPanel>

            <OperatorPanel
              eyebrow="Campaign Readiness"
              title="Was jetzt freigegeben werden kann"
              description="Die stärksten Vorschläge für den nächsten Move."
            >
              <div className="virus-radar-secondary-lead virus-radar-secondary-lead--campaigns">
                <span className="virus-radar-secondary-lead__eyebrow">Kurz gesagt</span>
                <strong className="virus-radar-secondary-lead__headline">{campaignReadinessModel.headline}</strong>
                <p className="virus-radar-secondary-lead__copy">{campaignReadinessModel.copy}</p>
              </div>
              <div className="virus-radar-campaigns">
                {campaignCards.length > 0 ? campaignCards.map((card) => (
                  <CampaignReadinessCard
                    key={card.id}
                    card={card}
                    onOpen={() => onOpenRecommendation(card.id)}
                  />
                )) : (
                  <div className="virus-radar-empty">Noch nichts freigabereif.</div>
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
