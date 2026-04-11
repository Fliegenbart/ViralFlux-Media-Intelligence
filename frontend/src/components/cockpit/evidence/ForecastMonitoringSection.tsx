import React from 'react';

import { COCKPIT_SEMANTICS, UI_COPY } from '../../../lib/copy';
import { ValidationSection } from '../BacktestVisuals';
import { BacktestResponse, ForecastMonitoring, ModelLineage, TruthCoverage } from '../../../types/media';
import { formatDateTime, formatPercent } from '../cockpitUtils';
import {
  formatSignedPercent,
  monitoringFreshnessLabel,
  numberFromUnknown,
  readinessGateLabel,
  sanitizeEvidenceCopy,
} from './evidenceUtils';

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
  const eventForecast = forecastMonitoring?.event_forecast;
  const eventProbabilityLabel = eventForecast?.fallback_used ? 'Fallback-Wahrscheinlichkeit' : UI_COPY.eventProbability;
  const eventProbabilityBadge = eventForecast?.fallback_used ? 'Fallback-Schätzung' : COCKPIT_SEMANTICS.eventProbability.badge;
  const eventProbabilityNote = eventForecast?.fallback_used
    ? 'Dieser Wert stammt aktuell aus einer Ersatzschätzung und sollte vorsichtiger gelesen werden als ein voll gelerntes Modell.'
    : 'Dieser Wert beschreibt die kalibrierte Wahrscheinlichkeit für das definierte Forecast-Ereignis.';
  const probabilitySource = readableProbabilitySource(eventForecast?.probability_source);
  const calibrationLabel = forecastMonitoring?.event_forecast?.calibration_passed == null
    ? '-'
    : forecastMonitoring.event_forecast.calibration_passed ? 'stabil' : 'Beobachten';
  const qualityGateLabel = latestBacktest?.quality_gate && typeof latestBacktest.quality_gate === 'object'
    ? ((latestBacktest.quality_gate as { overall_passed?: boolean }).overall_passed ? 'erfüllt' : 'Beobachten')
    : '-';

  return (
    <>
      <section className="evidence-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">Marktabgleich</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              Wie belastbar die Modellrichtung gerade ist
            </h2>
          </div>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Einsatzreife</span>
              <strong>{marketValidation?.decision_metrics?.readiness_score_0_100 != null ? `${Math.round(marketValidation.decision_metrics.readiness_score_0_100)}/100` : '-'}</strong>
            </div>
            <div className="metric-box">
              <span>Trefferquote</span>
              <strong>{formatPercent(marketValidation?.decision_metrics?.hit_rate_pct || 0)}</strong>
            </div>
            <div className="metric-box">
              <span>Fehlalarme</span>
              <strong>{formatPercent(marketValidation?.decision_metrics?.false_alarm_rate_pct || 0)}</strong>
            </div>
          </div>
          <p className="section-copy">
            Hier sehen wir, wie gut frühe Signale tatsächlich zu späteren Marktbewegungen passen. Das stützt den Vorlauf für die Planung, ersetzt aber noch keinen Kundendaten-Nachweis.
          </p>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">Vorhersage</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              Wann der Forecast mit Vorsicht gelesen werden sollte
            </h2>
          </div>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Prüfstatus</span>
              <strong>{readinessGateLabel(forecastMonitoring?.forecast_readiness)}</strong>
            </div>
            <div className="metric-box">
              <span>Stand der Vorhersage</span>
              <strong>{monitoringFreshnessLabel(forecastMonitoring?.freshness_status)}</strong>
            </div>
            <div className="metric-box">
              <span>Stand der Genauigkeit</span>
              <strong>{monitoringFreshnessLabel(forecastMonitoring?.accuracy_freshness_status)}</strong>
            </div>
          </div>
          <p className="section-copy">
            Dieser Block zeigt, ob die aktuelle Modellrichtung schon tragfähig genug ist oder ob sie nur mit Vorsicht erklärt werden sollte.
          </p>
          <div className="review-chip-row">
            <span className="step-chip">Rückblicktest: {monitoringFreshnessLabel(forecastMonitoring?.backtest_freshness_status)}</span>
            <span className="step-chip">Kalibrierung: {calibrationLabel}</span>
            <span className="step-chip">Quality Gate: {qualityGateLabel}</span>
            <span className="step-chip">
              Semantik: {eventProbabilityBadge}
            </span>
            <span className="step-chip">
              Quelle: {probabilitySource}
            </span>
            <span className="step-chip">
              Samples: {latestAccuracy?.samples != null ? latestAccuracy.samples : '-'}
            </span>
          </div>
          <div className="review-muted-copy" style={{ marginTop: 12 }}>
            {eventProbabilityNote}
          </div>
          <div className="soft-panel" style={{ padding: 16, marginTop: 16, display: 'grid', gap: 8 }}>
            <div className="campaign-focus-label">Was das aktuell bedeutet</div>
            <div className="review-body-copy">
              {COCKPIT_SEMANTICS.eventProbability.label} ist hier eine eigene Vorhersage-Metrik. Sie ist nicht dasselbe wie {COCKPIT_SEMANTICS.rankingSignal.label} oder {COCKPIT_SEMANTICS.decisionPriority.label}.
            </div>
            <div className="review-body-copy">
              Die Detail-Charts darunter halten Truth, Forecast und Unsicherheit bewusst getrennt. So bleibt nachvollziehbar, worauf sich die Empfehlung stützt.
            </div>
            <div className="review-body-copy">
              Wenn Kalibrierung, Quality Gate oder Sample Coverage schwach sind, solltest du die Richtung eher als Hinweis als als belastbare Freigabe lesen.
            </div>
            <div className="review-body-copy">
              {UI_COPY.stateLevelScope}: {COCKPIT_SEMANTICS.stateLevelScope.helper} {COCKPIT_SEMANTICS.noCityForecast.helper}
            </div>
          </div>
        </div>
      </section>

      <section style={{ display: 'grid', gap: 20 }}>
        <ValidationSection
          title="Markt-Validierung im Verlauf"
          subtitle="Hier siehst du, ob der Forecast eine Welle früh genug erkennt, um die Planung zeitlich sinnvoll zu unterstützen."
          result={marketValidation}
          loading={marketValidationLoading}
          emptyMessage="Noch keine detaillierten Daten für den Marktvergleich verfügbar."
        />
        {truthStatus?.coverage_weeks ? (
          <ValidationSection
            title="Kunden-Validierung im Verlauf"
            subtitle="Marktvergleich und Kundendaten bleiben getrennt. Dieser Bereich zeigt nur, wie gut das Modell an echte Outcome-Daten anschließt."
            result={customerValidation}
            loading={customerValidationLoading}
            emptyMessage="Noch keine ausreichend langen Kundenreihen für eine belastbare Validierung der Kundendaten verfügbar."
          />
        ) : (
          <section className="card subsection-card" style={{ padding: 24 }}>
            <div className="section-heading" style={{ gap: 6 }}>
              <h2 className="subsection-title">Kunden-Validierung im Verlauf</h2>
              <p className="subsection-copy">
                Dieser Block bleibt leer, bis echte Kundendaten angeschlossen sind. Frühere Läufe erscheinen separat nur als Hinweis.
              </p>
            </div>
            {legacyCustomer ? (
              <div className="soft-panel" style={{ padding: 16, marginTop: 14, display: 'grid', gap: 10 }}>
                <div className="evidence-row">
                  <span>Früherer Lauf</span>
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
          <span className="section-kicker">Vorhersage-Details</span>
          <h2 className="subsection-title">Technische Belastbarkeit im Detail</h2>
          <p className="subsection-copy">
            Diese Details brauchst du nur, wenn du die Belastbarkeit tiefer erklären oder einen Warnhinweis sauber begründen musst.
          </p>
        </div>

        <div className="metric-strip" style={{ marginTop: 18 }}>
          <div className="metric-box">
            <span>{eventProbabilityLabel}</span>
            <strong>{formatPercent((forecastMonitoring?.event_forecast?.event_probability || 0) * 100, 1)}</strong>
          </div>
          <div className="metric-box">
            <span>Mittlerer Fehler</span>
            <strong>{formatPercent(latestAccuracy?.mape, 1)}</strong>
          </div>
          <div className="metric-box">
            <span>Korrelation</span>
            <strong>{latestAccuracy?.correlation != null ? formatPercent(latestAccuracy.correlation * 100, 0) : '-'}</strong>
          </div>
          <div className="metric-box">
            <span>Vorlauf im Rückblicktest</span>
            <strong>{numberFromUnknown(leadLag.effective_lead_days) != null ? `${numberFromUnknown(leadLag.effective_lead_days)} Tage` : '-'}</strong>
          </div>
        </div>

        <div className="soft-panel" style={{ padding: 18, marginTop: 18, display: 'grid', gap: 10 }}>
          <div className="evidence-row">
            <span>Modellversion</span>
            <strong>{forecastMonitoring?.model_version || modelLineage?.model_version || '-'}</strong>
          </div>
          <div className="evidence-row">
            <span>Letzter Vorhersagelauf</span>
            <strong>{formatDateTime(forecastMonitoring?.issue_date || modelLineage?.latest_forecast_created_at)}</strong>
          </div>
          <div className="evidence-row">
            <span>Letzter Genauigkeitscheck</span>
            <strong>{formatDateTime(latestAccuracy?.computed_at)}</strong>
          </div>
          <div className="evidence-row">
            <span>Letzter Markt-Rückblicktest</span>
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
            <span>Fehler ggü. Persistenz-Basis</span>
            <strong>{formatSignedPercent(improvementVsBaselines.mae_vs_persistence_pct)}</strong>
          </div>
          <div className="evidence-row">
            <span>Fehler ggü. Saison-Basis</span>
            <strong>{formatSignedPercent(improvementVsBaselines.mae_vs_seasonal_pct)}</strong>
          </div>
        </div>

        {forecastMonitoring?.alerts?.length ? (
          <div className="soft-panel review-panel-soft" style={{ marginTop: 16, padding: 18 }}>
            <div className="campaign-focus-label">Wo der Forecast gerade Vorsicht braucht</div>
            <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
              {forecastMonitoring.alerts.map((alert) => (
                <div key={alert} className="review-body-copy">{sanitizeEvidenceCopy(alert)}</div>
              ))}
            </div>
          </div>
        ) : (
          <div className="review-muted-copy" style={{ marginTop: 16 }}>
            Aktuell gibt es keine offenen Warnhinweise aus der Vorhersage-Prüfung.
          </div>
        )}
      </section>
    </>
  );
};

export default ForecastMonitoringSection;

function readableProbabilitySource(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (!normalized) return 'noch unklar';
  if (normalized === 'learned') return 'gelerntes Modell';
  if (normalized === 'heuristic_sigmoid_proxy') return 'heuristischer Proxy';
  return value ? String(value) : 'noch unklar';
}
