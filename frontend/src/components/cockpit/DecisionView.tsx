import React from 'react';
import { Link } from 'react-router-dom';

import { BacktestResponse, RecommendationCard } from '../../types/media';
import { CockpitResponse } from './types';
import { WaveOutlookPanel } from './BacktestVisuals';
import {
  VIRUS_OPTIONS,
  formatCurrency,
  formatDateTime,
  formatPercent,
  readinessTone,
  truthLayerLabel,
} from './cockpitUtils';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  cockpit: CockpitResponse | null;
  loading: boolean;
  recommendations: RecommendationCard[];
  waveOutlook: BacktestResponse | null;
  waveOutlookLoading: boolean;
  onOpenRecommendation: (id: string) => void;
  onOpenRegions: () => void;
  onOpenCampaigns: () => void;
}

const DecisionView: React.FC<Props> = ({
  virus,
  onVirusChange,
  cockpit,
  loading,
  recommendations,
  waveOutlook,
  waveOutlookLoading,
  onOpenRecommendation,
  onOpenRegions,
  onOpenCampaigns,
}) => {
  const latestMarket = cockpit?.backtest_summary?.latest_market;
  const latestCustomer = cockpit?.backtest_summary?.latest_customer;
  const topCard = recommendations[0] || cockpit?.recommendations?.cards?.[0] || null;
  const topRegions = (cockpit?.map?.top_regions || []).slice(0, 3);
  const isGo = Boolean(latestMarket?.quality_gate?.overall_passed);
  const readiness = latestMarket?.decision_metrics?.readiness_score_0_100;
  const primaryRegion = topCard?.decision_brief?.recommendation?.primary_region || topRegions[0]?.name;
  const horizonMin = topCard?.decision_brief?.horizon?.min_days;
  const horizonMax = topCard?.decision_brief?.horizon?.max_days;

  const heroSentence = topCard?.decision_brief?.summary_sentence
    || (topRegions.length
      ? `Diese Woche ${isGo ? 'freigeben' : 'vorbereiten'}: Fokus auf ${topRegions
        .map((region) => region.name)
        .join(', ')}.`
      : 'Diese Woche die nationale Lage beobachten und regionale Signale priorisieren.');
  const horizonLabel = horizonMin && horizonMax
    ? `${horizonMin}-${horizonMax} Tagen`
    : (horizonMax || horizonMin)
      ? `${horizonMax || horizonMin} Tagen`
      : null;
  const heroLead = primaryRegion
    ? `${isGo ? 'Aktivieren' : 'Vorbereiten'} für ${primaryRegion}${horizonLabel ? ` in ${horizonLabel}` : ''}.`
    : (isGo ? 'Aktivieren, wo das Signal trägt.' : 'Vorbereiten, wo die Welle zuerst greift.');

  const gateTone = readinessTone(isGo);

  if (loading && !cockpit) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade Entscheidungssystem...</div>;
  }

  return (
    <div className="page-stack">
      <section className="context-filter-rail">
        <div className="section-heading">
          <span className="section-kicker">ViralFlux for GELO</span>
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
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <span className="step-chip step-chip-done">Datenstand {formatDateTime(cockpit?.map?.date)}</span>
          <span className="step-chip">Proxy-validiert</span>
          <span className="step-chip">Kunden-Check: {truthLayerLabel(latestCustomer)}</span>
        </div>
      </section>

      <section className="card decision-header hero-card" style={{ padding: 32 }}>
        <div className="hero-grid">
          <div className="hero-main">
            <div className="hero-status-row">
              <span
                style={{
                  padding: '8px 12px',
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  ...gateTone,
                }}
              >
                {isGo ? 'GO' : 'WATCH'}
              </span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {topCard?.playbook_title || 'Wochenentscheidung'} · {cockpit?.map?.date ? new Date(cockpit.map.date).toLocaleDateString('de-DE') : '-'}
              </span>
            </div>
            <div className="section-heading" style={{ gap: 12 }}>
              <h1 className="hero-title">{heroLead}</h1>
              <p className="hero-context">{heroSentence}</p>
              <p className="hero-copy">
                {isGo
                  ? 'Das Modell ist im Zielkorridor. Fokus liegt auf konkret freigabefähigen regionalen Kampagnenpaketen.'
                  : 'Die App schaltet auf defensiven Modus: vorbereiten, priorisieren und nur mit klaren Guardrails freigeben.'}
              </p>
            </div>
            <div className="action-row">
              <button className="media-button" type="button" onClick={onOpenCampaigns}>Kampagnen öffnen</button>
              <button className="media-button secondary" type="button" onClick={onOpenRegions}>Regionen prüfen</button>
              <Link className="media-button secondary" to="/bericht" style={{ textDecoration: 'none' }}>Bericht exportieren</Link>
            </div>
          </div>

          <div className="soft-panel aside-summary" style={{ padding: 24 }}>
            <div>
              <div className="section-kicker">Wochenfokus</div>
              <div className="summary-headline">
                {topCard?.recommended_product || 'GELO Portfolio'}
              </div>
              <div className="summary-note">
                Top-Regionen: {topRegions.map((region) => region.name).join(', ') || 'National'}
              </div>
            </div>
            <div className="decision-rail summary-grid">
              <div style={{ minWidth: 120 }}>
                <div className="section-kicker" style={{ marginBottom: 6 }}>Shift</div>
                <div className="summary-metric">
                  {formatPercent(topCard?.budget_shift_pct || 0)}
                </div>
              </div>
              <div style={{ minWidth: 140 }}>
                <div className="section-kicker" style={{ marginBottom: 6 }}>Budget</div>
                <div className="summary-metric">
                  {formatCurrency(topCard?.campaign_preview?.budget?.weekly_budget_eur)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="cockpit-grid">
        <WaveOutlookPanel result={waveOutlook} loading={waveOutlookLoading} />

        <div style={{ display: 'grid', gap: 20 }}>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Readiness</span>
              <strong>{readiness != null ? `${Math.round(readiness)}/100` : '-'}</strong>
            </div>
            <div className="metric-box">
              <span>Hit-Rate</span>
              <strong>{formatPercent(latestMarket?.decision_metrics?.hit_rate_pct || 0)}</strong>
            </div>
            <div className="metric-box">
              <span>False Alarms</span>
              <strong>{formatPercent(latestMarket?.decision_metrics?.false_alarm_rate_pct || 0)}</strong>
            </div>
          </div>

          <div className="card subsection-card" style={{ padding: 24 }}>
            <div className="section-heading" style={{ gap: 6 }}>
              <h2 className="subsection-title">Kampagnen, die jetzt zählen</h2>
              <p className="subsection-copy">
                Direkter Sprung in review- oder publishable Pakete.
              </p>
            </div>
            {(recommendations.slice(0, 3)).map((card) => (
              <button
                key={card.id}
                type="button"
                onClick={() => onOpenRecommendation(card.id)}
                className="campaign-list-card"
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {card.display_title || card.campaign_name || card.product}
                    </div>
                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                      {card.region_codes_display?.join(', ') || card.region || 'National'} · {card.recommended_product || card.product}
                    </div>
                  </div>
                  <strong style={{ fontSize: 14, color: 'var(--accent-violet)' }}>{formatPercent(card.budget_shift_pct || 0)}</strong>
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
};

export default DecisionView;
