import React from 'react';
import { motion } from 'framer-motion';
import GalleryHero from '../../components/cockpit/peix/GalleryHero';
import RosterList, { type RosterRow } from '../../components/cockpit/peix/RosterList';
import GermanyChoropleth from '../../components/cockpit/peix/GermanyChoropleth';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot } from './types';
import {
  fmtEurCompactOrDash,
  fmtPctOrDash,
  fmtSignalStrength,
  fmtSignedPct,
} from './format';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 01 — "Die Entscheidung".
 *
 * Gallery-refresh (2026-04-17): we inherit the Atlas dark-stage hero and
 * radically simplify everything below it. Before: five tinted cards in a
 * bento grid (hero, two maps, secondary rec list, top-driver grid, ink
 * quote card). After: one dark hero, one paired-map section, one roster
 * of shift candidates. The top-driver grid and the "wissenschaftliche
 * lesart" ink card were removed because their information is already
 * subsumed by the hero dek.
 */
export const DecisionPage: React.FC<Props> = ({ snapshot }) => {
  const rec = snapshot.primaryRecommendation;
  const calibrated = snapshot.modelStatus?.calibrationMode === 'calibrated';
  const mediaConnected = snapshot.mediaPlan?.connected === true;
  const lagNotice =
    snapshot.modelStatus?.lead?.bestLagDays !== null &&
    snapshot.modelStatus?.lead?.bestLagDays !== undefined &&
    snapshot.modelStatus.lead.bestLagDays < 0
      ? `Hinweis: gegenüber ${snapshot.modelStatus.lead.targetLabel ?? 'dem Meldewesen'} beträgt der Lag ${snapshot.modelStatus.lead.bestLagDays} Tage — nutzen Sie den Vorschlag zur Priorisierung, nicht als Punktprognose.`
      : '';

  // ---------- Hero content ------------------------------------------------
  const heroHeadline = rec ? (
    <>
      Verschieben Sie <em>{fmtEurCompactOrDash(rec.amountEur)}</em>
      <br />
      aus <s>{rec.fromName}</s> nach <em>{rec.toName}</em>.
    </>
  ) : (
    <>
      Aktuell <em>kein Shift-Vorschlag</em>.
    </>
  );

  const heroDek = rec ? (
    <>
      {rec.why}
      {lagNotice && <span style={{ display: 'block', marginTop: 8 }}>{lagNotice}</span>}
    </>
  ) : (
    <>
      Entweder meldet das Modell kein starkes Signal, oder es fehlt ein
      verbundener Media-Plan. Das Cockpit nimmt bewusst keine Platzhalter-
      Zahlen — echte Zahlen kommen, sobald das Ergebnis-Signal und der
      Plan vorliegen.
    </>
  );

  const heroActions = rec ? (
    <>
      <button
        type="button"
        className="peix-gal-btn"
        disabled={!mediaConnected}
      >
        {mediaConnected ? 'Shift übernehmen' : 'Media-Plan verbinden'}
      </button>
      <button type="button" className="peix-gal-btn peix-gal-btn--ghost">
        warum diese Empfehlung →
      </button>
    </>
  ) : !mediaConnected ? (
    <>
      <button type="button" className="peix-gal-btn">
        Media-Plan verbinden
      </button>
      <button type="button" className="peix-gal-btn peix-gal-btn--ghost">
        was das Cockpit braucht →
      </button>
    </>
  ) : null;

  const heroVisual = rec ? (
    <>
      <div className="peix-gal-bignum">
        <span className="peix-gal-bignum__kicker">
          {calibrated ? 'Konfidenz' : 'Signalstärke'}
        </span>
        <span className="peix-gal-bignum__value">
          {calibrated
            ? `${(rec.confidence * 100).toFixed(0)} %`
            : fmtSignalStrength(rec.confidence)}
        </span>
        <p className="peix-gal-bignum__caption">
          {calibrated
            ? 'Kalibriert — entspricht einer echten Eintritts­wahrscheinlichkeit.'
            : 'Ranking-Score (0–1), keine Prozent­wahrscheinlichkeit solange die Kalibrierung heuristisch ist.'}
        </p>
      </div>
      <div className="peix-gal-specs">
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">erw. Mehreffizienz</span>
          <span className="peix-gal-specs__value peix-gal-specs__value--warm">
            {fmtPctOrDash(rec.expectedReachUplift)}
          </span>
        </div>
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">Client-Budget (Woche)</span>
          <span className="peix-gal-specs__value">
            {fmtEurCompactOrDash(snapshot.totalSpendEur)}
          </span>
        </div>
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">Horizont</span>
          <span className="peix-gal-specs__value">
            {snapshot.modelStatus?.horizonDays ?? 7} Tage
          </span>
        </div>
      </div>
    </>
  ) : (
    <div className="peix-gal-bignum">
      <span className="peix-gal-bignum__kicker">Modell-Status</span>
      <span className="peix-gal-bignum__value" style={{ fontSize: 'clamp(32px, 4vw, 56px)' }}>
        {snapshot.modelStatus?.forecastReadiness ?? 'UNKNOWN'}
      </span>
      <p className="peix-gal-bignum__caption">
        {mediaConnected ? 'Media-Plan verbunden.' : 'Media-Plan nicht verbunden.'}
      </p>
    </div>
  );

  const captionMeta = (
    <>
      {snapshot.isoWeek} · {snapshot.virusLabel}
    </>
  );

  // ---------- Secondary recommendations as roster ------------------------
  const secondaryRows: RosterRow[] = snapshot.secondaryRecommendations.map((r) => ({
    id: r.id,
    name: `${r.fromName} → ${r.toName}`,
    meta: r.why,
    value:
      r.amountEur !== null && r.amountEur !== undefined
        ? fmtEurCompactOrDash(r.amountEur)
        : calibrated
          ? `${(r.confidence * 100).toFixed(0)} %`
          : fmtSignalStrength(r.confidence),
  }));

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.28, ease: [0.22, 0.61, 0.36, 1] }}
      className="peix-gal-wrap"
    >
      <GalleryHero
        kicker={`entscheidung · ${snapshot.isoWeek}`}
        headline={heroHeadline}
        dek={heroDek}
        actions={heroActions}
        visual={heroVisual}
        caption={{
          label: rec ? 'Empfehlung 01' : 'Status',
          meta: captionMeta,
        }}
      />

      <header className="peix-gal-section">
        <span className="peix-gal-section__kicker">Wellen-Bewegung</span>
        <h2 className="peix-gal-section__title">
          Wo die Welle <em>steigt</em> — und wo sie <em>abklingt</em>.
        </h2>
        <p className="peix-gal-section__dek">
          Zwei synoptische Kartenschichten. Links die Regionen mit erwartetem Anstieg
          über die nächsten {snapshot.modelStatus?.horizonDays ?? 7} Tage. Rechts jene,
          in denen Mediabudget gerade unterproportionale Reichweite erzeugt.
        </p>
      </header>

      <section className="peix-bento">
        <div className="peix-card peix-col-6 quiet">
          <GermanyChoropleth
            regions={snapshot.regions}
            mode="rising"
            kicker="dorthin shiften"
            title="Wo die Welle steigt"
            caption={`Bundesländer mit erwartetem Anstieg über ${snapshot.modelStatus?.horizonDays ?? 7} Tage.`}
          />
          <TopRisersBand regions={snapshot.regions} mode="rising" />
        </div>
        <div className="peix-card peix-col-6 quiet">
          <GermanyChoropleth
            regions={snapshot.regions}
            mode="falling"
            kicker="budget freiziehen"
            title="Wo die Welle abklingt"
            caption="Regionen, in denen das Signal aktuell nachlässt."
          />
          <TopRisersBand regions={snapshot.regions} mode="falling" />
        </div>
      </section>

      {secondaryRows.length > 0 && (
        <>
          <header className="peix-gal-section">
            <span className="peix-gal-section__kicker">Shift-Kandidaten</span>
            <h2 className="peix-gal-section__title">
              Weitere Empfehlungen der Woche.
            </h2>
            <p className="peix-gal-section__dek">
              {calibrated
                ? 'Konfidenz ist kalibriert gegen echte Eintritts­wahrscheinlichkeit.'
                : 'Werte sind Ranking-Scores — nicht Eintritts­wahrscheinlichkeit, solange die Kalibrierung heuristisch ist.'}
            </p>
          </header>
          <section
            className="peix-bento"
            style={{ gridTemplateColumns: 'repeat(12, 1fr)' }}
          >
            <div
              className="peix-card peix-col-12"
              style={{ padding: '8px 28px 24px' }}
            >
              <RosterList rows={secondaryRows} variant="paper" />
            </div>
          </section>
        </>
      )}

      <SourcesStrip sources={snapshot.sources} />
    </motion.div>
  );
};

// --------------------------------------------------------------------------
// A compact "top-3 lines" band under each choropleth — editorial footnote
// rather than a second full list. Uses the roster pattern but as a one-liner.
// --------------------------------------------------------------------------
const TopRisersBand: React.FC<{
  regions: CockpitSnapshot['regions'];
  mode: 'rising' | 'falling';
}> = ({ regions, mode }) => {
  const top = regions
    .filter((r) => typeof r.delta7d === 'number' && Number.isFinite(r.delta7d))
    .sort((a, b) =>
      mode === 'rising'
        ? (b.delta7d ?? -Infinity) - (a.delta7d ?? -Infinity)
        : (a.delta7d ?? Infinity) - (b.delta7d ?? Infinity),
    )
    .slice(0, 3);
  if (top.length === 0) return null;
  return (
    <div
      style={{
        marginTop: 18,
        paddingTop: 14,
        borderTop: '1px solid var(--peix-line)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div className="peix-gal-section__kicker" style={{ fontSize: 10 }}>
        {mode === 'rising' ? 'stärkster Anstieg' : 'stärkster Rückgang'}
      </div>
      {top.map((r, i) => (
        <div
          key={r.code}
          style={{
            display: 'grid',
            gridTemplateColumns: '28px 1fr auto',
            gap: 10,
            alignItems: 'baseline',
            padding: '4px 0',
          }}
        >
          <span
            className="peix-mono"
            style={{ color: 'var(--peix-ink-mute)', fontSize: 11 }}
          >
            {String(i + 1).padStart(2, '0')}
          </span>
          <span
            style={{
              fontFamily: 'var(--peix-font-display)',
              fontSize: 15,
              color: 'var(--peix-ink)',
            }}
          >
            {r.name}
          </span>
          <span
            style={{
              fontFamily: 'var(--peix-font-mono)',
              fontSize: 13,
              color:
                mode === 'rising'
                  ? 'var(--peix-warm-peak, #b94a2e)'
                  : 'var(--peix-ink-soft)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {fmtSignedPct(r.delta7d)}
          </span>
        </div>
      ))}
    </div>
  );
};

export default DecisionPage;
