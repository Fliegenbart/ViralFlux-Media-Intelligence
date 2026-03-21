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
        title="Was vor dem Handeln noch geprüft wird"
        description="Wir laden gerade die Qualitätsdaten. Gleich siehst du wieder, was noch offen ist."
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
        title="Was vor dem Handeln noch geprüft wird"
        description="Hier siehst du, ob Vorhersage, Daten und Kundensignale für den nächsten Schritt ausreichen."
        tone="muted"
        className="operator-toolbar-shell"
      >
        <div className="workspace-priority-grid">
          <OperatorPanel
            eyebrow="Schneller Überblick"
            title="Was du zuerst wissen solltest"
            description="Hier steht kurz, was gerade wichtig ist."
            tone="muted"
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">
                {workspaceStatus?.summary || 'Sobald Qualitätsdaten vorliegen, fassen wir hier den schnellsten Prüfpfad zusammen.'}
              </div>
              <div className="workspace-note-card">
                Geprüft werden Vorhersage, Kundendaten, Quellen und Importe.
              </div>
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Nächster Schritt"
            title="Worauf du jetzt achten solltest"
            description="Wenn hier etwas offen ist, findest du darunter die passende Detailstelle."
            tone="muted"
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">
                {workspaceStatus?.summary || 'Noch kein zusammengefasster Qualitätsstatus vorhanden.'}
              </div>
              <div className="workspace-note-card">
                Offene Punkte kannst du direkt in den vier Bereichen darunter nachverfolgen.
              </div>
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>

      <WorkspaceStatusPanel
        status={workspaceStatus}
        title="Was noch offen ist"
        intro="Hier siehst du sofort, ob du weitermachen kannst oder welcher Bereich zuerst geklärt werden sollte."
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
        subtitle="Hier siehst du, wie verlässlich die Vorhersage im Moment ist."
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
        subtitle="Hier siehst du, ob echte Kundendaten die Entscheidung zusätzlich stützen."
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
        subtitle="Hier siehst du, ob die zugrunde liegenden Daten noch aktuell genug sind."
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
        subtitle="Hier kannst du neue Kundendaten prüfen und bestehende Importe nachvollziehen."
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
        kicker="Mehr Details"
        title="Zusätzliche Hinweise"
        description="Wenn du tiefer prüfen musst, findest du hier weitere technische Details."
        tone="muted"
      >
        <div className="workspace-two-column">
          <OperatorPanel
            title="Signalsystem"
            description="Hier siehst du, welche Daten gerade in die Prüfung einfließen."
          >
            <div className="workspace-note-list">
              {(sourceStatusLabels.length ? sourceStatusLabels : ['Noch keine markierten Felder vorhanden.']).slice(0, 6).map((item) => (
                <div key={item} className="workspace-note-card">{item}</div>
              ))}
            </div>
          </OperatorPanel>

          <OperatorPanel
            title="Letzte Läufe"
            description="Hier siehst du, wann zuletzt geprüft wurde."
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
