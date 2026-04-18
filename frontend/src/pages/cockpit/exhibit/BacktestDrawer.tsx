import React, { useMemo, useState, useEffect } from 'react';
import { Drawer } from './Drawer';
import { useBacktest } from '../useBacktest';
import type { BacktestPayload, BacktestWeeklyHit } from '../backtestTypes';

// Virus scope switcher — the three viruses that have trained Option-B
// backtest artefacts on the server. Order matters: strongest pitch
// statement first.
const VIRUS_OPTIONS: Array<{ value: string; short: string; hint: string }> = [
  { value: 'Influenza B', short: 'Flu B', hint: 'stärkste Zahl' },
  { value: 'Influenza A', short: 'Flu A', hint: 'GO-Gate' },
  { value: 'RSV A', short: 'RSV A', hint: 'Watch · 13 BL' },
];

/**
 * BacktestDrawer — Drawer V: the pitch-story artifact.
 *
 * Single-sheet research brief feel:
 *   § V title block
 *   Monument (p@3 as %) + caption + window stamp
 *   Three-way comparison vs. persistence baseline
 *   Methodology stanza (walk-forward, point-in-time)
 *   Per-BL roster (ranked by p@3)
 *   Weekly hit-barcode (visual stripe of hits/misses over time)
 *   Honest-by-default disclaimer about how to translate ranking hits
 *   into euros (GELO owns that math, not us)
 *
 * Data source: GET /api/v1/media/cockpit/backtest, which shapes the
 * persisted regional-panel artifact produced by
 * regional_trainer_backtest.
 */

interface Props {
  open: boolean;
  onClose: () => void;
  virusLabel: string;     // comes from snapshot for consistency
  virusTyp?: string;      // defaults to "Influenza A" (pitch main story)
}

// ---------- Formatters ---------------------------------------------------
function fmtPct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${(v * 100).toFixed(digits)}`;
}

function fmtPctUnit(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${(v * 100).toFixed(digits)} %`;
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return v.toFixed(digits);
}

function fmtDateDE(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

// ---------- Sub-components ----------------------------------------------
const Monument: React.FC<{ data: BacktestPayload }> = ({ data }) => {
  const p3 = data.headline.precision_at_top3;
  return (
    <div className="ex-bt-monument-row ex-bt-reveal-2">
      <div>
        <div className="ex-bt-monument">
          {fmtPct(p3)}
          <span className="ex-bt-unit">%</span>
        </div>
      </div>
      <div>
        <p className="ex-bt-monument-caption">
          der Wochen hat unser Modell <em>mindestens ein Bundesland</em> mit
          echter Wellenbewegung in den Top-3 identifiziert.
        </p>
        <div className="ex-bt-window-stamp">
          <span>
            Fenster <strong>{fmtDateDE(data.window.start)} → {fmtDateDE(data.window.end)}</strong>
          </span>
          <span>
            Folds <strong>{data.window.folds}</strong>
          </span>
          <span>
            Horizont <strong>{data.horizon_days} d</strong>
          </span>
        </div>
      </div>
    </div>
  );
};

const Compare: React.FC<{ data: BacktestPayload }> = ({ data }) => {
  const modelP3 = data.headline.precision_at_top3;
  const persistP3 = data.baselines.persistence_precision_at_top3;
  const modelPrAuc = data.headline.pr_auc;
  const persistPrAuc = data.baselines.persistence_pr_auc;

  const p3Uplift =
    modelP3 !== null && persistP3 !== null && persistP3 > 0
      ? (modelP3 - persistP3) * 100
      : null;
  const prAucFold =
    modelPrAuc !== null && persistPrAuc !== null && persistPrAuc > 0
      ? modelPrAuc / persistPrAuc
      : null;

  return (
    <div className="ex-bt-compare ex-bt-reveal-3">
      <div className="ex-bt-compare-cell">
        <span className="ex-bt-compare-kicker">Top-3-Trefferquote</span>
        <span className="ex-bt-compare-value">{fmtPct(modelP3)}%</span>
        <span className="ex-bt-compare-vs">
          Persistenz-Baseline: {fmtPctUnit(persistP3)}
          {p3Uplift !== null && (
            <>
              {' · '}
              <em>
                {p3Uplift > 0 ? '+' : ''}
                {p3Uplift.toFixed(1)} pp besser
              </em>
            </>
          )}
        </span>
      </div>
      <div className="ex-bt-compare-cell">
        <span className="ex-bt-compare-kicker">PR-AUC</span>
        <span className="ex-bt-compare-value">{fmtNum(modelPrAuc, 3)}</span>
        <span className="ex-bt-compare-vs">
          Persistenz-Baseline: {fmtNum(persistPrAuc, 3)}
          {prAucFold !== null && (
            <>
              {' · '}
              <em>{prAucFold.toFixed(1)}× besser</em>
            </>
          )}
        </span>
      </div>
      <div className="ex-bt-compare-cell">
        <span className="ex-bt-compare-kicker">Lead-Time · Median</span>
        <span className="ex-bt-compare-value">
          {data.headline.median_lead_days !== null &&
          data.headline.median_lead_days !== undefined
            ? `${data.headline.median_lead_days} d`
            : '—'}
        </span>
        <span className="ex-bt-compare-vs">
          vor der amtlichen SURVSTAT-Meldung
        </span>
      </div>
    </div>
  );
};

const Method: React.FC = () => (
  <div className="ex-bt-method ex-bt-reveal-4">
    <div className="ex-bt-method-rail">§ Methode</div>
    <p className="ex-bt-method-body">
      Wir trainieren für jede Woche der Vergangenheit <em>ein frisches Modell</em>{' '}
      auf allen Daten, die damals verfügbar waren — strict vintage, keine
      Zukunfts-Lecke. Die Wochen-Prognose wird danach gegen die realen
      SURVSTAT-Inzidenzen der folgenden Wochen validiert. Die hier gezeigten
      Zahlen stammen aus <em>öffentlich überprüfbaren Daten</em>{' '}
      (SURVSTAT + Notaufnahme-Syndromsurveillance). Keine GELO-Verkaufsdaten
      wurden verwendet — die € rechnen Sie selbst mit Ihren ROI-Elastizitäten.
    </p>
  </div>
);

const Roster: React.FC<{ data: BacktestPayload }> = ({ data }) => (
  <div className="ex-bt-reveal-5">
    <div className="ex-bt-roster-head">
      <span>#</span>
      <span>Bundesland</span>
      <span style={{ textAlign: 'right' }}>p@3</span>
      <span style={{ textAlign: 'right' }}>PR-AUC</span>
      <span style={{ textAlign: 'right' }}>Brier</span>
      <span style={{ textAlign: 'right' }}>Fenster</span>
    </div>
    <ul className="ex-bt-roster">
      {data.per_bundesland.map((row, i) => (
        <li key={row.code}>
          <span className="ex-bt-roster-idx">{String(i + 1).padStart(2, '0')}</span>
          <span className="ex-bt-roster-name">
            {row.name}
            <span className="ex-bt-roster-code">{row.code}</span>
          </span>
          <span className="ex-bt-roster-num">{fmtPctUnit(row.precision_at_top3)}</span>
          <span className="ex-bt-roster-num">{fmtNum(row.pr_auc, 3)}</span>
          <span className="ex-bt-roster-num muted">{fmtNum(row.brier_score, 3)}</span>
          <span className="ex-bt-roster-num muted">{row.windows ?? '—'}</span>
        </li>
      ))}
    </ul>
  </div>
);

const Barcode: React.FC<{ weekly: BacktestWeeklyHit[] }> = ({ weekly }) => {
  // Classify each week as hit / partial / miss / blank
  // - hit    = predicted_top ≥ 1 ∩ observed_top = hits ≥ 1
  // - partial = observed_top ≥ 1 but no hits (predicted all wrong)
  // - miss   = no observed events at all (nothing to catch this week)
  const ticks = weekly.map((w) => {
    if (w.was_hit) return 'hit' as const;
    if (w.observed_top.length > 0) return 'partial' as const;
    return 'miss' as const;
  });
  const first = weekly[0];
  const last = weekly[weekly.length - 1];
  return (
    <div className="ex-bt-barcode ex-bt-reveal-6">
      <div className="ex-bt-method-rail" style={{ color: '#b94a2e', marginBottom: 6 }}>
        § Wochen-Barcode
      </div>
      <div className="ex-bt-barcode-rail" role="img" aria-label={`${weekly.length} Wochen Hit/Miss-Spur`}>
        {weekly.map((w, i) => (
          <span
            key={w.as_of_date}
            className={`ex-bt-barcode-tick ${ticks[i]}`}
            title={`KW ${w.as_of_date}: ${ticks[i] === 'hit' ? 'Treffer' : ticks[i] === 'partial' ? 'Welle vorhanden, aber Top-3 daneben' : 'keine Welle diese Woche'}`}
          />
        ))}
      </div>
      <div className="ex-bt-barcode-axis">
        <span>{fmtDateDE(first?.as_of_date || null)}</span>
        <span style={{ color: '#b94a2e' }}>■ Treffer</span>
        <span style={{ color: 'rgba(26,23,19,.45)' }}>■ keine Welle</span>
        <span>{fmtDateDE(last?.as_of_date || null)}</span>
      </div>
    </div>
  );
};

const Disclaimer: React.FC = () => (
  <div className="ex-bt-disclaimer">
    <div className="ex-bt-disclaimer-rail">Lesart</div>
    <p className="ex-bt-disclaimer-body">
      Das Modell identifiziert Regionen mit steigender Welle. Die
      wirtschaftliche Konsequenz — etwa „Wie viele Euro wurden in Regionen
      ohne echte Welle verbrannt?" — ergibt sich aus Ihren eigenen
      Reichweiten- und ROI-Elastizitäten. Wir liefern die Ranking-Validierung,
      Sie die monetäre Übersetzung.
    </p>
  </div>
);

// ---------- Virus scope switcher ----------------------------------------
const VirusSwitch: React.FC<{
  value: string;
  onChange: (virus: string) => void;
}> = ({ value, onChange }) => (
  <div
    className="ex-bt-virus-switch ex-bt-reveal-1"
    role="tablist"
    aria-label="Virus-Scope für Backtest"
  >
    <span className="ex-bt-virus-switch-label">Virus-Scope</span>
    <div className="ex-bt-virus-switch-chips">
      {VIRUS_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="tab"
          aria-selected={value === opt.value}
          className={
            'ex-bt-virus-chip' +
            (value === opt.value ? ' ex-bt-virus-chip--active' : '')
          }
          onClick={() => onChange(opt.value)}
        >
          <span className="ex-bt-virus-chip-name">{opt.short}</span>
          <span className="ex-bt-virus-chip-hint">{opt.hint}</span>
        </button>
      ))}
    </div>
  </div>
);

// ---------- Drawer root -------------------------------------------------
export const BacktestDrawer: React.FC<Props> = ({
  open,
  onClose,
  virusLabel,
  virusTyp = 'Influenza A',
}) => {
  // The Drawer keeps its OWN virus scope (independent from snapshot's
  // current virus) so the pitch user can flip between the three story
  // angles without leaving the drawer.
  const [selectedVirus, setSelectedVirus] = useState<string>(virusTyp);

  // When the drawer is re-opened after a snapshot virus change, sync once.
  useEffect(() => {
    if (open) setSelectedVirus(virusTyp);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const { data, loading, error } = useBacktest({
    virusTyp: selectedVirus,
    horizonDays: 7,
    weeksToSurface: 104,
  });

  const available = Boolean(data?.available);

  const kicker = useMemo(
    () => (
      <>
        <span>Drawer V</span>
        <span>·</span>
        <span>Backtest</span>
        <span>·</span>
        <span>{selectedVirus}</span>
      </>
    ),
    [selectedVirus],
  );

  const footLeft = data?.window
    ? `${data.window.folds} Folds · ${fmtDateDE(data.window.start)} → ${fmtDateDE(data.window.end)}`
    : 'Walk-forward · strict vintage';
  const footRight = data?.quality_gate?.forecast_readiness
    ? `Quality-Gate · ${data.quality_gate.forecast_readiness}`
    : 'Pitch-Artefakt · nicht-kommerziell';

  return (
    <Drawer
      open={open}
      onClose={onClose}
      kicker={kicker}
      title={
        <>
          In wie vielen Wochen hatten wir <em>recht</em>?
        </>
      }
      footLeft={footLeft}
      footRight={footRight}
    >
      <div className="ex-bt-wrap">
        <VirusSwitch value={selectedVirus} onChange={setSelectedVirus} />
        <header className="ex-bt-title ex-bt-reveal-1">
          <div className="ex-bt-title-mark">§ V</div>
          <div className="ex-bt-title-stack">
            <span className="ex-bt-title-kicker">
              Ranking-Validation · walk-forward · point-in-time
            </span>
            <p className="ex-bt-title-dek">
              Ein Backtest, keine Prognose. Für jede Woche der Vergangenheit
              fragen wir: <em>hätte unser Modell damals die richtigen Bundesländer
              benannt?</em>
            </p>
          </div>
        </header>

        {loading && !data && (
          <div className="ex-bt-unavailable">Lade Backtest-Daten…</div>
        )}

        {error && !data && (
          <div className="ex-bt-unavailable">
            Backtest-Payload nicht verfügbar. {error.message}
          </div>
        )}

        {data && !available && (
          <div className="ex-bt-unavailable">
            {data.reason ??
              `Für ${selectedVirus} (h=${data.horizon_days} d) liegt noch kein Backtest-Artefakt vor. Ein Retrain auf voller Historie läuft gerade im Hintergrund — bitte später erneut öffnen.`}
          </div>
        )}

        {data && available && (
          <>
            <Monument data={data} />
            <Compare data={data} />
            <Method />
            <Roster data={data} />
            <Barcode weekly={data.weekly_hits} />
            <Disclaimer />
          </>
        )}
      </div>
    </Drawer>
  );
};

export default BacktestDrawer;
