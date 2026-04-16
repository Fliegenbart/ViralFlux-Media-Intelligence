import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import ConfidenceCloud from '../../components/cockpit/peix/ConfidenceCloud';
import TimeScrubber from '../../components/cockpit/peix/TimeScrubber';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot } from './types';
import { fmtDate, fmtSignedPct } from './format';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 03 — Forecast-Zeitreise. Scrub from −14 to +7; the cloud widens to the right
 * and the advice panel updates to the selected horizon.
 */
export const TimelinePage: React.FC<Props> = ({ snapshot }) => {
  const min = -14, max = 7;
  const [focusDay, setFocusDay] = useState(3);

  const focus = useMemo(
    () => snapshot.timeline.find((p) => p.horizonDays === focusDay)!,
    [snapshot.timeline, focusDay],
  );

  const delta = (focus.q50 - 96) / 96; // relative vs today-anchor (96)
  const width = focus.q90 - focus.q10;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.24 }}
    >
      <section className="peix-hero">
        <div className="peix-hero-lede">
          <div className="peix-kicker kick">forecast-zeitreise</div>
          <h1 className="peix-display">
            Spulen Sie vor. <em>Dann zurück.</em>
            <br />Sehen Sie, wie sich die Empfehlung wandelt.
          </h1>
          <p className="dek">
            Links die beobachtete Vergangenheit, rechts die Prognose mit 80 %-Konfidenzband.
            Je weiter wir in die Zukunft blicken, desto breiter wird die Unsicherheit — bewusst
            sichtbar gemacht, nicht geglättet.
          </p>
        </div>
        <aside className="peix-hero-card">
          <div className="row">
            <span className="label">Ausgewählter Tag</span>
            <span className="val" style={{ fontSize: 18 }}>{fmtDate(focus.date)}</span>
          </div>
          <div className="row">
            <span className="label">Horizont</span>
            <span className="val peix-num">
              {focusDay === 0 ? 'heute' : focusDay > 0 ? `+${focusDay} Tage` : `${focusDay} Tage`}
            </span>
          </div>
          <div className="row">
            <span className="label">Prognose · Q50</span>
            <span className="val peix-num">{fmtSignedPct(delta)}<small>· vs heute</small></span>
          </div>
          <div className="row">
            <span className="label">Konfidenzbreite</span>
            <span className="val peix-num">{width.toFixed(1)} Pkt<small>· Q10–Q90</small></span>
          </div>
        </aside>
      </section>

      <section className="peix-bento">
        <div className="peix-card peix-col-12">
          <ConfidenceCloud
            series={snapshot.timeline}
            focusDay={focusDay}
            height={320}
            caption="Dunkle Linie: tatsächlich beobachtet. Graue Zone: Nowcast-Fenster (letzte 14 Tage, Meldeverzug korrigiert). Blau: Median-Forecast mit 80 %-Konfidenzwolke."
          />
          <TimeScrubber
            min={min}
            max={max}
            value={focusDay}
            onChange={setFocusDay}
          />
        </div>

        <div className="peix-card peix-col-7">
          <div className="peix-kicker">kalibrierungs-check · letzte 90 tage</div>
          <h3 className="peix-headline" style={{ marginTop: 4 }}>
            Wir sagen <em>72 %</em>. Es passiert in <em>69 %</em> der Fälle.
          </h3>
          <svg viewBox="0 0 520 200" width="100%" height="200" style={{ marginTop: 12 }}>
            <line x1="40" y1="170" x2="480" y2="170" stroke="var(--peix-line)" strokeWidth="1" />
            <line x1="40" y1="20" x2="40" y2="170" stroke="var(--peix-line)" strokeWidth="1" />
            <line x1="40" y1="170" x2="480" y2="20" stroke="var(--peix-line-strong)" strokeDasharray="3 4" />
            <polyline
              points="40,168 110,145 180,118 250,92 320,68 390,44 460,26 480,22"
              stroke="var(--peix-cool)" strokeWidth="2.4" fill="none"
            />
            {[
              [110, 145], [180, 118], [250, 92], [320, 68], [390, 44], [460, 26],
            ].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3.5" fill="var(--peix-cool)" />)}
            <text x={40} y={188} className="peix-axis-label">sagen wir 0 %</text>
            <text x={460} y={188} className="peix-axis-label" textAnchor="end">sagen wir 100 %</text>
            <text x={10} y={170} className="peix-axis-label" transform="rotate(-90 10 170)">tritt ein</text>
          </svg>
          <p className="peix-body" style={{ marginTop: 10 }}>
            Die Reliability-Kurve liegt nahe der Diagonale. Übersetzt: Wenn unsere
            Empfehlung behauptet, etwas passiert, passiert es in der angegebenen Häufigkeit.
            Das ist selten in unserer Branche — und das unterscheidet uns.
          </p>
        </div>

        <div className="peix-card peix-col-5 quiet">
          <div className="peix-kicker">was wäre wenn</div>
          <h3 className="peix-headline" style={{ marginTop: 4 }}>
            Vergangenheit als Beweis
          </h3>
          <p className="peix-body">
            Dieser Scrubber lässt sich auf jede historische Welle anwenden.
            Ziehen Sie ihn zurück auf Januar 2026 — dort hätte das Tool den RSV-Peak
            in Berlin fünf Tage vor den Meldedaten markiert.
          </p>
          <button className="peix-btn ghost" style={{ alignSelf: 'flex-start', marginTop: 8 }}>
            Historie durchspielen →
          </button>
        </div>
      </section>

      <SourcesStrip sources={snapshot.sources} />
    </motion.div>
  );
};

export default TimelinePage;
