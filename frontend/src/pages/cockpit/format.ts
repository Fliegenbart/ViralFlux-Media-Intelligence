/** Tiny formatters used across the cockpit. Currency, pct, signed deltas. */

export const fmtEur = (n: number): string =>
  new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n);

export const fmtEurCompact = (n: number): string => {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `€${(n / 1_000_000).toLocaleString('de-DE', { maximumFractionDigits: 2 })} M`;
  if (abs >= 1_000)     return `€${(n / 1_000).toLocaleString('de-DE', { maximumFractionDigits: 0 })}k`;
  return `€${n.toLocaleString('de-DE')}`;
};

/** Null-safe EUR formatter — "—" when no media plan is connected. */
export const fmtEurCompactOrDash = (n: number | null | undefined): string =>
  typeof n === 'number' && Number.isFinite(n) ? fmtEurCompact(n) : '—';

export const fmtPct = (p: number, digits = 0): string =>
  `${(p * 100).toLocaleString('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;

export const fmtPctOrDash = (p: number | null | undefined, digits = 0): string =>
  typeof p === 'number' && Number.isFinite(p) ? fmtPct(p, digits) : '—';

/**
 * Signal strength on [0,1], rendered as "0.78" NOT "78 %".
 * Used where the underlying value is NOT a calibrated probability
 * (see peix-math-audit.md — heuristic_event_score_from_forecast).
 */
export const fmtSignalStrength = (value: number | null | undefined, digits = 2): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return value.toLocaleString('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

export const fmtSignedPct = (p: number | null | undefined, digits = 0): string => {
  if (typeof p !== 'number' || !Number.isFinite(p)) return '—';
  const v = p * 100;
  const sign = v > 0 ? '+' : v < 0 ? '−' : '±';
  return `${sign}${Math.abs(v).toLocaleString('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;
};

export const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' });

export const fmtDateShort = (iso: string): string =>
  new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
