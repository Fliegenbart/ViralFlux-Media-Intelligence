export function issueFieldLabel(fieldName?: string | null): string {
  const normalized = String(fieldName || '').trim().toLowerCase();
  if (!normalized) return 'Allgemein';
  if (normalized === 'week_start') return 'Woche';
  if (normalized === 'product') return 'Produkt';
  if (normalized === 'region_code') return 'Region';
  if (normalized === 'media_spend_eur') return 'Media Spend';
  if (normalized === 'conversion') return 'Outcome';
  if (normalized === 'row') return 'Zeile';
  if (normalized === 'header') return 'CSV-Header';
  return normalized;
}

export function batchStatusLabel(status?: string | null): string {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'validated') return 'Validiert';
  if (normalized === 'imported') return 'Importiert';
  if (normalized === 'partial_success') return 'Teilweise importiert';
  if (normalized === 'failed') return 'Fehlgeschlagen';
  return status ? String(status) : 'Offen';
}

export function monitoringStatusLabel(status?: string | null): string {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'healthy') return 'Stabil';
  if (normalized === 'warning') return 'Beobachten';
  if (normalized === 'critical') return 'Kritisch';
  return status ? String(status) : 'Unbekannt';
}

export function monitoringFreshnessLabel(state?: string | null): string {
  const normalized = String(state || '').trim().toLowerCase();
  if (normalized === 'fresh') return 'frisch';
  if (normalized === 'stale') return 'veraltet';
  if (normalized === 'expired') return 'abgelaufen';
  if (normalized === 'missing') return 'fehlt';
  return state ? String(state) : '-';
}

export function numberFromUnknown(value: unknown): number | null {
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function formatSignedPercent(value: unknown, digits = 1): string {
  const numeric = numberFromUnknown(value);
  if (numeric == null) return '-';
  const prefix = numeric > 0 ? '+' : '';
  return `${prefix}${numeric.toFixed(digits)}%`;
}
