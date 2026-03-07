import React from 'react';
import { Link } from 'react-router-dom';

import {
  BacktestResponse,
  MediaDecisionResponse,
} from '../../types/media';
import { WaveOutlookPanel } from './BacktestVisuals';
import {
  VIRUS_OPTIONS,
  formatCurrency,
  formatDateTime,
  formatPercent,
  readinessTone,
  truthLayerLabel,
  workflowLabel,
} from './cockpitUtils';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  decision: MediaDecisionResponse | null;
  loading: boolean;
  waveOutlook: BacktestResponse | null;
  waveOutlookLoading: boolean;
  onOpenRecommendation: (id: string) => void;
  onOpenRegions: () => void;
  onOpenCampaigns: () => void;
}

const DecisionView: React.FC<Props> = ({
  virus,
  onVirusChange,
  decision,
  loading,
  waveOutlook,
  waveOutlookLoading,
  onOpenRecommendation,
  onOpenRegions,
  onOpenCampaigns,
}) => {
  const weeklyDecision = decision?.weekly_decision;
  const latestMarket = decision?.backtest_summary?.latest_market;
  const latestCustomer = decision?.backtest_summary?.latest_customer;
  const topCard = decision?.top_recommendations?.[0] || null;
  const recommendations = decision?.top_recommendations || [];
  const topRegions = weeklyDecision?.top_regions || [];
  const isGo = String(weeklyDecision?.decision_state || '').toUpperCase() === 'GO';
  const readiness = latestMarket?.decision_metrics?.readiness_score_0_100;
  const primaryRegion = topCard?.decision_brief?.recommendation?.primary_region || topRegions[0]?.name;
  const horizonMin = topCard?.decision_brief?.horizon?.min_days;
  const horizonMax = topCard?.decision_brief?.horizon?.max_days;
  const topDrivers = weeklyDecision?.signal_stack_summary?.top_drivers || [];
  const mathStack = weeklyDecision?.signal_stack_summary?.math_stack;
  const hiddenBacklog = decision?.campaign_summary?.hidden_backlog_cards || 0;

  const heroSentence = weeklyDecision?.recommended_action
    || topCard?.decision_brief?.summary_sentence
    || (topRegions.length
      ? `Diese Woche ${isGo ? 'freigeben' : 'vorbereiten'}: Fokus auf ${topRegions
        .map((region) => region.name || region.code)
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
  const shiftLabel = isGo && weeklyDecision?.budget_shift != null
    ? formatPercent(weeklyDecision.budget_shift as number)
    : 'Noch nicht freigegeben';
  const shiftNote = isGo
    ? 'Nationaler Shift ist freigegeben.'
    : 'WATCH blockiert aktuell eine harte nationale Budgetverschiebung.';

  const gateTone = readinessTone(isGo);

  if (loading && !decision) {
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
          <span className="step-chip step-chip-done">Letzte epidemiologische Woche {formatDateTime(weeklyDecision?.decision_window?.start)}</span>
          <span className="step-chip">Generiert {formatDateTime(decision?.generated_at)}</span>
          <span className="step-chip">Proxy: {weeklyDecision?.proxy_state === 'passed' ? 'GO-Korridor' : 'WATCH'}</span>
          <span className="step-chip">Kunden-Check: {truthLayerLabel(decision?.truth_coverage || latestCustomer)}</span>
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
                {topCard?.playbook_title || 'Wochenentscheidung'} · letzte epidemiologische Woche {weeklyDecision?.decision_window?.start ? new Date(weeklyDecision.decision_window.start).toLocaleDateString('de-DE') : '-'}
              </span>
            </div>
            <div className="section-heading" style={{ gap: 12 }}>
              <h1 className="hero-title">{heroLead}</h1>
              <p className="hero-context">{heroSentence}</p>
              <p className="hero-copy">
                {isGo
                  ? 'Das Modell ist im Zielkorridor. Fokus liegt auf konkret freigabefähigen regionalen Kampagnenpaketen.'
                  : 'Die App schaltet auf defensiven Modus: vorbereiten, priorisieren und erst nach Review/Freigabe weiterziehen.'}
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
                {weeklyDecision?.top_products?.[0] || topCard?.recommended_product || 'GELO Portfolio'}
              </div>
              <div className="summary-note">
                Top-Regionen: {topRegions.map((region) => region.name || region.code).join(', ') || 'National'}
              </div>
            </div>
            <div className="decision-rail summary-grid">
              <div style={{ minWidth: 120 }}>
                <div className="section-kicker" style={{ marginBottom: 6 }}>Nationaler Shift</div>
                <div className="summary-metric">{shiftLabel}</div>
                <div className="summary-note" style={{ marginTop: 6 }}>{shiftNote}</div>
              </div>
              <div style={{ minWidth: 140 }}>
                <div className="section-kicker" style={{ marginBottom: 6 }}>Wochenbudget</div>
                <div className="summary-metric">
                  {formatCurrency(topCard?.campaign_preview?.budget?.weekly_budget_eur)}
                </div>
                <div className="summary-note" style={{ marginTop: 6 }}>
                  {hiddenBacklog > 0 ? `${hiddenBacklog} weitere Pakete liegen im Backlog.` : 'Der Fokus liegt auf der kuratierten Review-Queue.'}
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
              <h2 className="subsection-title">Warum jetzt?</h2>
              <p className="subsection-copy">
                Decision Support aus expliziten Signalen statt Black Box.
              </p>
            </div>
            <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
              {(weeklyDecision?.why_now || []).map((reason) => (
                <div key={reason} className="soft-panel" style={{ padding: 14, fontSize: 14, color: 'var(--text-secondary)' }}>
                  {reason}
                </div>
              ))}
            </div>
          </div>

          <div className="card subsection-card" style={{ padding: 24 }}>
            <div className="section-heading" style={{ gap: 6 }}>
              <h2 className="subsection-title">Kampagnen, die jetzt zählen</h2>
              <p className="subsection-copy">
                Direkter Sprung in die nächste sinnvolle Stufe statt in einen rohen Paketstapel.
              </p>
            </div>
            {recommendations.length > 0 ? (recommendations.slice(0, 3)).map((card) => (
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
                  <strong style={{ fontSize: 14, color: 'var(--accent-violet)' }}>
                    {isGo && card.is_publishable ? formatPercent(card.budget_shift_pct || 0) : workflowLabel(card.lifecycle_state || card.status)}
                  </strong>
                </div>
              </button>
            )) : (
              <div className="soft-panel" style={{ padding: 14, marginTop: 14, fontSize: 14, color: 'var(--text-secondary)' }}>
                Noch keine kuratierten Review-Pakete im Fokus. Öffne die Kampagnenansicht, um den Backlog zu sichten oder neue Pakete zu erzeugen.
              </div>
            )}
          </div>

          <div className="card subsection-card" style={{ padding: 24 }}>
            <div className="section-heading" style={{ gap: 6 }}>
              <h2 className="subsection-title">Signal- und Modellkette</h2>
              <p className="subsection-copy">
                AMELAG und SurvStat bleiben Kernsignale. Holt-Winters, Ridge und Prophet laufen in XGBoost als Meta-Learner zusammen.
              </p>
            </div>
            <div className="review-chip-row" style={{ marginTop: 14 }}>
              {(mathStack?.base_models || []).map((label) => (
                <span key={label} className="step-chip">{label}</span>
              ))}
              {mathStack?.meta_learner && <span className="step-chip">{mathStack.meta_learner}</span>}
            </div>
            <div className="review-chip-row" style={{ marginTop: 10 }}>
              {topDrivers.map((driver) => (
                <span key={driver.label} className="step-chip">
                  {driver.label} {formatPercent(driver.strength_pct || 0)}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {(weeklyDecision?.risk_flags || []).length > 0 && (
        <section className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading" style={{ gap: 6 }}>
            <h2 className="subsection-title">Risiken und Sperren</h2>
            <p className="subsection-copy">
              GO/WATCH wird aus Datenfrische, Proxy, Truth, Modellzustand und Publishability abgeleitet.
            </p>
          </div>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {(weeklyDecision?.risk_flags || []).map((flag) => (
              <div key={flag} className="evidence-row">
                <span>{flag}</span>
                <strong>{weeklyDecision?.decision_state}</strong>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default DecisionView;
