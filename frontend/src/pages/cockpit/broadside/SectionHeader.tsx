import React from 'react';

/**
 * SectionHeader — uniform chapter-mark for every Broadside section.
 * §-numeral on left in big Fraunces, serif-italic title in the middle,
 * mono timestamp stamp on the right.
 *
 * Variants are driven by the *parent* section class (`.ex-section--stage`
 * vs `.ex-section--paper`) so the header inherits the right foreground
 * color automatically.
 */

export interface SectionHeaderProps {
  numeral: string;       // "§ I"
  kicker?: string;       // small mono kicker line
  title: React.ReactNode; // "Die Entscheidung." (italic em marks allowed)
  stamp?: React.ReactNode; // "KW 16 · 2026" — usually isoWeek
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  numeral,
  kicker,
  title,
  stamp,
}) => (
  <header className="ex-section-head">
    <div className="ex-section-num">{numeral}</div>
    <div className="ex-section-title-stack">
      {kicker && <span className="ex-section-kicker">{kicker}</span>}
      <h2 className="ex-section-title">{title}</h2>
    </div>
    <div className="ex-section-stamp">{stamp}</div>
  </header>
);

export default SectionHeader;
