import React from 'react';
import { motion } from 'framer-motion';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot } from './types';
import type { ImpactPayload, ImpactOutcomePipeline } from './impactTypes';
import { fmtDate, fmtSignalStrength } from './format';
import { useImpact } from './useImpact';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 04 — "Wirkung & Feedback-Loop".
 *
 * Closes the cockpit narrative: we showed a ranking on tab 01, we showed the
 * uncertainty on tab 03, now we show what actually happened historically and
 * what the feedback loop looks like once GELO-sales-data arrives.
 *
 * No fabricated numbers. If outcome data is missing, the UI says so.
 */
export const ImpactPage: React.FC<Props> = ({ snapshot }) => {
  const { data, loading, error, reload } = useImpact({
    virusTyp: snapshot.virusTyp,
    horizonDays: snapshot.modelStatus?.horizonDays ?? 7,
    client: snapshot.client,
    weeksBack: 12,
  });

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.24 }}
    >
      <section className="peix-hero">
        <div className="peix-hero-lede">
          <div className="peix-kicker kick">wirkung & feedback-loop</div>
          <h1 className="peix-display">
            Wir verkaufen <em>keinen</em> Forecast.
            <br />Wir verkaufen einen <em>Lernpfad</em>.
          </h1>
          <p className="dek">
            Dieser Tab zeigt drei Dinge: was wir gerade empfehlen, was tatsächlich in
            den letzten Wochen passiert ist, und wo der Feedback-Loop mit echten
            Verkaufsdaten von {snapshot.client} einklinken wird. Solange keine
            Outcome-Daten fließen, bleiben die entsprechenden Felder ehrlich leer.
          </p>
        </div>
        <aside className="peix-hero-card">
          <div className="row">
            <span className="label">Virus-Scope</span>
            <span className="val">{snapshot.virusTyp}</span>
          </div>
          <div className="row">
            <span className="label">Horizont</span>
            <span className="val peix-num">
              {snapshot.modelStatus?.horizonDays ?? 7} Tage
            </span>
          </div>
          <div className="row">
            <span className="label">Feedback-Loop</span>
            <span className="val">
              {data?.outcomePipeline.connected ? 'aktiv' : 'wartet auf Daten'}
            </span>
          </div>
        </aside>
      </section>

      {loading && !data && (
        <div className="peix-card peix-col-12" style={{ padding: 40, textAlign: 'center' }}>
          <span className="peix-kicker">lade wirkungs-daten…</span>
        </div>
      )}

      {error && !data && (
        <div className="peix-card peix-col-12" style={{ padding: 24 }}>
          <div className="peix-kicker">Wirkung nicht verfügbar</div>
          <p style={{ marginTop: 12 }}>{error.message}</p>
          <button type="button" className="peix-btn ghost" onClick={reload} style={{ marginTop: 12 }}>
            Erneut versuchen
          </button>
        </div>
      )}

      {data && (
        <section className="peix-bento">
          <LiveRankingCard data={data} />
          <TruthHistoryCard data={data} />
          <OutcomePipelineCard pipeline={data.outcomePipeline} />
          {data.notes.length > 0 && (
            <div className="peix-card peix-col-12 quiet">
              <div className="peix-kicker">fussnoten</div>
              <ul style={{ marginTop: 8, paddingLeft: 18 }}>
                {data.notes.map((n, i) => (
                  <li key={i} className="peix-body" style={{ marginTop: 4 }}>{n}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <SourcesStrip sources={snapshot.sources} />
    </motion.div>
  );
};

const LiveRankingCard: React.FC<{ data: ImpactPayload }> = ({ data }) => {
  const items = data.liveRanking;
  return (
    <div className="peix-card peix-col-5 warm-tint">
      <div className="peix-kicker">unser aktuelles ranking</div>
      <h3 className="peix-headline" style={{ marginTop: 4 }}>
        Top-5 Bundesländer, heute.
      </h3>
      <p className="peix-body" style={{ marginTop: 6, color: 'var(--peix-ink-soft)' }}>
        Modell-Output aus dem Live-Forecast. Signalstärke (0–1), nicht Wahrscheinlichkeit
        {' '}solange die Kalibrierung heuristisch ist.
      </p>
      {items.length === 0 ? (
        <div style={{ marginTop: 16, color: 'var(--peix-ink-mute)' }}>
          Kein Ranking verfügbar — der aktuelle Virus-Scope hat kein regionales Modell.
        </div>
      ) : (
        <ol style={{ marginTop: 16, listStyle: 'none', paddingLeft: 0 }}>
          {items.map((r, i) => (
            <li
              key={r.code}
              style={{
                display: 'grid',
                gridTemplateColumns: '24px 1fr auto auto',
                gap: 12,
                alignItems: 'baseline',
                padding: '8px 0',
                borderTop: i === 0 ? 'none' : '1px solid var(--peix-line)',
              }}
            >
              <span className="peix-num" style={{ color: 'var(--peix-ink-mute)', fontSize: 12 }}>
                {String(i + 1).padStart(2, '0')}
              </span>
              <span style={{ fontWeight: 500 }}>{r.name}</span>
              <span className="peix-num" style={{ color: 'var(--peix-ink-soft)' }}>
                {fmtSignalStrength(r.pRising)}
              </span>
              <span className="peix-pill" style={{ fontSize: 10 }}>
                {r.decisionLabel ?? '—'}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
};

const TruthHistoryCard: React.FC<{ data: ImpactPayload }> = ({ data }) => {
  const timeline = data.truthHistory.timeline;
  const recent = timeline.slice(-6); // last 6 weeks
  return (
    <div className="peix-card peix-col-7 cool-tint">
      <div className="peix-kicker">was tatsächlich passierte</div>
      <h3 className="peix-headline" style={{ marginTop: 4 }}>
        Reale BL-Aktivität der letzten Wochen.
      </h3>
      <p className="peix-body" style={{ marginTop: 6, color: 'var(--peix-ink-soft)' }}>
        Quelle: {data.truthHistory.source}. Diese Spur zeigt wo Wellen tatsächlich
        gelaufen sind — der Referenzrahmen gegen den unser Ranking beurteilt wird,
        sobald der Feedback-Loop Outcome-Daten bekommt.
      </p>
      {timeline.length === 0 ? (
        <div style={{ marginTop: 16, color: 'var(--peix-ink-mute)' }}>
          Keine BL-aufgelösten Truth-Daten für diesen Virus-Scope vorhanden.
        </div>
      ) : (
        <div style={{ marginTop: 16 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--peix-ink-mute)' }}>
                <th style={{ padding: '6px 0', fontWeight: 500 }}>KW</th>
                <th style={{ padding: '6px 0', fontWeight: 500 }}>#1</th>
                <th style={{ padding: '6px 0', fontWeight: 500 }}>#2</th>
                <th style={{ padding: '6px 0', fontWeight: 500 }}>#3</th>
                <th style={{ padding: '6px 0', fontWeight: 500, textAlign: 'right' }}>Top-1 Inzidenz</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((w) => {
                const top1 = w.regions[0];
                return (
                  <tr key={w.weekStart} style={{ borderTop: '1px solid var(--peix-line)' }}>
                    <td className="peix-num" style={{ padding: '8px 0' }}>{w.weekLabel}</td>
                    <td style={{ padding: '8px 0' }}>{w.top3[0] ?? '—'}</td>
                    <td style={{ padding: '8px 0' }}>{w.top3[1] ?? '—'}</td>
                    <td style={{ padding: '8px 0' }}>{w.top3[2] ?? '—'}</td>
                    <td className="peix-num" style={{ padding: '8px 0', textAlign: 'right' }}>
                      {top1 ? top1.incidence.toFixed(1) : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ marginTop: 10, fontSize: 11, color: 'var(--peix-ink-mute)' }}>
            Angezeigt: letzte {recent.length} von {timeline.length} verfügbaren Wochen.
          </div>
        </div>
      )}
    </div>
  );
};

const OutcomePipelineCard: React.FC<{ pipeline: ImpactOutcomePipeline }> = ({ pipeline }) => (
  <div className="peix-card peix-col-12 ink">
    <div className="peix-kicker">outcome-pipeline · feedback-loop</div>
    <h3 className="peix-headline" style={{ marginTop: 4, color: '#f5f3ee' }}>
      {pipeline.connected
        ? 'Feedback-Loop läuft — das Modell lernt mit jedem Datensatz mit.'
        : 'Pipeline steht, Daten fehlen — hier docken die Verkaufsdaten an.'}
    </h3>
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 20,
        marginTop: 20,
      }}
    >
      <PipelineStat label="Media-Outcome-Records" value={pipeline.mediaOutcomeRecords} />
      <PipelineStat label="Import-Batches" value={pipeline.importBatches} />
      <PipelineStat label="Outcome-Observations" value={pipeline.outcomeObservations} />
      <PipelineStat label="Holdout-Gruppen" value={pipeline.holdoutGroupsDefined} />
    </div>
    <div style={{ marginTop: 16, display: 'flex', gap: 18, flexWrap: 'wrap', fontSize: 12, color: 'rgba(245,243,238,0.7)' }}>
      <span>
        Letzter Import: <strong style={{ color: '#f5f3ee' }}>
          {pipeline.lastImportBatchAt ? fmtDate(pipeline.lastImportBatchAt) : '—'}
        </strong>
      </span>
      <span>
        Letzter Record-Update: <strong style={{ color: '#f5f3ee' }}>
          {pipeline.lastRecordUpdatedAt ? fmtDate(pipeline.lastRecordUpdatedAt) : '—'}
        </strong>
      </span>
    </div>
    <p style={{ marginTop: 14, fontStyle: 'italic', color: 'rgba(245,243,238,0.75)', fontFamily: 'var(--peix-font-display)' }}>
      {pipeline.note}
    </p>
    {!pipeline.connected && (
      <div style={{ marginTop: 14, padding: 12, border: '1px dashed rgba(245,243,238,0.25)', borderRadius: 8, fontSize: 12, color: 'rgba(245,243,238,0.85)' }}>
        <strong>Was {pipeline.connected ? '' : 'reinmuss'}:</strong> pro Woche × Bundesland × SKU die
        Felder <code>media_spend_eur</code>, <code>impressions</code>, <code>sales_units</code>,
        <code>revenue_eur</code>, optional <code>holdout_group</code>. Ingress via
        <code> POST /api/v1/media/outcomes</code> mit <code>X-API-Key</code> (M2M) oder CSV-Upload im Backoffice.
        DSGVO-neutral auf Aggregatebene — niemals auf Rezept- oder Personenebene.
      </div>
    )}
  </div>
);

const PipelineStat: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div>
    <div
      className="peix-num"
      style={{
        fontFamily: 'var(--peix-font-display)',
        fontSize: 36,
        fontWeight: 500,
        color: value > 0 ? '#ffb897' : 'rgba(245,243,238,0.5)',
        lineHeight: 1,
      }}
    >
      {value.toLocaleString('de-DE')}
    </div>
    <div style={{ marginTop: 4, fontSize: 11, color: 'rgba(245,243,238,0.7)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
      {label}
    </div>
  </div>
);

export default ImpactPage;
