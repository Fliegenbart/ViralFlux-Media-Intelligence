import React from 'react';
import type {
  CockpitSnapshot,
  CockpitSystemStatus,
  MediaSpendingTruthPayload,
  SourceStatus,
} from '../types';
import { firstBool, firstText } from './snapshotAccessors';

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

function budgetModeLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'diagnostic only' || normalized === 'diagnostic_only') return 'Diagnosemodus';
  if (normalized === 'budget active' || normalized === 'approved') return 'Budgetfreigabe aktiv';
  if (normalized === 'limited budget mode' || normalized === 'limited') return 'Begrenzter Budgetmodus';
  if (normalized === 'planner assist' || normalized === 'shadow_only') return 'Planer-Prüfung';
  return readableStatus(value);
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

function deriveBudgetMode(
  systemStatus: CockpitSystemStatus | null | undefined,
  mediaTruth: MediaSpendingTruthPayload | null | undefined,
  canChangeBudget: boolean,
): string {
  const explicit = firstText(
    systemStatus?.budget_mode,
    systemStatus?.budgetMode,
    mediaTruth?.release_mode,
    mediaTruth?.releaseMode,
  );
  const diagnosticOnly = firstBool(
    systemStatus?.diagnostic_only,
    systemStatus?.diagnosticOnly,
    mediaTruth?.diagnostic_only,
    mediaTruth?.diagnosticOnly,
  );

  if (diagnosticOnly === true || !canChangeBudget) return 'Diagnosemodus';
  if (explicit === 'approved') return 'Budgetfreigabe aktiv';
  if (explicit === 'limited') return 'Begrenzter Budgetmodus';
  if (explicit === 'shadow_only') return 'Planer-Prüfung';
  return explicit ?? 'Diagnosemodus';
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

  const canChangeBudget = deriveCanChangeBudget(systemStatus, mediaTruth);
  const budgetMode = deriveBudgetMode(systemStatus, mediaTruth, canChangeBudget);
  const pitchStatus = derivePitchStatus(snapshot);
  const operationalStatus = firstText(
    systemStatus?.operational_status,
    systemStatus?.operationalStatus,
  );
  const scienceStatus = firstText(
    systemStatus?.science_status,
    systemStatus?.scienceStatus,
  );
  const budgetStatus = firstText(
    systemStatus?.budget_status,
    systemStatus?.budgetStatus,
    mediaTruth?.release_mode,
    mediaTruth?.releaseMode,
  ) ?? (canChangeBudget ? 'budget active' : 'diagnostic only');
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

  return (
    <div className="evidence-status-bar" aria-label="Epidemiologischer Systemstatus">
      <div className="evidence-status-cell primary">
        <span className="evidence-status-label">Status</span>
        <span className="evidence-status-value">{pitchStatus}</span>
        {operationalStatus ? (
          <span className="evidence-status-note">Operational: {readableStatus(operationalStatus)}</span>
        ) : null}
        {scienceStatus ? (
          <span className="evidence-status-note">Science: {readableStatus(scienceStatus)}</span>
        ) : null}
      </div>
      <div className="evidence-status-cell">
        <span className="evidence-status-label">Budget-Modus</span>
        <span className="evidence-status-value">{budgetModeLabel(budgetMode)}</span>
        <span className="evidence-status-note">Budget: {readableStatus(budgetStatus)}</span>
        <span className="evidence-status-note">
          {canChangeBudget ? 'Budgetänderungen aktiviert' : 'Budgetänderungen deaktiviert'}
        </span>
      </div>
      <div className="evidence-status-cell">
        <span className="evidence-status-label">Datenstand</span>
        <span className="evidence-status-value">{dataFreshness}</span>
        <span className="evidence-status-note">
          latest wastewater data: {amelagDate}
        </span>
      </div>
      <div className="evidence-status-cell">
        <span className="evidence-status-label">AMELAG-Datum</span>
        <span className="evidence-status-value">{amelagDate}</span>
        <span className="evidence-status-note">AMELAG: {amelagSignal}</span>
      </div>
      <div className="evidence-status-cell">
        <span className="evidence-status-label">SurvStat-Datum</span>
        <span className="evidence-status-value">{survstatDate}</span>
        <span className="evidence-status-note">SurvStat: bestätigendes Signal</span>
      </div>
    </div>
  );
};

export default EvidenceStatusBar;
