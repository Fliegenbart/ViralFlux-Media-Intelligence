import React from 'react';
import type { CockpitSnapshot } from '../types';
import { fmtEurCompactOrDash, fmtSignedPct } from '../format';
import SectionHeader from './SectionHeader';
import type { GateTone } from './SectionHeader';

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
const VernierScale: React.FC<{
  pct: number;              // 0..1
  calibrated: boolean;
  leadDays: number | null;
  horizonWeeks: number;
  cov80: number | null;
  cov95: number | null;
  trainingSamples: number | null;
  maturityTier: 'pilot' | 'beta' | 'production' | 'unknown';
  maturityLabel: string | null;
}> = ({
  pct,
  calibrated,
  leadDays,
  horizonWeeks,
  cov80,
  cov95,
  trainingSamples,
  maturityTier,
  maturityLabel,
}) => {
  const clamped = Math.max(0, Math.min(1, pct));
  const display = Math.round(clamped * 100);

  // Ticks: major at 0/25/50/75/100, minor at 10/20/30/40/60/70/80/90
  const majorTicks = [0, 25, 50, 75, 100];
  const minorTicks = [10, 20, 30, 40, 60, 70, 80, 90];

  return (
    <aside className="vernier">
      <span className="corner-mark tl" />
      <span className="corner-mark tr" />
      <span className="corner-mark bl" />
      <span className="corner-mark br" />

      <div className="vernier-head">
        <span>Konfidenz</span>
        {calibrated ? (
          <span className="badge-cal">Kalibriert</span>
        ) : (
          <span className="badge-heur">Heuristisch</span>
        )}
      </div>

      <div className="vernier-readout">
        {display}
        <span className="pct">%</span>
      </div>

      <div className="vernier-scale">
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
        <div
          className="needle"
          style={{ left: `${clamped * 100}%` }}
          data-value={`▼ ${clamped.toFixed(2)}`}
        />
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
            {calibrated ? 'isotonic' : '—'}{' '}
            <span className="unit">
              {calibrated ? '' : 'nicht kalibriert'}
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
  const calibrated = snapshot.modelStatus?.calibrationMode === 'calibrated';
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

  return (
    <section className="instr-section" id="sec-decision">
      <SectionHeader
        numeral="I"
        title="Entscheidung der Woche"
        subtitle={
          <>
            {snapshot.isoWeek} · {virusLabel} · Ein Signal, eine Empfehlung.
          </>
        }
        gate={{ label: gateLabel, tone: gateTone }}
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
          ) : (
            <>
              <p className="decision-statement">
                <span className="from">Kein</span> klar gerichteter{' '}
                <span className="amt">Shift-Vorschlag</span> diese Woche.
              </p>

              <div className="rationale">
                <span className="instr-kicker">Begründung</span>
                <p>
                  Entweder meldet das Modell kein starkes Signal, oder es
                  fehlt ein verbundener Media-Plan. Diese Wochenausgabe
                  nimmt bewusst keine Platzhalter-Zahlen — Honest-by-default.
                </p>
              </div>
            </>
          )}
        </div>

        <VernierScale
          pct={rec ? rec.confidence : 0}
          calibrated={calibrated}
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
