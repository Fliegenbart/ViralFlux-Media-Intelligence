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
    return (
      <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
        Lade Evidenz...
      </div>
    );
  }

  const TABS = [
    {
      key: 'forecast',
      label: 'Forecast',
      kicker: 'Monitoring',
      description: 'Produktionsmodell, Markt-Check und die Frage, ob der Forecast aktuell stabil genug ist.',
      icon: 'insights',
    },
    {
      key: 'truth',
      label: 'Kundendaten',
      kicker: 'Outcome',
      description: 'CSV-Import, Business-Gate und beobachtete Wirkung statt nur Forecast und Ranking.',
      icon: 'check_circle',
    },
    {
      key: 'sources',
      label: 'Datenquellen',
      kicker: 'Stack',
      description: 'Frische, Quellenstatus und Modellhistorie für den epidemiologischen Kern.',
      icon: 'hub',
    },
    {
      key: 'import',
      label: 'Import',
      kicker: 'Batches',
      description: 'Neue Kundendaten prüfen, Uploads nachvollziehen und Probleme in einer Spur sehen.',
      icon: 'upload_file',
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

  const railSignals = [
    {
      label: 'Forecast',
      value: monitoringStatusLabel(forecastMonitoring?.monitoring_status),
      icon: 'monitoring',
    },
    {
      label: UI_COPY.customerData,
      value: truthLayerLabel(truthStatus || latestCustomer),
      icon: 'dataset',
    },
    {
      label: 'Drift',
      value: modelLineage?.drift_state || '-',
      icon: 'timeline',
    },
  ];

  const sourceFocus = sourceItems.slice(0, 4);
  const runPreview = recentRuns.slice(0, 3);

  return (
    <div className="page-stack evidence-template-page">
      <section className="evidence-page-header">
        <div className="evidence-page-header__copy">
          <span className="evidence-page-header__kicker">Media Intelligence</span>
          <h1 className="evidence-page-header__title">Warum wir dieser Woche vertrauen</h1>
          <p className="evidence-page-header__text">
            Diese Ansicht bleibt bewusst eine Analyse- und Prüfstrecke. Links liegt der Kontext, rechts die eigentliche Arbeitsfläche.
          </p>
        </div>

        <div className="evidence-page-header__switch">
          {TABS.map(({ key, label, icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveTab(key)}
              className={`evidence-switch-chip ${activeTab === key ? 'active' : ''}`}
            >
              <span className="material-symbols-outlined" aria-hidden="true">{icon}</span>
              <span>{label}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="evidence-template-layout">
        <aside className="evidence-filter-rail">
          <div className="evidence-filter-rail__block">
            <h3>
              <span className="material-symbols-outlined" aria-hidden="true">filter_list</span>
              Analysepfade
            </h3>
            <p>Der linke Bereich ersetzt die Social-Demo der Vorlage durch echte ViralFlux-Prüfpfade.</p>
          </div>

          <div className="evidence-filter-rail__tabs" role="tablist" aria-label="Evidenz-Bereiche">
            {TABS.map(({ key, label, kicker, description, icon }) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={activeTab === key}
                className={`evidence-sidebar-tab ${activeTab === key ? 'active' : ''}`}
                onClick={() => setActiveTab(key)}
              >
                <span className="evidence-sidebar-tab__icon material-symbols-outlined" aria-hidden="true">{icon}</span>
                <span className="evidence-sidebar-tab__kicker">{kicker}</span>
                <strong>{label}</strong>
                <small>{description}</small>
              </button>
            ))}
          </div>

          <div className="evidence-filter-rail__block">
            <span className="evidence-filter-rail__label">Systemstatus</span>
            <div className="evidence-status-list">
              {railSignals.map((item) => (
                <div key={item.label} className="evidence-status-row">
                  <span className="evidence-status-row__icon material-symbols-outlined" aria-hidden="true">{item.icon}</span>
                  <div>
                    <strong>{item.label}</strong>
                    <p>{item.value}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="evidence-filter-rail__block">
            <span className="evidence-filter-rail__label">Quellenfokus</span>
            <div className="evidence-source-pills">
              {(sourceFocus.length ? sourceFocus : [{ source_key: 'none', label: 'Noch keine Quelle', freshness_state: 'offen' }]).map((item) => (
                <span key={item.source_key} className="evidence-source-pill">
                  {item.label} · {item.freshness_state}
                </span>
              ))}
            </div>
          </div>

          <div className="evidence-brief-card">
            <span className="material-symbols-outlined" aria-hidden="true">auto_awesome</span>
            <h4>Kurzbriefing</h4>
            <p>{activeTabMeta.description}</p>
          </div>
        </aside>

        <div className="evidence-template-main">
          <section className="evidence-overview-grid">
            {overviewCards.map((card) => (
              <div key={card.label} className="card evidence-overview-card" style={{ padding: 22 }}>
                <span className="evidence-overview-card__label">{card.label}</span>
                <strong>{card.value}</strong>
                <p>{card.note}</p>
              </div>
            ))}
          </section>

          <section className="card evidence-primary-stage">
            <div className="evidence-primary-stage__header">
              <div>
                <span className="section-kicker">{activeTabMeta.kicker}</span>
                <h2>{activeTabMeta.label} im Detail</h2>
                <p>{activeTabMeta.description}</p>
              </div>
              <div className="evidence-primary-stage__chips">
                <span className="step-chip">Forecast: {forecastMonitoring?.monitoring_status || '-'}</span>
                <span className="step-chip">{UI_COPY.customerData}: {truthLayerLabel(truthStatus || latestCustomer)}</span>
                <span className="step-chip">Import: {latestImportStatus}</span>
              </div>
            </div>

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
          </section>

          <section className="evidence-support-grid">
            <div className="card evidence-support-card">
              <div className="section-kicker">Signal-Stack</div>
              <h3>Worauf der aktuelle Pfad gerade schaut</h3>
              <div className="evidence-source-pills">
                {(sourceStatusLabels.length ? sourceStatusLabels : ['Noch keine markierten Felder vorhanden.']).slice(0, 6).map((item) => (
                  <span key={item} className="evidence-source-pill">{item}</span>
                ))}
              </div>
              <p>
                {signalStack?.summary?.decision_mode_reason || 'Der Stack zeigt hier die Felder und Spuren, die für die aktuelle Prüfung gerade am wichtigsten sind.'}
              </p>
            </div>

            <div className="card evidence-support-card">
              <div className="section-kicker">Letzte Läufe</div>
              <h3>Welche Runs zuletzt auffällig waren</h3>
              <div className="evidence-support-card__list">
                {runPreview.length > 0 ? runPreview.map((run, index) => (
                  <div key={`${String(run.mode)}-${index}`} className="evidence-row">
                    <span>{String(run.mode || 'Run')}</span>
                    <strong>{String(run.status || '-')}</strong>
                  </div>
                )) : (
                  <div className="evidence-row">
                    <span>Historie</span>
                    <strong>Noch keine Laufhistorie vorhanden</strong>
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
      </section>
    </div>
  );
};

export default EvidencePanel;
