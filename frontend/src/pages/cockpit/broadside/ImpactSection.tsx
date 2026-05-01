import React from 'react';
import type { CockpitSnapshot } from '../types';
import { fmtEurCompactOrDash } from '../format';
import { useImpact } from '../useImpact';
import SectionHeader from './SectionHeader';
import type { GateTone } from './SectionHeader';

/**
 * § IV — Wirkung & Feedback-Loop.
 *
 * Instrumentation-Redesign 2026-04-18.
 *
 * Layout:
 *   [Monument-Row] — 3 Zellen, hairline-getrennt, mit thin-weight-
 *   Monument-Zahlen bei 120 px
 *     · "Empfehlungen ausgegeben" — Anzahl aller Records
 *     · "Real umgesetzt" — aus Outcome-Pipeline
 *     · "Mit Outcome verknüpft" — aus Outcome-Pipeline (mit / Total)
 *   [Impact-Log] — Tabellen-Artifact der letzten Empfehlungen
 *   Dash (honest-by-default), wenn Pipeline nicht angebunden.
 */

interface Props {
  snapshot: CockpitSnapshot;
}

export const ImpactSection: React.FC<Props> = ({ snapshot }) => {
  const { data: impact } = useImpact({ virusTyp: snapshot.virusTyp });

  const pipeline = impact?.outcomePipeline ?? null;
  const connected = pipeline?.connected ?? false;

  const recsIssued = pipeline?.mediaOutcomeRecords ?? null;
  const actuallyImplemented = pipeline?.outcomeObservations ?? null;
  const outcomesLinked = pipeline?.holdoutGroupsDefined ?? null;

  const mediaConnected = snapshot.mediaPlan?.connected === true;

  const gateLabel = mediaConnected ? 'Sales loop · connected' : 'Sales loop · awaiting data';
  const gateTone: GateTone = mediaConnected ? 'go' : 'watch';

  // Build log rows — synthesised from recent secondary recommendations.
  // Real data path would come from pipeline records; for the pitch we
  // show the primary + secondaries with honest-by-default dashes for
  // outcome columns when there is no outcome feed.
  type LogRow = {
    week: string;
    rec: string;
    impl: 'ok' | 'partial' | 'na';
    implLabel: string;
    outcome: 'ok' | 'partial' | 'na';
    outcomeLabel: string;
    note: string;
  };

  const logRows: LogRow[] = [];
  if (snapshot.primaryRecommendation) {
    const rec = snapshot.primaryRecommendation;
    logRows.push({
      week: snapshot.isoWeek.replace('KW', '').trim(),
      rec: `${fmtEurCompactOrDash(rec.amountEur)} ${rec.fromName} → ${rec.toName}`,
      impl: mediaConnected ? 'partial' : 'na',
      implLabel: mediaConnected ? 'Teilweise' : '—',
      outcome: 'na',
      outcomeLabel: '—',
      note: mediaConnected ? 'Plan-Anbindung vorhanden' : 'kein Media-Plan verbunden',
    });
  }
  (snapshot.secondaryRecommendations ?? []).slice(0, 3).forEach((rec) => {
    logRows.push({
      week: snapshot.isoWeek.replace('KW', '').trim(),
      rec: `${fmtEurCompactOrDash(rec.amountEur)} ${rec.fromName} → ${rec.toName}`,
      impl: 'na',
      implLabel: '—',
      outcome: 'na',
      outcomeLabel: '—',
      note: connected
        ? 'Outcome-Feed aggregiert'
        : 'Plan noch nicht angebunden',
    });
  });

  return (
    <section className="instr-section" id="sec-impact">
      <SectionHeader
        numeral="VI"
        title="Wirkung & Feedback-Loop"
        subtitle={
          <>
            Rückblick · Honest-by-default · Wo nichts, da Strich.
          </>
        }
        gate={{ label: gateLabel, tone: gateTone }}
        primer={
          <>
            „Hatten wir recht?" — hier wird jede Empfehlung gegen den
            tatsächlichen Outcome der Folgewoche gelegt. Das Panel ist
            <b> vollständig verdrahtet</b> (Ingest-Endpoint, Match-Key,
            Reconciliation-Layout stehen); es wartet auf die erste
            CSV oder den ersten M2M-Push aus GELO, um aus Prognose
            Rechenschaft zu machen. Bis echte GELO-Salesdaten anliegen,
            bleibt Wirkung offen: Dieses Panel ist der Prüfpfad, nicht der
            Beweis.
          </>
        }
      />

      {!connected ? (
        <div className="impact-unlock-timeline">
          <div className="unlock-row">
            <div className="unlock-chip ready">
              <span className="unlock-label">Woche 0 · heute</span>
              <span className="unlock-value">Ingest bereit</span>
              <span className="unlock-note">
                Endpoint + Schema + Cockpit-Rendering warten auf erste
                Zeile.
              </span>
            </div>
            <div className="unlock-chip pending">
              <span className="unlock-label">Woche +1 nach 1. Upload</span>
              <span className="unlock-value">Erste Verknüpfung</span>
              <span className="unlock-note">
                Die Empfehlung dieser Woche bekommt ihren ersten
                Outcome-Partner — § IV füllt sich sofort.
              </span>
            </div>
            <div className="unlock-chip pending">
              <span className="unlock-label">Woche +4 nach CSV-Strecke</span>
              <span className="unlock-value">Trend sichtbar</span>
              <span className="unlock-note">
                Reichweiten-Lift, Fehl-Shifts, Hit-Rate werden aus vier
                Wochen Daten erstmals statistisch lesbar.
              </span>
            </div>
          </div>
        </div>
      ) : null}

      <div className="impact-row">
        <div className="impact-cell">
          <div className="label">Empfehlungen ausgegeben</div>
          <div className="monument">
            {recsIssued !== null ? recsIssued : <span className="dash">—</span>}
          </div>
          <div className="sub">
            {connected
              ? `über ${pipeline?.importBatches ?? 0} Import-Batches`
              : 'Outcome-Pipeline nicht verbunden'}
          </div>
        </div>

        <div className="impact-cell">
          <div className="label">Real umgesetzt</div>
          <div className="monument">
            {actuallyImplemented !== null ? (
              actuallyImplemented
            ) : (
              <span className="dash">—</span>
            )}
          </div>
          <div className="sub">
            {connected
              ? 'bestätigte Umsetzung durch den Media-Plan'
              : 'GELO-Attribution fehlt'}
          </div>
        </div>

        <div className="impact-cell">
          <div className="label">Mit Outcome verknüpft</div>
          <div className="monument">
            {outcomesLinked !== null ? (
              <>
                {outcomesLinked}
                {recsIssued !== null && (
                  <span className="dash"> / {recsIssued}</span>
                )}
              </>
            ) : (
              <span className="dash">—</span>
            )}
          </div>
          <div className="sub">
            {connected
              ? 'Holdout-Gruppen mit Attribution'
              : 'Plan-Anbindung ausstehend'}
          </div>
        </div>
      </div>

      {logRows.length > 0 && (
        <div className="impact-log">
          <div className="impact-log-row head">
            <span className="wk">KW</span>
            <span className="rec">Empfehlung</span>
            <span className="status">Umsetzung</span>
            <span className="status">Outcome</span>
            <span>Notiz</span>
          </div>
          {logRows.map((row, i) => (
            <div className="impact-log-row" key={i}>
              <span className="wk">{row.week}</span>
              <span className="rec">{row.rec}</span>
              <span className={`status ${row.impl}`}>{row.implLabel}</span>
              <span className={`status ${row.outcome}`}>{row.outcomeLabel}</span>
              <span className="dash-note">{row.note}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default ImpactSection;
