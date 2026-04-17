import React from 'react';
import { motion } from 'framer-motion';
import type { CockpitSnapshot } from '../../../pages/cockpit/types';
import { fmtEurCompactOrDash, fmtPctOrDash, fmtSignalStrength } from '../../../pages/cockpit/format';

interface Props { snap: CockpitSnapshot; }

/**
 * The hero: editorial lede on the left, calm number stack on the right.
 *
 * History: before the 2026-04-16 math audit this section always rendered a
 * concrete EUR shift and a "Konfidenz 78 %" badge even when the underlying
 * model output was a heuristic signal. After the audit:
 *   - EUR amounts render as "—" when no media plan is connected.
 *   - The score badge says "Signalstärke" with two decimals (raw 0..1)
 *     unless modelStatus.calibrationMode === 'calibrated'.
 *   - If there is no primary recommendation at all, the hero shows an
 *     explicit "kein Shift-Vorschlag" copy instead of an invented one.
 */
export const DecisionHero: React.FC<Props> = ({ snap }) => {
  const rec = snap.primaryRecommendation;
  const calibrated = snap.modelStatus?.calibrationMode === 'calibrated';
  const mediaConnected = snap.mediaPlan?.connected === true;

  if (!rec) {
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
            Aktuell <em>kein Shift-Vorschlag</em>.
          </h1>
          <p className="dek">
            Entweder meldet das Modell kein starkes Signal, oder es fehlt ein
            verbundener Media-Plan. Das Cockpit nimmt bewusst keine Platzhalter-
            EUR-Zahlen — echte Zahlen kommen, sobald das Ergebnis-Signal und
            der Plan vorliegen.
          </p>
        </div>
        <aside className="peix-hero-card">
          <div className="row">
            <span className="label">Modell-Status</span>
            <span className="val">{snap.modelStatus?.forecastReadiness ?? 'UNKNOWN'}</span>
          </div>
          <div className="row">
            <span className="label">Media-Plan</span>
            <span className="val">{mediaConnected ? 'verbunden' : 'nicht verbunden'}</span>
          </div>
        </aside>
      </motion.section>
    );
  }

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
          Verschieben Sie <em>{fmtEurCompactOrDash(rec.amountEur)}</em>
          <br />
          aus <span style={{ textDecoration: 'line-through', textDecorationColor: 'rgba(138,144,162,0.5)', textDecorationThickness: '2px', color: 'var(--peix-ink-soft)' }}>{rec.fromName}</span>
          {' '}nach <em>{rec.toName}</em>.
        </h1>

        <p className="dek">
          {rec.why} {snap.modelStatus?.lead?.bestLagDays !== null && snap.modelStatus?.lead?.bestLagDays !== undefined && snap.modelStatus.lead.bestLagDays < 0
            ? `Hinweis: gegenüber ${snap.modelStatus.lead.targetLabel ?? 'dem Meldewesen'} beträgt der Lag ${snap.modelStatus.lead.bestLagDays} Tage — nutzen Sie den Vorschlag für Priorisierung, nicht als Punktprognose.`
            : ''}
        </p>

        <div className="peix-action-row">
          <button className="peix-btn" disabled={!mediaConnected}>
            {mediaConnected ? 'Shift in Mediaplan übernehmen' : 'Media-Plan verbinden'}
          </button>
          <button className="peix-btn ghost">Warum diese Empfehlung? →</button>
        </div>
      </div>

      <aside className="peix-hero-card">
        <div className="row">
          <span className="label">{calibrated ? 'Konfidenz' : 'Signalstärke'}</span>
          <span className="val peix-num">
            {calibrated ? `${(rec.confidence * 100).toFixed(0)} %` : fmtSignalStrength(rec.confidence)}
            <small>· {calibrated ? 'kalibriert' : 'heuristisch'}</small>
          </span>
        </div>
        <div className="row">
          <span className="label">Erw. Mehreffizienz</span>
          <span className="val peix-num">
            {fmtPctOrDash(rec.expectedReachUplift)}<small>· Reichweite</small>
          </span>
        </div>
        <div className="row">
          <span className="label">Buchungsfenster</span>
          <span className="val">—</span>
        </div>
        <div className="row">
          <span className="label">Client-Budget aktiv</span>
          <span className="val peix-num">
            {fmtEurCompactOrDash(snap.totalSpendEur)}<small>· wöchentlich</small>
          </span>
        </div>
      </aside>
    </motion.section>
  );
};

export default DecisionHero;
