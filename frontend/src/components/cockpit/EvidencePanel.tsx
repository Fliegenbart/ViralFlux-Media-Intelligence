import React, { useMemo, useState } from 'react';

import { UI_COPY, decisionStateLabel } from '../../lib/copy';
import {
  BacktestResponse,
  MediaEvidenceResponse,
  TruthImportBatchDetailResponse,
  TruthImportBatchSummary,
  TruthImportIssue,
  TruthImportResponse,
} from '../../types/media';
import { ValidationSection } from './BacktestVisuals';
import {
  formatDateShort,
  formatDateTime,
  formatPercent,
  learningStateLabel,
  truthFreshnessLabel,
  truthLayerLabel,
} from './cockpitUtils';

interface Props {
  evidence: MediaEvidenceResponse | null;
  loading: boolean;
  marketValidation: BacktestResponse | null;
  marketValidationLoading: boolean;
  customerValidation: BacktestResponse | null;
  customerValidationLoading: boolean;
  truthPreview: TruthImportResponse | null;
  truthBatchDetail: TruthImportBatchDetailResponse | null;
  truthActionLoading: boolean;
  truthBatchDetailLoading: boolean;
  onSubmitTruthCsv: (payload: {
    file: File;
    sourceLabel: string;
    replaceExisting: boolean;
    validateOnly: boolean;
  }) => Promise<void>;
  onLoadTruthBatchDetail: (batchId: string) => Promise<void>;
}

function issueFieldLabel(fieldName?: string | null): string {
  const normalized = String(fieldName || '').trim().toLowerCase();
  if (!normalized) return 'Allgemein';
  if (normalized === 'week_start') return 'Woche';
  if (normalized === 'product') return 'Produkt';
  if (normalized === 'region_code') return 'Region';
  if (normalized === 'media_spend_eur') return 'Media Spend';
  if (normalized === 'conversion') return 'Outcome';
  if (normalized === 'row') return 'Zeile';
  if (normalized === 'header') return 'CSV-Header';
  return normalized;
}

function batchStatusLabel(status?: string | null): string {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'validated') return 'Validiert';
  if (normalized === 'imported') return 'Importiert';
  if (normalized === 'partial_success') return 'Teilweise importiert';
  if (normalized === 'failed') return 'Fehlgeschlagen';
  return status ? String(status) : 'Offen';
}

function monitoringStatusLabel(status?: string | null): string {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'healthy') return 'Stabil';
  if (normalized === 'warning') return 'Beobachten';
  if (normalized === 'critical') return 'Kritisch';
  return status ? String(status) : 'Unbekannt';
}

function monitoringFreshnessLabel(state?: string | null): string {
  const normalized = String(state || '').trim().toLowerCase();
  if (normalized === 'fresh') return 'frisch';
  if (normalized === 'stale') return 'veraltet';
  if (normalized === 'expired') return 'abgelaufen';
  if (normalized === 'missing') return 'fehlt';
  return state ? String(state) : '-';
}

function numberFromUnknown(value: unknown): number | null {
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatSignedPercent(value: unknown, digits = 1): string {
  const numeric = numberFromUnknown(value);
  if (numeric == null) return '-';
  const prefix = numeric > 0 ? '+' : '';
  return `${prefix}${numeric.toFixed(digits)}%`;
}

const EvidencePanel: React.FC<Props> = ({
  evidence,
  loading,
  marketValidation,
  marketValidationLoading,
  customerValidation,
  customerValidationLoading,
  truthPreview,
  truthBatchDetail,
  truthActionLoading,
  truthBatchDetailLoading,
  onSubmitTruthCsv,
  onLoadTruthBatchDetail,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [sourceLabel, setSourceLabel] = useState('manual_csv');
  const [replaceExisting, setReplaceExisting] = useState(false);

  const latestMarket = evidence?.proxy_validation;
  const latestCustomer = evidence?.truth_validation;
  const legacyCustomer = evidence?.truth_validation_legacy;
  const sourceItems = evidence?.source_status?.items || [];
  const recentRuns = evidence?.recent_runs || [];
  const truthCoverage = evidence?.truth_coverage;
  const truthSnapshot = evidence?.truth_snapshot;
  const truthGate = evidence?.truth_gate || truthSnapshot?.truth_gate;
  const truthStatus = truthSnapshot?.coverage || truthCoverage;
  const outcomeLearning = evidence?.outcome_learning_summary || truthSnapshot?.outcome_learning_summary;
  const selectedBatch = truthBatchDetail?.batch || truthPreview?.batch_summary || truthSnapshot?.latest_batch;
  const displayIssues = useMemo<TruthImportIssue[]>(() => {
    if (truthPreview?.issues?.length) return truthPreview.issues;
    if (truthBatchDetail?.issues?.length) return truthBatchDetail.issues;
    return [];
  }, [truthBatchDetail?.issues, truthPreview?.issues]);
  const sourceStatusLabels = [
    ...(truthStatus?.required_fields_present || []),
    ...(truthStatus?.conversion_fields_present || []),
  ];
  const signalStack = evidence?.signal_stack;
  const modelLineage = evidence?.model_lineage;
  const forecastMonitoring = evidence?.forecast_monitoring;
  const latestAccuracy = forecastMonitoring?.latest_accuracy;
  const latestBacktest = forecastMonitoring?.latest_backtest;
  const intervalCoverage = (latestBacktest?.interval_coverage || {}) as Record<string, unknown>;
  const eventCalibration = (latestBacktest?.event_calibration || {}) as Record<string, unknown>;
  const leadLag = (latestBacktest?.lead_lag || {}) as Record<string, unknown>;
  const improvementVsBaselines = (latestBacktest?.improvement_vs_baselines || {}) as Record<string, unknown>;
  const driverGroups = signalStack?.summary?.driver_groups || {};

  if (loading && !evidence) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade Evidenz...</div>;
  }

  return (
    <div className="page-stack">
      <section className="context-filter-rail">
        <div className="section-heading">
          <span className="section-kicker">Evidenz</span>
          <h1 className="section-title">Marktvergleich, Kundendaten, Signalquellen und Modellzustand</h1>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <span className="step-chip">{UI_COPY.marketComparison}: validiert</span>
          <span className="step-chip">{UI_COPY.customerData}: {truthLayerLabel(truthStatus || latestCustomer)}</span>
          <span className="step-chip">{UI_COPY.customerDataFreshness}: {truthFreshnessLabel(truthStatus?.truth_freshness_state)}</span>
          <span className="step-chip">Learning: {learningStateLabel(outcomeLearning?.learning_state || truthGate?.learning_state)}</span>
          {signalStack?.summary?.decision_mode_label && <span className="step-chip">{signalStack.summary.decision_mode_label}</span>}
          <span className="step-chip">Forecast: {monitoringStatusLabel(forecastMonitoring?.monitoring_status)}</span>
          <span className="step-chip">Drift: {modelLineage?.drift_state || '-'}</span>
        </div>
      </section>

      <section className="evidence-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">Markt-Check</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              {decisionStateLabel(latestMarket?.quality_gate?.overall_passed ? 'GO' : 'WATCH')}
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
            Dieser Block zeigt, wie gut das System epidemiologische Trigger gegen Marktbewegungen trifft. Er misst Planungsguete im Marktvergleich, nicht den finalen Kundennachweis.
          </p>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">{UI_COPY.customerData}</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              {truthLayerLabel(truthStatus || latestCustomer)}
            </h2>
          </div>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Wochen</span>
              <strong>{truthStatus?.coverage_weeks ?? 0}</strong>
            </div>
            <div className="metric-box">
              <span>Aktualitaet</span>
              <strong>{truthFreshnessLabel(truthStatus?.truth_freshness_state)}</strong>
            </div>
            <div className="metric-box">
              <span>Letzter Import</span>
              <strong>{formatDateTime(truthStatus?.last_imported_at)}</strong>
            </div>
          </div>
          <p className="section-copy">
            Dieser Bereich basiert auf validiertem CSV-Import mit Media Spend und echten Outcome-Metriken. Er bewertet Datenbreite, Aktualitaet und Anschlussfaehigkeit an echte Kundenergebnisse.
          </p>
          <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
            <div className="evidence-row">
              <span>Truth-Gate</span>
              <strong>{truthGate?.passed ? 'freigeschaltet' : learningStateLabel(truthGate?.state)}</strong>
            </div>
            <div className="evidence-row">
              <span>Learning-State</span>
              <strong>{learningStateLabel(outcomeLearning?.learning_state || truthGate?.learning_state)}</strong>
            </div>
            <div className="evidence-row">
              <span>Outcome-Score</span>
              <strong>{formatPercent(outcomeLearning?.outcome_signal_score)}</strong>
            </div>
          </div>
          <div className="review-chip-row">
            {(sourceStatusLabels.length ? sourceStatusLabels : ['Noch keine Pflichtfelder vollständig vorhanden']).map((item) => (
              <span key={item} className="step-chip">{item}</span>
            ))}
          </div>
          {!truthStatus?.coverage_weeks && legacyCustomer && (
            <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
              <div className="campaign-focus-label">Explorativer Legacy-Run</div>
              <div className="review-body-copy" style={{ marginTop: 8 }}>
                {legacyCustomer.metrics?.data_points || 0} Punkte aus einem aelteren Kunden-Backtest. Dieser Run bleibt als historischer Hinweis sichtbar, zaehlt aber nicht als aktiver Bereich fuer Kundendaten.
              </div>
            </div>
          )}
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
            Dieser Block haengt direkt am Forecast-Kern: Drift, Accuracy, Backtest-Frische, Intervallabdeckung und Event-Kalibrierung werden aus demselben Stack gelesen wie die Opportunity-Gates.
          </p>
          <div className="review-chip-row">
            <span className="step-chip">Backtest: {monitoringFreshnessLabel(forecastMonitoring?.backtest_freshness_status)}</span>
            <span className="step-chip">
              Kalibrierung: {forecastMonitoring?.event_forecast?.calibration_passed == null ? '-' : forecastMonitoring?.event_forecast?.calibration_passed ? 'ok' : 'watch'}
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
          subtitle="Forecast gegen Ist, inklusive Baselines. So wird sichtbar, ob das Modell die Welle frueh erkennt und nicht nur nachzeichnet."
          result={marketValidation}
          loading={marketValidationLoading}
          emptyMessage="Noch keine detaillierten Daten fuer den Marktvergleich verfuegbar."
        />
        {truthStatus?.coverage_weeks ? (
          <ValidationSection
            title="Kunden-Validierung im Verlauf"
            subtitle="Marktvergleich und Kundendaten bleiben getrennt: Dieser Bereich zeigt nur, wie gut das Modell an echte Kunden-Outcome-Daten anschliesst."
            result={customerValidation}
            loading={customerValidationLoading}
            emptyMessage="Noch keine ausreichend langen Kundenreihen fuer eine belastbare Validierung der Kundendaten verfuegbar."
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
          <span className="section-kicker">Outcome-Learning</span>
          <h2 className="subsection-title">Beobachtete Wirkung statt nur Forecast und Ranking</h2>
          <p className="subsection-copy">
            Dieser Block zeigt, was aus importierten Outcome-Daten bereits gelernt wurde. Die Werte priorisieren, sind aber keine Forecast-Wahrscheinlichkeiten.
          </p>
        </div>
        <div className="metric-strip" style={{ marginTop: 16 }}>
          <div className="metric-box">
            <span>Learning-State</span>
            <strong>{learningStateLabel(outcomeLearning?.learning_state)}</strong>
          </div>
          <div className="metric-box">
            <span>Outcome-Score</span>
            <strong>{formatPercent(outcomeLearning?.outcome_signal_score)}</strong>
          </div>
          <div className="metric-box">
            <span>Learning-Konfidenz</span>
            <strong>{formatPercent(outcomeLearning?.outcome_confidence_pct)}</strong>
          </div>
        </div>
        <div className="soft-panel" style={{ padding: 18, marginTop: 18, display: 'grid', gap: 10 }}>
          {(outcomeLearning?.top_pair_learnings?.length ? outcomeLearning.top_pair_learnings : []).slice(0, 3).map((item, index) => (
            <div key={`${item.product_key || 'product'}-${item.region_code || index}`} className="evidence-row">
              <span>{item.product_key || item.product || 'Produkt'} · {item.region_code || 'Region'}</span>
              <strong>{formatPercent(item.outcome_signal_score)} · {learningStateLabel(outcomeLearning?.learning_state)}</strong>
            </div>
          ))}
          {!outcomeLearning?.top_pair_learnings?.length && (
            <div className="review-muted-copy">
              Noch keine granularen Produkt-Region-Learnings vorhanden. Sobald mehr Outcome-Reihen vorliegen, werden sie hier sichtbar.
            </div>
          )}
        </div>
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">Forecast-Details</span>
          <h2 className="subsection-title">Monitoring des Produktionsmodells</h2>
          <p className="subsection-copy">
            Hier sehen Analysten, ob der Forecast nicht nur laeuft, sondern auch mathematisch sauber ueber Accuracy, Vorlaufzeit, Intervalle und Kalibrierung im Zielkorridor bleibt.
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
            Aktuell gibt es keine offenen Monitoring-Warnungen fuer diesen Forecast-Stack.
          </div>
        )}
      </section>

      <section className="truth-analyst-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading">
            <span className="section-kicker">CSV Upload</span>
            <h2 className="subsection-title">Import der Kundendaten vorbereiten</h2>
            <p className="subsection-copy">
              Erwartet werden `week_start`, `product`, `region_code`, `media_spend_eur` plus mindestens eine echte Outcome-Metrik wie `sales_units`, `order_count` oder `revenue_eur`.
            </p>
          </div>

          <div className="truth-form-grid">
            <label className="campaign-field campaign-field-wide">
              <span>Datei</span>
              <input
                className="media-input"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
            </label>

            <label className="campaign-field">
              <span>Quellenlabel</span>
              <input
                className="media-input"
                value={sourceLabel}
                onChange={(event) => setSourceLabel(event.target.value)}
                placeholder="manual_csv"
              />
            </label>

            <label className="campaign-field truth-checkbox-field">
              <span>Vorhandene Daten ersetzen</span>
              <div className="truth-checkbox-row">
                <input
                  type="checkbox"
                  checked={replaceExisting}
                  onChange={(event) => setReplaceExisting(event.target.checked)}
                />
                <small>Bestehende Zeilen fuer dieselbe Woche, dasselbe Produkt und dieselbe Region ueberschreiben.</small>
              </div>
            </label>
          </div>

          <div className="campaign-setup-footer">
            <div className="campaign-setup-note">
              {file ? `Bereit: ${file.name}` : 'Zuerst eine Weekly-CSV auswaehlen, dann validieren und erst danach importieren.'}
            </div>
            <div className="review-action-row">
              <a className="media-button secondary" href={truthSnapshot?.template_url || '/api/v1/media/outcomes/template'}>
                Vorlage laden
              </a>
              <button
                className="media-button secondary"
                type="button"
                disabled={!file || truthActionLoading}
                onClick={() => file && onSubmitTruthCsv({ file, sourceLabel, replaceExisting, validateOnly: true })}
              >
                {truthActionLoading ? 'Validierung läuft...' : 'Zuerst validieren'}
              </button>
              <button
                className="media-button primary"
                type="button"
                disabled={!file || truthActionLoading}
                onClick={() => file && onSubmitTruthCsv({ file, sourceLabel, replaceExisting, validateOnly: false })}
              >
                {truthActionLoading ? 'Import läuft...' : 'Importieren'}
              </button>
            </div>
          </div>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading">
            <span className="section-kicker">Import-Vorschau</span>
            <h2 className="subsection-title">Pruefung und Ergebnis</h2>
            <p className="subsection-copy">
              Erst pruefen, dann importieren. Vorschau und importierter Upload zeigen dieselben Kennzahlen, Hinweise und Projektionen.
            </p>
          </div>

          {truthPreview?.batch_summary ? (
            <>
              <div className="metric-strip">
                <div className="metric-box">
                  <span>Status</span>
                  <strong>{batchStatusLabel(truthPreview.batch_summary.status)}</strong>
                </div>
                <div className="metric-box">
                  <span>Gültige Zeilen</span>
                  <strong>{truthPreview.batch_summary.rows_valid}</strong>
                </div>
                <div className="metric-box">
                  <span>Hinweise</span>
                  <strong>{truthPreview.issues.length}</strong>
                </div>
              </div>
              <div className="soft-panel review-panel-soft">
                <div className="evidence-row">
                  <span>Abdeckung nach Import</span>
                  <strong>{truthPreview.coverage_after_import?.coverage_weeks ?? 0} Wochen</strong>
                </div>
                <div className="evidence-row">
                  <span>Status Kundendaten</span>
                  <strong>{truthLayerLabel(truthPreview.coverage_after_import)}</strong>
                </div>
                <div className="evidence-row">
                  <span>Aktualitaet</span>
                  <strong>{truthFreshnessLabel(truthPreview.coverage_after_import?.truth_freshness_state)}</strong>
                </div>
              </div>
              <p className="section-copy">{truthPreview.message}</p>
            </>
          ) : (
            <div className="review-muted-copy">
              Noch keine Vorschau vorhanden. Lade eine CSV hoch und starte zuerst die Validierung.
            </div>
          )}
        </div>
      </section>

      <section className="truth-analyst-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading">
            <span className="section-kicker">Import-Historie</span>
            <h2 className="subsection-title">Letzte Uploads</h2>
          </div>
          <div className="truth-history-list">
            {(truthSnapshot?.recent_batches || []).length > 0 ? truthSnapshot!.recent_batches.map((batch: TruthImportBatchSummary) => (
              <button
                key={batch.batch_id}
                type="button"
                className={`truth-history-item ${selectedBatch?.batch_id === batch.batch_id ? 'is-active' : ''}`}
                onClick={() => onLoadTruthBatchDetail(batch.batch_id)}
              >
                <div>
                  <strong>{batch.file_name || batch.source_label || batch.batch_id}</strong>
                  <span>{batchStatusLabel(batch.status)} · {formatDateTime(batch.uploaded_at)}</span>
                </div>
                <small>{batch.rows_imported}/{batch.rows_total} importiert</small>
              </button>
            )) : (
              <div className="review-muted-copy">Noch keine Uploads fuer Kundendaten vorhanden.</div>
            )}
          </div>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading">
            <span className="section-kicker">Upload-Detail</span>
            <h2 className="subsection-title">Ausgewaehlter Import</h2>
          </div>
          {truthBatchDetailLoading ? (
            <div className="review-muted-copy">Upload-Detail laedt...</div>
          ) : selectedBatch ? (
            <div className="soft-panel review-panel-soft" style={{ display: 'grid', gap: 0 }}>
              <div className="evidence-row">
                <span>Batch</span>
                <strong>{selectedBatch.batch_id}</strong>
              </div>
              <div className="evidence-row">
                <span>Status</span>
                <strong>{batchStatusLabel(selectedBatch.status)}</strong>
              </div>
              <div className="evidence-row">
                <span>Zeitraum</span>
                <strong>{formatDateShort(selectedBatch.week_min)} bis {formatDateShort(selectedBatch.week_max)}</strong>
              </div>
              <div className="evidence-row">
                <span>Abdeckung nach Import</span>
                <strong>{selectedBatch.coverage_after_import?.coverage_weeks ?? 0} Wochen</strong>
              </div>
            </div>
          ) : (
            <div className="review-muted-copy">Waehle einen Upload aus der Historie oder validiere eine neue Datei.</div>
          )}
        </div>
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">Hinweis-Tabelle</span>
          <h2 className="subsection-title">Import-Probleme und Mapping-Hinweise</h2>
          <p className="subsection-copy">
            Jeder ausgeschlossene Datensatz bleibt sichtbar. Es gibt keine stillen Ausfaelle.
          </p>
        </div>
        <div className="truth-issue-table">
          {displayIssues.length > 0 ? displayIssues.map((issue, index) => (
            <div key={`${issue.issue_code}-${issue.row_number || index}`} className="truth-issue-row">
              <div>
                <strong>Zeile {issue.row_number ?? '-'}</strong>
                <span>{issueFieldLabel(issue.field_name)} · {issue.issue_code}</span>
              </div>
              <p>{issue.message}</p>
            </div>
          )) : (
            <div className="review-muted-copy">Keine Hinweise sichtbar. Die aktuelle Vorschau oder der ausgewaehlte Upload ist sauber.</div>
          )}
        </div>
      </section>

      <section className="cockpit-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Datenfrische</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {Object.entries(evidence?.data_freshness || {}).map(([key, value]) => (
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
                  {item.freshness_state}
                </strong>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="cockpit-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Signalquellen</h2>
          <div className="review-chip-row" style={{ marginTop: 14 }}>
            {Object.entries(driverGroups).map(([key, group]) => (
              <span key={key} className="step-chip">
                {group.label} {formatPercent(group.contribution || 0)}
              </span>
            ))}
          </div>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {(signalStack?.items || []).map((item) => (
              <div key={item.source_key} className="evidence-row">
                <span>{item.label}</span>
                <strong>{item.is_core_signal ? 'epi-kern' : item.contribution_state}</strong>
              </div>
            ))}
          </div>
          {signalStack?.summary?.decision_mode_reason && (
            <p className="section-copy" style={{ marginTop: 14 }}>
              {signalStack.summary.decision_mode_reason}
            </p>
          )}
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Modellhistorie</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            <div className="evidence-row">
              <span>Stack</span>
              <strong>{[...(modelLineage?.base_estimators || []), modelLineage?.meta_learner].filter(Boolean).join(' → ') || '-'}</strong>
            </div>
            <div className="evidence-row">
              <span>Version</span>
              <strong>{modelLineage?.model_version || '-'}</strong>
            </div>
            <div className="evidence-row">
              <span>Trainiert am</span>
              <strong>{formatDateTime(modelLineage?.trained_at)}</strong>
            </div>
            <div className="evidence-row">
              <span>Feature-Set</span>
              <strong>{modelLineage?.feature_set_version || '-'}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <h2 className="subsection-title">Letzte Laeufe</h2>
        <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
          {recentRuns.length > 0 ? recentRuns.slice(0, 6).map((run, index) => (
            <div key={`${String(run.mode)}-${index}`} className="evidence-row">
              <span>{String(run.mode || 'Run')}</span>
              <strong>{String(run.status || '-')}</strong>
            </div>
          )) : (
            <div style={{ color: 'var(--text-muted)' }}>Noch keine Laufhistorie im Cockpit vorhanden.</div>
          )}
        </div>
      </section>

      {(truthSnapshot?.known_limits || evidence?.known_limits || []).length > 0 && (
        <section className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Bekannte Grenzen</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {[...(truthSnapshot?.known_limits || []), ...(evidence?.known_limits || [])].map((item) => (
              <div key={item} className="evidence-row">
                <span>{item}</span>
                <strong>Limit</strong>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default EvidencePanel;
