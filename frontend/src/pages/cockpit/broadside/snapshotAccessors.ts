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
  let systemStatus: CockpitSystemStatus | null | undefined;
  let truth: MediaSpendingTruthPayload | null | undefined;

  if (isSnapshot(snapshotOrStatus)) {
    systemStatus = snapshotOrStatus.systemStatus;
    truth = snapshotOrStatus.mediaSpendingTruth;
  } else {
    systemStatus = snapshotOrStatus;
    truth = mediaTruth;
  }

  return firstBool(
    systemStatus?.can_change_budget,
    systemStatus?.canChangeBudget,
    systemStatus?.budget_can_change,
    systemStatus?.budgetCanChange,
    truth?.can_change_budget,
    truth?.canChangeBudget,
    truth?.budget_can_change,
    truth?.budgetCanChange,
  ) === true;
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
