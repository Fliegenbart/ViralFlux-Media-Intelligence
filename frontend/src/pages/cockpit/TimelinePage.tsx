import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import GalleryHero from '../../components/cockpit/peix/GalleryHero';
import ConfidenceCloud from '../../components/cockpit/peix/ConfidenceCloud';
import TimeScrubber from '../../components/cockpit/peix/TimeScrubber';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot, TimelinePoint } from './types';
import { fmtDate, fmtSignedPct } from './format';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 03 — "Forecast-Zeitreise".
 *
 * Gallery-refresh (2026-04-17): aligned with the Atlas dark-stage hero.
 * The previous "newspaper paper" treatment read distinct from the other
 * tabs; now the editorial lede lives in the same warm-black gallery stage
 * the other pages use, and the fan-chart sits on calmer paper underneath
 * with much more whitespace. Calibration + lag panels keep their
 * miniature-graphic approach but drop the coloured chrome.
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

  // Hero right-side visual: a big-type readout of the currently-selected
  // horizon. Changes live as the user scrubs.
  const horizonLabel =
    focusDay === 0 ? 'heute' : focusDay > 0 ? `+${focusDay} Tage` : `${focusDay} Tage`;

  const heroVisual = (
    <>
      <div className="peix-gal-bignum">
        <span className="peix-gal-bignum__kicker">Q50 vs. heute · {horizonLabel}</span>
        <span className="peix-gal-bignum__value">
          {delta !== null ? fmtSignedPct(delta) : '—'}
        </span>
        <p className="peix-gal-bignum__caption">
          {focus && focus.date
            ? fmtDate(focus.date)
            : 'Wählen Sie einen Tag im Fan-Chart unten.'}
        </p>
      </div>
      <div className="peix-gal-specs">
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">Intervall Q10–Q90</span>
          <span className="peix-gal-specs__value">
            {width !== null ? `${width.toFixed(1)} Pkt` : '—'}
          </span>
        </div>
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">Lead-Horizont</span>
          <span className="peix-gal-specs__value">{leadHorizon} Tage</span>
        </div>
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">Kalibrierung</span>
          <span
            className={
              'peix-gal-specs__value ' +
              (calibrated ? 'peix-gal-specs__value--warm' : '')
            }
          >
            {calibrated ? 'kalibriert' : 'heuristisch'}
          </span>
        </div>
      </div>
    </>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.28, ease: [0.22, 0.61, 0.36, 1] }}
      className="peix-gal-wrap"
    >
      <GalleryHero
        kicker={`zeitreise · ${snapshot.isoWeek}`}
        headline={
          <>
            Spulen Sie vor.
            <em> Dann zurück.</em>
          </>
        }
        dek={
          <>
            Links die beobachtete Vergangenheit, rechts die Prognose mit Q10–Q90-Fan.
            Je weiter in die Zukunft, desto breiter das Band —
            <em> bewusst sichtbar, nicht geglättet.</em>
          </>
        }
        visual={heroVisual}
        caption={{
          label: 'Diagramm 01',
          meta: (
            <>
              Prognose-Fan · Meldung · Notaufnahme-Spur
            </>
          ),
        }}
      />

      <header className="peix-gal-section">
        <span className="peix-gal-section__kicker">Fan-Chart</span>
        <h2 className="peix-gal-section__title">
          Q10, Q50, Q90 — <em>und</em> die Notaufnahme­-Spur als Frühindikator.
        </h2>
        <p className="peix-gal-section__dek">
          Oben der Median Q50 mit Unsicherheitsband plus SURVSTAT-Meldung.
          Unten die Notaufnahme-Aktivität — sie läuft dem Meldewesen typisch
          7–10 Tage voraus. Scroll-Regler unten wählt den Tag, dessen
          Eckdaten oben im Stein stehen.
        </p>
      </header>

      <section className="peix-bento">
        <div className="peix-card peix-col-12 quiet" style={{ padding: '32px 36px' }}>
          <ConfidenceCloud
            series={timeline}
            focusDay={focusDay}
            height={340}
            leadHorizonDays={leadHorizon}
            caption={null as unknown as string}
          />
          <div style={{ marginTop: 18 }}>
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
        </div>
      </section>

      <header className="peix-gal-section">
        <span className="peix-gal-section__kicker">Ehrlichkeits-Panele</span>
        <h2 className="peix-gal-section__title">
          Wie viel Vertrauen verdient <em>dieser</em> Fan?
        </h2>
      </header>

      <section className="peix-bento">
        <div className="peix-card peix-col-6 quiet" style={{ padding: '28px 30px' }}>
          <CalibrationPanel
            calibrated={calibrated}
            coverage80={coverage80}
            coverage95={coverage95}
          />
        </div>
        <div className="peix-card peix-col-6 quiet" style={{ padding: '28px 30px' }}>
          <LagPanel
            bestLag={bestLag}
            leadTargetLabel={leadTargetLabel}
            leadHorizon={leadHorizon}
          />
        </div>
      </section>

      <SourcesStrip sources={snapshot.sources} />
    </motion.div>
  );
};

// --------------------------------------------------------------------------
// Calibration — miniature reliability-style graphic.
// --------------------------------------------------------------------------
const CalibrationPanel: React.FC<{
  calibrated: boolean;
  coverage80: number | null;
  coverage95: number | null;
}> = ({ calibrated, coverage80, coverage95 }) => (
  <div>
    <div className="peix-gal-section__kicker" style={{ fontSize: 10.5 }}>
      Kalibrierungs-Status
    </div>
    <h3 className="peix-gal-h3">
      {calibrated
        ? 'Abdeckung liegt auf Ziel.'
        : 'Signalwerte sind ein Ranking-Score — keine %-Wahrscheinlichkeit.'}
    </h3>

    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 18 }}>
      <CoverageBar label="Band 80 %" actual={coverage80} target={80} />
      <CoverageBar label="Band 95 %" actual={coverage95} target={95} />
    </div>

    <p className="peix-gal-note">
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
  const actualPct =
    typeof actual === 'number' && Number.isFinite(actual) ? actual : null;
  const delta = actualPct !== null ? actualPct - target : null;
  const ok = delta !== null && Math.abs(delta) <= 3;
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '86px 1fr auto',
        gap: 14,
        alignItems: 'center',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--peix-font-mono)',
          fontSize: 11,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--peix-ink-mute)',
        }}
      >
        {label}
      </span>
      <div
        style={{
          position: 'relative',
          height: 10,
          background: 'var(--peix-line)',
          borderRadius: 5,
          overflow: 'hidden',
        }}
      >
        {/* Target tick */}
        <span
          style={{
            position: 'absolute',
            top: -3,
            bottom: -3,
            left: `${target}%`,
            width: 2,
            background: 'var(--peix-ink)',
            zIndex: 2,
          }}
          aria-label={`Ziel ${target} %`}
        />
        {actualPct !== null && (
          <span
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              bottom: 0,
              width: `${Math.min(Math.max(actualPct, 0), 100)}%`,
              background: ok
                ? 'var(--peix-warm-peak, #b94a2e)'
                : 'var(--peix-ink-soft)',
              borderRadius: 5,
              transition: 'width 220ms ease',
            }}
          />
        )}
      </div>
      <span
        style={{
          fontFamily: 'var(--peix-font-mono)',
          fontSize: 12.5,
          fontVariantNumeric: 'tabular-nums',
          color: 'var(--peix-ink)',
          minWidth: 72,
          textAlign: 'right',
        }}
      >
        {actualPct !== null ? `${actualPct.toFixed(1)} %` : '—'}
        {delta !== null && (
          <span
            style={{
              marginLeft: 8,
              color: ok ? 'var(--peix-warm-peak, #b94a2e)' : 'var(--peix-ink-mute)',
              fontSize: 11,
            }}
          >
            {delta > 0 ? '+' : ''}
            {delta.toFixed(1)}
          </span>
        )}
      </span>
    </div>
  );
};

// --------------------------------------------------------------------------
// Lag — linear "wave → ED → RKI" timeline with our forecast point placed
// on it, instead of a paragraph that reads like a disclaimer.
// --------------------------------------------------------------------------
const LagPanel: React.FC<{
  bestLag: number | null;
  leadTargetLabel: string;
  leadHorizon: number;
}> = ({ bestLag, leadTargetLabel, leadHorizon }) => {
  const REFS = [
    { at: 0, label: 'Echte Welle' },
    { at: 2, label: 'AMELAG' },
    { at: 3, label: 'Notaufnahme' },
    { at: 10, label: 'RKI-Meldung' },
  ];
  const domainMin = -4;
  const domainMax = 14;
  const pctFor = (d: number) => ((d - domainMin) / (domainMax - domainMin)) * 100;
  const NOTAUFNAHME_DAY = 3;
  const modelDay = bestLag !== null ? NOTAUFNAHME_DAY + bestLag : null;

  return (
    <div>
      <div className="peix-gal-section__kicker" style={{ fontSize: 10.5 }}>
        Lag-Ehrlichkeit
      </div>
      <h3 className="peix-gal-h3">
        Vorlauf gegen <em>{leadTargetLabel}</em>
      </h3>

      <div
        style={{
          position: 'relative',
          height: 86,
          marginBottom: 18,
        }}
        aria-hidden
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 28,
            height: 1,
            background: 'var(--peix-line-strong)',
          }}
        />
        {REFS.map((r) => (
          <div
            key={r.label}
            style={{
              position: 'absolute',
              left: `${pctFor(r.at)}%`,
              top: 0,
              transform: 'translateX(-50%)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 4,
              textAlign: 'center',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--peix-font-mono)',
                fontSize: 9.5,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                color: 'var(--peix-ink-mute)',
              }}
            >
              {r.label}
            </span>
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: 'var(--peix-ink)',
                marginTop: 14,
              }}
            />
            <span
              style={{
                fontFamily: 'var(--peix-font-mono)',
                fontSize: 9.5,
                color: 'var(--peix-ink-mute)',
              }}
            >
              {r.at === 0 ? 'Tag 0' : `+${r.at}d`}
            </span>
          </div>
        ))}
        {modelDay !== null && (
          <div
            style={{
              position: 'absolute',
              left: `${pctFor(modelDay)}%`,
              top: 0,
              transform: 'translateX(-50%)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
            }}
          >
            <span
              style={{
                width: 2,
                height: 28,
                background: 'var(--peix-warm-peak, #b94a2e)',
              }}
            />
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                background: 'var(--peix-warm-peak, #b94a2e)',
                marginTop: -6,
                border: '2px solid var(--peix-paper, #fafaf7)',
              }}
            />
            <span
              style={{
                fontFamily: 'var(--peix-font-mono)',
                fontSize: 9.5,
                textAlign: 'center',
                marginTop: 6,
                color: 'var(--peix-warm-peak, #b94a2e)',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
              }}
            >
              Forecast ({leadHorizon}d)
              <br />
              <strong style={{ fontSize: 11 }}>
                {bestLag! === 0 ? '0' : bestLag! > 0 ? `+${bestLag}` : bestLag} Tage
              </strong>
            </span>
          </div>
        )}
      </div>

      <p className="peix-gal-note">
        Typische Verzüge zwischen realer Infektion und verfügbaren Signalen. Der Forecast
        bleibt dem <em>RKI-Meldewesen</em> um circa 7–10 Tage voraus —
        {bestLag !== null && bestLag >= 0
          ? ' und läuft der Notaufnahme-Aktivität derzeit nicht hinterher.'
          : ' und liegt gegen die Notaufnahme-Aktivität aktuell leicht zurück, bleibt dem Meldewesen aber strukturell vor.'}
      </p>
    </div>
  );
};

export default TimelinePage;
