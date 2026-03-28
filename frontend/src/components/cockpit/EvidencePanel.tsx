import React from 'react';

import { COCKPIT_SEMANTICS } from '../../lib/copy';
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
import WaveValidationSection from './evidence/WaveValidationSection';
import { sanitizeEvidenceCopy } from './evidence/evidenceUtils';
import { formatDateTime, truthFreshnessLabel, truthLayerLabel } from './cockpitUtils';
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

type EvidenceTone = 'success' | 'warning' | 'neutral';

interface EvidenceSummaryCard {
  label: string;
  value: string;
  detail: string;
  tone: EvidenceTone;
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
  const blockerPreview = (workspaceStatus?.blockers || []).slice(0, 4);
  const latestImportAt = workspaceStatus?.last_import_at || truthStatus?.last_imported_at || truthSnapshot?.latest_batch?.uploaded_at || null;
  const sourceAttentionCount = sourceItems.filter((item) => String(item.status_color || '').toLowerCase() !== 'green').length;
  const completenessDetail = buildCompletenessDetail(truthStatus, latestImportAt, sourceAttentionCount, sourceItems.length);
  const reliabilityItem = workspaceStatus?.items.find((item) => item.key === 'forecast_status') || null;
  const freshnessItem = workspaceStatus?.items.find((item) => item.key === 'data_freshness') || null;
  const customerItem = workspaceStatus?.items.find((item) => item.key === 'customer_data_status') || null;
  const hasTruthData = Boolean((truthStatus?.coverage_weeks || 0) > 0);
  const hasOutcomeLearning = Boolean(
    outcomeLearning?.outcome_signal_score != null
    || outcomeLearning?.top_pair_learnings?.length
    || outcomeLearning?.top_product_learnings?.length
    || outcomeLearning?.top_region_learnings?.length,
  );
  const hasBlockers = Boolean(workspaceStatus?.blocker_count);
  const readyForWeeklyPlanning = Boolean(
    hasTruthData
    && !hasBlockers
    && reliabilityItem?.tone === 'success'
    && freshnessItem?.tone !== 'warning',
  );
  const canUseWithCaution = Boolean(
    !readyForWeeklyPlanning
    && (
      hasTruthData
      || reliabilityItem?.tone === 'success'
      || freshnessItem?.tone === 'success'
    ),
  );
  const heroTone: EvidenceTone = readyForWeeklyPlanning ? 'success' : (hasBlockers || !hasTruthData ? 'warning' : 'neutral');
  const heroLabel = readyForWeeklyPlanning
    ? 'Belastbar genug für die Wochenplanung'
    : hasBlockers
      ? 'Noch nicht vollständig frei'
      : canUseWithCaution
        ? 'Mit Vorsicht nutzbar'
        : 'GELO-Datenbasis im Aufbau';
  const heroTitle = readyForWeeklyPlanning
    ? 'Die GELO-Planung ist für diese Woche belastbar genug.'
    : hasBlockers
      ? 'Die Datenlage ist sichtbar, aber offene Punkte bremsen die Freigabe.'
      : canUseWithCaution
        ? 'Die Empfehlungen sind nutzbar, aber noch nicht überall gleich stark belegt.'
        : 'Für GELO fehlen noch Daten, bevor die Empfehlungen wirklich belastbar werden.';
  const heroSummary = firstNonEmpty(
    workspaceStatus?.summary,
    businessValidation?.guidance,
    businessValidation?.message,
    truthGate?.guidance,
    truthSnapshot?.analyst_note,
    'Hier steht kompakt, was bereits belastbar ist, was noch fehlt und was als Nächstes geklärt werden sollte.',
  );
  const trustedNow = readyForWeeklyPlanning
    ? 'Vorhersage, frische Quellen und GELO-Kundendaten stützen die Wochenplanung gemeinsam.'
    : reliabilityItem?.tone === 'success'
      ? 'Vorhersage und Quellen geben eine gute Richtung, auch wenn Kundendaten noch nicht überall gleich stark tragen.'
      : 'Es gibt erste Signale, aber noch nicht genug belastbare Belege für jede Empfehlung.';
  const missingNow = !hasTruthData
    ? 'Es fehlen noch GELO-Kundendaten mit Wochen-, Produkt- und Bundesland-Bezug.'
    : !hasOutcomeLearning
      ? 'Erkenntnisse aus Kundendaten sind noch im Aufbau und stützen die Priorisierung bisher nur begrenzt.'
      : sourceAttentionCount > 0
        ? `${sourceAttentionCount} Datenquellen brauchen noch Frische- oder Qualitätsprüfung.`
        : 'Die größten Lücken liegen aktuell weniger bei Pflichtdaten als in der Tiefe der Kundendaten-Belege.';
  const blockedNow = hasBlockers
    ? sanitizeEvidenceCopy(blockerPreview[0])
    : 'Aktuell blockiert kein offener Punkt den nächsten sinnvollen Schritt.';
  const cautionNow = reliabilityItem?.tone === 'warning'
    ? 'Die Richtung ist sichtbar, sollte aber weiterhin vorsichtig gelesen werden.'
    : freshnessItem?.tone === 'warning'
      ? 'Ein Teil der Quellen ist noch nicht frisch genug für eine klare Aussage.'
      : !hasTruthData
        ? 'Ohne Kundendaten bleibt die Planung eher richtungsgebend als vollständig belastbar.'
        : `${COCKPIT_SEMANTICS.stateLevelScope.helper} ${COCKPIT_SEMANTICS.noCityForecast.helper}`;
  const primaryCtaLabel = (!hasTruthData || hasBlockers || sourceAttentionCount > 0)
    ? 'Fehlende Evidenz klären'
    : 'Evidenzlage prüfen';
  const primaryCtaHref = (!hasTruthData || hasBlockers || sourceAttentionCount > 0)
    ? '#evidence-import'
    : '#evidence-support';
  const cautionAndBlocker = hasBlockers
    ? `${blockedNow} ${cautionNow}`
    : cautionNow;
  const trustCards: EvidenceSummaryCard[] = [
    {
      label: 'Datenvollständigkeit',
      value: hasTruthData ? `${truthStatus?.coverage_weeks ?? 0} Wochen verbunden` : 'GELO-Daten fehlen noch',
      detail: completenessDetail,
      tone: hasTruthData ? (customerItem?.tone || 'success') : 'warning',
    },
    {
      label: 'Modell-Belastbarkeit',
      value: reliabilityItem?.value || 'Noch offen',
      detail: reliabilityItem?.detail || 'Sobald die Modellprüfung geladen ist, wird hier die aktuelle Stabilität sichtbar.',
      tone: reliabilityItem?.tone || 'neutral',
    },
    {
      label: 'Operative Einsatzreife',
      value: hasBlockers ? `${workspaceStatus?.blocker_count || blockerPreview.length} offene Blocker` : (readyForWeeklyPlanning ? 'Bereit für Wochenplanung' : 'Mit Vorsicht nutzbar'),
      detail: hasBlockers
        ? sanitizeEvidenceCopy(blockerPreview[0])
        : workspaceStatus?.summary || 'Aktuell blockiert nichts den nächsten sinnvollen operativen Schritt.',
      tone: hasBlockers ? 'warning' : (readyForWeeklyPlanning ? 'success' : 'neutral'),
    },
  ];
  const connectedItems = [
    `Kundendatenstatus: ${truthLayerLabel(truthStatus)}`,
    `Letzter GELO-Import: ${latestImportAt ? formatDateTime(latestImportAt) : 'noch keiner'}`,
    `Verbunden: ${truthStatus?.coverage_weeks ?? 0} Wochen · ${truthStatus?.regions_covered ?? 0} Bundesländer · ${truthStatus?.products_covered ?? 0} Produkte`,
    `Live-Quellen: ${(evidence?.source_status?.live_count || 0)}/${evidence?.source_status?.total || 0} aktuell`,
  ];
  const missingItems = uniqueNonEmpty([
    !hasTruthData ? 'Für GELO fehlen noch passende Kundendaten für eine saubere Wochenplanung.' : '',
    !hasOutcomeLearning ? 'Erkenntnisse aus Kundendaten sind noch im Aufbau.' : '',
    sourceAttentionCount > 0 ? `${sourceAttentionCount} Datenquellen brauchen noch eine Prüfung (Qualität oder Frische).` : '',
    ...blockerPreview.map((item) => sanitizeEvidenceCopy(item)),
  ]);
  const importNeedsAttention = !hasTruthData || hasBlockers || sourceAttentionCount > 0;

  if (loading && !evidence) {
    return (
      <OperatorSection
        kicker="Evidenz"
        title="Evidenz wird aufgebaut"
        description="Die Seite ordnet gerade neu, was bereits belastbar ist und was noch geklärt werden muss."
        tone="muted"
      >
        <div className="evidence-briefing-skeleton" role="status" aria-live="polite" aria-label="GELO-Datenlage wird geladen">
          <div className="workspace-note-card evidence-briefing-skeleton__hero" />
          <div className="evidence-briefing-skeleton__grid">
            <div className="workspace-note-card evidence-briefing-skeleton__block" />
            <div className="workspace-note-card evidence-briefing-skeleton__block" />
            <div className="workspace-note-card evidence-briefing-skeleton__block" />
          </div>
        </div>
      </OperatorSection>
    );
  }

  if (!loading && !evidence) {
    return (
      <OperatorSection
        kicker="Evidenz"
        title="Evidenz noch nicht verfügbar"
        description="Im Moment fehlt die Datengrundlage. Sichtbar bleibt trotzdem, was fehlt, was bereits gilt und welcher Schritt als Nächstes sinnvoll ist."
        tone="muted"
      >
        <div className="evidence-empty-stage">
          <div className="workspace-note-card evidence-empty-stage__panel">
            <span className="campaign-focus-label">Aktueller Stand</span>
            <strong>Für diese Pilotansicht liegen aktuell keine belastbaren Evidenzdaten vor.</strong>
            <p>Ohne Import-, Qualitäts- und Statusdaten lässt sich die Lage noch nicht belastbar einordnen.</p>
          </div>
          <div className="workspace-note-card evidence-empty-stage__panel">
            <span className="campaign-focus-label">Was weiterhin gilt</span>
            <strong>Die Arbeitslogik bleibt gleich: erst Belastbarkeit klären, dann entscheiden.</strong>
            <p>Die Oberfläche vermeidet bewusst Scheinsicherheit und zeigt deshalb keine künstlich belastbar wirkende Empfehlung.</p>
          </div>
          <div className="workspace-note-card evidence-empty-stage__panel">
            <span className="campaign-focus-label">Nächster Schritt</span>
            <strong>Verbindung prüfen oder Import erneut auslösen</strong>
            <p>Wenn die Daten wieder erreichbar sind, baut sich die Evidenzansicht an derselben Stelle erneut auf.</p>
          </div>
        </div>
      </OperatorSection>
    );
  }

  return (
    <div className="page-stack evidence-template-page">
      <OperatorSection
        kicker="Evidenz"
        title="Belastbarkeit sauber einordnen"
        description="Sichtbar wird, was Empfehlungen bereits trägt, was noch fehlt und wo Vorsicht nötig bleibt."
        tone="accent"
        className="evidence-briefing-shell"
      >
        <div className="evidence-briefing-grid">
          <OperatorPanel tone="accent" className="evidence-briefing-hero">
            <div id="evidence-trust" className="evidence-briefing-hero__header">
              <div>
                <span className="campaign-focus-label">Aktueller Evidenzstatus</span>
                <h3 className="campaign-focus-title">{heroTitle}</h3>
                <div className="campaign-focus-context">
                  {latestImportAt ? `Letzter GELO-Import ${formatDateTime(latestImportAt)}` : 'Noch kein GELO-Import'} · {truthLayerLabel(truthStatus)} · {truthFreshnessLabel(truthStatus?.truth_freshness_state)}
                </div>
              </div>
              <span className={`campaign-confidence-chip campaign-confidence-chip--${heroTone}`}>
                {heroLabel}
              </span>
            </div>

            <p className="campaign-focus-copy">{heroSummary}</p>

            <div className="evidence-briefing-note-grid">
              <div className="workspace-note-card evidence-briefing-note">
                <strong>Bereits belastbar</strong>
                <p>{trustedNow}</p>
              </div>
              <div className="workspace-note-card evidence-briefing-note">
                <strong>Noch offen</strong>
                <p>{missingNow}</p>
              </div>
              <div className="workspace-note-card evidence-briefing-note">
                <strong>Vorsichtig lesen oder noch offen</strong>
                <p>{cautionAndBlocker}</p>
              </div>
            </div>

            <div className="action-row">
              <a className="media-button" href={primaryCtaHref}>
                {primaryCtaLabel}
              </a>
              {truthSnapshot?.template_url ? (
                <a className="media-button secondary" href={truthSnapshot.template_url}>
                  CSV-Vorlage laden
                </a>
              ) : null}
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Einordnung"
            title="Was die Evidenz bereits trägt"
            description="Sichtbar bleibt, ob die offene Frage derzeit eher Daten, Belastbarkeit oder operative Einsatzreife betrifft."
            tone="muted"
            className="evidence-trust-panel"
          >
            <div className="workspace-status-grid evidence-trust-grid">
              {trustCards.map((card) => (
                <article
                  key={card.label}
                  className={`workspace-status-card workspace-status-card--${card.tone}`}
                >
                  <span className="workspace-status-card__question">{card.label}</span>
                  <strong>{card.value}</strong>
                  <p>{card.detail}</p>
                </article>
              ))}
            </div>
            <div className="workspace-note-card">
              <strong>Gilt auf Bundesland-Ebene, nicht für einzelne Städte.</strong> {COCKPIT_SEMANTICS.stateLevelScope.helper} {COCKPIT_SEMANTICS.noCityForecast.helper}
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>

      <OperatorSection
        kicker="Arbeitskontext"
        title="Verbindung und Lücken"
        description="Was bereits verbunden ist, was noch fehlt und welcher Daten- oder Klärungsschritt als Nächstes sinnvoll ist."
        tone="muted"
      >
        <div id="evidence-onboarding" className="workspace-two-column evidence-onboarding-grid">
          <OperatorPanel
            title="Bereits verbunden"
            description="Das kann die Wochenplanung heute bereits stützen."
          >
            <div className="workspace-note-list">
              {connectedItems.map((item) => (
                <div key={item} className="workspace-note-card">
                  {item}
                </div>
              ))}
            </div>
          </OperatorPanel>

          <OperatorPanel
            title="Fehlend oder offen"
            description="Hier liegt der nächste sinnvolle Klärungs-, Qualitäts- oder Import-Schritt."
          >
            <div className="workspace-note-list">
              {missingItems.length > 0 ? missingItems.map((item) => (
                <div key={item} className="workspace-note-card">
                  {item}
                </div>
              )) : (
                <div className="workspace-note-card">
                  Aktuell gibt es keinen klaren offenen Stopper. Die nächsten Schritte liegen eher in der laufenden Qualitätsbeobachtung.
                </div>
              )}
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>

      <CollapsibleSection
        title="Kundendaten und Wirkung (optional)"
        subtitle="Zeigt, wie stark Kundendaten die Empfehlungen zusätzlich stützen und absichern."
      >
        <div id="evidence-data">
          <WaveValidationSection
            customerDataCoverage={truthStatus}
            customerDataGate={truthGate}
            businessValidation={businessValidation}
            regionalImpact={outcomeLearning}
            legacyCustomerValidation={legacyCustomer}
            connectedFieldLabels={sourceStatusLabels}
          />
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Import und Validierung"
        subtitle="Hier werden fehlende Kundendaten geklärt, CSV-Importe geprüft und bestehende Importe nachvollzogen."
        defaultOpen={importNeedsAttention}
      >
        <div id="evidence-import">
          <ImportValidationSection
            truthSnapshot={truthSnapshot}
            truthPreview={truthPreview}
            truthBatchDetail={truthBatchDetail}
            truthActionLoading={truthActionLoading}
            truthBatchDetailLoading={truthBatchDetailLoading}
            onSubmitTruthCsv={onSubmitTruthCsv}
            onLoadTruthBatchDetail={onLoadTruthBatchDetail}
          />
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Vorhersage und Monitoring (Details)"
        subtitle="Diese Details helfen, die Vorhersage einzuordnen und bleiben bewusst eine zweite Ebene hinter der Evidenzlage."
      >
        <div id="evidence-support">
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
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Quellen & Grenzen"
        subtitle="Hier wird sichtbar, welche Live-Daten einfließen, welche Quellen Beobachtung brauchen und wo die fachlichen Grenzen liegen."
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
        title="Technische Tiefe (optional)"
        subtitle="Nur relevant, wenn ein technischer Blick in Signalsystem, Prüfmarker oder Import-Historie nötig ist."
      >
        <div className="workspace-two-column">
          <OperatorPanel
            title="Signale und Felder"
            description="Zeigt, welche Datenfelder und Signale aktuell in die Evidenzlage einfließen."
          >
            <div className="workspace-note-list">
              {(sourceStatusLabels.length ? sourceStatusLabels : ['Noch keine markierten Pflicht- oder Wirkungsfelder vorhanden.']).slice(0, 6).map((item) => (
                <div key={item} className="workspace-note-card">{item}</div>
              ))}
            </div>
          </OperatorPanel>

          <OperatorPanel
            title="Technische Hinweise"
            description="Hilft beim Nachvollziehen, ist für die eigentliche Entscheidung aber nicht zwingend nötig."
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">
                Letzter Import: {latestImportAt ? formatDateTime(latestImportAt) : 'noch nicht vorhanden'}
              </div>
              <div className="workspace-note-card">
                Offene Stopper (Blocker): {workspaceStatus?.open_blockers || 'keine'}
              </div>
              <div className="workspace-note-card">
                Kundendaten-Felder sichtbar: {sourceStatusLabels.length}
              </div>
            </div>
          </OperatorPanel>
        </div>
      </CollapsibleSection>
    </div>
  );
};

export default EvidencePanel;

function firstNonEmpty(...values: Array<string | null | undefined>): string {
  return values.find((value) => typeof value === 'string' && value.trim().length > 0)?.trim() || '';
}

function uniqueNonEmpty(values: string[]): string[] {
  return values.filter((value, index, all) => value && all.indexOf(value) === index);
}

function buildCompletenessDetail(
  truthStatus: MediaEvidenceResponse['truth_coverage'] | null | undefined,
  latestImportAt: string | null,
  sourceAttentionCount: number,
  totalSources: number,
): string {
  if (!truthStatus) {
    return 'Noch keine GELO-Kundendaten verbunden. Live-Quellen allein reichen nur für eine vorsichtige Planung.';
  }

  const connected = `${truthStatus.regions_covered ?? 0} Bundesländer · ${truthStatus.products_covered ?? 0} Produkte`;
  const freshness = truthFreshnessLabel(truthStatus.truth_freshness_state);
  const sourceHint = totalSources > 0
    ? `${Math.max(totalSources - sourceAttentionCount, 0)}/${totalSources} Quellen aktuell`
    : 'Quellenstatus noch offen';

  return `${connected}${latestImportAt ? ` · letzter Import ${formatDateTime(latestImportAt)}` : ''} · ${freshness} · ${sourceHint}`;
}
