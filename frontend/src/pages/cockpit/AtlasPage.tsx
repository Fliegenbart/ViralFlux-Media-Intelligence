import React from 'react';
import { motion } from 'framer-motion';
import DataSculpture from '../../components/cockpit/peix/DataSculpture';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot } from './types';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 02 — The signature screen. 3D data sculpture of Germany with wave heights.
 * Intended for the opening of sales pitches and the "memorable image".
 */
export const AtlasPage: React.FC<Props> = ({ snapshot }) => (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    transition={{ duration: 0.3 }}
  >
    <DataSculpture
      regions={snapshot.regions}
      headline="Die nächste Hustenwelle — sie steht östlich, und sie wächst."
      dek="Jeder Turm ist ein Bundesland. Höhe zeigt die erwartete Bewegung der Reizhusten-Aktivität über die nächsten sieben Tage. Was Sie heute sehen, wird GELO nächste Woche buchen."
    />

    <section className="peix-bento" style={{ marginTop: 28 }}>
      <div className="peix-card peix-col-8">
        <div className="peix-kicker">was treibt die skulptur</div>
        <h3 className="peix-headline" style={{ marginTop: 4, marginBottom: 12 }}>
          Drei Signale, die sich diese Woche gegenseitig bestätigen
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
          <div>
            <div className="peix-eyebrow">1 · Abwasser (AMELAG)</div>
            <p className="peix-body" style={{ marginTop: 6 }}>
              Viruslast in BY, BE und SN um 38 – 44 % höher als Vorwoche.
              Das Signal liegt dem Meldewesen systematisch voraus.
            </p>
          </div>
          <div>
            <div className="peix-eyebrow">2 · Google Trends</div>
            <p className="peix-body" style={{ marginTop: 6 }}>
              Suchbegriffe „Reizhusten" und „Hustensaft" in den Ost-Bundesländern
              um Faktor 2,1 ggü. Vorwoche. Verhaltenssignal korreliert mit Abwasser.
            </p>
          </div>
          <div>
            <div className="peix-eyebrow">3 · Wetter & Kalender</div>
            <p className="peix-body" style={{ marginTop: 6 }}>
              Kälteeinbruch Montag, 20.04. Schulbeginn nach Osterferien in MV und BE.
              Beide Bedingungen sind empirisch gekoppelt an Wellen-Onset.
            </p>
          </div>
        </div>
      </div>

      <div className="peix-card peix-col-4 ink">
        <div className="peix-kicker">die zahl</div>
        <div style={{
          fontFamily: 'var(--peix-font-display)', fontWeight: 500,
          fontSize: 64, letterSpacing: '-0.02em', lineHeight: 1,
          marginTop: 18, marginBottom: 12, color: '#ffb897',
        }}>
          +26 %
        </div>
        <p style={{
          fontFamily: 'var(--peix-font-display)', fontStyle: 'italic',
          fontSize: 17, lineHeight: 1.4, color: 'rgba(245,243,238,0.75)',
        }}>
          erwartete Bewegung der Hustenaktivität in Bayern über die nächsten
          sieben Tage — der höchste Wert bundesweit.
        </p>
      </div>
    </section>

    <SourcesStrip sources={snapshot.sources} />
  </motion.div>
);

export default AtlasPage;
