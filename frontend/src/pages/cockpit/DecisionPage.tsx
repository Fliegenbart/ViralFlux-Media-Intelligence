import React from 'react';
import { motion } from 'framer-motion';
import DecisionHero from '../../components/cockpit/peix/DecisionHero';
import GermanyChoropleth from '../../components/cockpit/peix/GermanyChoropleth';
import RecommendationList from '../../components/cockpit/peix/RecommendationList';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot } from './types';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 01 — The editorial lede: "Move money east".
 * FT/Linear-premium look with split-view maps and secondary recs below.
 */
export const DecisionPage: React.FC<Props> = ({ snapshot }) => (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    transition={{ duration: 0.24 }}
    className="peix-fade-in"
  >
    <DecisionHero snap={snapshot} />

    <section className="peix-bento">
      <div className="peix-card peix-col-6 warm-tint">
        <GermanyChoropleth
          regions={snapshot.regions}
          mode="rising"
          kicker="dorthin shiften"
          title="Wo die Welle steigt"
          caption="Bundesländer mit erwartetem Anstieg der Reizhusten-Aktivität in den nächsten 7 Tagen."
        />
      </div>
      <div className="peix-card peix-col-6 cool-tint">
        <GermanyChoropleth
          regions={snapshot.regions}
          mode="falling"
          kicker="budget freiziehen"
          title="Wo die Welle abklingt"
          caption="Regionen, in denen Mediabudget gerade unterproportionale Reichweite erzeugt."
        />
      </div>

      <div className="peix-card peix-col-12">
        <header>
          <div>
            <div className="peix-kicker">weitere empfehlungen</div>
            <h3 className="peix-headline" style={{ marginTop: 4 }}>Shift-Kandidaten der Woche</h3>
          </div>
          <span className="peix-pill">
            {snapshot.modelStatus?.calibrationMode === 'calibrated'
              ? 'kalibrierte Konfidenz · Q50'
              : 'heuristische Signalstärke · Q50'}
          </span>
        </header>
        <RecommendationList
          items={snapshot.secondaryRecommendations}
          calibrated={snapshot.modelStatus?.calibrationMode === 'calibrated'}
        />
      </div>

      <div className="peix-card peix-col-7 quiet">
        <div className="peix-kicker">top-treiber diese woche</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 20, marginTop: 12 }}>
          {snapshot.topDrivers.map((d) => (
            <div key={d.label}>
              <div className="peix-headline" style={{ fontSize: 20 }}>{d.value}</div>
              <div className="peix-eyebrow">{d.label}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="peix-card peix-col-5 ink">
        <div className="peix-kicker">wissenschaftliche lesart</div>
        <p style={{
          fontFamily: 'var(--peix-font-display)', fontStyle: 'italic',
          fontSize: 19, lineHeight: 1.4, marginTop: 8, color: 'rgba(245,243,238,0.86)',
        }}>
          „Unser stärkstes Frühsignal — Abwasser — liegt den Meldedaten
          um 7 bis 10 Tage voraus. Diese Empfehlung verschiebt Mediabudget
          genau dorthin, wo die Welle in einer Woche sichtbar wird."
        </p>
        <div style={{ marginTop: 'auto', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span className="peix-pill ink">{snapshot.modelStatus?.horizonDays ?? 7}-Tage-Horizont</span>
          <span className="peix-pill ink">Q10 · Q50 · Q90</span>
          <span className="peix-pill ink">
            {snapshot.modelStatus?.calibrationMode === 'calibrated'
              ? 'isotonisch kalibriert'
              : 'heuristische Signalstärke'}
          </span>
        </div>
      </div>
    </section>

    <SourcesStrip sources={snapshot.sources} />
  </motion.div>
);

export default DecisionPage;
