import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import type { CockpitSnapshot } from '../types';
import SectionHeader from './SectionHeader';
import { useForecastVintage } from '../useForecastVintage';

/**
 * § VI — Nächste Schritte.
 *
 * Schluss-Kachel-Set für einen Entscheider, der bis hier durchgescrollt
 * hat. Statt einen stillen Seiten-Fuß zu servieren, listen wir 2-4
 * konkrete, zustandsabhängige Aktionen auf:
 *   - "CSV hochladen" — wenn der Media-Plan noch nicht verbunden ist
 *   - "GELO-IT kontaktieren" — für den M2M-Key-Rollout
 *   - "Retraining abwarten" — wenn Drift erkannt wurde
 *   - "Forecast neu anfordern" — wenn das Signal stark ist aber EUR fehlen
 *   - "Data Office öffnen" — Standard-Diagnose-Einstieg
 *
 * Die Cards werden in priority-Reihenfolge gerendert; leer bleibt das
 * Panel nie, weil der Data-Office-Link als Default am Ende steht.
 */

interface Props {
  snapshot: CockpitSnapshot;
}

interface StepCard {
  id: string;
  kicker: string;
  title: string;
  body: string;
  cta: string;
  href?: string;
  external?: boolean;
  tone: 'action' | 'wait' | 'default';
  priority: number;
}

const STRONG_RISER_THRESHOLD = 0.15;

export const NextStepsSection: React.FC<Props> = ({ snapshot }) => {
  const { data: vintagePayload } = useForecastVintage(snapshot.virusTyp, 1);

  const hasStrongSignal = useMemo(() => {
    return snapshot.regions.some(
      (r) =>
        typeof r.delta7d === 'number' &&
        r.delta7d > STRONG_RISER_THRESHOLD &&
        r.decisionLabel !== 'TrainingPending',
    );
  }, [snapshot.regions]);

  const mediaPlanConnected = snapshot.mediaPlan?.connected === true;
  const driftDetected = vintagePayload?.reconciliation?.drift_detected === true;
  const hasRec = snapshot.primaryRecommendation !== null;
  const pendingRegions = snapshot.regions.filter(
    (r) => r.decisionLabel === 'TrainingPending',
  ).length;

  const cards = useMemo<StepCard[]>(() => {
    const cards: StepCard[] = [];

    if (!mediaPlanConnected) {
      cards.push({
        id: 'upload-csv',
        kicker: 'Pilot-Start · Woche 1',
        title: 'Erste GELO-CSV hochladen',
        body:
          'Eine Datei mit Wochenwerten (Spend + Sales + Reichweite) ' +
          'pro Produkt × Bundesland reicht, damit das Cockpit aus ' +
          'Prognose Rechenschaft macht. § IV füllt sich am Abend, ' +
          '§ II zeigt konkrete EUR-Shifts ab Woche 2.',
        cta: 'Data Office öffnen',
        href: '/cockpit/data',
        tone: 'action',
        priority: 100,
      });
      cards.push({
        id: 'm2m-api',
        kicker: 'Dauerbetrieb · nach Pilot',
        title: 'M2M-API an GELO-BI anbinden',
        body:
          'Wöchentliches CSV-Handschieben ist Bridge, nicht Ziel. Der ' +
          'POST-Endpoint nimmt die gleichen Zeilen als JSON aus dem ' +
          'GELO-BI-Stack direkt entgegen — ein API-Key-Austausch.',
        cta: 'data@peix.de',
        href: 'mailto:data@peix.de?subject=M2M-API-Key%20f%C3%BCr%20GELO',
        external: true,
        tone: 'action',
        priority: 90,
      });
    }

    if (driftDetected) {
      cards.push({
        id: 'drift-wait',
        kicker: 'Operationaler Hinweis',
        title: 'Drift-Warnung: nächsten Retraining-Zyklus abwarten',
        body:
          'Das Modell weicht systematisch vom Truth-Signal ab. Das ' +
          'nächste monatliche Retraining kalibriert nach; bis dahin ' +
          'sind Empfehlungen mit Vorsicht zu lesen. Der Cron läuft am ' +
          '1. des Monats um 07:10 UTC.',
        cta: 'Retraining-Status ansehen',
        href: '/cockpit/data',
        tone: 'wait',
        priority: 80,
      });
    }

    if (!hasRec && hasStrongSignal && !mediaPlanConnected) {
      cards.push({
        id: 'request-forecast',
        kicker: 'Wenn der Media-Plan anliegt',
        title: 'Forecast mit Budget-Anchor neu anfordern',
        body:
          'Das Wellen-Signal ist aktuell deutlich, aber ohne ' +
          'Media-Plan keine EUR-Empfehlung. Sobald der Plan im Data ' +
          'Office sitzt, reicht ein Refresh und § II zieht den ' +
          'prüfbaren Shift-Kandidaten.',
        cta: 'Cockpit neu laden',
        tone: 'wait',
        priority: 70,
      });
    }

    if (pendingRegions > 0) {
      cards.push({
        id: 'pending-training',
        kicker: 'Atlas-Abdeckung',
        title: `${pendingRegions} Bundesland${pendingRegions === 1 ? '' : 'ländern'} fehlt regionales Modell`,
        body:
          'Für diese Bundesländer liegt kein trainiertes regionales ' +
          'Panel vor — die Atlas-Kacheln stehen auf "Training pending". ' +
          'Mehr SURVSTAT-Tiefe oder das nächste Retraining mit breiterer ' +
          'Datenbasis füllt die Lücke.',
        cta: 'Truth-Coverage prüfen',
        href: '/cockpit/data',
        tone: 'wait',
        priority: 50,
      });
    }

    cards.push({
      id: 'data-office',
      kicker: 'Standard-Einstieg',
      title: 'Data Office öffnen',
      body:
        'Coverage-Heatmap, Upload-Panel, Import-Historie, M2M-Doku — ' +
        'das Betriebszentrum für alles, was unter dem Cockpit liegt.',
      cta: 'Zum Data Office',
      href: '/cockpit/data',
      tone: 'default',
      priority: 10,
    });

    // Wirkungsquantifizierung als sichtbarer Pilot-Meilenstein.
    // Ehrliche Versprechen: das wird quantifiziert, sobald GELO-Outcomes
    // 8 Wochen lang reingelaufen sind. Dem Pitch-Publikum macht das
    // den Roadmap-Moment greifbar, ohne dass das Tool heute schon eine
    // 'wir haben X % Media-Waste vermieden'-Zahl behaupten muss.
    cards.push({
      id: 'pilot-milestone',
      kicker: 'Pilot-Meilenstein · Woche 8',
      title: 'Erstes „Media-Waste vermieden"-Statement',
      body:
        'Sobald acht Wochen GELO-Sell-Out-Daten zurückgeflossen sind, ' +
        'rechnet § IV das erste belastbare Wirkungsdelta aus: wie viel ' +
        'Reichweite die Shifts gebracht haben, wo Empfehlungen geirrt ' +
        'haben, welche Prozent-Punkte Budget-Effizienz gewonnen wurden. ' +
        'Heute ein Versprechen, dann eine Zahl.',
      cta: 'Im Pitch-Deck als Meilenstein',
      tone: 'wait',
      priority: 30,
    });

    return cards.sort((a, b) => b.priority - a.priority).slice(0, 5);
  }, [
    mediaPlanConnected,
    driftDetected,
    hasRec,
    hasStrongSignal,
    pendingRegions,
  ]);

  return (
    <section className="instr-section" id="sec-next-steps">
      <SectionHeader
        numeral="VI"
        title="Nächste Schritte"
        subtitle={
          <>
            {cards.length} Handlung{cards.length === 1 ? '' : 'en'} · zustandsabhängig
          </>
        }
        primer={
          <>
            Alles was du gleich morgen anstoßen kannst, damit dieses
            Cockpit vom Demo-Asset zum operativen Werkzeug wird. Die
            Karten sind nach Hebel sortiert — oben der grösste Schritt
            Richtung Pilot-Go-Live.
          </>
        }
      />
      <div className="next-steps-grid">
        {cards.map((card) => {
          const content = (
            <>
              <div className="ns-kicker">{card.kicker}</div>
              <div className="ns-title">{card.title}</div>
              <p className="ns-body">{card.body}</p>
              <div className="ns-cta">
                {card.cta}
                <span className="ns-cta-arrow" aria-hidden>
                  →
                </span>
              </div>
            </>
          );
          if (card.href && card.external) {
            return (
              <a
                key={card.id}
                className={`next-step-card tone-${card.tone}`}
                href={card.href}
                target={card.href.startsWith('mailto:') ? undefined : '_blank'}
                rel="noreferrer"
              >
                {content}
              </a>
            );
          }
          if (card.href) {
            return (
              <Link
                key={card.id}
                className={`next-step-card tone-${card.tone}`}
                to={card.href}
              >
                {content}
              </Link>
            );
          }
          return (
            <div key={card.id} className={`next-step-card tone-${card.tone}`}>
              {content}
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default NextStepsSection;
