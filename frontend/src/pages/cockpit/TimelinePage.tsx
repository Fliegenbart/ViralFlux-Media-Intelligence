import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import ConfidenceCloud from '../../components/cockpit/peix/ConfidenceCloud';
import TimeScrubber from '../../components/cockpit/peix/TimeScrubber';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot, TimelinePoint } from './types';
import { fmtDate, fmtSignedPct } from './format';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 03 — forecast timeline.
 *
 * After the 2026-04-16 math audit the reliability/calibration panel now
 * gates on snapshot.modelStatus.calibrationMode; a handcrafted reliability
 * diagram with invented percentages ("Wir sagen 72 %, es passiert in 69 %")
 * was removed. Historical claims that the tool "predicted peak X days
 * before" were also removed — the actual best_lag_days signal is shown
 * instead.
 */
export const TimelinePage: React.FC<Props> = ({ snapshot }) => {
  const timeline: TimelinePoint[] = useMemo(
    () => snapshot.timeline ?? [],
    [snapshot.timeline],
  );

  const available = useMemo(
    () => timeline.map((p) => p.horizonDays).sort((a, b) => a - b),
    [timeline],
  );
  const min = available.length ? available[0] : -14;
  const max = available.length ? available[available.length - 1] : 7;

  const [focusDay, setFocusDay] = useState(() =>
    available.includes(3) ? 3 : available.find((d) => d >= 0) ?? min,
  );

  const focus = useMemo(
    () =>
      timeline.find((p) => p.horizonDays === focusDay) ??
      timeline[0] ??
      null,
    [timeline, focusDay],
  );

  const anchor = useMemo(() => {
    const today = timeline.find((p) => p.horizonDays === 0);
    return today?.q50 ?? focus?.q50 ?? null;
  }, [timeline, focus]);

  const delta =
    focus?.q50 !== null && focus?.q50 !== undefined && anchor !== null && anchor !== 0
      ? (focus.q50 - anchor) / anchor
      : null;
  const width =
    focus?.q10 !== null && focus?.q10 !== undefined && focus?.q90 !== null && focus?.q90 !== undefined
      ? focus.q90 - focus.q10
      : null;

  const calibrated = snapshot.modelStatus?.calibrationMode === 'calibrated';
  const coverage80 = snapshot.modelStatus?.intervalCoverage80Pct ?? null;
  const coverage95 = snapshot.modelStatus?.intervalCoverage95Pct ?? null;
  const bestLag = snapshot.modelStatus?.bestLagDays ?? null;

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
            Links die beobachtete Vergangenheit, rechts die Prognose mit Q10/Q90-Band.
            Je weiter wir in die Zukunft blicken, desto breiter wird die Unsicherheit —
            bewusst sichtbar gemacht, nicht geglättet.
          </p>
        </div>
        <aside className="peix-hero-card">
          <div className="row">
            <span className="label">Ausgewählter Tag</span>
            <span className="val" style={{ fontSize: 18 }}>
              {focus ? fmtDate(focus.date) : '—'}
            </span>
          </div>
          <div className="row">
            <span className="label">Horizont</span>
            <span className="val peix-num">
              {focusDay === 0 ? 'heute' : focusDay > 0 ? `+${focusDay} Tage` : `${focusDay} Tage`}
            </span>
          </div>
          <div className="row">
            <span className="label">Prognose · Q50</span>
            <span className="val peix-num">
              {delta !== null ? fmtSignedPct(delta) : '—'}
              <small>· vs heute</small>
            </span>
          </div>
          <div className="row">
            <span className="label">Intervall-Breite</span>
            <span className="val peix-num">
              {width !== null ? `${width.toFixed(1)} Pkt` : '—'}
              <small>· Q10–Q90</small>
            </span>
          </div>
        </aside>
      </section>

      <section className="peix-bento">
        <div className="peix-card peix-col-12">
          <ConfidenceCloud
            series={timeline}
            focusDay={focusDay}
            height={320}
            caption="Dunkle Linie: beobachtet/nowcast (letzte 14 Tage). Blau: Median-Forecast mit Q10–Q90-Band. Breite = Unsicherheit, nicht geglättet."
          />
          <TimeScrubber
            min={min}
            max={max}
            value={focusDay}
            onChange={setFocusDay}
          />
        </div>

        <div className="peix-card peix-col-7">
          <div className="peix-kicker">kalibrierungs-status</div>
          {calibrated ? (
            <>
              <h3 className="peix-headline" style={{ marginTop: 4 }}>
                Intervall-Abdeckung liegt an den Zielwerten.
              </h3>
              <p className="peix-body" style={{ marginTop: 10 }}>
                Ziel: 80 % der tatsächlichen Werte liegen im Q10–Q90-Band; 95 % im
                weiteren Band. Aktueller Backtest:
                <strong> {coverage80 !== null ? `${coverage80.toFixed(1)} %` : '—'}</strong> bei 80 %,
                <strong> {coverage95 !== null ? `${coverage95.toFixed(1)} %` : '—'}</strong> bei 95 %.
              </p>
            </>
          ) : (
            <>
              <h3 className="peix-headline" style={{ marginTop: 4 }}>
                Signalstärke ist <em>nicht</em> kalibriert.
              </h3>
              <p className="peix-body" style={{ marginTop: 10 }}>
                Das aktuelle Backend meldet
                <strong> calibration_mode = {snapshot.modelStatus?.calibrationMode ?? 'unknown'}</strong>.
                Die pro-Region-Scores sind Sigmoid-Transformationen einer Forecast-vs-Baseline-
                Heuristik — NICHT als Wahrscheinlichkeit zu lesen. Intervall-Abdeckung
                (80/95&nbsp;%): <strong>{coverage80 !== null ? `${coverage80.toFixed(1)} %` : '—'}</strong> /
                <strong> {coverage95 !== null ? `${coverage95.toFixed(1)} %` : '—'}</strong>.
              </p>
            </>
          )}
        </div>

        <div className="peix-card peix-col-5 quiet">
          <div className="peix-kicker">lag-ehrlichkeit</div>
          <h3 className="peix-headline" style={{ marginTop: 4 }}>
            Wo läuft das Modell <em>relativ zur Realität</em>?
          </h3>
          <p className="peix-body">
            Der Backtest misst den Lag, bei dem die Korrelation zwischen Forecast und
            tatsächlichem Verlauf maximal wird. Aktueller Wert:
            <strong> {bestLag !== null ? `${bestLag} Tage` : '—'}</strong>. Werte &lt; 0 bedeuten:
            der Forecast läuft der Realität hinterher — er ist für <em>Priorisierung</em>
            tauglich, nicht für Punktprognose.
          </p>
        </div>
      </section>

      <SourcesStrip sources={snapshot.sources} />
    </motion.div>
  );
};

export default TimelinePage;
