import type {
  CockpitSnapshot,
  CockpitSystemStatus,
  MediaSpendingTruthPayload,
} from '../types';

export function firstText(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

export function firstNumber(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

export function firstBool(...values: Array<boolean | null | undefined>): boolean | null {
  for (const value of values) {
    if (typeof value === 'boolean') return value;
  }
  return null;
}

function isSnapshot(
  value: CockpitSnapshot | CockpitSystemStatus | null | undefined,
): value is CockpitSnapshot {
  return !!value && 'systemStatus' in value;
}

export function canChangeBudget(
  snapshotOrStatus: CockpitSnapshot | CockpitSystemStatus | null | undefined,
  mediaTruth?: MediaSpendingTruthPayload | null | undefined,
): boolean {
  let snapshot: CockpitSnapshot | null = null;
  let systemStatus: CockpitSystemStatus | null | undefined;
  let truth: MediaSpendingTruthPayload | null | undefined;

  if (isSnapshot(snapshotOrStatus)) {
    snapshot = snapshotOrStatus;
    systemStatus = snapshotOrStatus.systemStatus;
    truth = snapshotOrStatus.mediaSpendingTruth;
  } else {
    systemStatus = snapshotOrStatus;
    truth = mediaTruth;
  }

  const explicitCanChange = firstBool(
    systemStatus?.can_change_budget,
    systemStatus?.canChangeBudget,
    systemStatus?.budget_can_change,
    systemStatus?.budgetCanChange,
    truth?.can_change_budget,
    truth?.canChangeBudget,
    truth?.budget_can_change,
    truth?.budgetCanChange,
  ) === true;

  if (!explicitCanChange) return false;
  if (!snapshot) return true;

  const businessValidation = snapshot.evidenceScore?.businessValidation ?? null;
  const budgetValidated =
    businessValidation?.validated_for_budget_activation === true &&
    sellOutWeeks(snapshot) >= 12 &&
    snapshot.mediaPlan?.connected === true;

  return budgetValidated;
}

export function isDiagnosticOnly(snapshot: CockpitSnapshot): boolean {
  const explicit = firstBool(
    snapshot.systemStatus?.diagnostic_only,
    snapshot.systemStatus?.diagnosticOnly,
    snapshot.mediaSpendingTruth?.diagnostic_only,
    snapshot.mediaSpendingTruth?.diagnosticOnly,
  );
  return explicit === true || !canChangeBudget(snapshot);
}

export function sellOutWeeks(snapshot: CockpitSnapshot): number {
  return firstNumber(
    snapshot.evidenceScore?.businessValidation?.weeks,
    snapshot.evidenceScore?.businessValidation?.rows,
  ) ?? 0;
}

export function signalRiserCount(snapshot: CockpitSnapshot, threshold = 0.15): number {
  return (snapshot.regions ?? []).filter(
    (region) =>
      typeof region.delta7d === 'number' &&
      Number.isFinite(region.delta7d) &&
      region.delta7d > threshold &&
      region.decisionLabel !== 'TrainingPending',
  ).length;
}
