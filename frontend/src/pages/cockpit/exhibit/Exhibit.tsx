import React from 'react';
import type { CockpitSnapshot, ShiftRecommendation } from '../types';
import { fmtEurCompactOrDash, fmtSignalStrength } from '../format';
import Hero from './Hero';
import {
  Dash,
  KEur,
  MarginNote,
  SectionHead,
  RosterRow,
} from './primitives';

/**
 * Exhibit — the single main screen.
 *
 * Composition (top to bottom):
 *   TopChrome  — three-column editorial masthead
 *   Hero        — the full-bleed stage (Verschiebe €X aus A nach B)
 *   Rationale   — § 01 Begründung (3-sentence pull quote + 3 stats)
 *   Candidates  — § 02 Weitere Kandidaten (roster on alt paper)
 *   FootRail    — edition stamp (Ausgabe / Redaktionsschluss / Nächste)
 *
 * Drawer dock and drawers live outside this component — the shell
 * composes them.
 */

interface ExhibitProps {
  snapshot: CockpitSnapshot;
  onOpenDrawer: (id: 'atlas' | 'forecast' | 'impact') => void;
}

// --------------------------------------------------------------
// TopChrome — three-column editorial masthead
// --------------------------------------------------------------
const TopChrome: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const generated = snapshot.generatedAt ? new Date(snapshot.generatedAt) : null;
  const editionShort = generated
    ? generated
        .toLocaleDateString('de-DE', { day: '2-digit', month: 'short', year: '2-digit' })
        .toUpperCase()
        .replace(/\./g, '')
        .replace(/ /g, '·')
    : '—';
  return (
    <div className="ex-chrome">
      <div className="ex-chrome-left ex-mono">
        <span>ViralFlux</span>
        <span style={{ color: 'var(--ex-ink-30)' }}>·</span>
        <span>peix / {snapshot.client}</span>
      </div>
      <div className="ex-chrome-center ex-mono">
        <span
          className="ex-serif-italic"
          style={{ fontSize: 14, color: 'var(--ex-ink-60)' }}
        >
          Wochenausgabe ·{' '}
        </span>
        <span>{snapshot.isoWeek}</span>
        <span style={{ margin: '0 10px', color: 'var(--ex-ink-30)' }}>·</span>
        <span>{snapshot.virusLabel}</span>
      </div>
      <div className="ex-chrome-right ex-mono">
        <span>ED. {editionShort}</span>
      </div>
    </div>
  );
};

// --------------------------------------------------------------
// § 01 Begründung
// --------------------------------------------------------------
const RationaleSection: React.FC<{
  snapshot: CockpitSnapshot;
}> = ({ snapshot }) => {
  const rec = snapshot.primaryRecommendation;
  const horizonWeeks = Math.max(
    1,
    Math.round((snapshot.modelStatus?.horizonDays ?? 7) / 7),
  );
  const leadDays = snapshot.modelStatus?.lead?.bestLagDays ?? null;
  const altCount = snapshot.secondaryRecommendations?.length ?? 0;
  if (!rec) {
    return (
      <section className="ex-section">
        <SectionHead
          idx="§ 01"
          title="Begründung."
          titleItalic="Noch keine Empfehlung."
        />
        <div className="ex-with-margin" style={{ padding: 0 }}>
          <div />
          <div style={{ maxWidth: 760 }}>
            <p
              className="ex-serif-italic"
              style={{ fontSize: 26, lineHeight: 1.35, margin: 0, color: 'var(--ex-ink)' }}
            >
              In dieser Woche ergibt die Modellarbeit keinen eindeutig
              gerichteten Shift-Vorschlag. Statt einer erfundenen Zahl
              steht hier die Leere, die das Produkt-Axiom verlangt.
            </p>
          </div>
          <div />
        </div>
      </section>
    );
  }
  return (
    <section className="ex-section">
      <SectionHead
        idx="§ 01"
        title="Begründung."
        titleItalic="In drei Sätzen."
        leftNote={{
          idx: 'M.01',
          text:
            'Die Welle verlagert sich. Wer zuletzt im abklingenden Gebiet geplant hat, planiert jetzt einen fallenden Boden.',
        }}
      />
      <div className="ex-with-margin" style={{ padding: 0 }}>
        <div />
        <div style={{ maxWidth: 760 }}>
          <p
            className="ex-serif-italic"
            style={{
              fontSize: 26,
              lineHeight: 1.35,
              margin: 0,
              color: 'var(--ex-ink)',
            }}
          >
            {rec.why}
          </p>
          <hr className="ex-rule-soft" style={{ margin: '32px 0' }} />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 40,
            }}
          >
            <div>
              <div
                className="ex-mono"
                style={{ color: 'var(--ex-ink-45)', marginBottom: 8 }}
              >
                Lead-Time
              </div>
              <div className="ex-num" style={{ fontSize: 36 }}>
                {leadDays !== null
                  ? leadDays >= 0
                    ? `+${leadDays} d`
                    : `${leadDays} d`
                  : '—'}
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: 'var(--ex-ink-60)',
                  marginTop: 4,
                }}
              >
                {leadDays !== null && leadDays >= 0
                  ? 'Notaufnahme vor Meldewesen'
                  : leadDays !== null
                    ? 'hinter Notaufnahme'
                    : 'Lag-Messung liegt nicht vor'}
              </div>
            </div>
            <div>
              <div
                className="ex-mono"
                style={{ color: 'var(--ex-ink-45)', marginBottom: 8 }}
              >
                Horizont
              </div>
              <div className="ex-num" style={{ fontSize: 36 }}>
                {horizonWeeks} W.
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: 'var(--ex-ink-60)',
                  marginTop: 4,
                }}
              >
                kommende{horizonWeeks === 1 ? '' : ''} {horizonWeeks}{' '}
                Wochen
              </div>
            </div>
            <div>
              <div
                className="ex-mono"
                style={{ color: 'var(--ex-ink-45)', marginBottom: 8 }}
              >
                Alternativen
              </div>
              <div className="ex-num" style={{ fontSize: 36 }}>
                {altCount}
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: 'var(--ex-ink-60)',
                  marginTop: 4,
                }}
              >
                schwächer, aber gerichtet
              </div>
            </div>
          </div>
        </div>
        <div />
      </div>
    </section>
  );
};

// --------------------------------------------------------------
// § 02 Weitere Kandidaten (roster)
// --------------------------------------------------------------
const CandidatesSection: React.FC<{
  snapshot: CockpitSnapshot;
}> = ({ snapshot }) => {
  const calibrated = snapshot.modelStatus?.calibrationMode === 'calibrated';
  const candidates = snapshot.secondaryRecommendations ?? [];
  if (candidates.length === 0) {
    return null;
  }
  return (
    <section className="ex-section alt">
      <SectionHead
        idx="§ 02"
        title="Weitere Kandidaten."
        titleItalic="nach Konfidenz, absteigend."
      />
      <div className="ex-with-margin" style={{ padding: 0 }}>
        <div>
          <MarginNote
            idx="R.01"
            text={
              <>
                Ein Kandidat ohne verbundenen Plan erscheint als{' '}
                <span className="ex-dash">—</span>, niemals als
                Phantom-Betrag. Vorsatz, nicht Mangel.
              </>
            }
          />
        </div>
        <div>
          <ul className="ex-roster">
            {candidates.map((c: ShiftRecommendation, i: number) => {
              const confText = calibrated
                ? `${Math.round(c.confidence * 100)} %`
                : fmtSignalStrength(c.confidence);
              const dirClass: 'up' | 'down' | 'flat' = calibrated
                ? 'up'
                : 'flat';
              return (
                <RosterRow
                  key={c.id}
                  idx={`0${i + 1}`.slice(-2)}
                  name={`${c.fromName} → ${c.toName}`}
                  sub={c.why}
                  value={<KEur eur={c.amountEur ?? ('—' as const)} />}
                  direction={confText}
                  dirClass={dirClass}
                />
              );
            })}
          </ul>
        </div>
        <div />
      </div>
    </section>
  );
};

// --------------------------------------------------------------
// FootRail — edition stamp
// --------------------------------------------------------------
const FootRail: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const generated = snapshot.generatedAt ? new Date(snapshot.generatedAt) : null;
  const generatedLabel = generated
    ? generated.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      })
    : '—';
  const generatedTime = generated
    ? `${generated.toLocaleTimeString('de-DE', {
        hour: '2-digit',
        minute: '2-digit',
      })} MEZ`
    : '—';
  // Parse week number from "KW 16 / 2026" or similar
  const currentKw = parseInt(snapshot.isoWeek.match(/\d+/)?.[0] || '0', 10);
  const nextKw = currentKw + 1;
  return (
    <section className="ex-section" style={{ paddingTop: 40, paddingBottom: 40 }}>
      <div className="ex-with-margin" style={{ padding: 0 }}>
        <div className="ex-edition-mark">Redaktion</div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 48,
            alignItems: 'baseline',
          }}
        >
          <div>
            <div
              className="ex-mono"
              style={{ color: 'var(--ex-ink-45)', marginBottom: 6 }}
            >
              Ausgabe
            </div>
            <div className="ex-serif-italic" style={{ fontSize: 18 }}>
              ViralFlux · Cockpit · {snapshot.isoWeek}
            </div>
          </div>
          <div>
            <div
              className="ex-mono"
              style={{ color: 'var(--ex-ink-45)', marginBottom: 6 }}
            >
              Redaktionsschluss
            </div>
            <div className="ex-num" style={{ fontSize: 18 }}>
              {generatedLabel} · {generatedTime}
            </div>
          </div>
          <div>
            <div
              className="ex-mono"
              style={{ color: 'var(--ex-ink-45)', marginBottom: 6 }}
            >
              Nächste
            </div>
            <div className="ex-num" style={{ fontSize: 18 }}>
              KW {nextKw} · Fr 09:00
            </div>
          </div>
        </div>
        <div className="ex-edition-mark" style={{ textAlign: 'right' }}>
          {snapshot.primaryRecommendation ? (
            <span>
              {fmtEurCompactOrDash(snapshot.primaryRecommendation.amountEur)} ·{' '}
              {snapshot.primaryRecommendation.fromName} →{' '}
              {snapshot.primaryRecommendation.toName}
            </span>
          ) : (
            <Dash note="kein Shift diese Woche" />
          )}
        </div>
      </div>
    </section>
  );
};

// --------------------------------------------------------------
// Exhibit root
// --------------------------------------------------------------
export const Exhibit: React.FC<ExhibitProps> = ({ snapshot, onOpenDrawer }) => (
  <div className="peix-exhibit">
    <div className="ex-page">
      <TopChrome snapshot={snapshot} />
      <Hero snapshot={snapshot} onOpen={onOpenDrawer} />
      <RationaleSection snapshot={snapshot} />
      <CandidatesSection snapshot={snapshot} />
      <FootRail snapshot={snapshot} />
    </div>
  </div>
);

export default Exhibit;
