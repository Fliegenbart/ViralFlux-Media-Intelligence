import React from 'react';
import { motion } from 'framer-motion';
import DataSculpture from '../../components/cockpit/peix/DataSculpture';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot } from './types';
import { fmtSignedPct } from './format';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 02 — The signature screen.
 *
 * After the 2026-04-16 audit the hand-written "three signals that confirm each
 * other this week" narrative was removed because it was static demo copy,
 * not derived from the backend. We now render snapshot.topDrivers plus the
 * strongest-delta region pulled from snapshot.regions.
 */
export const AtlasPage: React.FC<Props> = ({ snapshot }) => {
  const strongestRising = [...snapshot.regions]
    .filter((r) => typeof r.delta7d === 'number' && Number.isFinite(r.delta7d))
    .sort((a, b) => (b.delta7d ?? -Infinity) - (a.delta7d ?? -Infinity))[0];

  const dek = snapshot.regions.length
    ? `Jeder Turm ist ein Bundesland. Höhe zeigt die erwartete Bewegung über ${snapshot.modelStatus?.horizonDays ?? 7} Tage.`
    : 'Kein regionales Modell für den aktuellen Virus-Scope — die 3D-Darstellung wird erst gefüllt, wenn regionale Forecasts vorliegen.';

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.28, ease: [0.22, 0.61, 0.36, 1] }}
      className="peix-gal-wrap"
    >
      <DataSculpture
        regions={snapshot.regions}
        headline={`${snapshot.virusLabel} — was das Modell für die nächsten ${snapshot.modelStatus?.horizonDays ?? 7} Tage sagt.`}
        dek={dek}
      />

      <header className="peix-gal-section">
        <span className="peix-gal-section__kicker">Signalquellen</span>
        <h2 className="peix-gal-section__title">
          Woher das Modell die nächsten Wochen <em>liest</em>.
        </h2>
      </header>

      <section className="peix-bento">
        <div className="peix-card peix-col-8 quiet">
          <div className="peix-kicker">signal-quellen hinter der skulptur</div>
          <h3 className="peix-headline" style={{ marginTop: 4, marginBottom: 12 }}>
            {snapshot.topDrivers.length > 0
              ? 'Woher das Modell die nächsten Wochen liest'
              : 'Keine Signalquellen aktuell verfügbar'}
          </h3>
          {snapshot.topDrivers.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
              {snapshot.topDrivers.slice(0, 3).map((d, i) => (
                <div key={`${d.label}-${i}`}>
                  <div className="peix-eyebrow">{`${String(i + 1).padStart(2, '0')} · ${d.label}`}</div>
                  <p
                    className="peix-body"
                    style={{
                      marginTop: 6,
                      fontFamily: 'var(--peix-font-display, Georgia, serif)',
                      fontStyle: 'italic',
                      fontSize: 17,
                      lineHeight: 1.3,
                      color: 'var(--peix-ink, #17171a)',
                    }}
                  >
                    {d.value || '—'}
                  </p>
                  {d.subtitle && (
                    <div
                      className="peix-eyebrow"
                      style={{ marginTop: 4, opacity: 0.7, fontSize: 10.5 }}
                    >
                      {d.subtitle}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="peix-body" style={{ marginTop: 6, color: 'var(--peix-ink-soft)' }}>
              Keine der drei zentralen Signalquellen (Abwasser, Notaufnahme, Suchsignale)
              liefert aktuell verwertbare Daten — im Regelbetrieb ein seltenes Ereignis,
              vermutlich ein Ingest-Ausfall. Siehe Quellen-Status unten.
            </p>
          )}
        </div>

        <div className="peix-card peix-col-4 ink">
          <div className="peix-kicker">stärkster anstieg</div>
          {strongestRising && typeof strongestRising.delta7d === 'number' ? (
            <>
              <div style={{
                fontFamily: 'var(--peix-font-display)', fontWeight: 500,
                fontSize: 64, letterSpacing: '-0.02em', lineHeight: 1,
                marginTop: 18, marginBottom: 12, color: '#ffb897',
              }}>
                {fmtSignedPct(strongestRising.delta7d)}
              </div>
              <p style={{
                fontFamily: 'var(--peix-font-display)', fontStyle: 'italic',
                fontSize: 17, lineHeight: 1.4, color: 'rgba(245,243,238,0.75)',
              }}>
                erwartete Bewegung in <strong>{strongestRising.name}</strong> über die nächsten
                {` ${snapshot.modelStatus?.horizonDays ?? 7} `}Tage — der höchste Wert bundesweit.
              </p>
            </>
          ) : (
            <p style={{
              fontFamily: 'var(--peix-font-display)', fontStyle: 'italic',
              fontSize: 17, lineHeight: 1.4, color: 'rgba(245,243,238,0.75)', marginTop: 18,
            }}>
              Kein regionales Ranking verfügbar — für den gewählten Virus-Scope
              existiert kein regionales Modell oder es liegen keine Features vor.
            </p>
          )}
        </div>
      </section>

      <SourcesStrip sources={snapshot.sources} />
    </motion.div>
  );
};

export default AtlasPage;
