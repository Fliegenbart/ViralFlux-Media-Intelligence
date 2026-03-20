import { normalizeGermanText } from '../../../lib/plainLanguage';

export function issueFieldLabel(fieldName?: string | null): string {
  const normalized = String(fieldName || '').trim().toLowerCase();
  if (!normalized) return 'Allgemein';
  if (normalized === 'week_start') return 'Woche';
  if (normalized === 'product') return 'Produkt';
  if (normalized === 'region_code') return 'Region';
  if (normalized === 'media_spend_eur') return 'Mediabudget';
  if (normalized === 'conversion') return 'Wirkungsdaten';
  if (normalized === 'row') return 'Zeile';
  if (normalized === 'header') return 'CSV-Header';
  return normalizeGermanText(normalized);
}

function fallbackLabel(value?: string | null): string {
  const normalized = String(value || '').trim();
  if (!normalized) return 'Offen';
  return normalizeGermanText(normalized
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase()));
}

export function batchStatusLabel(status?: string | null): string {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'validated') return 'Validiert';
  if (normalized === 'imported') return 'Importiert';
  if (normalized === 'partial_success') return 'Teilweise importiert';
  if (normalized === 'failed') return 'Fehlgeschlagen';
  return fallbackLabel(status);
}

export function readinessGateLabel(status?: string | null): string {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'go' || normalized === 'ready') return 'Freigabe bereit';
  if (normalized === 'watch' || normalized === 'warning') return 'Beobachten';
  if (normalized === 'no_go' || normalized === 'critical' || normalized === 'failed') return 'Nicht freigegeben';
  return fallbackLabel(status);
}

export function monitoringStatusLabel(status?: string | null): string {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'ok') return 'Stabil';
  if (normalized === 'healthy') return 'Stabil';
  if (normalized === 'warning') return 'Beobachten';
  if (normalized === 'watch') return 'Beobachten';
  if (normalized === 'critical') return 'Kritisch';
  if (normalized === 'validated') return 'Validiert';
  if (normalized === 'imported') return 'Importiert';
  if (normalized === 'partial_success') return 'Teilweise importiert';
  if (normalized === 'live') return 'Aktuell';
  return status ? fallbackLabel(status) : 'Unbekannt';
}

export function monitoringFreshnessLabel(state?: string | null): string {
  const normalized = String(state || '').trim().toLowerCase();
  if (normalized === 'live') return 'aktuell';
  if (normalized === 'ok') return 'stabil';
  if (normalized === 'fresh') return 'frisch';
  if (normalized === 'stale') return 'veraltet';
  if (normalized === 'expired') return 'abgelaufen';
  if (normalized === 'missing') return 'fehlt';
  return state ? fallbackLabel(state) : '-';
}

export function sourceFreshnessLabel(state?: string | null): string {
  const normalized = String(state || '').trim().toLowerCase();
  if (normalized === 'live' || normalized === 'healthy' || normalized === 'ok' || normalized === 'fresh') return 'aktuell';
  if (normalized === 'warning' || normalized === 'watch' || normalized === 'stale') return 'beobachten';
  if (normalized === 'critical' || normalized === 'expired') return 'kritisch';
  if (normalized === 'missing') return 'fehlt';
  return state ? fallbackLabel(state).toLowerCase() : 'offen';
}

export function runModeLabel(mode?: string | null): string {
  const normalized = String(mode || '').trim().toLowerCase();
  if (normalized === 'market_check') return 'Markt-Check';
  if (normalized === 'truth_validation') return 'Kunden-Validierung';
  if (normalized === 'forecast_monitoring') return 'Prüfung der Vorhersage';
  if (normalized === 'source_status') return 'Quellenstatus';
  if (normalized === 'import_validation') return 'Import-Prüfung';
  return fallbackLabel(mode);
}

export function sanitizeEvidenceCopy(value?: string | null): string {
  const raw = normalizeGermanText(String(value || '').trim());
  if (!raw) return '';

  let normalized = raw
    .replace(/\bWATCH\b/g, 'Beobachten')
    .replace(/\bwarning\b/g, 'Beobachten')
    .replace(/\bvalidated\b/g, 'Validiert')
    .replace(/\bMARKET_CHECK\b/g, 'Markt-Check')
    .replace(/\bTRUTH_VALIDATION\b/g, 'Kunden-Validierung')
    .replace(/\bFORECAST_MONITORING\b/g, 'Prüfung der Vorhersage')
    .replace(/\bReadiness\b/g, 'Einsatzreife')
    .replace(/0T Lead/g, '0 Tage Vorlauf')
    .replace(/Decision-Layer:/g, 'Entscheidungsebene:')
    .replace(/Walk-forward Backtest:/g, 'Walk-forward-Rückblicktest:')
    .replace(/corr@best/g, 'beste Korrelation')
    .replace(/\bbest_lag\b/g, 'bester Lag')
    .replace(/\bFalse-Alarms\b/g, 'Fehlalarme')
    .replace(/\bOutcome-Daten\b/g, 'Kundendaten')
    .replace(/\bBacktest\b/g, 'Rückblicktest')
    .replace(/\s+/g, ' ')
    .trim();

  if (/^Prognose und Ist-Wert sind effektiv gleichzeitig \(0 Tage Vorlauf\)\./i.test(normalized)) {
    normalized = normalized.replace(
      /^Prognose und Ist-Wert sind effektiv gleichzeitig \(0 Tage Vorlauf\)\./i,
      'Prognose und Ist-Wert liegen aktuell ohne messbaren Vorlauf übereinander.',
    );
  }

  normalized = normalized.replace(
    /Timing: bester Lag=(\d+) Tage, beste Korrelation=([\d.]+)\./i,
    (_, lag, correlation) => `Timing: Der beste Vergleich liegt bei ${lag} Tagen Verschiebung, die Korrelation liegt dort bei ${correlation}.`,
  );

  normalized = normalized.replace(
    /Einsatzreife Beobachten\./i,
    'Status Beobachten.',
  );

  return normalizeGermanText(normalized);
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
