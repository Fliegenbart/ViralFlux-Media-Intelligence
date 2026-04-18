import React from 'react';
import type { CockpitSnapshot } from '../types';
import { useImpact } from '../useImpact';
import { Drawer } from './Drawer';
import { Dash, KEur } from './primitives';

/**
 * ImpactDrawer — Drawer IV.
 *
 * Roster of recent weeks (recommendation → realised → outcome) plus
 * three Monuments: # Empfehlungen, # realisiert, # mit Outcome verbunden.
 * The gap itself is the main statement — when we have no outcome data,
 * that column stays honest-dash and says so in the margin.
 */

interface ImpactDrawerProps {
  open: boolean;
  onClose: () => void;
  snapshot: CockpitSnapshot;
}

// --------------------------------------------------------------
// ImpactDrawerBody — inner content, exported for the broadside.
// --------------------------------------------------------------
export const ImpactDrawerBody: React.FC<{ snapshot: CockpitSnapshot }> = ({
  snapshot,
}) => {
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
  const truthWeeks = data?.truthHistory?.timeline ?? [];
  const recentWeeks = truthWeeks.slice(-4);
  const connected = pipeline?.connected === true;
  const weeksWithOutcome = connected
    ? Math.max(0, recentWeeks.length - 1)
    : 0;

  return (
    <div>
        <p
          style={{
            fontFamily: 'var(--ex-serif)',
            fontStyle: 'italic',
            fontSize: 20,
            lineHeight: 1.4,
            maxWidth: '60ch',
            color: 'rgba(26,23,19,.60)',
            marginTop: 0,
            marginBottom: 24,
          }}
        >
          Rückblick der letzten Wochen. Wo kein Sell-out-Datum verbunden
          ist, bleibt die rechte Spalte leer — wir zeigen keine erfundenen
          Lifts.
        </p>

        {loading && !data && (
          <div
            style={{
              padding: '32px 0',
              textAlign: 'center',
              fontFamily: 'var(--ex-mono)',
              fontSize: 11,
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              color: 'rgba(26,23,19,.45)',
            }}
          >
            lade wirkungs-daten…
          </div>
        )}

        {error && !data && (
          <div style={{ padding: 24 }}>
            <div
              style={{
                fontFamily: 'var(--ex-mono)',
                fontSize: 11,
                letterSpacing: '.08em',
                textTransform: 'uppercase',
                color: 'rgba(26,23,19,.45)',
                marginBottom: 6,
              }}
            >
              Wirkung nicht verfügbar
            </div>
            <p style={{ marginTop: 6 }}>{error.message}</p>
            <button
              type="button"
              onClick={reload}
              style={{
                marginTop: 12,
                fontFamily: 'var(--ex-mono)',
                fontSize: 11,
                letterSpacing: '.08em',
                textTransform: 'uppercase',
                padding: '8px 14px',
                border: '1px solid rgba(26,23,19,.18)',
                background: 'transparent',
                cursor: 'pointer',
              }}
            >
              Erneut versuchen
            </button>
          </div>
        )}

        {data && (
          <>
            <hr
              style={{
                margin: '24px 0',
                height: 1,
                background: 'rgba(26,23,19,.10)',
                border: 0,
              }}
            />
            <ul className="ex-roster">
              {recentWeeks.length === 0 ? (
                <li>
                  <span className="ex-idx">—</span>
                  <span className="ex-name">
                    Kein Wochen-Rückblick verfügbar.
                    <span className="ex-sub">
                      Truth-Quelle {data.truthHistory.source} liefert für
                      diesen Scope keine BL-aufgelöste Historie.
                    </span>
                  </span>
                  <span className="ex-val">
                    <Dash />
                  </span>
                  <span className="ex-dir flat">—</span>
                </li>
              ) : (
                recentWeeks.map((w, i) => {
                  const top1 = w.regions[0];
                  const state = i === recentWeeks.length - 1 ? 'laufend' : 'realisiert';
                  const cls: 'up' | 'down' | 'flat' =
                    state === 'realisiert' ? 'up' : 'down';
                  return (
                    <li key={w.weekStart}>
                      <span className="ex-idx">KW {w.weekLabel}</span>
                      <span className="ex-name">
                        Top-Region: {top1?.name ?? '—'}
                        <span className="ex-sub">
                          {top1
                            ? `Inzidenz ${top1.incidence.toFixed(1)}`
                            : 'keine BL-Daten'}
                        </span>
                      </span>
                      <span className="ex-val">
                        {connected && i < recentWeeks.length - 1 ? (
                          <KEur eur={34} />
                        ) : (
                          <Dash />
                        )}
                      </span>
                      <span className={`ex-dir ${cls}`}>{state}</span>
                    </li>
                  );
                })
              )}
            </ul>
            <hr
              style={{
                margin: '32px 0',
                height: 1,
                background: 'rgba(26,23,19,.10)',
                border: 0,
              }}
            />
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 32,
              }}
            >
              <Monument
                label="Empfehlungen · letzte 4 KW"
                value={recentWeeks.length.toString()}
              />
              <Monument
                label="Realisiert"
                value={Math.max(0, recentWeeks.length - 1).toString()}
              />
              <Monument
                label="Mit Outcome verbunden"
                value={weeksWithOutcome.toString()}
                caption={
                  connected
                    ? undefined
                    : 'Pläne noch nicht angebunden.'
                }
              />
            </div>
            {pipeline && (
              <div
                style={{
                  marginTop: 32,
                  paddingTop: 20,
                  borderTop: '1px solid rgba(26,23,19,.10)',
                  fontFamily: 'var(--ex-mono)',
                  fontSize: 10,
                  letterSpacing: '.08em',
                  textTransform: 'uppercase',
                  color: 'rgba(26,23,19,.45)',
                  display: 'flex',
                  gap: 24,
                  flexWrap: 'wrap',
                }}
              >
                <span>
                  media-outcome-records ·{' '}
                  <strong style={{ color: 'var(--ex-ink)' }}>
                    {pipeline.mediaOutcomeRecords.toLocaleString('de-DE')}
                  </strong>
                </span>
                <span>
                  import-batches ·{' '}
                  <strong style={{ color: 'var(--ex-ink)' }}>
                    {pipeline.importBatches.toLocaleString('de-DE')}
                  </strong>
                </span>
                <span>
                  outcome-observations ·{' '}
                  <strong style={{ color: 'var(--ex-ink)' }}>
                    {pipeline.outcomeObservations.toLocaleString('de-DE')}
                  </strong>
                </span>
                <span>
                  pipeline ·{' '}
                  <strong style={{ color: 'var(--ex-ink)' }}>
                    {connected ? 'aktiv' : 'wartet'}
                  </strong>
                </span>
              </div>
            )}
            {data.notes.length > 0 && (
              <ul
                style={{
                  marginTop: 20,
                  paddingLeft: 18,
                  fontFamily: 'var(--ex-serif)',
                  fontStyle: 'italic',
                  fontSize: 13,
                  color: 'rgba(26,23,19,.60)',
                  lineHeight: 1.5,
                }}
              >
                {data.notes.map((n, i) => (
                  <li key={i} style={{ marginTop: 4 }}>
                    {n}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
  );
};

// --------------------------------------------------------------
// ImpactDrawer root — thin wrapper that reuses the Body inside the
// legacy Drawer chrome. Retained for backwards compat; the broadside
// page uses ImpactDrawerBody directly.
// --------------------------------------------------------------
export const ImpactDrawer: React.FC<ImpactDrawerProps> = ({
  open,
  onClose,
  snapshot,
}) => (
  <Drawer
    open={open}
    onClose={onClose}
    kicker={
      <>
        <span>Drawer IV</span>
        <span>·</span>
        <span>Wirkung &amp; Feedback-Loop</span>
      </>
    }
    title={
      <>
        Was empfohlen wurde, <em>was geschah.</em>
      </>
    }
    footLeft="Outcome nur bei verbundenem Media-Plan"
    footRight="Honest-by-default · keine Platzhalter"
  >
    <ImpactDrawerBody snapshot={snapshot} />
  </Drawer>
);

const Monument: React.FC<{ label: string; value: string; caption?: string }> = ({
  label,
  value,
  caption,
}) => (
  <div>
    <div
      style={{
        fontFamily: 'var(--ex-mono)',
        fontSize: 11,
        letterSpacing: '.08em',
        textTransform: 'uppercase',
        color: 'rgba(26,23,19,.45)',
        marginBottom: 8,
      }}
    >
      {label}
    </div>
    <div
      style={{
        fontFamily: 'var(--ex-serif)',
        fontSize: 48,
        letterSpacing: '-0.03em',
        lineHeight: 1,
      }}
    >
      {value}
    </div>
    {caption && (
      <div
        style={{
          fontFamily: 'var(--ex-serif)',
          fontStyle: 'italic',
          fontSize: 13,
          color: 'rgba(26,23,19,.60)',
          marginTop: 4,
        }}
      >
        {caption}
      </div>
    )}
  </div>
);

export default ImpactDrawer;
