import React from 'react';

import { RegionalBenchmarkResponse, RegionalPortfolioResponse } from '../../types/media';
import { businessValidationLabel, evidenceTierLabel, formatDateShort, formatPercent } from './cockpitUtils';

interface Props {
  currentVirus: string;
  benchmark: RegionalBenchmarkResponse | null;
  portfolio: RegionalPortfolioResponse | null;
  loading: boolean;
  onFocusOpportunity: (virus: string, regionCode: string) => void;
}

function signedPercentDelta(value?: number): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value * 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}

const RegionalPortfolioPanel: React.FC<Props> = ({
  currentVirus,
  benchmark,
  portfolio,
  loading,
  onFocusOpportunity,
}) => {
  const benchmarkItems = benchmark?.benchmark || portfolio?.benchmark || [];
  const topBenchmark = benchmarkItems.slice(0, 3);
  const topOpportunities = portfolio?.top_opportunities || [];
  const topRegions = portfolio?.region_rollup?.slice(0, 6) || [];

  return (
    <section className="card subsection-card" style={{ padding: 24 }}>
      <div className="section-heading" style={{ gap: 6 }}>
        <h2 className="subsection-title">Virus-Portfolio</h2>
        <p className="subsection-copy">
          Regionen und Viruslinien werden gemeinsam priorisiert, damit nicht nur ein einzelner Screen entscheidet.
        </p>
      </div>

      <div className="review-chip-row" style={{ marginTop: 12 }}>
        <span className="step-chip">Referenz: {benchmark?.reference_virus || portfolio?.reference_virus || 'Influenza A'}</span>
        <span className="step-chip">Trainierte Linien: {portfolio?.summary?.trained_viruses ?? benchmark?.trained_viruses ?? '-'}</span>
        <span className="step-chip">Validierte GO-Linien: {portfolio?.summary?.go_viruses ?? benchmark?.go_viruses ?? '-'}</span>
        <span className="step-chip">Business-Evidenz: {evidenceTierLabel(portfolio?.evidence_tier || benchmark?.evidence_tier)}</span>
        <span className="step-chip">Stand {formatDateShort(portfolio?.latest_as_of_date || benchmark?.generated_at)}</span>
        <span className="step-chip">Bundesland-Level</span>
      </div>

      <div style={{ display: 'grid', gap: 20, marginTop: 18 }}>
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          {topBenchmark.length > 0 ? topBenchmark.map((item) => {
            const metrics = item.aggregate_metrics || {};
            const isActiveVirus = item.virus_typ === currentVirus;
            return (
              <div
                key={item.virus_typ}
                className="soft-panel"
                style={{
                  padding: 16,
                  border: isActiveVirus ? '1px solid rgba(10, 132, 255, 0.28)' : undefined,
                  boxShadow: isActiveVirus ? '0 0 0 1px rgba(10, 132, 255, 0.10)' : undefined,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                  <div>
                    <div className="section-kicker">Benchmark #{item.rank || '-'}</div>
                    <div style={{ marginTop: 6, fontSize: 16, fontWeight: 800, color: 'var(--text-primary)' }}>
                      {item.virus_typ}
                    </div>
                  </div>
                  <span className="step-chip">{item.quality_gate?.forecast_readiness || 'NO MODEL'}</span>
                </div>
                <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {businessValidationLabel(item.business_gate?.validation_status)} · {evidenceTierLabel(item.evidence_tier)}
                </div>
                <div className="metric-strip" style={{ marginTop: 14 }}>
                  <div className="metric-box">
                    <span>Precision@3</span>
                    <strong>{formatPercent((metrics.precision_at_top3 || 0) * 100, 1)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>PR-AUC</span>
                    <strong>{formatPercent((metrics.pr_auc || 0) * 100, 1)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>ECE</span>
                    <strong>{formatPercent((metrics.ece || 0) * 100, 1)}</strong>
                  </div>
                </div>
                <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
                  Gegen {benchmark?.reference_virus || portfolio?.reference_virus || 'Influenza A'}:
                  {' '}
                  <strong style={{ color: 'var(--text-primary)' }}>
                    {signedPercentDelta(item.delta_vs_reference?.precision_at_top3)}
                  </strong>
                  {' '}bei Precision@3
                </div>
              </div>
            );
          }) : (
            <div className="soft-panel" style={{ padding: 16, color: 'var(--text-secondary)' }}>
              {loading ? 'Benchmark wird geladen…' : 'Noch keine Benchmark-Daten verfügbar.'}
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gap: 18, gridTemplateColumns: 'minmax(0, 1.45fr) minmax(280px, 0.95fr)' }}>
          <div className="soft-panel" style={{ padding: 18, display: 'grid', gap: 10 }}>
            <div className="section-kicker">Top-Chancen über alle Viren</div>
            {topOpportunities.length > 0 ? topOpportunities.slice(0, 6).map((item) => (
              <button
                key={`${item.virus_typ}-${item.bundesland}-${item.rank}`}
                type="button"
                onClick={() => onFocusOpportunity(item.virus_typ, item.bundesland)}
                className="campaign-list-card"
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>
                      #{item.rank} {item.bundesland_name}
                    </div>
                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                      {item.virus_typ} · {item.products?.join(' / ') || 'Portfolio-Fokus'}
                    </div>
                    <div style={{ marginTop: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                      {item.portfolio_action === 'prioritize'
                        ? 'Als Watchlist-Fokus vorziehen'
                        : item.portfolio_action === 'activate'
                          ? 'Validierter Aktivierungs-Case'
                          : item.portfolio_action === 'prepare'
                            ? 'Validiert vorbereiten'
                            : 'Weiter beobachten'}
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                      Bundesland-Level · {businessValidationLabel(item.business_gate?.validation_status)} · {evidenceTierLabel(item.evidence_tier)}
                    </div>
                  </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--accent-violet)' }}>
                      {formatPercent(item.event_probability * 100, 1)}
                      </div>
                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                      Score {item.portfolio_priority_score.toFixed(1)}
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                      {formatPercent(item.change_pct || 0, 1)} · {item.quality_gate?.forecast_readiness || 'WATCH'}
                    </div>
                  </div>
                </div>
              </button>
            )) : (
              <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
                {loading ? 'Portfolio wird geladen…' : 'Noch keine portfolio-weiten Chancen verfügbar.'}
              </div>
            )}
          </div>

          <div className="soft-panel" style={{ padding: 18, display: 'grid', gap: 10 }}>
            <div className="section-kicker">Führender Virus pro Region</div>
            {topRegions.length > 0 ? topRegions.map((region) => (
              <div key={region.bundesland} className="evidence-row">
                <span>
                  {region.bundesland_name}
                  <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                    Bundesland-Level · {region.top_signals.map((signal) => signal.virus_typ).join(' · ')}
                  </div>
                </span>
                <strong>
                  {region.leading_virus} · {formatPercent(region.leading_probability * 100, 1)}
                </strong>
              </div>
            )) : (
              <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
                {loading ? 'Regionen-Rollup wird geladen…' : 'Noch kein regionales Portfolio-Rollup verfügbar.'}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};

export default RegionalPortfolioPanel;
