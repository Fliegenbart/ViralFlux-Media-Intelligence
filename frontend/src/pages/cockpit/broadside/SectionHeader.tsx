import React from 'react';

/**
 * SectionHeader — full-width dark stage strip that announces each
 * Broadside chapter like a sport-magazine cover spread.
 *
 * Layout:
 *   [§ I ◼]        MONO-KICKER                  [BADGE] [BADGE]
 *                  TITLE · CAPS · DISPLAY
 *                                                 MONO STAMP
 *
 * The numeral sits left at 96 px display-serif with a terracotta
 * block punched into its baseline. The title fills the middle in
 * uppercase Fraunces (loud, not editorial). Status badges and the
 * week-stamp cluster at the right.
 */

export type StatusBadgeTone = 'go' | 'watch' | 'neutral' | 'ochre' | 'solid';

export interface StatusBadge {
  label: string;
  tone?: StatusBadgeTone;
}

export interface SectionHeaderProps {
  numeral: string;        // "§ I"
  kicker?: string;        // small mono kicker line
  title: React.ReactNode; // "DIE ENTSCHEIDUNG" (italic <em> in terracotta allowed)
  stamp?: React.ReactNode;
  badges?: StatusBadge[];
}

const toneClass: Record<StatusBadgeTone, string> = {
  go: 'ex-status-badge ex-status-badge--go',
  watch: 'ex-status-badge ex-status-badge--watch',
  neutral: 'ex-status-badge ex-status-badge--neutral',
  ochre: 'ex-status-badge ex-status-badge--ochre',
  solid: 'ex-status-badge ex-status-badge--solid',
};

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  numeral,
  kicker,
  title,
  stamp,
  badges,
}) => (
  <header className="ex-section-head">
    <div className="ex-section-num">{numeral}</div>
    <div className="ex-section-title-stack">
      {kicker && <span className="ex-section-kicker">{kicker}</span>}
      <h2 className="ex-section-title">{title}</h2>
    </div>
    <div className="ex-section-stamp">
      {badges && badges.length > 0 && (
        <div className="ex-section-badges">
          {badges.map((b, i) => (
            <span key={`${b.label}-${i}`} className={toneClass[b.tone ?? 'neutral']}>
              {b.label}
            </span>
          ))}
        </div>
      )}
      {stamp && <span>{stamp}</span>}
    </div>
  </header>
);

export default SectionHeader;
