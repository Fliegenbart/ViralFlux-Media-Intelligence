import React from 'react';

import {
  BacktestResponse,
  MediaEvidenceResponse,
  TruthImportBatchDetailResponse,
  TruthImportResponse,
  WorkspaceStatusSummary,
} from '../../types/media';
import CollapsibleSection from '../CollapsibleSection';
import ForecastMonitoringSection from './evidence/ForecastMonitoringSection';
import ImportValidationSection from './evidence/ImportValidationSection';
import SourceFreshnessSection from './evidence/SourceFreshnessSection';
import TruthOutcomeSection from './evidence/TruthOutcomeSection';
import { monitoringStatusLabel, runModeLabel } from './evidence/evidenceUtils';
import WorkspaceStatusPanel from './WorkspaceStatusPanel';

interface Props {
  evidence: MediaEvidenceResponse | null;
  workspaceStatus: WorkspaceStatusSummary | null;
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
  workspaceStatus,
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

  if (loading && !evidence) {
    return (
      <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
        Lade Qualität...
      </div>
    );
  }

  return (
    <div className="page-stack evidence-template-page">
      <section className="context-filter-rail">
        <div className="section-heading" style={{ marginBottom: 0 }}>
          <span className="section-kicker">Qualität</span>
          <h1 className="section-title">Warum wir die Vorhersage vertreten</h1>
          <p className="section-copy">
            Hier belegen wir, warum wir das 3-, 5- oder 7-Tage-Fenster vertreten und wo wir den frühen Start einer Welle sehen.
          </p>
        </div>

        <div className="soft-panel" style={{ padding: 16, maxWidth: 360 }}>
          <div className="section-kicker">Kurzfazit</div>
          <p className="section-copy" style={{ margin: '10px 0 0' }}>
            {workspaceStatus?.summary || 'Sobald Qualitätsdaten vorliegen, fassen wir hier den schnellsten Prüfpfad zusammen.'}
          </p>
        </div>
      </section>

      <WorkspaceStatusPanel
        status={workspaceStatus}
        title="Vier schnelle Fragen"
        intro="Wenn hier etwas wackelt, gehen wir tiefer in Vorhersage, Kundendaten, Quellen oder Import."
      />

      {workspaceStatus?.blockers?.length ? (
        <section className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading" style={{ gap: 6 }}>
            <h2 className="subsection-title">Offene Punkte zuerst</h2>
            <p className="subsection-copy">
              Das sind die wichtigsten offenen Punkte, bevor wir blind weitermachen.
            </p>
          </div>
          <div className="workspace-note-list">
            {workspaceStatus.blockers.map((blocker) => (
              <div key={blocker} className="workspace-note-card">
                {blocker}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <CollapsibleSection
        title="1. Vorhersage prüfen"
        subtitle="Ist das Modell stabil genug, um das 3-, 5- oder 7-Tage-Fenster belastbar zu tragen?"
        defaultOpen
      >
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
      </CollapsibleSection>

      <CollapsibleSection
        title="2. Kundendaten prüfen"
        subtitle="Sind echte Kundendaten angeschlossen und stark genug, um die Empfehlung zusätzlich zu stützen?"
      >
        <TruthOutcomeSection
          truthStatus={truthStatus}
          truthGate={truthGate}
          businessValidation={businessValidation}
          outcomeLearning={outcomeLearning}
          legacyCustomer={legacyCustomer}
          sourceStatusLabels={sourceStatusLabels}
        />
      </CollapsibleSection>

      <CollapsibleSection
        title="3. Quellen prüfen"
        subtitle="Wie frisch sind Quellen, Signalsystem und Modellhistorie wirklich?"
      >
        <SourceFreshnessSection
          evidence={evidence}
          sourceItems={sourceItems}
          signalStack={signalStack}
          driverGroups={driverGroups}
          modelLineage={modelLineage}
          recentRuns={recentRuns}
          truthSnapshot={truthSnapshot}
        />
      </CollapsibleSection>

      <CollapsibleSection
        title="4. Import prüfen"
        subtitle="Neue Kundendaten validieren, importieren und vorhandene Batches nachvollziehen."
      >
        <ImportValidationSection
          truthSnapshot={truthSnapshot}
          truthPreview={truthPreview}
          truthBatchDetail={truthBatchDetail}
          truthActionLoading={truthActionLoading}
          truthBatchDetailLoading={truthBatchDetailLoading}
          onSubmitTruthCsv={onSubmitTruthCsv}
          onLoadTruthBatchDetail={onLoadTruthBatchDetail}
        />
      </CollapsibleSection>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading" style={{ gap: 6 }}>
          <h2 className="subsection-title">Technischer Überblick</h2>
          <p className="subsection-copy">
            Nur die wichtigsten technischen Hinweise, falls wir schnell die Quelle eines Problems verstehen wollen.
          </p>
        </div>
        <div className="workspace-two-column">
          <div className="soft-panel workspace-detail-panel">
            <div className="section-kicker">Signalsystem</div>
            <div className="workspace-note-list" style={{ marginTop: 12 }}>
              {(sourceStatusLabels.length ? sourceStatusLabels : ['Noch keine markierten Felder vorhanden.']).slice(0, 6).map((item) => (
                <div key={item} className="workspace-note-card">{item}</div>
              ))}
            </div>
          </div>

          <div className="soft-panel workspace-detail-panel">
            <div className="section-kicker">Letzte Läufe</div>
            <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
              {recentRuns.length > 0 ? recentRuns.slice(0, 3).map((run, index) => (
                <div key={`${String(run.mode)}-${index}`} className="evidence-row">
                  <span>{runModeLabel(String(run.mode || 'Lauf'))}</span>
                  <strong>{monitoringStatusLabel(String(run.status || '-'))}</strong>
                </div>
              )) : (
                <div className="workspace-note-card">Noch keine Laufhistorie vorhanden.</div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default EvidencePanel;
