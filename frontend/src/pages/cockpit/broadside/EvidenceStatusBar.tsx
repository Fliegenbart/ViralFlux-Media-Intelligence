import React from 'react';
import type {
  CockpitSnapshot,
  CockpitSystemStatus,
  MediaSpendingTruthPayload,
  SourceStatus,
} from '../types';
import { firstBool, firstText, sellOutWeeks } from './snapshotAccessors';

interface Props {
  snapshot: CockpitSnapshot;
}

function sourceDate(sources: SourceStatus[], pattern: RegExp): string | null {
  const source = sources.find((item) => pattern.test(item.name));
  return source?.lastUpdate ?? null;
}

function recordDate(record: Record<string, unknown> | null | undefined, ...keys: string[]): string | null {
  if (!record) return null;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

function readableStatus(value: string): string {
  return value.replace(/_/g, ' ');
}

function getActiveAlertCount(snapshot: CockpitSnapshot): number | null {
  const site = snapshot.siteEarlyWarning ?? snapshot.site_early_warning ?? null;
  if (!site) return null;
  if (typeof site.active_alert_count === 'number') return site.active_alert_count;
  if (typeof site.activeAlertCount === 'number') return site.activeAlertCount;
  if (Array.isArray(site.activeAlerts)) return site.activeAlerts.length;
  if (Array.isArray(site.active_alerts)) return site.active_alerts.length;
  if (typeof site.active_alerts === 'number') return site.active_alerts;
  return null;
}

function fmtNextMondayCountdown(now: Date): string {
  const next = new Date(now);
  const dow = now.getDay();
  const daysToMon = ((8 - dow) % 7) || 7;
  next.setDate(next.getDate() + daysToMon);
  next.setHours(8, 0, 0, 0);
  const diffMs = Math.max(0, next.getTime() - now.getTime());
  const d = Math.floor(diffMs / 86_400_000);
  const h = String(Math.floor((diffMs % 86_400_000) / 3_600_000)).padStart(2, '0');
  const m = String(Math.floor((diffMs % 3_600_000) / 60_000)).padStart(2, '0');
  return `${d}d ${h}:${m}`;
}

function deriveCanChangeBudget(
  systemStatus: CockpitSystemStatus | null | undefined,
  mediaTruth: MediaSpendingTruthPayload | null | undefined,
): boolean {
  const explicit = firstBool(
    systemStatus?.can_change_budget,
    systemStatus?.canChangeBudget,
    systemStatus?.budget_can_change,
    systemStatus?.budgetCanChange,
    mediaTruth?.can_change_budget,
    mediaTruth?.canChangeBudget,
    mediaTruth?.budget_can_change,
    mediaTruth?.budgetCanChange,
  );
  if (explicit !== null) return explicit;

  const releaseMode = firstText(mediaTruth?.release_mode, mediaTruth?.releaseMode);
  const permission = firstText(mediaTruth?.budget_permission, mediaTruth?.budgetPermission);
  return releaseMode === 'approved' && permission === 'approved_with_cap';
}

function deriveDisplayCanChangeBudget(snapshot: CockpitSnapshot): boolean {
  const rawCanChange = deriveCanChangeBudget(snapshot.systemStatus, snapshot.mediaSpendingTruth);
  if (!rawCanChange) return false;

  const businessValidation = snapshot.evidenceScore?.businessValidation ?? null;
  return (
    businessValidation?.validated_for_budget_activation === true &&
    sellOutWeeks(snapshot) >= 12 &&
    snapshot.mediaPlan?.connected === true
  );
}

function derivePitchStatus(snapshot: CockpitSnapshot): string {
  const businessValidation = snapshot.evidenceScore?.businessValidation ?? null;
  const missingRequirements = businessValidation?.missing_requirements ?? [];

  if (businessValidation?.validated_for_budget_activation === true) {
    return 'GELO-Daten validiert';
  }
  if (missingRequirements.length > 0 || snapshot.mediaPlan?.connected !== true) {
    return 'wartet auf GELO-Daten';
  }
  return 'Sales-Validierung läuft';
}

export const EvidenceStatusBar: React.FC<Props> = ({ snapshot }) => {
  const mediaTruth = snapshot.mediaSpendingTruth ?? null;
  const systemStatus = snapshot.systemStatus ?? null;
  const waveTruth = snapshot.virusWaveTruth ?? mediaTruth?.virusWaveTruth ?? null;
  const siteWarning = snapshot.siteEarlyWarning ?? snapshot.site_early_warning ?? null;

  const canChangeBudget = deriveDisplayCanChangeBudget(snapshot);
  const pitchStatus = derivePitchStatus(snapshot);
  const operationalStatus = firstText(
    systemStatus?.operational_status,
    systemStatus?.operationalStatus,
  );
  const scienceStatus = firstText(
    systemStatus?.science_status,
    systemStatus?.scienceStatus,
  );
  const featureLagDays = snapshot.modelStatus?.forecastFreshness?.featureLagDays;
  const dataFreshness =
    snapshot.modelStatus?.forecastFreshness?.isStale === true
      ? 'stale'
      : typeof featureLagDays === 'number'
        ? `${featureLagDays}d feature lag`
        : 'freshness unknown';

  const amelagDate = firstText(
    systemStatus?.latest_amelag_date,
    systemStatus?.latestAmelagDate,
    siteWarning?.latest_measurement_date,
    siteWarning?.latestMeasurementDate,
    snapshot.modelStatus?.forecastFreshness?.featureAsOf,
    waveTruth?.amelag?.latest_date,
    waveTruth?.amelag?.latestDate,
    recordDate(waveTruth?.sourceStatus, 'latest_amelag_date', 'latestAmelagDate'),
    sourceDate(snapshot.sources ?? [], /AMELAG|Abwasser/i),
  ) ?? '—';

  const survstatDate = firstText(
    systemStatus?.latest_survstat_date,
    systemStatus?.latestSurvstatDate,
    waveTruth?.survstat?.latest_date,
    waveTruth?.survstat?.latestDate,
    recordDate(waveTruth?.sourceStatus, 'latest_survstat_date', 'latestSurvstatDate'),
    sourceDate(snapshot.sources ?? [], /SURVSTAT|RKI/i),
  ) ?? '—';

  const activeAlertCount = getActiveAlertCount(snapshot);
  const amelagSignal =
    activeAlertCount !== null && activeAlertCount > 0
      ? `aktives Frühsignal (${activeAlertCount})`
      : firstText(waveTruth?.amelag?.phase)
        ? `${waveTruth?.amelag?.phase}`
        : 'waiting for signal';
  const hasAmelag = amelagDate !== '—';
  const hasSurvStat = survstatDate !== '—';
  const hasSellOut = sellOutWeeks(snapshot) > 0;
  const sourceCount = [hasAmelag, hasSurvStat, hasSellOut].filter(Boolean).length;
  const budgetGate = canChangeBudget ? 'offen' : 'geschlossen — Kalibrierungsfenster';
  const systemLabel =
    snapshot.modelStatus?.forecastFreshness?.isStale === true
      ? 'wartet auf Daten'
      : snapshot.modelStatus?.forecastReadiness === 'DRIFT_WARN'
        ? 'Drift erkannt'
        : operationalStatus === 'healthy'
          ? 'läuft'
          : pitchStatus;
  const scienceLabel =
    scienceStatus === 'review'
      ? 'Review'
      : snapshot.modelStatus?.calibrationMode === 'calibrated'
        ? 'live'
        : 'Kalibrierung';
  const now = new Date();
  const dataTooltip =
    `AMELAG: ${amelagDate} · SurvStat: ${survstatDate} · ` +
    `Feature-Lag: ${typeof featureLagDays === 'number' ? `${featureLagDays}d` : '—'} · ` +
    `nächster Lauf: ${fmtNextMondayCountdown(now)}`;

  return (
    <div className="evidence-status-bar" aria-label="Epidemiologischer Systemstatus">
      <div className="evidence-status-cell primary" title={`Operational: ${readableStatus(operationalStatus ?? 'unknown')} · ${pitchStatus}`}>
        <span className="evidence-status-label">System</span>
        <span className="evidence-status-value">{systemLabel}</span>
      </div>
      <div className="evidence-status-cell" title={`Science: ${readableStatus(scienceStatus ?? 'unknown')} · Kalibrierung: ${snapshot.modelStatus?.calibrationMode ?? '—'}`}>
        <span className="evidence-status-label">Wissenschaft</span>
        <span className="evidence-status-value">{scienceLabel}</span>
      </div>
      <div className="evidence-status-cell" title={dataTooltip}>
        <span className="evidence-status-label">Daten</span>
        <span className="evidence-status-value">{sourceCount} von 3 Quellen</span>
        <span className="evidence-status-note">{dataFreshness}</span>
      </div>
      <div className="evidence-status-cell" title={`AMELAG: ${amelagSignal} · Budget kann ändern: ${canChangeBudget ? 'true' : 'false'}`}>
        <span className="evidence-status-label">Budget-Gate</span>
        <span className="evidence-status-value">{budgetGate}</span>
      </div>
    </div>
  );
};

export default EvidenceStatusBar;
