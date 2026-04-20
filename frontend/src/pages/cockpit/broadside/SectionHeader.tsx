import React from 'react';

/**
 * SectionHeader — Instrumentation-Variante.
 *
 * Drei-Spalten-Grid wie im Design-Handoff (KRdoxTmbT3xAVAhYEP211Q):
 *   [ROMAN]   [TITLE + SUBTITLE]                 [GATE · GO]
 *
 * Das römische Numeral steht links bei 48 px Supreme Regular, der
 * Titel in der Mitte bei 32 px Supreme Medium mit Untertitel bei
 * 18 px General Sans, und rechts ein Gate-Badge (GO / WATCH /
 * UNKNOWN) als typographische Mark mit 1px-Rahmen.
 *
 * Kein Kicker mehr, keine badges[]-Liste — die vorige Punk-Variante
 * war ein Badge-Cluster; hier genau ein Gate, das den Produkt-Gate
 * (forecastReadiness) direkt spiegelt.
 */

export type GateTone = 'go' | 'watch' | 'unknown';

export interface SectionHeaderProps {
  numeral: string;                  // "I", "II", …
  title: React.ReactNode;           // "Entscheidung der Woche"
  subtitle?: React.ReactNode;       // "KW 16 / 2026 · Influenza A"
  gate?: { label: string; tone: GateTone };
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  numeral,
  title,
  subtitle,
  gate,
}) => (
  <header className="sec-head">
    <div className="sec-numeral">{numeral}</div>
    <div>
      <h2 className="sec-title">
        {title}
        {subtitle && <span className="sub">{subtitle}</span>}
      </h2>
    </div>
    {gate ? (
      <span className={`gate ${gate.tone}`}>{gate.label}</span>
    ) : (
      <span />
    )}
  </header>
);

export default SectionHeader;
