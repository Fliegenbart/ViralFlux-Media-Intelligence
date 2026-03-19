import React, { useState } from 'react';

import { UI_COPY } from '../../lib/copy';
import {
  BacktestResponse,
  MediaEvidenceResponse,
  TruthImportBatchDetailResponse,
  TruthImportResponse,
} from '../../types/media';
import {
  truthLayerLabel,
} from './cockpitUtils';
import { monitoringStatusLabel } from './evidence/evidenceUtils';
import ForecastMonitoringSection from './evidence/ForecastMonitoringSection';
import ImportValidationSection from './evidence/ImportValidationSection';
import SourceFreshnessSection from './evidence/SourceFreshnessSection';
import TruthOutcomeSection from './evidence/TruthOutcomeSection';

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
  const legacyCustomer = evidence?.truth_validation_legacy;
  const sourceItems = evidence?.source_status?.items || [];
  const recentRuns = evidence?.recent_runs || [];
  const truthCoverage = evidence?.truth_coverage;
  const latestCustomer = evidence?.truth_validation;
  const truthSnapshot = evidence?.truth_snapshot;
  const truthGate = evidence?.truth_gate || truthSnapshot?.truth_gate;
  const truthStatus = truthSnapshot?.coverage || truthCoverage;
  const businessValidation = evidence?.business_validation || truthSnapshot?.business_validation;
  const outcomeLearning = evidence?.outcome_learning_summary || truthSnapshot?.outcome_learning_summary;
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
  const [activeTab, setActiveTab] = useState<string>('forecast');

  if (loading && !evidence) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade Evidenz...</div>;
  }

  const TABS = [
    {
      key: 'forecast',
      label: 'Forecast',
      kicker: 'Monitoring',
      description: 'Produktionsmodell, Markt-Check und die Frage, ob der Forecast aktuell stabil genug ist.',
    },
    {
      key: 'truth',
      label: 'Kundendaten',
      kicker: 'Outcome',
      description: 'CSV-Import, Business-Gate und beobachtete Wirkung statt nur Forecast und Ranking.',
    },
    {
      key: 'sources',
      label: 'Datenquellen',
      kicker: 'Stack',
      description: 'Frische, Quellenstatus und Modellhistorie für den epidemiologischen Kern.',
    },
    {
      key: 'import',
      label: 'Import',
      kicker: 'Batches',
      description: 'Neue Kundendaten prüfen, Uploads nachvollziehen und Probleme in einer Spur sehen.',
    },
  ] as const;
  const activeTabMeta = TABS.find(({ key }) => key === activeTab) || TABS[0];
  const sourceAttentionCount = sourceItems.filter((item) => String(item.status_color || '').toLowerCase() !== 'green').length;
  const latestImportStatus = truthBatchDetail?.batch?.status
    || truthPreview?.batch_summary?.status
    || truthStatus?.truth_freshness_state
    || '-';
  const overviewCards = [
    {
      label: 'Forecast-Monitoring',
      value: monitoringStatusLabel(forecastMonitoring?.monitoring_status),
      note: forecastMonitoring?.forecast_readiness || 'Status offen',
    },
    {
      label: UI_COPY.customerData,
      value: truthLayerLabel(truthStatus || latestCustomer),
      note: truthStatus?.coverage_weeks != null ? `${truthStatus.coverage_weeks} Wochen verbunden` : 'Noch keine breite Coverage',
    },
    {
      label: 'Datenquellen',
      value: `${sourceItems.length || 0}`,
      note: sourceAttentionCount > 0 ? `${sourceAttentionCount} Quelle(n) brauchen Aufmerksamkeit` : 'Alle Quellen im grünen Bereich',
    },
    {
      label: 'Importstatus',
      value: latestImportStatus,
      note: truthPreview?.preview_only ? 'Aktuell nur Vorschau geprüft' : 'Letzter Batch oder Frischestatus',
    },
  ];

  return (
    <div className="page-stack evidence-page-shell">
      <section className="context-filter-rail evidence-toolbar">
        <div className="section-heading">
          <span className="section-kicker">Evidenz</span>
          <h1 className="section-title">Warum wir dieser Woche vertrauen</h1>
          <p className="section-copy">
            Diese Seite ist bewusst eine Analyse- und Prüfstrecke. Links wählen wir die Spur, rechts prüfen wir Forecast, Datenquellen und Kundendaten im Detail.
          </p>
        </div>
        <div className="review-chip-row">
          <span className="step-chip">Forecast: {forecastMonitoring?.monitoring_status || '-'}</span>
          <span className="step-chip">{UI_COPY.customerData}: {truthLayerLabel(truthStatus || latestCustomer)}</span>
          <span className="step-chip">Drift: {modelLineage?.drift_state || '-'}</span>
          <span className="step-chip">Aktive Spur: {activeTabMeta.label}</span>
        </div>
      </section>

      <section className="evidence-analysis-layout">
        <aside className="card evidence-analysis-sidebar" style={{ padding: 24 }}>
          <div className="section-heading" style={{ gap: 6 }}>
            <span className="section-kicker">Analysepfade</span>
            <h2 className="subsection-title">Wo wir prüfen</h2>
            <p className="subsection-copy">{activeTabMeta.description}</p>
          </div>

          <div className="evidence-sidebar__tab-list" role="tablist" aria-label="Evidenz-Bereiche">
            {TABS.map(({ key, label, kicker, description }) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={activeTab === key}
                className={`evidence-sidebar-tab ${activeTab === key ? 'active' : ''}`}
                onClick={() => setActiveTab(key)}
              >
                <span className="evidence-sidebar-tab__kicker">{kicker}</span>
                <strong>{label}</strong>
                <small>{description}</small>
              </button>
            ))}
          </div>

          <div className="evidence-sidebar__summary">
            <div className="soft-panel evidence-sidebar__note">
              <div className="section-kicker">Aktuell</div>
              <strong>{activeTabMeta.label}</strong>
              <p>{activeTabMeta.description}</p>
            </div>
            <div className="soft-panel evidence-sidebar__note">
              <div className="section-kicker">Kundendaten</div>
              <strong>{truthLayerLabel(truthStatus || latestCustomer)}</strong>
              <p>
                {truthStatus?.coverage_weeks != null
                  ? `${truthStatus.coverage_weeks} Wochen Coverage verbunden.`
                  : 'Noch keine belastbare Kundendaten-Coverage verbunden.'}
              </p>
            </div>
          </div>
        </aside>

        <div className="evidence-analysis-main">
          <section className="evidence-overview-grid">
            {overviewCards.map((card) => (
              <div key={card.label} className="card evidence-overview-card" style={{ padding: 22 }}>
                <span className="evidence-overview-card__label">{card.label}</span>
                <strong>{card.value}</strong>
                <p>{card.note}</p>
              </div>
            ))}
          </section>

          <div className="evidence-analysis-content">
            {activeTab === 'forecast' && (
              <ForecastMonitoringSection
                forecastMonitoring={forecastMonitoring}
                modelLineage={modelLineage}
                latestAccuracy={latestAccuracy}
                latestBacktest={latestBacktest}
                intervalCoverage={intervalCoverage}
                eventCalibration={eventCalibration}
                leadLag={leadLag}
                improvementVsBaselines={improvementVsBaselines}
                marketValidation={marketValidation}
                marketValidationLoading={marketValidationLoading}
                customerValidation={customerValidation}
                customerValidationLoading={customerValidationLoading}
                legacyCustomer={legacyCustomer}
                truthStatus={truthStatus}
              />
            )}

            {activeTab === 'truth' && (
              <TruthOutcomeSection
                truthStatus={truthStatus}
                truthGate={truthGate}
                businessValidation={businessValidation}
                outcomeLearning={outcomeLearning}
                legacyCustomer={legacyCustomer}
                sourceStatusLabels={sourceStatusLabels}
              />
            )}

            {activeTab === 'sources' && (
              <SourceFreshnessSection
                evidence={evidence}
                sourceItems={sourceItems}
                signalStack={signalStack}
                driverGroups={driverGroups}
                modelLineage={modelLineage}
                recentRuns={recentRuns}
                truthSnapshot={truthSnapshot}
              />
            )}

            {activeTab === 'import' && (
              <ImportValidationSection
                truthSnapshot={truthSnapshot}
                truthPreview={truthPreview}
                truthBatchDetail={truthBatchDetail}
                truthActionLoading={truthActionLoading}
                truthBatchDetailLoading={truthBatchDetailLoading}
                onSubmitTruthCsv={onSubmitTruthCsv}
                onLoadTruthBatchDetail={onLoadTruthBatchDetail}
              />
            )}
          </div>
        </div>
      </section>
    </div>
  );
};

export default EvidencePanel;
