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

function fallbackLabel(value?: string | null): string {
  const normalized = String(value || '').trim();
  if (!normalized) return 'Offen';
  return normalized
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
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
  if (normalized === 'forecast_monitoring') return 'Forecast-Monitoring';
  if (normalized === 'source_status') return 'Quellenstatus';
  if (normalized === 'import_validation') return 'Import-Prüfung';
  return fallbackLabel(mode);
}

export function sanitizeEvidenceCopy(value?: string | null): string {
  const raw = String(value || '').trim();
  if (!raw) return '';

  const normalized = raw
    .replace(/zukuenftige/g, 'zukünftige')
    .replace(/naechste/g, 'nächste')
    .replace(/naechsten/g, 'nächsten')
    .replace(/anschliesst/g, 'anschließt')
    .replace(/\bWATCH\b/g, 'Beobachten')
    .replace(/\bwarning\b/g, 'Beobachten')
    .replace(/\bvalidated\b/g, 'Validiert')
    .replace(/\bMARKET_CHECK\b/g, 'Markt-Check')
    .replace(/\bTRUTH_VALIDATION\b/g, 'Kunden-Validierung')
    .replace(/\bFORECAST_MONITORING\b/g, 'Forecast-Monitoring')
    .replace(/Readiness\b/g, 'Readiness')
    .replace(/0T Lead/g, '0 Tage Vorlauf')
    .replace(/Decision-Layer:/g, 'Entscheidungsebene:')
    .replace(/Walk-forward Backtest:/g, 'Walk-forward-Backtest:')
    .replace(/corr@best/g, 'Korrelation am besten Punkt')
    .replace(/\bbest_lag\b/g, 'bester Lag')
    .replace(/\bFalse-Alarms\b/g, 'False-Alarms')
    .replace(/\s+/g, ' ')
    .trim();

  const leadSentence = normalized.match(/^Prognose und Ist-Wert sind effektiv gleichzeitig \(0 Tage Vorlauf\)\./i);
  if (leadSentence) {
    return normalized.replace(
      /^Prognose und Ist-Wert sind effektiv gleichzeitig \(0 Tage Vorlauf\)\./i,
      'Prognose und Ist-Wert liegen aktuell ohne messbaren Vorlauf übereinander.',
    );
  }

  return normalized;
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
