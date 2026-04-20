import React, { useMemo, useState } from 'react';
import type { CockpitSnapshot } from '../types';
import { fmtEurCompactOrDash, fmtSignedPct } from '../format';
import SectionHeader from './SectionHeader';
import type { GateTone } from './SectionHeader';

// A region qualifies as a 'strong riser' when its 7-day delta crosses this
// absolute threshold. The value is deliberately conservative: we only want
// the "signal is there, EUR is missing" empty-state to fire when the wave
// is unmistakable in the atlas, not on marginal ranking noise.
const STRONG_RISER_THRESHOLD = 0.15;

/**
 * § I — Entscheidung der Woche.
 *
 * Instrumentation-Redesign 2026-04-18 (Handoff KRdoxTmbT3xAVAhYEP211Q).
 *
 * Layout:
 *   [Linker Block — 1.2fr]             [Rechter Block — 1fr]
 *   Empfehlung-Satz mit farbigem       Vernier-Skala mit
 *   amt/from/to-Markup                 Haarlinien-Ticks + Nadel
 *     + Transfer-Flow-Visual
 *     + Begründung (rationale)
 *
 * Die 78 % sind kein Zahlenblock, sondern eine mechanische Skala mit
 * Major/Minor-Ticks und einer Nadel bei dem genauen Wert. Das ist
 * der Haupt-Move dieses Redesigns: Konfidenz wird haptisch.
 */

interface Props {
  snapshot: CockpitSnapshot;
}

// -----------------------------------------------------------------
// VernierScale — mechanische Skala
// -----------------------------------------------------------------
type CalibrationMode = 'calibrated' | 'heuristic' | 'skipped' | 'unknown' | string;

const VernierScale: React.FC<{
  pct: number | null;       // 0..1 — null when no recommendation exists
  calibrationMode: CalibrationMode;
  leadDays: number | null;
  horizonWeeks: number;
  cov80: number | null;
  cov95: number | null;
  trainingSamples: number | null;
  maturityTier: 'pilot' | 'beta' | 'production' | 'unknown';
  maturityLabel: string | null;
}> = ({
  pct,
  calibrationMode,
  leadDays,
  horizonWeeks,
  cov80,
  cov95,
  trainingSamples,
  maturityTier,
  maturityLabel,
}) => {
  const hasValue = pct !== null;
  const clamped = hasValue ? Math.max(0, Math.min(1, pct as number)) : 0;
  const display = Math.round(clamped * 100);
  const calibrated = calibrationMode === 'calibrated';
  const calibrationUnknown =
    calibrationMode === 'unknown' || !calibrationMode || calibrationMode === '';

  // Ticks: major at 0/25/50/75/100, minor at 10/20/30/40/60/70/80/90
  const majorTicks = [0, 25, 50, 75, 100];
  const minorTicks = [10, 20, 30, 40, 60, 70, 80, 90];

  return (
    <aside className={`vernier${hasValue ? '' : ' empty'}`}>
      <span className="corner-mark tl" />
      <span className="corner-mark tr" />
      <span className="corner-mark bl" />
      <span className="corner-mark br" />

      <div className="vernier-head">
        <span>Konfidenz</span>
        {hasValue ? (
          calibrated ? (
            <span className="badge-cal">Kalibriert</span>
          ) : calibrationUnknown ? (
            <span
              className="badge-unknown"
              title={
                'Kalibrierung für dieses Virus ist aktuell nicht bewertet — ' +
                'es liegt kein Backtest-Lauf vor, der einen Kalibrierungs-' +
                'Modus feststellen könnte. Der Zahlenwert ist ein Ranking-' +
                'Score, keine kalibrierte Wahrscheinlichkeit.'
              }
            >
              Nicht bewertet
            </span>
          ) : (
            <span className="badge-heur">Heuristisch</span>
          )
        ) : (
          <span className="badge-empty">Kein Signal</span>
        )}
      </div>

      {hasValue ? (
        <div className="vernier-readout">
          {display}
          <span className="pct">%</span>
        </div>
      ) : (
        <div className="vernier-readout empty">
          <span className="dash">—</span>
        </div>
      )}

      <div className={`vernier-scale${hasValue ? '' : ' empty'}`}>
        <div className="axis" />
        {majorTicks.map((t) => (
          <React.Fragment key={`maj-${t}`}>
            <div className="tick major" style={{ left: `${t}%` }} />
            <div className="tick-label" style={{ left: `${t}%` }}>{t}</div>
          </React.Fragment>
        ))}
        {minorTicks.map((t) => (
          <div key={`min-${t}`} className="tick" style={{ left: `${t}%` }} />
        ))}
        {hasValue ? (
          <div
            className="needle"
            style={{ left: `${clamped * 100}%` }}
            data-value={`▼ ${clamped.toFixed(2)}`}
          />
        ) : null}
      </div>

      <dl className="vernier-meta">
        <div>
          <dt>Lead-Time</dt>
          <dd>
            {leadDays !== null
              ? `${leadDays >= 0 ? '+' : ''}${leadDays} `
              : '— '}
            <span className="unit">Tage</span>
          </dd>
        </div>
        <div>
          <dt>Horizont</dt>
          <dd>
            {horizonWeeks * 7} <span className="unit">Tage</span>
          </dd>
        </div>
        <div>
          <dt>Kalibrierung</dt>
          <dd>
            {calibrated
              ? 'isotonic'
              : calibrationUnknown
                ? '—'
                : 'heuristisch'}{' '}
            <span className="unit">
              {calibrated
                ? ''
                : calibrationUnknown
                  ? 'nicht bewertet'
                  : 'nicht kalibriert'}
            </span>
          </dd>
        </div>
        <div>
          <dt>Coverage</dt>
          <dd>
            {cov80 !== null ? cov80.toFixed(1) : '—'}{' '}
            <span className="unit">% Q80</span>
          </dd>
        </div>
        <div>
          <dt>Training-Panel</dt>
          <dd className={`maturity maturity-${maturityTier}`}>
            {trainingSamples !== null ? `N=${trainingSamples}` : '—'}{' '}
            <span className="unit">
              {maturityLabel ?? 'unbekannt'}
            </span>
          </dd>
        </div>
      </dl>
    </aside>
  );
};

// -----------------------------------------------------------------
// Root — Decision Section
// -----------------------------------------------------------------
export const DecisionSection: React.FC<Props> = ({ snapshot }) => {
  const rec = snapshot.primaryRecommendation;
  const calibrationMode = snapshot.modelStatus?.calibrationMode ?? 'unknown';
  const calibrated = calibrationMode === 'calibrated';
  const bestLag = snapshot.modelStatus?.lead?.bestLagDays ?? null;
  const horizonWeeks = Math.max(
    1,
    Math.round((snapshot.modelStatus?.horizonDays ?? 7) / 7),
  );
  const cov80 = snapshot.modelStatus?.intervalCoverage80Pct ?? null;
  const cov95 = snapshot.modelStatus?.intervalCoverage95Pct ?? null;

  const readiness = snapshot.modelStatus?.forecastReadiness ?? 'UNKNOWN';
  const gateTone: GateTone =
    readiness === 'GO_RANKING' || readiness === 'RANKING_OK'
      ? 'go'
      : readiness === 'WATCH' || readiness === 'LEAD_ONLY'
        ? 'watch'
        : 'unknown';
  const gateLabel =
    readiness === 'GO_RANKING'
      ? 'Gate · GO'
      : readiness === 'RANKING_OK'
        ? 'Gate · GO (Ranking)'
        : readiness === 'LEAD_ONLY'
          ? 'Gate · WATCH (Lead)'
          : readiness === 'WATCH'
            ? 'Gate · WATCH'
            : 'Gate · UNKNOWN';

  // Rec-Delta-Signalstärke: use region's delta7d if we can find it
  const toRegion = rec
    ? snapshot.regions.find((r) => r.code === rec.toCode)
    : null;
  const fromRegion = rec
    ? snapshot.regions.find((r) => r.code === rec.fromCode)
    : null;
  const toDeltaLabel =
    toRegion && typeof toRegion.delta7d === 'number'
      ? fmtSignedPct(toRegion.delta7d)
      : '—';
  const fromDeltaLabel =
    fromRegion && typeof fromRegion.delta7d === 'number'
      ? fmtSignedPct(fromRegion.delta7d)
      : '—';

  const virusLabel = snapshot.virusLabel || snapshot.virusTyp;

  // Strong-signal regions for the "Signal da, EUR fehlt" empty state.
  // Rendered only when there is no primaryRecommendation — i.e. when the
  // atlas shows a clear wave but the cockpit cannot translate it into a
  // EUR shift because the Media-Plan is not connected yet (honest-by-
  // default). Sorted by delta descending, capped at top-2 so the § I
  // copy stays tight.
  const strongRisers = useMemo(
    () =>
      [...snapshot.regions]
        .filter(
          (r) =>
            typeof r.delta7d === 'number' &&
            r.delta7d > STRONG_RISER_THRESHOLD &&
            r.decisionLabel !== 'TrainingPending',
        )
        .sort((a, b) => (b.delta7d ?? 0) - (a.delta7d ?? 0))
        .slice(0, 2),
    [snapshot.regions],
  );
  const hasStrongSignal = strongRisers.length > 0;
  const mediaPlanConnected = snapshot.mediaPlan?.connected === true;

  // Demo-Budget-Szene: when no real recommendation is available AND no
  // Media-Plan is connected, offer a "what-if" simulation so a
  // first-time reader can see how the cockpit would translate the atlas
  // signal into a concrete EUR shift once data lands. The card is
  // explicitly marked DEMO and bound to an assumption-budget input; it
  // does not pretend to be a real recommendation.
  const [demoOpen, setDemoOpen] = useState(false);
  const [demoBudget, setDemoBudget] = useState(100_000);

  const topFallers = useMemo(
    () =>
      [...snapshot.regions]
        .filter(
          (r) =>
            typeof r.delta7d === 'number' &&
            r.delta7d < -0.05 &&
            r.decisionLabel !== 'TrainingPending',
        )
        .sort((a, b) => (a.delta7d ?? 0) - (b.delta7d ?? 0))
        .slice(0, 1),
    [snapshot.regions],
  );
  const demoTo = strongRisers[0] ?? null;
  const demoFrom = topFallers[0] ?? null;
  const demoShiftEur =
    demoTo && demoFrom
      ? Math.round((demoBudget * Math.min(0.35, (demoTo.delta7d ?? 0) * 0.4)) / 1_000) * 1_000
      : 0;
  const showDemo = !mediaPlanConnected && !rec && hasStrongSignal && demoTo && demoFrom;

  return (
    <section className="instr-section" id="sec-decision">
      <SectionHeader
        numeral="II"
        title="Entscheidung der Woche"
        subtitle={
          <>
            {snapshot.isoWeek} · {virusLabel} ·{' '}
            {rec
              ? 'Ein Signal, eine Empfehlung.'
              : hasStrongSignal
                ? 'Signal klar — Euro-Shift wartet auf Media-Plan.'
                : 'Signallage zu eng für einen Shift.'}
          </>
        }
        gate={{ label: gateLabel, tone: gateTone }}
        primer={
          <>
            Links siehst du die <b>eine</b> Media-Empfehlung dieser Woche
            — oder eine ehrliche Leerseite, wenn keine zu vertreten ist.
            Rechts ein Vernier-Instrument: die <b>Konfidenz</b> des
            Modells als Skala mit Nadel statt Prozent-Pille, darunter
            Lead-Time, Coverage und Training-Panel-Reife als Kontext.
            Wert für dich: die eine Zahl, die du am Montag umsetzt —
            oder das Signal „heute passt keine Platzhalter-Zahl".
          </>
        }
      />

      <div className="decision-grid">
        <div>
          <p className="instr-kicker" style={{ marginBottom: 24 }}>
            Empfehlung · {snapshot.isoWeek}
          </p>

          {rec ? (
            <>
              <p className="decision-statement">
                Verschiebe{' '}
                <span className="amt">
                  {fmtEurCompactOrDash(rec.amountEur)}
                </span>{' '}
                aus <span className="from">{rec.fromName}</span>{' '}
                nach <span className="to">{rec.toName}</span>
                {rec.why ? ' — ' : '.'}
                {rec.why}
              </p>

              <div className="transfer">
                <div className="transfer-node from">
                  <div className="label">Abfluss</div>
                  <div className="place">{rec.fromName}</div>
                  <div className="delta down">
                    Welle schwächer · {fromDeltaLabel}
                  </div>
                </div>
                <div className="transfer-arrow">
                  <span className="amt">
                    {fmtEurCompactOrDash(rec.amountEur)}
                  </span>
                </div>
                <div className="transfer-node to">
                  <div className="label">Zufluss</div>
                  <div className="place">{rec.toName}</div>
                  <div className="delta up">
                    Anstieg erwartet · {toDeltaLabel}
                  </div>
                </div>
              </div>

              <div className="rationale">
                <span className="instr-kicker">Begründung</span>
                <p>
                  {rec.why || 'Begründung nicht hinterlegt.'}
                  {bestLag !== null && bestLag >= 0 && (
                    <>
                      {' '}
                      Lead-Zeit gegen Meldewesen:{' '}
                      <b>+{bestLag} Tage</b>.
                    </>
                  )}
                </p>
              </div>
            </>
          ) : hasStrongSignal ? (
            <>
              <p className="decision-statement">
                Signallage deutlich in{' '}
                <span className="to">{strongRisers[0].name}</span>{' '}
                <span className="amt">
                  ({fmtSignedPct(strongRisers[0].delta7d)} in 7 d)
                </span>
                {strongRisers.length > 1 && (
                  <>
                    {' '}und{' '}
                    <span className="to">{strongRisers[1].name}</span>{' '}
                    ({fmtSignedPct(strongRisers[1].delta7d)}).
                  </>
                )}
                {strongRisers.length === 1 && '.'}
              </p>

              <div className="rationale">
                <span className="instr-kicker">Warum kein EUR-Vorschlag</span>
                <p>
                  Das Modell sieht{' '}
                  {strongRisers.length > 1 ? 'Wellen' : 'eine Welle'} — der
                  Shift-Betrag in EUR wartet auf die Anbindung des
                  {mediaPlanConnected ? ' ' : ' '}Media-Plans
                  {mediaPlanConnected
                    ? '.'
                    : ' (mediaPlan.connected = false).'}{' '}
                  Honest-by-default: keine Platzhalter-Beträge.
                </p>
              </div>

              {showDemo ? (
                <div className={`demo-budget${demoOpen ? ' open' : ''}`}>
                  <button
                    type="button"
                    className="demo-budget-toggle"
                    onClick={() => setDemoOpen(!demoOpen)}
                  >
                    <span className="demo-badge">Demo-Szene</span>
                    {demoOpen ? 'Was-wäre-wenn schließen' : 'Was wäre wenn? Simulierte EUR-Shift ansehen'}
                  </button>
                  {demoOpen ? (
                    <div className="demo-budget-body">
                      <div className="demo-note">
                        <b>Demo — keine echten Daten.</b> Angenommen ein
                        Wochenbudget wäre verbunden, würde das System das
                        atlas-beobachtete Signal etwa so in einen Shift
                        übersetzen. Zahl ist rein illustrativ.
                      </div>
                      <label className="demo-budget-slider">
                        <span>Angenommenes Wochenbudget</span>
                        <input
                          type="range"
                          min={20_000}
                          max={500_000}
                          step={10_000}
                          value={demoBudget}
                          onChange={(e) => setDemoBudget(Number(e.target.value))}
                        />
                        <output>
                          {demoBudget.toLocaleString('de-DE')} €
                        </output>
                      </label>
                      <p className="demo-statement">
                        <span className="demo-verb">Verschiebe</span>{' '}
                        <span className="demo-amt">
                          {demoShiftEur.toLocaleString('de-DE')} €
                        </span>{' '}
                        aus <span className="demo-from">{demoFrom!.name}</span>{' '}
                        <span className="demo-faller-delta">
                          ({fmtSignedPct(demoFrom!.delta7d)})
                        </span>{' '}
                        nach <span className="demo-to">{demoTo!.name}</span>{' '}
                        <span className="demo-riser-delta">
                          ({fmtSignedPct(demoTo!.delta7d)})
                        </span>
                        .
                      </p>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </>
          ) : (
            <>
              <p className="decision-statement">
                <span className="from">Kein</span> klar gerichteter{' '}
                <span className="amt">Shift-Vorschlag</span> diese Woche.
              </p>

              <div className="rationale">
                <span className="instr-kicker">Begründung</span>
                <p>
                  Weder ein starkes regionales Signal noch ein verbundener
                  Media-Plan — keine Woche für einen Shift. Diese
                  Wochenausgabe nimmt bewusst keine Platzhalter-Zahlen —
                  Honest-by-default.
                </p>
              </div>
            </>
          )}
        </div>

        <VernierScale
          pct={rec ? rec.confidence : null}
          calibrationMode={calibrationMode}
          leadDays={bestLag}
          horizonWeeks={horizonWeeks}
          cov80={cov80}
          cov95={cov95}
          trainingSamples={snapshot.modelStatus?.trainingPanel?.trainingSamples ?? null}
          maturityTier={snapshot.modelStatus?.trainingPanel?.maturityTier ?? 'unknown'}
          maturityLabel={
            snapshot.modelStatus?.trainingPanel?.maturityLabel ?? null
          }
        />
      </div>
    </section>
  );
};

export default DecisionSection;
