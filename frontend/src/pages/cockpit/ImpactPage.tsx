import React from 'react';
import { motion } from 'framer-motion';
import GalleryHero from '../../components/cockpit/peix/GalleryHero';
import RosterList, { type RosterRow } from '../../components/cockpit/peix/RosterList';
import SourcesStrip from '../../components/cockpit/peix/SourcesStrip';
import type { CockpitSnapshot } from './types';
import type { ImpactPayload, ImpactOutcomePipeline } from './impactTypes';
import { fmtDate, fmtSignalStrength } from './format';
import { useImpact } from './useImpact';

interface Props { snapshot: CockpitSnapshot; }

/**
 * Tab 04 — "Wirkung & Feedback-Loop".
 *
 * Gallery-refresh (2026-04-17): same dark-stage hero as Decision/Timeline,
 * then a calm roster for the live ranking, a minimal truth-history table,
 * and a single dark pipeline card at the bottom. The previous four-card
 * bento with warm-tint / cool-tint / ink gradients is collapsed into three
 * quieter sections with generous whitespace.
 */
export const ImpactPage: React.FC<Props> = ({ snapshot }) => {
  const { data, loading, error, reload } = useImpact({
    virusTyp: snapshot.virusTyp,
    horizonDays: snapshot.modelStatus?.horizonDays ?? 14,
    leadTarget:
      (snapshot.modelStatus?.lead?.targetSource as
        | 'ATEMWEGSINDEX'
        | 'RKI_ARE'
        | 'SURVSTAT'
        | undefined) ?? 'ATEMWEGSINDEX',
    client: snapshot.client,
    weeksBack: 12,
  });

  const pipeline = data?.outcomePipeline;
  const heroMain = pipeline?.mediaOutcomeRecords ?? 0;

  const heroVisual = (
    <>
      <div className="peix-gal-bignum">
        <span className="peix-gal-bignum__kicker">Media-Outcome-Records</span>
        <span
          className="peix-gal-bignum__value"
          style={{
            color: heroMain > 0 ? undefined : 'rgba(239,232,220,0.45)',
          }}
        >
          {heroMain.toLocaleString('de-DE')}
        </span>
        <p className="peix-gal-bignum__caption">
          {pipeline?.connected
            ? 'Feedback-Loop läuft — jede Woche lernt das Modell mit.'
            : 'Pipeline steht. Sobald GELO wöchentliche Outcome-Daten liefert, klinkt sich der Lernpfad hier ein.'}
        </p>
      </div>
      <div className="peix-gal-specs">
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">Import-Batches</span>
          <span className="peix-gal-specs__value">
            {(pipeline?.importBatches ?? 0).toLocaleString('de-DE')}
          </span>
        </div>
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">Outcome-Observations</span>
          <span className="peix-gal-specs__value">
            {(pipeline?.outcomeObservations ?? 0).toLocaleString('de-DE')}
          </span>
        </div>
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">Holdout-Gruppen</span>
          <span className="peix-gal-specs__value">
            {(pipeline?.holdoutGroupsDefined ?? 0).toLocaleString('de-DE')}
          </span>
        </div>
        <div className="peix-gal-specs__row">
          <span className="peix-gal-specs__label">Status</span>
          <span
            className={
              'peix-gal-specs__value ' +
              (pipeline?.connected ? 'peix-gal-specs__value--warm' : '')
            }
          >
            {pipeline?.connected ? 'aktiv' : 'wartet auf Daten'}
          </span>
        </div>
      </div>
    </>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.28, ease: [0.22, 0.61, 0.36, 1] }}
      className="peix-gal-wrap"
    >
      <GalleryHero
        kicker={`wirkung · ${snapshot.isoWeek}`}
        headline={
          <>
            Wir verkaufen <em>keinen</em> Forecast.
            <br />
            Wir verkaufen einen <em>Lernpfad</em>.
          </>
        }
        dek={
          <>
            Drei Sichten: was das Modell gerade empfiehlt, was in den letzten Wochen
            wirklich passierte, und wo der Feedback-Loop mit Verkaufsdaten von{' '}
            {snapshot.client} einklinkt. Ohne Outcome-Daten bleiben die entsprechenden
            Felder ehrlich leer.
          </>
        }
        visual={heroVisual}
        caption={{
          label: 'Pipeline-Status',
          meta: (
            <>
              {pipeline?.lastImportBatchAt
                ? `zuletzt ${fmtDate(pipeline.lastImportBatchAt)}`
                : 'noch kein Import'}
            </>
          ),
        }}
      />

      {loading && !data && (
        <div style={{ padding: '48px 0', textAlign: 'center' }}>
          <span className="peix-gal-section__kicker">lade wirkungs-daten…</span>
        </div>
      )}

      {error && !data && (
        <>
          <header className="peix-gal-section">
            <span className="peix-gal-section__kicker">Fehler</span>
            <h2 className="peix-gal-section__title">Wirkung nicht verfügbar.</h2>
            <p className="peix-gal-section__dek">{error.message}</p>
          </header>
          <section className="peix-bento">
            <div className="peix-card peix-col-12 quiet" style={{ padding: 24 }}>
              <button
                type="button"
                className="peix-btn ghost"
                onClick={reload}
              >
                Erneut versuchen
              </button>
            </div>
          </section>
        </>
      )}

      {data && (
        <>
          <header className="peix-gal-section">
            <span className="peix-gal-section__kicker">Aktuelles Ranking</span>
            <h2 className="peix-gal-section__title">
              Top-5 Bundesländer <em>heute</em>.
            </h2>
            <p className="peix-gal-section__dek">
              Modell-Output aus dem Live-Forecast. Signalstärke (0–1) — nicht
              Wahrscheinlichkeit, solange die Kalibrierung heuristisch ist.
            </p>
          </header>
          <section className="peix-bento">
            <div
              className="peix-card peix-col-12 quiet"
              style={{ padding: '8px 30px 20px' }}
            >
              <LiveRankingBody data={data} />
            </div>
          </section>

          <header className="peix-gal-section">
            <span className="peix-gal-section__kicker">Was tatsächlich passierte</span>
            <h2 className="peix-gal-section__title">
              Reale BL-Aktivität der letzten Wochen.
            </h2>
            <p className="peix-gal-section__dek">
              Quelle: {data.truthHistory.source}. Diese Spur ist der Referenz­rahmen,
              gegen den sich unser Ranking wöchentlich selbst beurteilt — sobald der
              Feedback-Loop Outcome-Daten bekommt.
            </p>
          </header>
          <section className="peix-bento">
            <div
              className="peix-card peix-col-12 quiet"
              style={{ padding: '20px 30px' }}
            >
              <TruthHistoryTable data={data} />
            </div>
          </section>

          <header className="peix-gal-section">
            <span className="peix-gal-section__kicker">Feedback-Loop</span>
            <h2 className="peix-gal-section__title">
              Hier docken die Verkaufsdaten <em>an</em>.
            </h2>
          </header>
          <section className="peix-bento">
            <div className="peix-card peix-col-12 ink" style={{ padding: '28px 32px' }}>
              <OutcomePipelineBody pipeline={data.outcomePipeline} />
            </div>
          </section>

          {data.notes.length > 0 && (
            <section className="peix-bento" style={{ marginTop: 24 }}>
              <div
                className="peix-card peix-col-12 quiet"
                style={{ padding: '22px 30px' }}
              >
                <div className="peix-gal-section__kicker" style={{ fontSize: 10 }}>
                  Fussnoten
                </div>
                <ul
                  style={{
                    margin: '10px 0 0',
                    paddingLeft: 18,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                  }}
                >
                  {data.notes.map((n, i) => (
                    <li key={i} className="peix-gal-note">
                      {n}
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          )}
        </>
      )}

      <SourcesStrip sources={snapshot.sources} />
    </motion.div>
  );
};

// --------------------------------------------------------------------------
// Live ranking — dispatched into a paper roster with decision label as meta.
// --------------------------------------------------------------------------
const LiveRankingBody: React.FC<{ data: ImpactPayload }> = ({ data }) => {
  const rows: RosterRow[] = data.liveRanking.map((r) => ({
    id: r.code,
    name: r.name,
    meta: r.decisionLabel ? `Entscheidung · ${r.decisionLabel}` : '',
    value: fmtSignalStrength(r.pRising),
  }));
  return (
    <RosterList
      rows={rows}
      variant="paper"
      empty={
        <>
          Kein Ranking verfügbar — der aktuelle Virus-Scope hat kein regionales Modell.
        </>
      }
    />
  );
};

// --------------------------------------------------------------------------
// Truth history — kept as a minimal FT-style table, no chrome.
// --------------------------------------------------------------------------
const TruthHistoryTable: React.FC<{ data: ImpactPayload }> = ({ data }) => {
  const timeline = data.truthHistory.timeline;
  const recent = timeline.slice(-6);
  if (timeline.length === 0) {
    return (
      <p
        style={{
          margin: '12px 0',
          fontFamily: 'var(--peix-font-display)',
          fontStyle: 'italic',
          color: 'var(--peix-ink-soft)',
        }}
      >
        Keine BL-aufgelösten Truth-Daten für diesen Virus-Scope vorhanden.
      </p>
    );
  }
  return (
    <div>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 13.5,
          fontFamily: 'var(--peix-font-sans)',
        }}
      >
        <thead>
          <tr
            style={{
              textAlign: 'left',
              color: 'var(--peix-ink-mute)',
              borderBottom: '1px solid var(--peix-line)',
            }}
          >
            <th style={{ padding: '10px 0', fontWeight: 500, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase' }}>KW</th>
            <th style={{ padding: '10px 0', fontWeight: 500, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase' }}>#1</th>
            <th style={{ padding: '10px 0', fontWeight: 500, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase' }}>#2</th>
            <th style={{ padding: '10px 0', fontWeight: 500, fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase' }}>#3</th>
            <th
              style={{
                padding: '10px 0',
                fontWeight: 500,
                fontSize: 11,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                textAlign: 'right',
              }}
            >
              Top-1 Inzidenz
            </th>
          </tr>
        </thead>
        <tbody>
          {recent.map((w) => {
            const top1 = w.regions[0];
            return (
              <tr
                key={w.weekStart}
                style={{ borderBottom: '1px solid var(--peix-line)' }}
              >
                <td
                  style={{
                    padding: '14px 0',
                    fontFamily: 'var(--peix-font-mono)',
                    fontSize: 12,
                    color: 'var(--peix-ink-mute)',
                  }}
                >
                  {w.weekLabel}
                </td>
                <td
                  style={{
                    padding: '14px 0',
                    fontFamily: 'var(--peix-font-display)',
                    fontSize: 16,
                  }}
                >
                  {w.top3[0] ?? '—'}
                </td>
                <td
                  style={{
                    padding: '14px 0',
                    fontFamily: 'var(--peix-font-display)',
                    fontSize: 16,
                    color: 'var(--peix-ink-soft)',
                  }}
                >
                  {w.top3[1] ?? '—'}
                </td>
                <td
                  style={{
                    padding: '14px 0',
                    fontFamily: 'var(--peix-font-display)',
                    fontSize: 16,
                    color: 'var(--peix-ink-soft)',
                  }}
                >
                  {w.top3[2] ?? '—'}
                </td>
                <td
                  style={{
                    padding: '14px 0',
                    textAlign: 'right',
                    fontFamily: 'var(--peix-font-mono)',
                    fontSize: 13,
                    color: 'var(--peix-ink)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {top1 ? top1.incidence.toFixed(1) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div
        style={{
          marginTop: 14,
          fontSize: 10.5,
          color: 'var(--peix-ink-mute)',
          fontFamily: 'var(--peix-font-mono)',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
        }}
      >
        letzte {recent.length} von {timeline.length} verfügbaren Wochen
      </div>
    </div>
  );
};

// --------------------------------------------------------------------------
// Outcome pipeline — kept on the dark ink-card at the bottom to echo the
// hero's warm-black voice without duplicating its full gallery treatment.
// --------------------------------------------------------------------------
const OutcomePipelineBody: React.FC<{ pipeline: ImpactOutcomePipeline }> = ({
  pipeline,
}) => (
  <>
    <div className="peix-kicker">outcome-pipeline</div>
    <h3 className="peix-gal-h3 peix-gal-h3--dark" style={{ marginTop: 6 }}>
      {pipeline.connected
        ? 'Feedback-Loop läuft — das Modell lernt mit jedem Datensatz.'
        : 'Pipeline steht, Daten fehlen. Hier docken die Verkaufsdaten an.'}
    </h3>

    <div
      style={{
        marginTop: 18,
        display: 'flex',
        gap: 22,
        flexWrap: 'wrap',
        fontSize: 12.5,
        color: 'rgba(239,232,220,0.65)',
        fontFamily: 'var(--peix-font-mono)',
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
      }}
    >
      <span>
        zuletzt importiert ·{' '}
        <strong style={{ color: 'var(--gal-ink, #efe8dc)' }}>
          {pipeline.lastImportBatchAt ? fmtDate(pipeline.lastImportBatchAt) : '—'}
        </strong>
      </span>
      <span>
        record-update ·{' '}
        <strong style={{ color: 'var(--gal-ink, #efe8dc)' }}>
          {pipeline.lastRecordUpdatedAt ? fmtDate(pipeline.lastRecordUpdatedAt) : '—'}
        </strong>
      </span>
    </div>

    <p
      style={{
        marginTop: 16,
        fontFamily: 'var(--peix-font-display)',
        fontStyle: 'italic',
        fontSize: 15.5,
        lineHeight: 1.5,
        color: 'rgba(239,232,220,0.78)',
        maxWidth: '68ch',
      }}
    >
      {pipeline.note}
    </p>

    {!pipeline.connected && (
      <div
        style={{
          marginTop: 20,
          padding: '16px 18px',
          border: '1px dashed rgba(239,232,220,0.25)',
          borderRadius: 8,
          fontSize: 12.5,
          lineHeight: 1.55,
          color: 'rgba(239,232,220,0.85)',
          fontFamily: 'var(--peix-font-sans)',
        }}
      >
        <strong style={{ color: 'var(--gal-warm, #d68a5a)' }}>Was reinmuss: </strong>
        pro Woche × Bundesland × SKU die Felder <code>media_spend_eur</code>,{' '}
        <code>impressions</code>, <code>sales_units</code>, <code>revenue_eur</code>,
        optional <code>holdout_group</code>. Ingress via{' '}
        <code>POST /api/v1/media/outcomes</code> mit <code>X-API-Key</code> (M2M) oder
        CSV-Upload im Backoffice. DSGVO-neutral auf Aggregat­ebene — niemals auf
        Rezept- oder Personenebene.
      </div>
    )}
  </>
);

export default ImpactPage;
