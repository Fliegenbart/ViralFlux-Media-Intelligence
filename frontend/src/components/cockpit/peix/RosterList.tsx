import React from 'react';

/**
 * RosterList — universal editorial list pattern. Origin: the "top risers"
 * list on the Atlas page (left lede column). Now promoted to a shared
 * component so Decision / Timeline / Impact reuse the same visual rhythm:
 *
 *   01  ▎ name                              ─────  +18 %
 *   02  ▎ name                              ─────  +14 %
 *
 * Two surfaces:
 *   - default: dark/gallery (warm-black ground, cream ink, terracotta value)
 *   - variant="paper": light (cream paper ground, ink, deep terracotta)
 *
 * Each row has an optional "meta" slot (caption / secondary line) rendered
 * between the name and the hairline rule.
 */

export interface RosterRow {
  id: string;
  name: string;
  value: string;           // already-formatted (e.g. "+14 %", "84 k EUR")
  meta?: string;           // optional secondary line
}

interface Props {
  rows: RosterRow[];
  variant?: 'paper';
  /** If true, show hairline rule between name/meta and value (default true). */
  showRule?: boolean;
  /** Optional empty-state node when rows is empty. */
  empty?: React.ReactNode;
}

export const RosterList: React.FC<Props> = ({
  rows,
  variant,
  showRule = true,
  empty,
}) => {
  if (rows.length === 0) {
    return (
      <div
        style={{
          padding: '16px 0',
          fontFamily: 'var(--peix-font-display)',
          fontStyle: 'italic',
          color: variant === 'paper' ? 'var(--peix-ink-soft)' : 'rgba(239,232,220,0.55)',
          fontSize: 14.5,
        }}
      >
        {empty ?? 'Kein Eintrag vorhanden.'}
      </div>
    );
  }
  const cls =
    variant === 'paper' ? 'peix-gal-roster peix-gal-roster--paper' : 'peix-gal-roster';
  return (
    <ol className={cls}>
      {rows.map((r, i) => (
        <li key={r.id} className="peix-gal-roster__row">
          <span className="peix-gal-roster__idx">{String(i + 1).padStart(2, '0')}</span>
          <span className="peix-gal-roster__name" title={r.name}>
            {r.name}
          </span>
          <span className="peix-gal-roster__meta" title={r.meta}>
            {showRule && !r.meta ? <HairRule /> : r.meta ?? <HairRule />}
          </span>
          <span className="peix-gal-roster__value">{r.value}</span>
        </li>
      ))}
    </ol>
  );
};

const HairRule: React.FC = () => (
  <span
    aria-hidden
    style={{
      display: 'inline-block',
      width: '100%',
      height: 1,
      background: 'currentColor',
      opacity: 0.2,
      transform: 'translateY(-4px)',
    }}
  />
);

export default RosterList;
