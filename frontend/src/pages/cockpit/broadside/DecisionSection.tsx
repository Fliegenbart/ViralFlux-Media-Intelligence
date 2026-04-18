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
        color: 'var(--ex-cream)',
        padding: '104px 88px 128px',
        // Pull up so there's no gap between the section-head strip
        // and this hero strip — one continuous dark block. Matches
        // the section-head's margin-bottom (120 px).
        margin: '-120px -88px 0',
      }}
    >
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* Kicker — single mono line, no dots */}
        <div
          style={{
            display: 'flex',
            gap: 32,
            alignItems: 'baseline',
            marginBottom: 72,
            flexWrap: 'wrap',
          }}
        >
          <span className="ex-mono" style={{ color: 'var(--ex-stage-45)' }}>
            Empfehlung der Woche
          </span>
          <span className="ex-mono" style={{ color: 'var(--ex-stage-45)' }}>
            {horizonLabel}
          </span>
          <MethodBadge calibrated={calibrated} />
        </div>

        {/* Lede + monument side by side */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 96,
            alignItems: 'end',
          }}
        >
          <div>
            {rec ? (
              <h1
                style={{
                  fontFamily: 'var(--ex-serif)',
                  fontWeight: 300,
                  fontSize: 'clamp(44px, 5vw, 80px)',
                  lineHeight: 1.06,
                  letterSpacing: '-0.025em',
                  margin: '0 0 40px',
                  maxWidth: '14ch',
                }}
              >
                Verschiebe{' '}
                <em
                  style={{
                    fontStyle: 'italic',
                    color: 'var(--ex-cream)',
                    fontWeight: 300,
                  }}
                >
                  {fmtEurCompactOrDash(rec.amountEur)}
                </em>
                <br />
                aus{' '}
                <em
                  style={{
                    fontStyle: 'italic',
                    color: 'var(--ex-cream)',
                    fontWeight: 300,
                  }}
                >
                  {rec.fromName}
                </em>{' '}
                nach{' '}
                <em
                  style={{
                    fontStyle: 'italic',
                    color: 'var(--ex-fired)',
                    fontWeight: 300,
                  }}
                >
                  {rec.toName}
                </em>
                .
              </h1>
            ) : (
              <h1
                style={{
                  fontFamily: 'var(--ex-serif)',
                  fontWeight: 300,
                  fontSize: 'clamp(44px, 5vw, 80px)',
                  lineHeight: 1.06,
                  letterSpacing: '-0.025em',
                  margin: '0 0 40px',
                }}
              >
                Aktuell{' '}
                <em
                  style={{
                    fontStyle: 'italic',
                    color: 'var(--ex-fired)',
                    fontWeight: 300,
                  }}
                >
                  kein Shift-Vorschlag
                </em>
                .
              </h1>
            )}

            <p
              style={{
                fontFamily: 'var(--ex-sans)',
                fontWeight: 400,
                fontSize: 18,
                lineHeight: 1.7,
                color: 'var(--ex-stage-60)',
                maxWidth: '58ch',
                margin: 0,
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
              style={{
                color: 'var(--ex-stage-45)',
                marginBottom: 32,
              }}
            >
              Konfidenz · {calibrated ? 'kalibriert' : 'heuristisch'}
            </div>
            <div
              className="ex-punk-monument"
              style={{ color: 'var(--ex-cream)' }}
            >
              {rec && calibrated
                ? Math.round(rec.confidence * 100)
                : rec
                  ? fmtSignalStrength(rec.confidence)
                  : '—'}
              {rec && calibrated && (
                <span className="ex-punk-monument__unit">%</span>
              )}
            </div>

            <div style={{ marginTop: 64, maxWidth: 420 }}>
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
    <div style={{ marginTop: 160 }}>
      <div
        style={{
          marginBottom: 40,
        }}
      >
        <span className="ex-mono" style={{ color: 'var(--ex-ink-45)' }}>
          Begründung
        </span>
      </div>
      <div className="ex-reading-column">
        <p
          style={{
            fontFamily: 'var(--ex-serif)',
            fontWeight: 300,
            fontSize: 26,
            lineHeight: 1.5,
            margin: 0,
            color: 'var(--ex-ink)',
            letterSpacing: '-0.015em',
          }}
        >
          {rec
            ? rec.why
            : 'In dieser Woche ergibt die Modellarbeit keinen eindeutig gerichteten Shift-Vorschlag. Statt einer erfundenen Zahl steht hier die Leere, die das Produkt-Axiom verlangt.'}
        </p>
      </div>

      {rec && (
        <div
          style={{
            marginTop: 96,
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 64,
            maxWidth: 880,
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
      )}
    </div>
  );
};

const StatCell: React.FC<{
  label: string;
  value: React.ReactNode;
  caption: string;
}> = ({ label, value, caption }) => (
  <div>
    <div className="ex-mono" style={{ color: 'var(--ex-ink-45)', marginBottom: 16 }}>
      {label}
    </div>
    <div
      className="ex-num"
      style={{
        fontFamily: 'var(--ex-serif)',
        fontWeight: 200,
        fontSize: 56,
        letterSpacing: '-0.03em',
        lineHeight: 1,
      }}
    >
      {value}
    </div>
    <div
      style={{
        fontSize: 14,
        color: 'var(--ex-ink-60)',
        marginTop: 14,
        fontFamily: 'var(--ex-sans)',
        lineHeight: 1.55,
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
    <div style={{ marginTop: 160 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 28,
          marginBottom: 40,
        }}
      >
        <span className="ex-mono" style={{ color: 'var(--ex-ink-45)' }}>
          Weitere Kandidaten
        </span>
        <span
          style={{
            fontSize: 14,
            color: 'var(--ex-ink-60)',
            fontFamily: 'var(--ex-sans)',
          }}
        >
          nach {calibrated ? 'Konfidenz' : 'Signalstärke'}, absteigend
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
  );
};

// ---------- Root --------------------------------------------------------
export const DecisionSection: React.FC<Props> = ({ snapshot }) => {
  const rec = snapshot.primaryRecommendation;
  const calibrated = snapshot.modelStatus?.calibrationMode === 'calibrated';
  const bestLag = snapshot.modelStatus?.lead?.bestLagDays ?? null;

  const badges: Array<{ label: string; tone: 'go' | 'watch' | 'neutral' | 'solid' }> = [];
  if (rec) {
    badges.push({ label: 'Hauptakt', tone: 'solid' });
  } else {
    badges.push({ label: 'Kein Shift', tone: 'watch' });
  }
  badges.push({
    label: calibrated ? 'Kalibriert' : 'Heuristisch',
    tone: calibrated ? 'go' : 'neutral',
  });
  if (bestLag !== null) {
    badges.push({
      label:
        bestLag >= 0
          ? `Lead +${bestLag} d`
          : `Lag ${bestLag} d`,
      tone: bestLag >= 0 ? 'go' : 'watch',
    });
  }

  return (
    <>
      <SectionHeader
        numeral="§ I"
        kicker="Empfehlung der Woche"
        title={
          <>
            Die <em>Entscheidung</em>
          </>
        }
        stamp={snapshot.isoWeek}
        badges={badges}
      />
      <HeroBlock snapshot={snapshot} />
      <RationaleBlock snapshot={snapshot} />
      <CandidatesBlock snapshot={snapshot} />
    </>
  );
};

export default DecisionSection;
