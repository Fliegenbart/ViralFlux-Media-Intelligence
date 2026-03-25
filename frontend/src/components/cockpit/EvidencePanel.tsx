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
  const quickStatusItems = (workspaceStatus?.items || []).slice(0, 4);
  const blockerPreview = (workspaceStatus?.blockers || []).slice(0, 4);
  const recentRunPreview = recentRuns.slice(0, 3);

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
        description="Hier siehst du sofort, ob du handeln kannst."
        tone="accent"
        className="operator-toolbar-shell"
      >
        <div className="evidence-command-grid">
          <OperatorPanel
            eyebrow="Freigabe-Lage"
            title="Kannst du weitermachen?"
            description={workspaceStatus?.summary || 'Hier steht gleich die kurze Freigabe-Lage.'}
            tone="accent"
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">
                {workspaceStatus?.summary || 'Sobald Qualitätsdaten vorliegen, fassen wir hier den schnellsten Prüfpfad zusammen.'}
              </div>
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Schnellcheck"
            title="Die drei wichtigsten Prüfpunkte"
            description="So erkennst du sofort, was dich noch bremst."
            tone="muted"
          >
            <div className="now-trust-grid evidence-status-grid">
              {quickStatusItems.slice(0, 3).length > 0 ? quickStatusItems.slice(0, 3).map((item) => (
                <article
                  key={item.key}
                  className={`workspace-status-card workspace-status-card--${item.tone}`}
                >
                  <span className="workspace-status-card__question">{item.question}</span>
                  <strong>{item.value}</strong>
                  <p>{item.detail}</p>
                </article>
              )) : (
                <div className="workspace-note-card">Noch kein zusammengefasster Qualitätsstatus vorhanden.</div>
              )}
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
          kicker="Zuerst klären"
          title="Das bremst die Freigabe gerade"
          description="Hier stehen die wichtigsten offenen Punkte."
          tone="muted"
        >
          <div className="workspace-two-column">
            <OperatorPanel
              title="Offene Punkte"
              description="Das zuerst klären."
            >
              <div className="workspace-note-list">
                {blockerPreview.map((blocker) => (
                  <div key={blocker} className="workspace-note-card">
                    {blocker}
                  </div>
                ))}
              </div>
            </OperatorPanel>

            <OperatorPanel
              title="Letzte Prüfungen"
              description="Das lief zuletzt."
            >
              <div className="workspace-note-list">
                {recentRunPreview.length > 0 ? recentRunPreview.map((run, index) => (
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
        title="Technische Hinweise"
        description="Wenn du tiefer prüfen musst, findest du hier zusätzliche technische Einordnung."
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
            title="Import- und Prüfmarker"
            description="Diese Hinweise helfen beim Nachvollziehen der aktuellen Datenlage."
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">
                Letzter Import: {workspaceStatus?.last_import_at || 'noch nicht vorhanden'}
              </div>
              <div className="workspace-note-card">
                Blocker aktuell: {workspaceStatus?.open_blockers || 'keine'}
              </div>
              <div className="workspace-note-card">
                Truth-Felder sichtbar: {sourceStatusLabels.length > 0 ? sourceStatusLabels.length : 0}
              </div>
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>
    </div>
  );
};

export default EvidencePanel;
