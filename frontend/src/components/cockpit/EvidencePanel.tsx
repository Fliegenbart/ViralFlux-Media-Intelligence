import React, { useState } from 'react';

import { UI_COPY } from '../../lib/copy';
import {
  BacktestResponse,
  MediaEvidenceResponse,
  TruthImportBatchDetailResponse,
  TruthImportResponse,
} from '../../types/media';
import {
  learningStateLabel,
  truthFreshnessLabel,
  truthLayerLabel,
} from './cockpitUtils';
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

  if (loading && !evidence) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade Evidenz...</div>;
  }

  const TABS = [
    { key: 'forecast', label: 'Forecast' },
    { key: 'truth', label: 'Kundendaten' },
    { key: 'sources', label: 'Datenquellen' },
    { key: 'import', label: 'Import' },
  ] as const;

  const [activeTab, setActiveTab] = useState<string>('forecast');

  return (
    <div className="page-stack">
      <section className="context-filter-rail">
        <div className="section-heading">
          <span className="section-kicker">Evidenz</span>
          <h1 className="section-title">Warum wir dieser Woche vertrauen</h1>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          <span className="step-chip">Forecast: {forecastMonitoring?.monitoring_status || '-'}</span>
          <span className="step-chip">{UI_COPY.customerData}: {truthLayerLabel(truthStatus || latestCustomer)}</span>
          <span className="step-chip">Drift: {modelLineage?.drift_state || '-'}</span>
        </div>
      </section>

      <div className="evidence-tab-bar" role="tablist" aria-label="Evidenz-Bereiche">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            role="tab"
            aria-selected={activeTab === key}
            className={`evidence-tab-btn ${activeTab === key ? 'active' : ''}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

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
  );
};

export default EvidencePanel;
