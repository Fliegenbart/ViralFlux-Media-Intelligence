import React from 'react';

/**
 * SectionHeader — Instrumentation-Variante.
 *
 * Drei-Spalten-Grid wie im Design-Handoff (KRdoxTmbT3xAVAhYEP211Q):
 *   [ROMAN]   [TITLE + SUBTITLE]                 [GATE · GO]
 *
 * Unterhalb der Header-Zeile kann optional ein `primer`-Absatz gesetzt
 * werden: zwei bis drei Sätze in Serif, die das Element für einen
 * Erstleser einordnen — was sehe ich, wie lese ich es, welchen
 * Mehrwert hat es. Das ist die "Lese-Hilfe"-Ebene, die das Cockpit
 * vorher nicht hatte; ein Decision-Maker soll nicht externe Handoffs
 * lesen müssen, um § II von § III zu unterscheiden.
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
  /**
   * Optional reader's guide (2-3 sentences) shown below the header.
   * Purpose: orient a first-time reader — what is this element, how
   * to read it, what value it provides. Plain language, no jargon.
   */
  primer?: React.ReactNode;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  numeral,
  title,
  subtitle,
  gate,
  primer,
}) => (
  <>
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
    {primer ? <p className="sec-primer">{primer}</p> : null}
  </>
);

export default SectionHeader;
