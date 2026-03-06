import React from 'react';

import { BacktestResponse } from '../../types/media';
import { ValidationSection } from './BacktestVisuals';
import { CockpitResponse } from './types';
import {
  formatDateTime,
  formatPercent,
  truthLayerLabel,
} from './cockpitUtils';

interface Props {
  cockpit: CockpitResponse | null;
  loading: boolean;
  marketValidation: BacktestResponse | null;
  marketValidationLoading: boolean;
  customerValidation: BacktestResponse | null;
  customerValidationLoading: boolean;
}

const EvidencePanel: React.FC<Props> = ({
  cockpit,
  loading,
  marketValidation,
  marketValidationLoading,
  customerValidation,
  customerValidationLoading,
}) => {
  const latestMarket = cockpit?.backtest_summary?.latest_market;
  const latestCustomer = cockpit?.backtest_summary?.latest_customer;
  const sourceItems = cockpit?.source_status?.items || [];
  const recentRuns = cockpit?.backtest_summary?.recent_runs || [];

  if (loading) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade Evidenz...</div>;
  }

  return (
    <div className="page-stack">
      <section className="context-filter-rail">
        <div className="section-heading">
          <span className="section-kicker">Evidenz</span>
          <h1 className="section-title">Proxy und Truth sauber getrennt</h1>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <span className="step-chip">Proxy-validiert</span>
          <span className="step-chip">Truth-Layer: {truthLayerLabel(latestCustomer)}</span>
        </div>
      </section>

      <section className="evidence-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">Markt-Check (Proxy-Validierung)</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              {latestMarket?.quality_gate?.overall_passed ? 'GO' : 'WATCH'}
            </h2>
          </div>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Readiness</span>
              <strong>{latestMarket?.decision_metrics?.readiness_score_0_100 != null ? `${Math.round(latestMarket.decision_metrics.readiness_score_0_100)}/100` : '-'}</strong>
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
          <p className="section-copy">
            Dieser Block zeigt, wie gut das System epidemiologische Trigger gegen Marktbewegungen trifft. Er ist ein Proxy für Planungsgüte, nicht der finale Kundenbeweis.
          </p>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">Kunden-Check (Truth-Layer)</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              {truthLayerLabel(latestCustomer)}
            </h2>
          </div>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Datenpunkte</span>
              <strong>{latestCustomer?.metrics?.data_points ?? 0}</strong>
            </div>
            <div className="metric-box">
              <span>Korrelation</span>
              <strong>{formatPercent((latestCustomer?.metrics?.correlation_pct ?? latestCustomer?.metrics?.correlation ?? 0) as number)}</strong>
            </div>
            <div className="metric-box">
              <span>R²</span>
              <strong>{latestCustomer?.metrics?.r2_score != null ? latestCustomer.metrics.r2_score.toFixed(2) : '-'}</strong>
            </div>
          </div>
          <p className="section-copy">
            Unter 26 Wochen bleibt dieser Layer explorativ. Unter 52 Wochen ist er kein belastbarer Freigabebeweis für kundennahe Media-Automation.
          </p>
        </div>
      </section>

      <section style={{ display: 'grid', gap: 20 }}>
        <ValidationSection
          title="Markt-Validierung im Verlauf"
          subtitle="Forecast gegen Ist, inklusive Baselines. So sieht PEIX, ob das Modell die Welle früh genug erkennt und nicht nur nachzeichnet."
          result={marketValidation}
          loading={marketValidationLoading}
          emptyMessage="Noch keine detaillierten Markt-Validierungsdaten verfügbar."
        />
        <ValidationSection
          title="Kunden-Validierung im Verlauf"
          subtitle="Proxy und Truth bleiben getrennt: Dieser Layer zeigt nur, wie gut das Modell an echte Kunden-Outcome-Daten anschließt."
          result={customerValidation}
          loading={customerValidationLoading}
          emptyMessage="Noch keine ausreichend langen Kundenreihen für eine belastbare Truth-Validierung verfügbar."
        />
      </section>

      <section className="cockpit-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Datenfrische</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {Object.entries(cockpit?.data_freshness || {}).map(([key, value]) => (
              <div key={key} className="evidence-row">
                <span>{key}</span>
                <strong>{formatDateTime(value)}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Quellenstatus</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {sourceItems.map((item) => (
              <div key={item.source_key} className="evidence-row">
                <span>{item.label}</span>
                <strong style={{ color: item.status_color === 'green' ? '#047857' : item.status_color === 'amber' ? '#b45309' : '#b91c1c' }}>
                  {item.is_live ? 'live' : 'stale'}
                </strong>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <h2 className="subsection-title">Recent Runs</h2>
        <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
          {recentRuns.length > 0 ? recentRuns.slice(0, 6).map((run, index) => (
            <div key={`${String(run.mode)}-${index}`} className="evidence-row">
              <span>{String(run.mode || 'Run')}</span>
              <strong>{String(run.status || '-')}</strong>
            </div>
          )) : (
            <div style={{ color: 'var(--text-muted)' }}>Noch keine Run-Historie im Cockpit vorhanden.</div>
          )}
        </div>
      </section>
    </div>
  );
};

export default EvidencePanel;
