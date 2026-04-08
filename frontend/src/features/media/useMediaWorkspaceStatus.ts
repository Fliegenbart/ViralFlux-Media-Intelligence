import {
  MediaDecisionResponse,
  MediaEvidenceResponse,
  WorkspaceStatusSummary,
} from '../../types/media';
import { explainInPlainGerman } from '../../lib/plainLanguage';
import { formatDateTime, truthFreshnessLabel, truthLayerLabel } from '../../components/cockpit/cockpitUtils';
import {
  monitoringStatusLabel,
  readinessGateLabel,
  sanitizeEvidenceCopy,
} from '../../components/cockpit/evidence/evidenceUtils';

function uniqueText(values: Array<string | null | undefined>, limit = 4): string[] {
  const seen = new Set<string>();

  return values
    .map((value) => String(value || '').trim())
    .filter((value) => {
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    })
    .slice(0, limit);
}

function cleanCopy(value?: string | null): string {
  return explainInPlainGerman(value);
}

function forecastStatusTone(value: string): 'success' | 'warning' | 'neutral' {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'stabil' || normalized === 'freigabe bereit') return 'success';
  if (normalized === 'beobachten') return 'warning';
  return 'neutral';
}

function customerStatusTone(value: string): 'success' | 'warning' | 'neutral' {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'belastbar') return 'success';
  if (normalized === 'im aufbau' || normalized === 'erste signale') return 'warning';
  return 'neutral';
}

export function buildWorkspaceStatus(
  decision: MediaDecisionResponse | null,
  evidence: MediaEvidenceResponse | null,
): WorkspaceStatusSummary | null {
  if (!decision && !evidence) return null;

  const truthStatus = decision?.truth_coverage
    || evidence?.truth_snapshot?.coverage
    || evidence?.truth_coverage
    || null;
  const sourceSummary = evidence?.source_status || null;
  const sourceItems = sourceSummary?.items || [];
  const sourceAttentionCount = sourceItems.filter((item) => String(item.status_color || '').toLowerCase() !== 'green').length;
  const forecastStatus = evidence?.forecast_monitoring?.forecast_readiness
    ? readinessGateLabel(evidence.forecast_monitoring.forecast_readiness)
    : monitoringStatusLabel(
      evidence?.forecast_monitoring?.monitoring_status
      || decision?.weekly_decision?.forecast_state
      || decision?.weekly_decision?.decision_state,
    );
  const dataFreshness = sourceSummary
    ? (sourceAttentionCount > 0 ? 'Beobachten' : 'Aktuell')
    : 'Unbekannt';
  const customerDataStatus = truthLayerLabel(truthStatus);
  const hasCustomerTruthData = Boolean((truthStatus?.coverage_weeks || 0) > 0);
  const rawLastImportAt = truthStatus?.last_imported_at
    || evidence?.truth_snapshot?.latest_batch?.uploaded_at
    || decision?.weekly_decision?.truth_last_imported_at
    || null;
  const lastImportAt = hasCustomerTruthData ? rawLastImportAt : null;

  const blockers = uniqueText([
    ...(decision?.weekly_decision?.risk_flags || []),
    decision?.weekly_decision?.truth_risk_flag,
    evidence?.truth_gate?.guidance,
    evidence?.business_validation?.guidance,
    evidence?.business_validation?.message,
    ...(evidence?.forecast_monitoring?.alerts || []),
    evidence?.truth_snapshot?.analyst_note,
  ].map((item) => cleanCopy(sanitizeEvidenceCopy(item))), 4);

  const blockerCount = blockers.length;
  const openBlockers = blockerCount > 0 ? `${blockerCount} offen` : 'Keine';
  const sourceDetail = sourceSummary
    ? `${sourceSummary.live_count || 0}/${sourceSummary.total || 0} Quellen aktuell${sourceAttentionCount > 0 ? `, ${sourceAttentionCount} mit Prüfbedarf` : ''}`
    : 'Noch kein Quellenstatus verfügbar.';
  const customerDetail = hasCustomerTruthData
    ? `${truthStatus?.coverage_weeks ?? 0} Wochen verbunden${lastImportAt ? ` · letzter Import ${formatDateTime(lastImportAt)}` : ''}`
    : 'Noch keine Kundendaten verbunden.';
  const forecastDetail = evidence?.forecast_monitoring
    ? `Prüfung ${monitoringStatusLabel(evidence.forecast_monitoring.monitoring_status)} · Vorhersage ${truthFreshnessLabel(evidence.forecast_monitoring.freshness_status)}`
    : 'Noch kein detaillierter Monitoring-Status verfügbar.';

  return {
    forecast_status: forecastStatus,
    data_freshness: dataFreshness,
    customer_data_status: customerDataStatus,
    open_blockers: openBlockers,
    last_import_at: lastImportAt,
    blocker_count: blockerCount,
    blockers,
    summary: blockerCount > 0
      ? 'Vor dem nächsten Schritt sollten wir zuerst die offenen Punkte prüfen.'
      : 'Die Lage ist klar genug für den nächsten sinnvollen Schritt.',
    items: [
      {
        key: 'forecast_status',
        question: 'Ist die Vorhersage stabil?',
        value: forecastStatus,
        detail: forecastDetail,
        tone: forecastStatusTone(forecastStatus),
      },
      {
        key: 'data_freshness',
        question: 'Sind die Daten frisch?',
        value: dataFreshness,
        detail: sourceDetail,
        tone: sourceSummary ? (sourceAttentionCount > 0 ? 'warning' : 'success') : 'neutral',
      },
      {
        key: 'customer_data_status',
        question: 'Sind Kundendaten verbunden?',
        value: customerDataStatus,
        detail: customerDetail,
        tone: customerStatusTone(customerDataStatus),
      },
      {
        key: 'open_blockers',
        question: 'Gibt es offene Blocker?',
        value: openBlockers,
        detail: blockerCount > 0 ? blockers[0] : 'Aktuell gibt es keine offenen Blocker.',
        tone: blockerCount > 0 ? 'warning' : 'success',
      },
    ],
  };
}
