import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import type { CockpitSnapshot } from '../types';
import SectionHeader from './SectionHeader';
import { useForecastVintage } from '../useForecastVintage';
import { sellOutWeeks } from './snapshotAccessors';

/**
 * § VI — Nächste Schritte.
 *
 * Schluss-Kachel-Set für einen Entscheider, der bis hier durchgescrollt
 * hat. Statt einen stillen Seiten-Fuß zu servieren, listen wir 2-4
 * konkrete, zustandsabhängige Aktionen auf:
 *   - "CSV hochladen" — wenn noch keine Sell-Out-Wochen verbunden sind
 *   - "M2M-API anbinden" — wenn manuelle Imports laufen
 *   - "Retraining abwarten" — wenn Drift erkannt wurde
 *   - "Forecast neu rechnen" — wenn neue Daten oder ein starkes Signal anliegen
 *   - "Data Office öffnen" — Standard-Einstieg ins Kalibrierungsfenster
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

  const dataWeeks = sellOutWeeks(snapshot);
  const driftDetected = vintagePayload?.reconciliation?.drift_detected === true;
  const hasRec = snapshot.primaryRecommendation !== null;
  const pendingRegions = snapshot.regions.filter(
    (r) => r.decisionLabel === 'TrainingPending',
  ).length;

  const cards = useMemo<StepCard[]>(() => {
    const cards: StepCard[] = [];

    if (dataWeeks <= 0) {
      cards.push({
        id: 'upload-csv',
        kicker: 'Pilot-Start',
        title: 'Erste GELO-CSV hochladen',
        body: 'Drei Monate Verkaufsdaten machen das Modell empfehlungsfähig.',
        cta: 'Data Office öffnen',
        href: '/cockpit/data',
        tone: 'action',
        priority: 120,
      });
    }

    if (dataWeeks > 0 && dataWeeks < 12) {
      cards.push({
        id: 'm2m-api',
        kicker: 'Dauerbetrieb',
        title: 'M2M-API anbinden',
        body:
          'Damit der Forecast jede Nacht von selbst auf eure aktuellen ' +
          'Sales läuft.',
        cta: 'Endpoint zeigen',
        href: '/cockpit/data',
        tone: 'action',
        priority: 90,
      });
    }

    if ((hasRec || hasStrongSignal) && dataWeeks > 0) {
      cards.push({
        id: 'recompute-sales-anchor',
        kicker: 'Neue Daten',
        title: 'Forecast mit Sales-Anchor neu rechnen',
        body:
          'Wenn neue GELO-Daten anliegen, rechnen wir Signal und Media-Gates ' +
          'gegen eure Realität neu.',
        cta: 'Neu rechnen',
        tone: 'action',
        priority: dataWeeks >= 12 ? 110 : 70,
      });
    }

    if (dataWeeks >= 12) {
      cards.push({
        id: 'budget-efficiency',
        kicker: 'Auswertung',
        title: 'Erste belastbare Budget-Effizienz-Auswertung',
        body:
          'Zwölf Wochen Sell-Out reichen, um erste Shift-Kandidaten gegen ' +
          'echte Outcomes zu prüfen.',
        cta: 'Auswertung öffnen',
        href: '/cockpit/data',
        tone: 'action',
        priority: 100,
      });
    }

    if (driftDetected) {
      cards.push({
        id: 'drift-wait',
        kicker: 'Operationaler Hinweis',
        title: 'Drift-Warnung: nächsten Retraining-Zyklus abwarten',
        body:
          'Das Modell weicht systematisch vom Vergleichssignal ab. Das ' +
          'nächste monatliche Retraining kalibriert nach; bis dahin ' +
          'sind Empfehlungen mit Vorsicht zu lesen. Der Cron läuft am ' +
          '1. des Monats um 07:10 UTC.',
        cta: 'Retraining-Status ansehen',
        href: '/cockpit/data',
        tone: 'wait',
        priority: 80,
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
        cta: 'Datenabdeckung prüfen',
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

    return cards.sort((a, b) => b.priority - a.priority).slice(0, 5);
  }, [
    dataWeeks,
    driftDetected,
    hasRec,
    hasStrongSignal,
    pendingRegions,
  ]);

  return (
    <section className="instr-section" id="sec-next-steps">
      <SectionHeader
        numeral="VII"
        title="Nächste Schritte"
        subtitle={
          <>
            {cards.length} Handlung{cards.length === 1 ? '' : 'en'} · zustandsabhängig
          </>
        }
        primer={
          <>
            Alles was du gleich morgen anstoßen kannst, damit dieses
            Cockpit vom Review-Werkzeug zum operativen Werkzeug wird. Die
            Karten sind nach Hebel sortiert — oben der größte Schritt
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
                className={`next-step-card tone-${card.tone}${card.id === 'upload-csv' ? ' is-primary' : ''}`}
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
                className={`next-step-card tone-${card.tone}${card.id === 'upload-csv' ? ' is-primary' : ''}`}
                to={card.href}
              >
                {content}
              </Link>
            );
          }
          return (
            <div key={card.id} className={`next-step-card tone-${card.tone}${card.id === 'upload-csv' ? ' is-primary' : ''}`}>
              {content}
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default NextStepsSection;
