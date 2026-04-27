import React from 'react';
import type { CockpitSnapshot } from '../types';
import { fmtEurCompactOrDash, fmtSignalStrength } from '../format';
import {
  CaptionStrip,
  MaturityBadge,
  MethodBadge,
  Thermometer,
} from './primitives';

/**
 * Hero — the full-bleed Exhibit lede.
 *
 * Design reference: Cockpit.html fullbleed variant (the default).
 * The split/marginalia variants are defined in CSS and reachable via
 * the `layout` prop; we ship fullbleed as the live default because that
 * is what the final screenshot shows (final-01-hero.png).
 */

type HeroLayout = 'fullbleed' | 'split' | 'marginalia';

interface HeroProps {
  snapshot: CockpitSnapshot;
  layout?: HeroLayout;
  onOpen: (id: 'atlas' | 'forecast' | 'impact' | 'backtest') => void;
}

export const Hero: React.FC<HeroProps> = ({ snapshot, layout = 'fullbleed', onOpen }) => {
  const rec = snapshot.primaryRecommendation;
  const calibrated = snapshot.modelStatus?.calibrationMode === 'calibrated';
  const mediaConnected = snapshot.mediaPlan?.connected === true;
  const horizonWeeks = Math.max(
    1,
    Math.round((snapshot.modelStatus?.horizonDays ?? 7) / 7),
  );
  const horizonLabel = `${horizonWeeks}-Wochen-Horizont`;

  // Calibration / Plan / Lead-Time thermometer values.
  // - Calibration = lead.intervalCoverage80Pct normalised to [0,1]
  // - Plan availability = count of regions with currentSpendEur > 0 / total
  // - Lead = clamp(bestLagDays / 10, 0, 1) — 10 days is our design-max
  const cov80 = snapshot.modelStatus?.intervalCoverage80Pct ?? null;
  const calibValue = calibrated
    ? rec?.confidence ?? 0.5
    : rec?.confidence ?? 0.5;
  const planValue = (() => {
    const total = snapshot.regions.length || 1;
    const withPlan = snapshot.regions.filter(
      (r) => typeof r.currentSpendEur === 'number' && r.currentSpendEur > 0,
    ).length;
    return withPlan / total;
  })();
  const bestLag = snapshot.modelStatus?.lead?.bestLagDays ?? null;
  const leadValue =
    bestLag !== null ? Math.max(0, Math.min(1, bestLag / 10)) : 0;
  const leadIsCalibrated = bestLag !== null && bestLag > 0;
  const leadDaysLabel =
    bestLag !== null && bestLag >= 0
      ? `Lead-Time +${bestLag} d`
      : bestLag !== null
        ? `Lag ${bestLag} d`
        : 'Lead-Time';

  const trainingPanel = snapshot.modelStatus?.trainingPanel;

  // Kicker — mono labels + method badge + maturity badge
  const kicker = (
    <div className="ex-hero-kicker">
      <span className="ex-mono">Empfehlung der Woche</span>
      <span className="ex-dot" />
      <span className="ex-mono">{horizonLabel}</span>
      <span
        className="ex-dot"
        style={{ background: 'var(--ex-stage-hair)' }}
      />
      <MethodBadge calibrated={calibrated} />
      {trainingPanel && trainingPanel.maturityTier !== 'unknown' ? (
        <>
          <span
            className="ex-dot"
            style={{ background: 'var(--ex-stage-hair)' }}
          />
          <MaturityBadge
            tier={trainingPanel.maturityTier}
            label={trainingPanel.maturityLabel}
          />
        </>
      ) : null}
    </div>
  );

  // Lede — full serif display with italic accents on from / to / amount
  const lede = rec ? (
    <h1 className="ex-lede">
      Prüfe <em>{fmtEurCompactOrDash(rec.amountEur)}</em>
      <br />
      als Shift-Kandidat von <em>{rec.fromName}</em> nach
      <br />
      <em>{rec.toName}</em>.
    </h1>
  ) : (
    <h1 className="ex-lede">
      Aktuell <em>kein Shift-Kandidat</em>.
    </h1>
  );

  // Dek — 2–3 sentences, serif italic
  const dek = rec ? (
    <p className="ex-dek">{rec.why}</p>
  ) : (
    <p className="ex-dek">
      Entweder meldet das Modell kein starkes Signal, oder es fehlt ein
      verbundener Media-Plan. Diese Wochenausgabe nimmt bewusst keine
      Platzhalter-Zahlen — echte Zahlen kommen zurück, sobald Signal
      und Plan vorliegen.
    </p>
  );

  // Action row — link-style drawer openers
  const actions = (
    <div className="ex-hero-actions">
      <button
        type="button"
        className="ex-link-act"
        onClick={() => onOpen('atlas')}
      >
        Wellen-Atlas öffnen →
      </button>
      <button
        type="button"
        className="ex-link-act"
        onClick={() => onOpen('forecast')}
      >
        Forecast zeigen →
      </button>
      <button
        type="button"
        className="ex-link-act"
        onClick={() => onOpen('impact')}
      >
        Wirkung &amp; Rückkopplung →
      </button>
      <button
        type="button"
        className="ex-link-act"
        onClick={() => onOpen('backtest')}
      >
        Backtest zeigen →
      </button>
    </div>
  );

  const confidencePct = rec && calibrated
    ? Math.round(rec.confidence * 100)
    : rec
      ? rec.confidence
      : null;

  // Monument — the 160px numeral
  const monument = (
    <div style={{ textAlign: layout === 'fullbleed' ? 'left' : 'right' }}>
      <div
        className="ex-mono"
        style={{ marginBottom: 12, color: 'var(--ex-stage-45)' }}
      >
        Konfidenz · {calibrated ? 'kalibriert' : 'heuristisch'}
      </div>
      <div className="ex-monument">
        {confidencePct !== null && calibrated
          ? confidencePct
          : confidencePct !== null
            ? fmtSignalStrength(confidencePct as number)
            : '—'}
        {calibrated && confidencePct !== null ? (
          <span className="ex-unit">%</span>
        ) : null}
      </div>
      <div
        style={{
          marginTop: 24,
          maxWidth: 360,
          marginLeft: layout === 'fullbleed' ? 0 : 'auto',
        }}
      >
        <Thermometer
          value={calibValue}
          label="Signalstärke"
          onStage={true}
          calibrated={calibrated}
        />
        <Thermometer
          value={planValue}
          label={mediaConnected ? 'Planverfügbark.' : 'Plan fehlt'}
          onStage={true}
          calibrated={true}
        />
        <Thermometer
          value={leadValue}
          label={leadDaysLabel}
          onStage={true}
          calibrated={leadIsCalibrated}
        />
      </div>
    </div>
  );

  // --------------------------------------------------------------
  // Layout variants
  // --------------------------------------------------------------

  if (layout === 'fullbleed') {
    return (
      <section className="ex-hero fullbleed">
        {kicker}
        <div className="ex-hero-grid">
          <div>
            {lede}
            {dek}
            <div
              style={{
                display: 'flex',
                gap: 48,
                marginTop: 8,
                marginBottom: 24,
                flexWrap: 'wrap',
              }}
            >
              <div style={{ flex: 1, minWidth: 240 }}>
                <Thermometer
                  value={calibValue}
                  label="Signalstärke"
                  onStage={true}
                  calibrated={calibrated}
                />
              </div>
              <div style={{ flex: 1, minWidth: 240 }}>
                <Thermometer
                  value={planValue}
                  label="Planverfügbarkeit"
                  onStage={true}
                  calibrated={true}
                />
              </div>
              <div style={{ flex: 1, minWidth: 240 }}>
                <Thermometer
                  value={leadValue}
                  label={leadDaysLabel}
                  onStage={true}
                  calibrated={leadIsCalibrated}
                />
              </div>
            </div>
            <div
              className="ex-monument"
              style={{
                fontSize: 160,
                textAlign: 'left',
                lineHeight: 0.9,
                margin: '8px 0 0',
              }}
            >
              {confidencePct !== null && calibrated
                ? confidencePct
                : confidencePct !== null
                  ? fmtSignalStrength(confidencePct as number)
                  : '—'}
              {calibrated && confidencePct !== null ? (
                <span className="ex-unit">%</span>
              ) : null}
            </div>
            {actions}
          </div>
        </div>
        <CaptionStrip
          label={`Konfidenz · ${calibrated ? 'kalibriert' : 'heuristisch'} · ${snapshot.isoWeek}`}
          pinAt={rec ? rec.confidence : 0.5}
          value={
            cov80 !== null
              ? `Abdeckung ${cov80.toFixed(0)} %`
              : 'schwach · mittel · STARK'
          }
        />
      </section>
    );
  }

  if (layout === 'marginalia') {
    return (
      <section className="ex-hero marginalia">
        {kicker}
        <div className="ex-hero-grid">
          <div className="ex-margin-rail">
            <span className="ex-mono">M.01</span>
            Die Welle verlagert sich. Wer zuletzt im abklingenden Gebiet
            geplant hat, planiert jetzt einen fallenden Boden.
          </div>
          <div>
            {lede}
            {dek}
            {actions}
          </div>
          <div>{monument}</div>
          <div className="ex-margin-rail">
            <span className="ex-mono">M.02</span>
            {calibrated
              ? 'Die Zahl ist eine kalibrierte Wahrscheinlichkeit, keine Dashboard-Deko. Die Skala ist gemessen, nicht gemalt.'
              : 'Solange die Kalibrierung heuristisch ist, ist dies ein Ranking-Score (0..1), keine Wahrscheinlichkeit.'}
          </div>
        </div>
        <CaptionStrip
          label={`Konfidenz · ${calibrated ? 'kalibriert' : 'heuristisch'} · ${snapshot.isoWeek}`}
          pinAt={rec ? rec.confidence : 0.5}
          value={cov80 !== null ? `Abdeckung ${cov80.toFixed(0)} %` : '—'}
        />
      </section>
    );
  }

  // split (classic two-column)
  return (
    <section className="ex-hero">
      {kicker}
      <div className="ex-hero-grid">
        <div>
          {lede}
          {dek}
          {actions}
        </div>
        {monument}
      </div>
      <CaptionStrip
        label={`Konfidenz · ${calibrated ? 'kalibriert' : 'heuristisch'} · ${snapshot.isoWeek}`}
        pinAt={rec ? rec.confidence : 0.5}
        value={cov80 !== null ? `Abdeckung ${cov80.toFixed(0)} %` : '—'}
      />
    </section>
  );
};

export default Hero;
