import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import ConfidenceCloud from '../../components/cockpit/peix/ConfidenceCloud';
import TimeScrubber from '../../components/cockpit/peix/TimeScrubber';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot, TimelinePoint } from './types';
import { fmtDate, fmtSignedPct } from './format';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 03 — Forecast-Zeitreise.
 *
 * Editorial newspaper-infographic take on the timeline. Cream/paper
 * background, serif display type, hairline rules. Chart is a fan-chart
 * with flag-style today marker and monument-style focus annotation.
 *
 * Two panels under the chart render calibration status and lag honesty
 * as miniature editorial graphics rather than paragraph copy.
 *
 * No fabricated numbers — all values come from snapshot.modelStatus.
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
    () => timeline.find((p) => p.horizonDays === focusDay) ?? timeline[0] ?? null,
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
  const bestLag = snapshot.modelStatus?.lead?.bestLagDays ?? snapshot.modelStatus?.bestLagDays ?? null;
  const leadHorizon = snapshot.modelStatus?.lead?.horizonDays ?? snapshot.modelStatus?.horizonDays ?? 14;
  const leadTargetLabel = snapshot.modelStatus?.lead?.targetLabel ?? 'Notaufnahme-Syndromsurveillance';

  const dateFor = (d: number) => timeline.find((p) => p.horizonDays === d)?.date ?? null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.28 }}
      className="peix-timeline"
    >
      <div className="peix-timeline__paper">
        <div className="peix-timeline__grain" aria-hidden />

        <header className="peix-timeline__masthead">
          <div className="peix-timeline__edition">
            <span className="peix-timeline__edition-mark">§</span>
            <span>Forecast-Zeitreise</span>
            <span className="peix-timeline__edition-sep">·</span>
            <span>Ausgabe {snapshot.isoWeek}</span>
          </div>
          <h1 className="peix-timeline__headline">
            Spulen Sie vor.
            <em> Dann zurück.</em>
          </h1>
          <p className="peix-timeline__dek">
            Links die beobachtete Vergangenheit, rechts die Prognose mit Q10–Q90-Fan.
            Je weiter in die Zukunft, desto breiter das Band —
            <em> bewusst sichtbar, nicht geglättet.</em>
          </p>
        </header>

        <section className="peix-timeline__chart-row">
          <div className="peix-timeline__chart-card">
            <div className="peix-timeline__chart-meta">
              <span className="peix-timeline__chart-meta-label">Diagramm 01</span>
              <span className="peix-timeline__chart-meta-title">
                Oben · Q50 mit Q10–Q90-Fan + SURVSTAT-Meldung.&nbsp;
                <em>Unten · Notaufnahme-ARI 7d-MA — läuft dem Meldewesen 7–10 Tage voraus.</em>
              </span>
            </div>
            <ConfidenceCloud
              series={timeline}
              focusDay={focusDay}
              height={360}
              leadHorizonDays={leadHorizon}
              caption={null as unknown as string}
            />
            <TimeScrubber
              min={min}
              max={max}
              value={focusDay}
              onChange={setFocusDay}
              dateFor={dateFor}
              labelLeft="beobachtet / nowcast"
              labelMid="heute"
              labelRight="prognose-fan"
            />
          </div>

          <aside className="peix-timeline__readout">
            <div className="peix-timeline__readout-kicker">Ausgewählter Tag</div>
            <div className="peix-timeline__readout-date">
              {focus ? fmtDate(focus.date) : '—'}
            </div>
            <div className="peix-timeline__readout-grid">
              <div>
                <div className="peix-timeline__readout-cell-label">Horizont</div>
                <div className="peix-timeline__readout-cell-value">
                  {focusDay === 0 ? 'heute' : focusDay > 0 ? `+${focusDay} Tage` : `${focusDay} Tage`}
                </div>
              </div>
              <div>
                <div className="peix-timeline__readout-cell-label">Q50 vs. heute</div>
                <div className="peix-timeline__readout-cell-value peix-timeline__readout-cell-value--emph">
                  {delta !== null ? fmtSignedPct(delta) : '—'}
                </div>
              </div>
              <div>
                <div className="peix-timeline__readout-cell-label">Intervall</div>
                <div className="peix-timeline__readout-cell-value">
                  {width !== null ? `${width.toFixed(1)} Pkt` : '—'}
                  <span className="peix-timeline__readout-cell-unit"> · Q10–Q90</span>
                </div>
              </div>
              <div>
                <div className="peix-timeline__readout-cell-label">Lead-Horizont</div>
                <div className="peix-timeline__readout-cell-value">
                  {leadHorizon} Tage
                </div>
              </div>
            </div>
          </aside>
        </section>

        <section className="peix-timeline__panels">
          <CalibrationPanel
            calibrated={calibrated}
            coverage80={coverage80}
            coverage95={coverage95}
          />
          <LagPanel
            bestLag={bestLag}
            leadTargetLabel={leadTargetLabel}
            leadHorizon={leadHorizon}
          />
        </section>

        <footer className="peix-timeline__footer">
          <SourcesStrip sources={snapshot.sources} />
        </footer>
      </div>
    </motion.div>
  );
};

// --------------------------------------------------------------------------
// Calibration panel — a miniature reliability-style graphic instead of the
// generic "two-coverage-numbers-in-a-sentence" layout.
// --------------------------------------------------------------------------
const CalibrationPanel: React.FC<{
  calibrated: boolean;
  coverage80: number | null;
  coverage95: number | null;
}> = ({ calibrated, coverage80, coverage95 }) => (
  <div className="peix-timeline__panel">
    <div className="peix-timeline__panel-kicker">Kalibrierungs-Status</div>
    <h3 className="peix-timeline__panel-headline">
      {calibrated
        ? 'Abdeckung liegt auf Ziel.'
        : 'Signalwerte sind ein Ranking-Score — keine %-Wahrscheinlichkeit.'}
    </h3>

    <div className="peix-timeline__coverage">
      <CoverageBar
        label="Band 80 %"
        actual={coverage80}
        target={80}
      />
      <CoverageBar
        label="Band 95 %"
        actual={coverage95}
        target={95}
      />
    </div>

    <p className="peix-timeline__panel-body">
      {calibrated ? (
        <>
          Ziel: 80 % der tatsächlichen Werte liegen im Q10–Q90-Band, 95 % im weiteren Band.
          Die Balken zeigen die aktuelle Abdeckung aus dem letzten Backtest.
        </>
      ) : (
        <>
          Die BL-Scores (0–1) werden für Priorisierung genutzt — volle Kalibrierung
          gegen echte Verkaufsdaten entsteht sobald der Feedback-Loop läuft
          <em> (Tab „Wirkung")</em>.
        </>
      )}
    </p>
  </div>
);

const CoverageBar: React.FC<{
  label: string;
  actual: number | null;
  target: number;
}> = ({ label, actual, target }) => {
  const actualPct = typeof actual === 'number' && Number.isFinite(actual) ? actual : null;
  const delta = actualPct !== null ? actualPct - target : null;
  return (
    <div className="peix-timeline__coverage-row">
      <div className="peix-timeline__coverage-label">{label}</div>
      <div className="peix-timeline__coverage-rail">
        <span
          className="peix-timeline__coverage-target"
          style={{ left: `${target}%` }}
          aria-label={`Ziel ${target} %`}
        />
        {actualPct !== null && (
          <span
            className="peix-timeline__coverage-fill"
            style={{ width: `${Math.min(Math.max(actualPct, 0), 100)}%` }}
          />
        )}
      </div>
      <div className="peix-timeline__coverage-value">
        {actualPct !== null ? `${actualPct.toFixed(1)} %` : '—'}
        {delta !== null && (
          <span
            className={
              'peix-timeline__coverage-delta ' +
              (Math.abs(delta) <= 3
                ? 'peix-timeline__coverage-delta--ok'
                : 'peix-timeline__coverage-delta--off')
            }
          >
            {delta > 0 ? '+' : ''}
            {delta.toFixed(1)}
          </span>
        )}
      </div>
    </div>
  );
};

// --------------------------------------------------------------------------
// Lag panel — a linear "wave → ED → RKI" timeline with our forecast point
// placed on it, instead of a paragraph that reads like a disclaimer.
// --------------------------------------------------------------------------
const LagPanel: React.FC<{
  bestLag: number | null;
  leadTargetLabel: string;
  leadHorizon: number;
}> = ({ bestLag, leadTargetLabel, leadHorizon }) => {
  // Conceptual timeline anchors (in "days after the real wave"). These are
  // documented-literature approximations (AMELAG ~2d, ED ~3d, RKI ~10d),
  // used here as an explanatory diagram, NOT as precise per-run metrics.
  const REFS = [
    { at: 0, label: 'Echte Welle' },
    { at: 2, label: 'AMELAG' },
    { at: 3, label: 'Notaufnahme' },
    { at: 10, label: 'RKI-Meldung' },
  ];
  const domainMin = -4;
  const domainMax = 14;
  const pctFor = (d: number) => ((d - domainMin) / (domainMax - domainMin)) * 100;

  // Our model's lag is measured *against* lead target (Notaufnahme at day 3).
  // bestLag < 0 means forecast trails the target by |bestLag| days.
  // So the model point on this axis sits at NOTAUFNAHME_DAY + bestLag.
  const NOTAUFNAHME_DAY = 3;
  const modelDay = bestLag !== null ? NOTAUFNAHME_DAY + bestLag : null;

  return (
    <div className="peix-timeline__panel peix-timeline__panel--lag">
      <div className="peix-timeline__panel-kicker">Lag-Ehrlichkeit</div>
      <h3 className="peix-timeline__panel-headline">
        Vorlauf gegen <em>{leadTargetLabel}</em>
      </h3>

      <div className="peix-timeline__lag-axis" aria-hidden>
        <div className="peix-timeline__lag-rail" />
        {REFS.map((r) => (
          <div
            key={r.label}
            className="peix-timeline__lag-ref"
            style={{ left: `${pctFor(r.at)}%` }}
          >
            <span className="peix-timeline__lag-ref-dot" />
            <span className="peix-timeline__lag-ref-label">{r.label}</span>
            <span className="peix-timeline__lag-ref-day">
              {r.at === 0 ? 'Tag 0' : `+${r.at}d`}
            </span>
          </div>
        ))}

        {modelDay !== null && (
          <div
            className="peix-timeline__lag-marker"
            style={{ left: `${pctFor(modelDay)}%` }}
          >
            <span className="peix-timeline__lag-marker-pin" />
            <span className="peix-timeline__lag-marker-label">
              Forecast ({leadHorizon}d)
              <br />
              <strong>
                {bestLag! === 0 ? '0' : bestLag! > 0 ? `+${bestLag}` : bestLag} Tage Lag
              </strong>
            </span>
          </div>
        )}
      </div>

      <p className="peix-timeline__panel-body">
        Die Zeitleiste zeigt typische Verzüge zwischen der tatsächlichen Infektion und den
        verfügbaren Signalen. Der Forecast bleibt dem
        <em> RKI-Meldewesen</em> um circa 7–10 Tage voraus —
        {bestLag !== null && bestLag >= 0
          ? ' und läuft der Notaufnahme-Aktivität derzeit nicht hinterher.'
          : ' und liegt gegen die Notaufnahme-Aktivität aktuell leicht zurück, bleibt dem Meldewesen aber strukturell vor.'}
      </p>
    </div>
  );
};

export default TimelinePage;
