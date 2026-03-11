import React from 'react';

import { ValidationSection } from '../BacktestVisuals';
import { BacktestResponse, ForecastMonitoring, ModelLineage, TruthCoverage } from '../../../types/media';
import { formatDateTime, formatPercent } from '../cockpitUtils';
import { formatSignedPercent, monitoringFreshnessLabel, monitoringStatusLabel, numberFromUnknown } from './evidenceUtils';
import { decisionStateLabel } from '../../../lib/copy';

interface Props {
  forecastMonitoring?: ForecastMonitoring;
  modelLineage?: ModelLineage | null;
  latestAccuracy?: ForecastMonitoring['latest_accuracy'];
  latestBacktest?: ForecastMonitoring['latest_backtest'];
  intervalCoverage: Record<string, unknown>;
  eventCalibration: Record<string, unknown>;
  leadLag: Record<string, unknown>;
  improvementVsBaselines: Record<string, unknown>;
  marketValidation: BacktestResponse | null;
  marketValidationLoading: boolean;
  customerValidation: BacktestResponse | null;
  customerValidationLoading: boolean;
  legacyCustomer?: BacktestResponse | null;
  truthStatus?: TruthCoverage | null;
}

const ForecastMonitoringSection: React.FC<Props> = ({
  forecastMonitoring,
  modelLineage,
  latestAccuracy,
  latestBacktest,
  intervalCoverage,
  eventCalibration,
  leadLag,
  improvementVsBaselines,
  marketValidation,
  marketValidationLoading,
  customerValidation,
  customerValidationLoading,
  legacyCustomer,
  truthStatus,
}) => {
  return (
    <>
      <section className="evidence-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">Markt-Check</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              {decisionStateLabel(marketValidation?.quality_gate?.overall_passed ? 'GO' : 'WATCH')}
            </h2>
          </div>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Readiness</span>
              <strong>{marketValidation?.decision_metrics?.readiness_score_0_100 != null ? `${Math.round(marketValidation.decision_metrics.readiness_score_0_100)}/100` : '-'}</strong>
            </div>
            <div className="metric-box">
              <span>Hit-Rate</span>
              <strong>{formatPercent(marketValidation?.decision_metrics?.hit_rate_pct || 0)}</strong>
            </div>
            <div className="metric-box">
              <span>False Alarms</span>
              <strong>{formatPercent(marketValidation?.decision_metrics?.false_alarm_rate_pct || 0)}</strong>
            </div>
          </div>
          <p className="section-copy">
            Dieser Block zeigt, wie gut das System epidemiologische Trigger gegen Marktbewegungen trifft. Er misst Planungsgüte im Marktvergleich, nicht den finalen Kundennachweis.
          </p>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">Forecast-Monitoring</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              {monitoringStatusLabel(forecastMonitoring?.monitoring_status)}
            </h2>
          </div>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Forecast-Gate</span>
              <strong>{forecastMonitoring?.forecast_readiness || '-'}</strong>
            </div>
            <div className="metric-box">
              <span>Forecast-Frische</span>
              <strong>{monitoringFreshnessLabel(forecastMonitoring?.freshness_status)}</strong>
            </div>
            <div className="metric-box">
              <span>Accuracy-Fenster</span>
              <strong>{monitoringFreshnessLabel(forecastMonitoring?.accuracy_freshness_status)}</strong>
            </div>
          </div>
          <p className="section-copy">
            Dieser Block hängt direkt am Forecast-Kern: Drift, Accuracy, Backtest-Frische, Intervallabdeckung und Event-Kalibrierung werden aus demselben Stack gelesen wie die Opportunity-Gates.
          </p>
          <div className="review-chip-row">
            <span className="step-chip">Backtest: {monitoringFreshnessLabel(forecastMonitoring?.backtest_freshness_status)}</span>
            <span className="step-chip">
              Kalibrierung: {forecastMonitoring?.event_forecast?.calibration_passed == null ? '-' : forecastMonitoring.event_forecast.calibration_passed ? 'ok' : 'watch'}
            </span>
            <span className="step-chip">
              Samples: {latestAccuracy?.samples != null ? latestAccuracy.samples : '-'}
            </span>
          </div>
        </div>
      </section>

      <section style={{ display: 'grid', gap: 20 }}>
        <ValidationSection
          title="Markt-Validierung im Verlauf"
          subtitle="Forecast gegen Ist, inklusive Baselines. So wird sichtbar, ob das Modell die Welle früh erkennt und nicht nur nachzeichnet."
          result={marketValidation}
          loading={marketValidationLoading}
          emptyMessage="Noch keine detaillierten Daten für den Marktvergleich verfügbar."
        />
        {truthStatus?.coverage_weeks ? (
          <ValidationSection
            title="Kunden-Validierung im Verlauf"
            subtitle="Marktvergleich und Kundendaten bleiben getrennt: Dieser Bereich zeigt nur, wie gut das Modell an echte Kunden-Outcome-Daten anschliesst."
            result={customerValidation}
            loading={customerValidationLoading}
            emptyMessage="Noch keine ausreichend langen Kundenreihen für eine belastbare Validierung der Kundendaten verfügbar."
          />
        ) : (
          <section className="card subsection-card" style={{ padding: 24 }}>
            <div className="section-heading" style={{ gap: 6 }}>
              <h2 className="subsection-title">Kunden-Validierung im Verlauf</h2>
              <p className="subsection-copy">
                Dieser Block bleibt leer, bis echte Outcome-Daten angeschlossen sind. Legacy-Runs erscheinen separat nur als explorativer Hinweis.
              </p>
            </div>
            {legacyCustomer ? (
              <div className="soft-panel" style={{ padding: 16, marginTop: 14, display: 'grid', gap: 10 }}>
                <div className="evidence-row">
                  <span>Legacy-Run</span>
                  <strong>{legacyCustomer.run_id || '-'}</strong>
                </div>
                <div className="evidence-row">
                  <span>Datenpunkte</span>
                  <strong>{legacyCustomer.metrics?.data_points ?? 0}</strong>
                </div>
                <div className="evidence-row">
                  <span>R²</span>
                  <strong>{legacyCustomer.metrics?.r2_score ?? '-'}</strong>
                </div>
              </div>
            ) : (
              <div className="review-muted-copy" style={{ marginTop: 14 }}>
                Noch kein aktiver oder historischer Kundenlauf vorhanden.
              </div>
            )}
          </section>
        )}
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">Forecast-Details</span>
          <h2 className="subsection-title">Monitoring des Produktionsmodells</h2>
          <p className="subsection-copy">
            Hier sehen Analysten, ob der Forecast nicht nur läuft, sondern auch mathematisch sauber über Accuracy, Vorlaufzeit, Intervalle und Kalibrierung im Zielkorridor bleibt.
          </p>
        </div>

        <div className="metric-strip" style={{ marginTop: 18 }}>
          <div className="metric-box">
            <span>7T Event</span>
            <strong>{formatPercent((forecastMonitoring?.event_forecast?.event_probability || 0) * 100, 1)}</strong>
          </div>
          <div className="metric-box">
            <span>MAPE</span>
            <strong>{formatPercent(latestAccuracy?.mape, 1)}</strong>
          </div>
          <div className="metric-box">
            <span>Korrelation</span>
            <strong>{latestAccuracy?.correlation != null ? formatPercent(latestAccuracy.correlation * 100, 0) : '-'}</strong>
          </div>
          <div className="metric-box">
            <span>Lead Time</span>
            <strong>{numberFromUnknown(leadLag.effective_lead_days) != null ? `${numberFromUnknown(leadLag.effective_lead_days)}T` : '-'}</strong>
          </div>
        </div>

        <div className="soft-panel" style={{ padding: 18, marginTop: 18, display: 'grid', gap: 10 }}>
          <div className="evidence-row">
            <span>Modellversion</span>
            <strong>{forecastMonitoring?.model_version || modelLineage?.model_version || '-'}</strong>
          </div>
          <div className="evidence-row">
            <span>Letzter Forecast-Lauf</span>
            <strong>{formatDateTime(forecastMonitoring?.issue_date || modelLineage?.latest_forecast_created_at)}</strong>
          </div>
          <div className="evidence-row">
            <span>Letzter Accuracy-Check</span>
            <strong>{formatDateTime(latestAccuracy?.computed_at)}</strong>
          </div>
          <div className="evidence-row">
            <span>Letzter Markt-Backtest</span>
            <strong>{formatDateTime(latestBacktest?.created_at)}</strong>
          </div>
          <div className="evidence-row">
            <span>80%-Intervallabdeckung</span>
            <strong>{formatPercent(numberFromUnknown(intervalCoverage.coverage_80_pct), 1)}</strong>
          </div>
          <div className="evidence-row">
            <span>Brier Score</span>
            <strong>{numberFromUnknown(eventCalibration.brier_score)?.toFixed(3) || '-'}</strong>
          </div>
          <div className="evidence-row">
            <span>ECE</span>
            <strong>{numberFromUnknown(eventCalibration.ece)?.toFixed(3) || '-'}</strong>
          </div>
          <div className="evidence-row">
            <span>MAE vs Persistence</span>
            <strong>{formatSignedPercent(improvementVsBaselines.mae_vs_persistence_pct)}</strong>
          </div>
          <div className="evidence-row">
            <span>MAE vs Seasonal</span>
            <strong>{formatSignedPercent(improvementVsBaselines.mae_vs_seasonal_pct)}</strong>
          </div>
        </div>

        {forecastMonitoring?.alerts?.length ? (
          <div className="soft-panel review-panel-soft" style={{ marginTop: 16, padding: 18 }}>
            <div className="campaign-focus-label">Offene Monitoring-Signale</div>
            <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
              {forecastMonitoring.alerts.map((alert) => (
                <div key={alert} className="review-body-copy">{alert}</div>
              ))}
            </div>
          </div>
        ) : (
          <div className="review-muted-copy" style={{ marginTop: 16 }}>
            Aktuell gibt es keine offenen Monitoring-Warnungen für diesen Forecast-Stack.
          </div>
        )}
      </section>
    </>
  );
};

export default ForecastMonitoringSection;
