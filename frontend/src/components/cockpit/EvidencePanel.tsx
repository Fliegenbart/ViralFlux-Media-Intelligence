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
import { OperatorPanel, OperatorSection } from './operator/OperatorPrimitives';

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
      <OperatorSection
        kicker="Qualität"
        title="Warum wir die Vorhersage vertreten"
        description="Wir holen gerade die Qualitätsdaten. Gleich siehst du wieder die wichtigsten Prüfpfade."
        tone="muted"
      >
        <div className="workspace-note-card">Lade Qualität...</div>
      </OperatorSection>
    );
  }

  return (
    <div className="page-stack evidence-template-page">
      <OperatorSection
        kicker="Qualität"
        title="Warum wir die Vorhersage vertreten"
        description="Hier zeigen wir, warum wir das 3-, 5- oder 7-Tage-Fenster vertreten und woran wir den frühen Start einer Welle erkennen."
        tone="muted"
        className="operator-toolbar-shell"
      >
        <div className="workspace-priority-grid">
          <OperatorPanel
            eyebrow="Prüffokus"
            title="Was zuerst wichtig ist"
            description="Das Kurzfazit bleibt oben, damit wir nicht erst durch die Detailblöcke springen müssen."
            tone="muted"
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">
                {workspaceStatus?.summary || 'Sobald Qualitätsdaten vorliegen, fassen wir hier den schnellsten Prüfpfad zusammen.'}
              </div>
              <div className="workspace-note-card">
                Prüfpfad: Vorhersage, Kundendaten, Quellen und Import.
              </div>
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Kurzfazit"
            title="Was gerade im Blick bleibt"
            description="Das Kurzfazit steht oben, damit man nicht erst durch die Detailblöcke springen muss."
            tone="muted"
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">
                {workspaceStatus?.summary || 'Noch kein zusammengefasster Qualitätsstatus vorhanden.'}
              </div>
              <div className="workspace-note-card">
                Wenn hier etwas offen bleibt, gehen wir tiefer in die vier Prüfbereiche.
              </div>
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>

      <WorkspaceStatusPanel
        status={workspaceStatus}
        title="Vier schnelle Fragen"
        intro="Wenn hier etwas offen bleibt, gehen wir tiefer in Vorhersage, Kundendaten, Quellen oder Import."
      />

      {workspaceStatus?.blockers?.length ? (
        <OperatorSection
          kicker="Offene Punkte"
          title="Offene Punkte zuerst"
          description="Das sind die wichtigsten offenen Punkte, bevor wir weitergehen."
          tone="muted"
        >
          <div className="workspace-note-list">
            {workspaceStatus.blockers.map((blocker) => (
              <div key={blocker} className="workspace-note-card">
                {blocker}
              </div>
            ))}
          </div>
        </OperatorSection>
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

      <OperatorSection
        kicker="Technischer Blick"
        title="Die wichtigsten technischen Hinweise auf einen Blick"
        description="Nur wenn wir tiefer prüfen müssen, öffnen wir hier die Rohdaten und Laufhistorie."
        tone="muted"
      >
        <div className="workspace-two-column">
          <OperatorPanel
            title="Signalsystem"
            description="Die markierten Felder zeigen, welche Daten gerade in die Qualitätssicherung eingehen."
          >
            <div className="workspace-note-list">
              {(sourceStatusLabels.length ? sourceStatusLabels : ['Noch keine markierten Felder vorhanden.']).slice(0, 6).map((item) => (
                <div key={item} className="workspace-note-card">{item}</div>
              ))}
            </div>
          </OperatorPanel>

          <OperatorPanel
            title="Letzte Läufe"
            description="Hier siehst du, wann die Prüfungen zuletzt gelaufen sind."
          >
            <div className="workspace-note-list">
              {recentRuns.length > 0 ? recentRuns.slice(0, 3).map((run, index) => (
                <div key={`${String(run.mode)}-${index}`} className="workspace-note-card">
                  {runModeLabel(String(run.mode || 'Lauf'))} · {monitoringStatusLabel(String(run.status || '-'))}
                </div>
              )) : (
                <div className="workspace-note-card">Noch keine Laufhistorie vorhanden.</div>
              )}
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>
    </div>
  );
};

export default EvidencePanel;
