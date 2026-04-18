import React from 'react';

/**
 * Exhibit primitives — the editorial atoms used across the Museum-Exhibit
 * cockpit. Ported 1:1 from the Claude Design handoff (handoff bundle
 * cFK0P9N815z30StKWtXAHw, 2026-04-18), converted to TypeScript.
 *
 * Why these are their own module: they're used by Hero, Rationale,
 * Candidates, Atlas roster, Forecast legend, Impact roster — splitting
 * them out keeps every page file readable.
 */

// --------------------------------------------------------------
// Calibration thermometer — the signature "not a confidence pill".
// --------------------------------------------------------------
export interface ThermometerProps {
  value: number;                // 0..1
  label: string;
  onStage?: boolean;            // true = dark hero, false = paper
  calibrated?: boolean;         // controls display format (78 % vs 0.78)
}
export const Thermometer: React.FC<ThermometerProps> = ({
  value,
  label,
  onStage = true,
  calibrated = true,
}) => {
  const pct = Math.max(0, Math.min(1, value));
  const displayed = calibrated ? `${Math.round(pct * 100)} %` : pct.toFixed(2);
  return (
    <div className={'ex-thermo-row' + (onStage ? '' : ' paper')}>
      <span className="ex-thermo-label">{label}</span>
      <div className={'ex-thermo' + (onStage ? '' : ' paper')}>
        <div className="ex-tube">
          <div className="ex-fill" style={{ transform: `scaleX(${pct})` }} />
          <div className="ex-ticks" />
        </div>
      </div>
      <span
        className="ex-num"
        style={{
          fontSize: 13,
          color: onStage ? '#f6f1e7' : 'var(--ex-ink, #1a1713)',
          minWidth: 52,
          textAlign: 'right',
        }}
      >
        {displayed}
      </span>
    </div>
  );
};

// --------------------------------------------------------------
// Method badge — calibrated vs heuristic, never both.
// --------------------------------------------------------------
export const MethodBadge: React.FC<{ calibrated: boolean; onPaper?: boolean }> = ({
  calibrated,
  onPaper = false,
}) => (
  <span
    className={
      'ex-method-badge' +
      (calibrated ? ' calibrated' : '') +
      (onPaper ? ' paper' : '')
    }
  >
    {calibrated ? 'kalibriert' : 'heuristisch'}
  </span>
);

// --------------------------------------------------------------
// Dash — for missing values. Honest-by-default.
// --------------------------------------------------------------
export const Dash: React.FC<{ note?: string }> = ({ note }) => (
  <span>
    <span className="ex-dash">—</span>
    {note ? (
      <span className="ex-dash-note" style={{ marginLeft: 6 }}>
        {note}
      </span>
    ) : null}
  </span>
);

// --------------------------------------------------------------
// Euro formatters. KEur renders the short form (€82 k); MoneyDE
// renders full integer EUR. Both fall back to Dash for null/"—".
// --------------------------------------------------------------
export const KEur: React.FC<{ eur: number | null | undefined | '—' }> = ({ eur }) => {
  if (eur === '—' || eur == null || !Number.isFinite(eur as number)) return <Dash />;
  // Heuristic: if the value is already in thousands (typical range < 10000)
  // display as k-suffixed. Otherwise, downscale.
  const n = eur as number;
  if (n < 10000) {
    return <span className="ex-num">€{Math.round(n).toLocaleString('de-DE')} k</span>;
  }
  return (
    <span className="ex-num">
      €{Math.round(n / 1000).toLocaleString('de-DE')} k
    </span>
  );
};

export const MoneyDE: React.FC<{ eur: number | null | undefined | '—' }> = ({ eur }) => {
  if (eur === '—' || eur == null || !Number.isFinite(eur as number)) return <Dash />;
  const n = eur as number;
  // If the incoming number is plausibly already in thousands (snapshot convention
  // passes full EUR; legacy prototype passed thousands), normalise to full EUR.
  const full = n < 10000 ? n * 1000 : n;
  return <span className="ex-num">€{Math.round(full).toLocaleString('de-DE')}</span>;
};

// --------------------------------------------------------------
// Caption strip — gradient bar + pinned marker, shared footer of
// every hero visual.
// --------------------------------------------------------------
export interface CaptionStripProps {
  label: React.ReactNode;
  value: React.ReactNode;
  pinAt?: number;              // 0..1
  onPaper?: boolean;
}
export const CaptionStrip: React.FC<CaptionStripProps> = ({
  label,
  value,
  pinAt = 0.5,
  onPaper = false,
}) => (
  <div className={'ex-caption-strip' + (onPaper ? ' paper' : '')}>
    <span className="ex-mono">{label}</span>
    <div className="ex-gradient-bar">
      <div
        className="ex-pin"
        style={{ left: `${Math.max(0, Math.min(1, pinAt)) * 100}%` }}
      />
    </div>
    <span className="ex-mono">{value}</span>
  </div>
);

// --------------------------------------------------------------
// Marginalia note — rendered into the outer 160 px rail.
// --------------------------------------------------------------
export const MarginNote: React.FC<{
  idx: string;
  text: React.ReactNode;
  onStage?: boolean;
}> = ({ idx, text, onStage = false }) => (
  <div
    className="ex-margin-note"
    style={
      onStage
        ? { color: 'rgba(246,241,231,.60)' }
        : undefined
    }
  >
    <span
      className="ex-mono-idx"
      style={
        onStage ? { color: 'rgba(246,241,231,.45)' } : undefined
      }
    >
      {idx}
    </span>
    {text}
  </div>
);

// --------------------------------------------------------------
// Section head — 3-col with optional marginalia in the side rails.
// --------------------------------------------------------------
export interface SectionHeadProps {
  idx: string;                 // e.g. "§ 01"
  title: React.ReactNode;      // "Begründung."
  titleItalic?: React.ReactNode; // " In drei Sätzen."
  leftNote?: { idx: string; text: React.ReactNode };
  rightNote?: { idx: string; text: React.ReactNode };
}
export const SectionHead: React.FC<SectionHeadProps> = ({
  idx,
  title,
  titleItalic,
  leftNote,
  rightNote,
}) => (
  <div className="ex-section-head">
    <div>
      {leftNote ? (
        <MarginNote idx={leftNote.idx} text={leftNote.text} />
      ) : (
        <span className="ex-mono" style={{ color: 'var(--ex-ink-45)' }}>
          {idx}
        </span>
      )}
    </div>
    <h2>
      {title}
      {titleItalic ? <em> {titleItalic}</em> : null}
    </h2>
    <div style={{ textAlign: 'right' }}>
      {rightNote ? <MarginNote idx={rightNote.idx} text={rightNote.text} /> : null}
    </div>
  </div>
);

// --------------------------------------------------------------
// Roster row — used by Candidates and Impact.
// --------------------------------------------------------------
export interface RosterRowProps {
  idx: React.ReactNode;
  name: React.ReactNode;
  sub?: React.ReactNode;
  value: React.ReactNode;
  direction: React.ReactNode;
  dirClass?: 'up' | 'down' | 'flat';
}
export const RosterRow: React.FC<RosterRowProps> = ({
  idx,
  name,
  sub,
  value,
  direction,
  dirClass = 'flat',
}) => (
  <li>
    <span className="ex-idx">{idx}</span>
    <span className="ex-name">
      {name}
      {sub ? <span className="ex-sub">{sub}</span> : null}
    </span>
    <span className="ex-val">{value}</span>
    <span className={`ex-dir ${dirClass}`}>{direction}</span>
  </li>
);
