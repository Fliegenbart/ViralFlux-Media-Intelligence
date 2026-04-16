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
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <DataSculpture
        regions={snapshot.regions}
        headline={`${snapshot.virusLabel} — was das Modell für die nächsten ${snapshot.modelStatus?.horizonDays ?? 7} Tage sagt.`}
        dek={dek}
      />

      <section className="peix-bento" style={{ marginTop: 28 }}>
        <div className="peix-card peix-col-8">
          <div className="peix-kicker">top-treiber laut modell</div>
          <h3 className="peix-headline" style={{ marginTop: 4, marginBottom: 12 }}>
            {snapshot.topDrivers.length > 0
              ? 'Signale mit der höchsten Gewichtung diese Woche'
              : 'Aktuell keine dominierenden Treiber vom Modell zurückgemeldet'}
          </h3>
          {snapshot.topDrivers.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
              {snapshot.topDrivers.slice(0, 3).map((d, i) => (
                <div key={`${d.label}-${i}`}>
                  <div className="peix-eyebrow">{`${i + 1} · ${d.label}`}</div>
                  <p className="peix-body" style={{ marginTop: 6 }}>
                    {d.value || 'Treiber aus Modell-reason_trace — aktuell ohne numerische Ausprägung.'}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="peix-body" style={{ marginTop: 6, color: 'var(--peix-ink-soft)' }}>
              Das Modell liefert in diesem Durchlauf keine Top-Treiber im
              reason_trace. Das passiert, wenn das Event-Signal homogen oder
              schwach ist, oder wenn die Kalibrierung übersprungen wurde
              (siehe Modell-Status).
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
