import React from 'react';
import { motion } from 'framer-motion';
import type { CockpitSnapshot } from '../../../pages/cockpit/types';
import { fmtEurCompact, fmtPct } from '../../../pages/cockpit/format';

interface Props { snap: CockpitSnapshot; }

/**
 * The hero: editorial lede on the left, calm number stack on the right.
 * Designed so a CMO gets the single action within the first 5 seconds.
 */
export const DecisionHero: React.FC<Props> = ({ snap }) => {
  const rec = snap.primaryRecommendation;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.38, ease: [0.22, 0.61, 0.36, 1] }}
      className="peix-hero"
    >
      <div className="peix-hero-lede">
        <div className="peix-kicker kick">empfehlung der woche</div>

        <h1 className="peix-display">
          Verschieben Sie <em>{fmtEurCompact(rec.amountEur)}</em>
          <br />
          aus <span style={{ textDecoration: 'line-through', textDecorationColor: 'rgba(138,144,162,0.5)', textDecorationThickness: '2px', color: 'var(--peix-ink-soft)' }}>{rec.fromName}</span>
          {' '}nach <em>{rec.toName}</em>.
        </h1>

        <p className="dek">
          {rec.why} Das Abwassersignal schreibt uns die nächste Hustenwelle eine
          Woche voraus — die Zahlen ordnen sie einer Region zu.
        </p>

        <div className="peix-action-row">
          <button className="peix-btn">Shift in Mediaplan übernehmen</button>
          <button className="peix-btn ghost">Warum diese Empfehlung? →</button>
        </div>
      </div>

      <aside className="peix-hero-card">
        <div className="row">
          <span className="label">Konfidenz</span>
          <span className="val peix-num">
            {fmtPct(rec.confidence)}
            <small>· kalibriert</small>
          </span>
        </div>
        <div className="row">
          <span className="label">Erw. Mehreffizienz</span>
          <span className="val peix-num">+{fmtPct(rec.expectedReachUplift)}<small>· Reichweite</small></span>
        </div>
        <div className="row">
          <span className="label">Buchungsfenster</span>
          <span className="val">Mo 20.04., 18:00</span>
        </div>
        <div className="row">
          <span className="label">GELO-Budget aktiv</span>
          <span className="val peix-num">{fmtEurCompact(snap.totalSpendEur)}<small>· wöchentlich</small></span>
        </div>
      </aside>
    </motion.section>
  );
};

export default DecisionHero;
