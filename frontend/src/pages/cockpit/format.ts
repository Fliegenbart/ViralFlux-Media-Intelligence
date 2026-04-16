/** Tiny formatters used across the cockpit. Currency, pct, signed deltas. */

export const fmtEur = (n: number): string =>
  new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n);

export const fmtEurCompact = (n: number): string => {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `€${(n / 1_000_000).toLocaleString('de-DE', { maximumFractionDigits: 2 })} M`;
  if (abs >= 1_000)     return `€${(n / 1_000).toLocaleString('de-DE', { maximumFractionDigits: 0 })}k`;
  return `€${n.toLocaleString('de-DE')}`;
};

export const fmtPct = (p: number, digits = 0): string =>
  `${(p * 100).toLocaleString('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;

export const fmtSignedPct = (p: number, digits = 0): string => {
  const v = p * 100;
  const sign = v > 0 ? '+' : v < 0 ? '−' : '±';
  return `${sign}${Math.abs(v).toLocaleString('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;
};

export const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' });

export const fmtDateShort = (iso: string): string =>
  new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
