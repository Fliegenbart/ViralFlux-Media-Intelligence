import React, { useMemo } from 'react';
import type { CockpitSnapshot } from '../types';

/**
 * ExecutiveHero — 30-Sekunden-Überblick ganz oben, zwischen Status-Strip
 * und § I. Drei Kacheln, die ein GELO-Marketing-Manager ohne ML-Background
 * sofort versteht: wo sind wir in der Saison, was sagt der Atlas gerade,
 * wie würde ein Euro-Shift aussehen.
 *
 * Kein Fake-Budget: die Demo-Zahl kommt aus einer klar als "Demo"
 * markierten Formel auf Basis der echten Top-Risers. Sobald der
 * Media-Plan verbunden ist, ersetzen echte EUR-Werte die Demo-Zahlen
 * und der "Demo"-Tag verschwindet.
 */

interface Props {
  snapshot: CockpitSnapshot;
}

const STRONG_RISER_THRESHOLD = 0.15;
const DEMO_ASSUMED_WEEKLY_BUDGET = 100_000;

// Season phase heuristic: ISO-Week ranges — DE-spezifisch, ja.
function detectSeasonPhase(isoWeek: string): {
  label: string;
  tone: 'peak' | 'shoulder' | 'off';
  note: string;
} {
  const m = isoWeek.match(/\d+/);
  const kw = m ? parseInt(m[0], 10) : 0;
  if (kw >= 40 || kw <= 10) {
    return {
      label: 'Peak-Saison',
      tone: 'peak',
      note: 'Wellen-Fenster aktiv. Empfehlungen haben größten Hebel.',
    };
  }
  if ((kw >= 11 && kw <= 17) || (kw >= 36 && kw <= 39)) {
    return {
      label: 'Übergangs-Saison',
      tone: 'shoulder',
      note: 'Welle baut ab oder auf. Signal vorhanden, aber Trigger vorsichtig.',
    };
  }
  return {
    label: 'Post-Saison · Sparmodus',
    tone: 'off',
    note:
      'Aktuell keine Welle. Das Tool ruht bewusst: keine Empfehlung, kein Budget-Shift — das ist Kostendisziplin, kein Stillstand.',
  };
}

export const ExecutiveHero: React.FC<Props> = ({ snapshot }) => {
  const phase = useMemo(() => detectSeasonPhase(snapshot.isoWeek), [snapshot.isoWeek]);

  const topRiser = useMemo(() => {
    return [...snapshot.regions]
      .filter(
        (r) =>
          typeof r.delta7d === 'number' &&
          r.decisionLabel !== 'TrainingPending',
      )
      .sort((a, b) => (b.delta7d ?? 0) - (a.delta7d ?? 0))[0];
  }, [snapshot.regions]);

  const topFaller = useMemo(() => {
    return [...snapshot.regions]
      .filter(
        (r) =>
          typeof r.delta7d === 'number' &&
          r.decisionLabel !== 'TrainingPending',
      )
      .sort((a, b) => (a.delta7d ?? 0) - (b.delta7d ?? 0))[0];
  }, [snapshot.regions]);

  const hasStrongSignal =
    topRiser && typeof topRiser.delta7d === 'number' && topRiser.delta7d > STRONG_RISER_THRESHOLD;

  const mediaConnected = snapshot.mediaPlan?.connected === true;

  const demoShiftEur =
    topRiser && topFaller && typeof topRiser.delta7d === 'number'
      ? Math.round((DEMO_ASSUMED_WEEKLY_BUDGET * Math.min(0.35, topRiser.delta7d * 0.4)) / 1_000) * 1_000
      : null;

  const virusLabel = snapshot.virusLabel || snapshot.virusTyp;

  return (
    <section className="exec-hero" id="sec-exec-hero">
      <div className="exec-hero-inner">
        <div className={`exec-cell phase-${phase.tone}`}>
          <div className="exec-cell-kicker">Saison-Phase</div>
          <div className="exec-cell-value">{phase.label}</div>
          <div className="exec-cell-note">{phase.note}</div>
        </div>

        <div className={`exec-cell signal-${hasStrongSignal ? 'strong' : 'quiet'}`}>
          <div className="exec-cell-kicker">Atlas sagt gerade</div>
          {hasStrongSignal && topRiser ? (
            <>
              <div className="exec-cell-value">
                Welle vorn in{' '}
                <b>{topRiser.name}</b>
                <span className="exec-delta">
                  {' '}+{Math.round((topRiser.delta7d ?? 0) * 100)} % · 7 d
                </span>
              </div>
              <div className="exec-cell-note">
                {virusLabel}-Aktivität steigt hier merklich — Region in
                der Top-Riser-Liste des Atlas.
              </div>
            </>
          ) : (
            <>
              <div className="exec-cell-value">Kein Wellen-Trigger</div>
              <div className="exec-cell-note">
                Alle 16 Bundesländer unterhalb des Aktivierungs-Schwellwerts.
                Kein Shift diese Woche; das Tool schont dein Budget.
              </div>
            </>
          )}
        </div>

        <div className={`exec-cell budget-${mediaConnected ? 'connected' : 'demo'}`}>
          <div className="exec-cell-kicker">
            {mediaConnected ? 'Empfohlener Shift' : 'Demo-Szene · 100k € Wochenbudget'}
          </div>
          {demoShiftEur && hasStrongSignal ? (
            <>
              <div className="exec-cell-value exec-eur">
                {demoShiftEur.toLocaleString('de-DE')} €
                <span className="exec-direction">
                  {' '}{topFaller?.code} → {topRiser?.code}
                </span>
              </div>
              <div className="exec-cell-note">
                {mediaConnected
                  ? `Shift-Vorschlag des Modells für diese Woche.`
                  : `So würde das Tool bei 100 k € Wochenbudget shiften. Echte EUR sobald GELO-Media-Plan angebunden.`}
              </div>
            </>
          ) : (
            <>
              <div className="exec-cell-value exec-eur exec-eur-off">0 €</div>
              <div className="exec-cell-note">
                {hasStrongSignal
                  ? 'Shift-Betrag wartet auf Media-Plan-Anbindung.'
                  : 'Kein Shift — Tool ruht bis zum nächsten Wellen-Trigger.'}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
};

export default ExecutiveHero;
