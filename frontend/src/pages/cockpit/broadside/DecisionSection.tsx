import React from 'react';
import type { CockpitSnapshot, ShiftRecommendation } from '../types';
import {
  fmtEurCompactOrDash,
  fmtPctOrDash,
  fmtSignalStrength,
} from '../format';
import {
  CaptionStrip,
  Dash,
  KEur,
  MethodBadge,
  RosterRow,
  Thermometer,
} from '../exhibit/primitives';
import SectionHeader from './SectionHeader';

/**
 * § I — Entscheidung.
 *
 * The first and most important section of the broadside. Composition:
 *   - Hero block on the warm-black stage: the one-sentence
 *     recommendation ("Verschiebe €82k aus Bayern nach Brandenburg.")
 *     plus confidence monument + thermometer row.
 *   - Rationale block on paper: rec.why + 3 stats (lead / horizon /
 *     alternatives).
 *   - Candidates roster: secondary recommendations.
 *
 * No drawer, no click-to-reveal — everything is visible on scroll.
 */

interface Props {
  snapshot: CockpitSnapshot;
}

// ---------- Hero block (dark stage) -------------------------------------
const HeroBlock: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const rec = snapshot.primaryRecommendation;
  const calibrated = snapshot.modelStatus?.calibrationMode === 'calibrated';
  const mediaConnected = snapshot.mediaPlan?.connected === true;
  const horizonWeeks = Math.max(
    1,
    Math.round((snapshot.modelStatus?.horizonDays ?? 7) / 7),
  );
  const horizonLabel = `${horizonWeeks}-Wochen-Horizont`;

  const calibValue = rec?.confidence ?? 0.5;
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

  const cov80 = snapshot.modelStatus?.intervalCoverage80Pct ?? null;

  return (
    <div
      style={{
        background: 'var(--ex-stage)',
        color: '#f6f1e7',
        padding: '56px 48px 56px',
        margin: '40px -48px 0',
      }}
    >
      <div style={{ maxWidth: 1344, margin: '0 auto' }}>
        {/* Kicker */}
        <div
          className="ex-hero-kicker"
          style={{ display: 'flex', gap: 28, alignItems: 'center', marginBottom: 40, flexWrap: 'wrap' }}
        >
          <span className="ex-mono" style={{ color: 'var(--ex-stage-45)' }}>
            Empfehlung der Woche
          </span>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: 'var(--ex-ochre)',
            }}
          />
          <span className="ex-mono" style={{ color: 'var(--ex-stage-45)' }}>
            {horizonLabel}
          </span>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: 'var(--ex-stage-hair)',
            }}
          />
          <MethodBadge calibrated={calibrated} />
        </div>

        {/* Lede + monument side by side */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1.1fr 1fr',
            gap: 64,
            alignItems: 'end',
          }}
        >
          <div>
            {rec ? (
              <h1
                style={{
                  fontFamily: 'var(--ex-serif)',
                  fontWeight: 400,
                  fontSize: 'clamp(40px, 5vw, 72px)',
                  lineHeight: 1.02,
                  letterSpacing: '-0.03em',
                  margin: '0 0 28px',
                  fontVariationSettings: '"opsz" 144',
                }}
              >
                Verschiebe{' '}
                <em
                  style={{ fontStyle: 'italic', color: 'var(--ex-ochre)' }}
                >
                  {fmtEurCompactOrDash(rec.amountEur)}
                </em>
                <br />
                aus{' '}
                <em style={{ fontStyle: 'italic', color: 'var(--ex-ochre)' }}>
                  {rec.fromName}
                </em>{' '}
                nach
                <br />
                <em style={{ fontStyle: 'italic', color: 'var(--ex-ochre)' }}>
                  {rec.toName}
                </em>
                .
              </h1>
            ) : (
              <h1
                style={{
                  fontFamily: 'var(--ex-serif)',
                  fontWeight: 400,
                  fontSize: 'clamp(40px, 5vw, 72px)',
                  lineHeight: 1.02,
                  letterSpacing: '-0.03em',
                  margin: '0 0 28px',
                  fontVariationSettings: '"opsz" 144',
                }}
              >
                Aktuell{' '}
                <em style={{ fontStyle: 'italic', color: 'var(--ex-ochre)' }}>
                  kein Shift-Vorschlag
                </em>
                .
              </h1>
            )}

            <p
              style={{
                fontFamily: 'var(--ex-serif)',
                fontStyle: 'italic',
                fontSize: 19,
                lineHeight: 1.45,
                color: 'var(--ex-stage-60)',
                maxWidth: '46ch',
                margin: '0 0 32px',
                fontVariationSettings: '"opsz" 36',
              }}
            >
              {rec
                ? rec.why
                : 'Entweder meldet das Modell kein starkes Signal, oder es fehlt ein verbundener Media-Plan. Diese Wochenausgabe nimmt bewusst keine Platzhalter-Zahlen.'}
            </p>
          </div>

          {/* Monument + thermometers */}
          <div>
            <div
              className="ex-mono"
              style={{ color: 'var(--ex-stage-45)', marginBottom: 10 }}
            >
              Konfidenz · {calibrated ? 'kalibriert' : 'heuristisch'}
            </div>
            <div
              style={{
                fontFamily: 'var(--ex-serif)',
                fontWeight: 400,
                fontSize: 128,
                lineHeight: 0.9,
                letterSpacing: '-0.045em',
                fontVariationSettings: '"opsz" 144',
                color: '#f6f1e7',
              }}
            >
              {rec && calibrated
                ? Math.round(rec.confidence * 100)
                : rec
                  ? fmtSignalStrength(rec.confidence)
                  : '—'}
              {rec && calibrated && (
                <span
                  style={{
                    fontSize: 28,
                    color: 'var(--ex-stage-60)',
                    marginLeft: 8,
                    fontFamily: 'var(--ex-mono)',
                    verticalAlign: 'top',
                  }}
                >
                  %
                </span>
              )}
            </div>

            <div style={{ marginTop: 28, maxWidth: 360 }}>
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
        </div>

        <div style={{ marginTop: 40 }}>
          <CaptionStrip
            label={`Konfidenz · ${calibrated ? 'kalibriert' : 'heuristisch'} · ${snapshot.isoWeek}`}
            pinAt={rec ? rec.confidence : 0.5}
            value={
              cov80 !== null ? `Abdeckung ${cov80.toFixed(0)} %` : '—'
            }
          />
        </div>
      </div>
    </div>
  );
};

// ---------- Rationale block (paper) -------------------------------------
const RationaleBlock: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const rec = snapshot.primaryRecommendation;
  const horizonWeeks = Math.max(
    1,
    Math.round((snapshot.modelStatus?.horizonDays ?? 7) / 7),
  );
  const leadDays = snapshot.modelStatus?.lead?.bestLagDays ?? null;
  const altCount = snapshot.secondaryRecommendations?.length ?? 0;

  return (
    <div style={{ marginTop: 72 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 14,
          marginBottom: 24,
        }}
      >
        <span
          style={{
            fontFamily: 'var(--ex-serif)',
            fontStyle: 'italic',
            fontSize: 24,
            color: 'var(--ex-fired)',
            fontVariationSettings: '"opsz" 36',
          }}
        >
          §
        </span>
        <span
          className="ex-mono"
          style={{ color: 'var(--ex-ink-45)', letterSpacing: '.16em' }}
        >
          Begründung
        </span>
      </div>
      <div style={{ maxWidth: 900 }}>
        <p
          style={{
            fontFamily: 'var(--ex-serif)',
            fontStyle: 'italic',
            fontSize: 26,
            lineHeight: 1.35,
            margin: 0,
            color: 'var(--ex-ink)',
            fontVariationSettings: '"opsz" 36',
          }}
        >
          {rec
            ? rec.why
            : 'In dieser Woche ergibt die Modellarbeit keinen eindeutig gerichteten Shift-Vorschlag. Statt einer erfundenen Zahl steht hier die Leere, die das Produkt-Axiom verlangt.'}
        </p>

        {rec && (
          <>
            <hr
              className="ex-rule-soft"
              style={{ margin: '32px 0', height: 1, background: 'var(--ex-hairline-soft)', border: 0 }}
            />
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 40,
              }}
            >
              <StatCell
                label="Lead-Time"
                value={
                  leadDays !== null
                    ? leadDays >= 0
                      ? `+${leadDays} d`
                      : `${leadDays} d`
                    : '—'
                }
                caption={
                  leadDays !== null && leadDays >= 0
                    ? 'Notaufnahme vor Meldewesen'
                    : leadDays !== null
                      ? 'hinter Notaufnahme'
                      : 'Lag-Messung liegt nicht vor'
                }
              />
              <StatCell
                label="Horizont"
                value={`${horizonWeeks} W.`}
                caption={`kommende ${horizonWeeks} Wochen`}
              />
              <StatCell
                label="Alternativen"
                value={String(altCount)}
                caption="schwächer, aber gerichtet"
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
};

const StatCell: React.FC<{
  label: string;
  value: React.ReactNode;
  caption: string;
}> = ({ label, value, caption }) => (
  <div>
    <div className="ex-mono" style={{ color: 'var(--ex-ink-45)', marginBottom: 8 }}>
      {label}
    </div>
    <div
      className="ex-num"
      style={{
        fontFamily: 'var(--ex-serif)',
        fontSize: 40,
        fontVariationSettings: '"opsz" 144',
        letterSpacing: '-0.02em',
        lineHeight: 1,
      }}
    >
      {value}
    </div>
    <div
      style={{
        fontSize: 13,
        color: 'var(--ex-ink-60)',
        marginTop: 6,
        fontFamily: 'var(--ex-serif)',
        fontStyle: 'italic',
        fontVariationSettings: '"opsz" 36',
      }}
    >
      {caption}
    </div>
  </div>
);

// ---------- Candidates block (paper, alt-tinted strip) ------------------
const CandidatesBlock: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const calibrated = snapshot.modelStatus?.calibrationMode === 'calibrated';
  const candidates = snapshot.secondaryRecommendations ?? [];
  if (candidates.length === 0) return null;
  return (
    <div
      style={{
        marginTop: 72,
        padding: '40px 48px',
        margin: '72px -48px 0',
        background: 'var(--ex-paper-deep)',
      }}
    >
      <div style={{ maxWidth: 1344, margin: '0 auto' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 14,
            marginBottom: 24,
          }}
        >
          <span
            style={{
              fontFamily: 'var(--ex-serif)',
              fontStyle: 'italic',
              fontSize: 24,
              color: 'var(--ex-fired)',
              fontVariationSettings: '"opsz" 36',
            }}
          >
            §
          </span>
          <span
            className="ex-mono"
            style={{ color: 'var(--ex-ink-45)', letterSpacing: '.16em' }}
          >
            Weitere Kandidaten
          </span>
          <span
            style={{
              fontFamily: 'var(--ex-serif)',
              fontStyle: 'italic',
              fontSize: 14,
              color: 'var(--ex-ink-60)',
              marginLeft: 16,
              fontVariationSettings: '"opsz" 36',
            }}
          >
            nach{' '}
            {calibrated ? 'Konfidenz' : 'Signalstärke'}, absteigend
          </span>
        </div>
        <ul className="ex-roster" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {candidates.map((c: ShiftRecommendation, i: number) => {
            const confText = calibrated
              ? `${Math.round(c.confidence * 100)} %`
              : fmtSignalStrength(c.confidence);
            return (
              <RosterRow
                key={c.id}
                idx={`0${i + 1}`.slice(-2)}
                name={`${c.fromName} → ${c.toName}`}
                sub={c.why}
                value={<KEur eur={c.amountEur ?? ('—' as const)} />}
                direction={confText}
                dirClass={calibrated ? 'up' : 'flat'}
              />
            );
          })}
        </ul>
      </div>
    </div>
  );
};

// ---------- Root --------------------------------------------------------
export const DecisionSection: React.FC<Props> = ({ snapshot }) => (
  <>
    <SectionHeader
      numeral="§ I"
      kicker="Hauptakt · Empfehlung der Woche"
      title={
        <>
          Die <em>Entscheidung</em>.
        </>
      }
      stamp={snapshot.isoWeek}
    />
    <HeroBlock snapshot={snapshot} />
    <RationaleBlock snapshot={snapshot} />
    <CandidatesBlock snapshot={snapshot} />
  </>
);

export default DecisionSection;
