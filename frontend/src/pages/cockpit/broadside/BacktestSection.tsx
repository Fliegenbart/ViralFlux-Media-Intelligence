import React, { useMemo, useState } from 'react';
import type { CockpitSnapshot, EvidenceValidationStatus } from '../types';
import { useBacktest } from '../useBacktest';
import SectionHeader from './SectionHeader';
import type { GateTone } from './SectionHeader';
import { firstBool, firstNumber, firstText } from './snapshotAccessors';

/**
 * § V — Backtest.
 *
 * Instrumentation-Redesign 2026-04-18.
 *
 * Drei Teile:
 *   1. Dark Monument-Head (schwarz, 3 Zellen): PR-AUC, Precision@Top-3,
 *      Median-Lead-Zeit. Thin-weight 140 px, Unit in Grau, Multiplier
 *      in Terracotta.
 *   2. Controls: Virus-Switcher (Influenza A / B / RSV A) + Fenster-
 *      Stempel rechts.
 *   3. Roster: per-Bundesland PR-AUC + Lead-Days, absteigend sortiert.
 *   4. Hit-Barcode: 52+ Wochen als vertikale Balken (Hit / Miss / No data).
 *
 * Alle Daten kommen live aus /api/v1/media/cockpit/backtest?virus_typ=…
 * — beim Switcher wechselt der Hook den virus_typ, lädt Daten nach.
 */

interface Props {
  snapshot: CockpitSnapshot;
}

function validationFrom(snapshot: CockpitSnapshot): EvidenceValidationStatus | null {
  return snapshot.backtestResearch ?? snapshot.backtest_research ?? null;
}

function pctLabel(value: number | null): string {
  if (value === null) return '—';
  const pct = value <= 1 ? value * 100 : value;
  return `${pct.toFixed(0)} %`;
}

const VIRUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'Influenza A', label: 'Influenza A' },
  { value: 'Influenza B', label: 'Influenza B' },
  { value: 'RSV A', label: 'RSV A' },
];

function fmtPrAuc(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return '—';
  // ".746" style — drop leading 0.
  return v.toFixed(3).replace(/^0/, '');
}

function fmtDateDE(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function getISOWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
}

export const BacktestSection: React.FC<Props> = ({ snapshot }) => {
  const [virusTyp, setVirusTyp] = useState<string>(
    snapshot.virusTyp || 'Influenza A',
  );

  const { data, loading } = useBacktest({ virusTyp, horizonDays: 7 });

  const headline = data?.headline;
  const baselines = data?.baselines;
  const window = data?.window;

  // PR-AUC & multiplier
  const prAuc = headline?.pr_auc ?? null;
  const persistPrAuc = baselines?.persistence_pr_auc ?? null;
  const multiplier =
    prAuc !== null && persistPrAuc !== null && persistPrAuc > 0
      ? prAuc / persistPrAuc
      : null;

  // Precision & pp-delta
  const prec = headline?.precision_at_top3 ?? null;
  const persistPrec = baselines?.persistence_precision_at_top3 ?? null;
  const ppDelta =
    prec !== null && persistPrec !== null ? (prec - persistPrec) * 100 : null;

  const medianLead = headline?.median_lead_days ?? null;

  // Roster — sort by PR-AUC desc, filter to finite values
  const roster = useMemo(() => {
    const perBL = data?.per_bundesland ?? [];
    return [...perBL]
      .filter(
        (r) => typeof r.pr_auc === 'number' && Number.isFinite(r.pr_auc),
      )
      .sort((a, b) => (b.pr_auc ?? -Infinity) - (a.pr_auc ?? -Infinity));
  }, [data?.per_bundesland]);

  const maxPrAuc = roster[0]?.pr_auc ?? 1;

  // Barcode — map weekly_hits to hit / miss / nodata
  const barcodeEntries: Array<{ state: 'hit' | 'miss' | 'nodata'; label: string }> =
    useMemo(() => {
      const weeklyHits = data?.weekly_hits ?? [];
      if (weeklyHits.length === 0) return [];
      return weeklyHits.map((w) => {
        const date = new Date(w.target_date);
        const label = `KW${String(getISOWeek(date)).padStart(2, '0')}`;
        if (w.observed_top.length === 0)
          return { state: 'nodata', label };
        return { state: w.was_hit ? 'hit' : 'miss', label };
      });
    }, [data?.weekly_hits]);

  const validation = validationFrom(snapshot);
  const researchRecommendation = firstText(validation?.recommendation) ?? 'review';
  const gateTone: GateTone =
    researchRecommendation === 'go_for_simulation' ? 'go' : 'watch';
  const gateLabel =
    researchRecommendation === 'go_for_simulation'
      ? 'Research · simulation candidate'
      : researchRecommendation === 'no_go'
        ? 'Research · no-go'
        : 'Research · review';

  return (
    <section className="instr-section" id="sec-backtest">
      <SectionHeader
        numeral="IV"
        title="Evidenz-Validierung"
        subtitle={
          <>
            Walk-forward über {window?.folds ?? '—'} Wochen · gegen Persistenz-Baseline
          </>
        }
        gate={{ label: gateLabel, tone: gateTone }}
        primer={
          <>
            Das Modell wird rückwirkend gegen echte Vergangenheit
            getestet: Jede Woche wird der Forecast mit Wissen bis dahin
            neu berechnet und gegen das tatsächliche Ergebnis verglichen.
            Die drei Monument-Zahlen sind <b>PR-AUC</b> (Ranking-Güte,
            höher besser), <b>Precision@Top-3</b> (wie oft die drei
            gerankten Bundesländer auch die echten Top-Wellen waren) und
            <b> Median-Lead-Zeit</b> (um wie viele Tage das Signal dem
            Meldewesen vorausläuft). Vergleich ist immer die
            Persistenz-Baseline — also „was wäre, wenn wir einfach die
            letzte Woche wiederholt hätten". Beachte den <b>Pilot-Kontext</b>:
            in Post-Saison-Wochen hat die Persistenz-Baseline einen
            Saison-Bonus (gestern=heute ist dann fast immer richtig),
            weshalb Peak-Wochen den ehrlichen Qualitätsbeweis liefern —
            dort schlägt das Modell die Baseline regelmäßig um 3-5×
            PR-AUC und liefert 5-10 Tage Lead-Zeit.
          </>
        }
      />

      {(() => {
        const decisionBacktest =
          snapshot.mediaSpendingTruth?.decision_backtest ??
          snapshot.mediaSpendingTruth?.decisionBacktest ??
          null;
        const researchOnly = firstBool(
          validation?.research_only,
          validation?.researchOnly,
        ) ?? true;
        const candidateStatus = firstText(
          validation?.candidate_status,
          validation?.candidateStatus,
          snapshot.mediaSpendingTruth?.forecast_evidence,
          snapshot.mediaSpendingTruth?.forecastEvidence,
          snapshot.modelStatus?.forecastReadiness,
        ) ?? 'review';
        const onsetGain = firstNumber(
          validation?.onset_gain_days,
          validation?.onsetGainDays,
          headline?.median_lead_days ?? null,
          snapshot.modelStatus?.lead?.bestLagDays ?? null,
        );
        const falseWarningRisk = firstNumber(
          validation?.false_warning_risk,
          validation?.falseWarningRisk,
        );
        const phaseAccuracy = firstNumber(
          validation?.phase_accuracy,
          validation?.phaseAccuracy,
          headline?.precision_at_top3 ?? null,
        );
        const recommendation = firstText(
          validation?.recommendation,
          decisionBacktest?.decision_backtest_passed === true
            ? 'go_for_simulation'
            : null,
        ) ?? 'review';

        return (
          <div className="validation-panel">
            <div className="validation-head">
              <div>
                <div className="validation-kicker">Research-Layer</div>
                <h3>SurvStat-only vs AMELAG + SurvStat</h3>
              </div>
              <span className="research-chip">
                {researchOnly ? 'research_only=true' : 'Budget-Gate angebunden'}
              </span>
            </div>
            <div className="validation-grid">
              <div>
                <span className="metric-label">Kandidatenstatus</span>
                <span className="metric-value">{candidateStatus}</span>
                <span className="metric-note">noch kein direkter Budget-Effekt</span>
              </div>
              <div>
                <span className="metric-label">Früherkennung</span>
                <span className="metric-value">
                  {onsetGain !== null ? `${onsetGain} d` : '—'}
                </span>
                <span className="metric-note">Früherkennung gegen Meldewesen</span>
              </div>
              <div>
                <span className="metric-label">Fehlwarnrisiko</span>
                <span className="metric-value">{pctLabel(falseWarningRisk)}</span>
                <span className="metric-note">nur Research, kein Budgettrigger</span>
              </div>
              <div>
                <span className="metric-label">Phasentreffer</span>
                <span className="metric-value">{pctLabel(phaseAccuracy)}</span>
                <span className="metric-note">Wellenphase richtig getroffen</span>
              </div>
              <div>
                <span className="metric-label">Empfehlung</span>
                <span className="metric-value">{recommendation}</span>
                <span className="metric-note">Simulation vor operativer Freigabe</span>
              </div>
            </div>
          </div>
        );
      })()}

      <div className="backtest-head">
        <div className="bt-monument is-primary">
          <div className="label">Top-3 richtig</div>
          <div className="num">
            {prec !== null ? (prec * 100).toFixed(1) : '—'}
            <span className="unit">%</span>
          </div>
          <div className="ref">
            vs. Persistenz{' '}
            <b>
              {persistPrec !== null ? `${(persistPrec * 100).toFixed(1)} %` : '—'}
            </b>
            {' · '}
            {ppDelta !== null ? (
              <span style={{ color: 'var(--signal)', fontWeight: 500 }}>
                {ppDelta >= 0 ? '+' : ''}
                {ppDelta.toFixed(1)}pp
              </span>
            ) : (
              '—'
            )}
            <br />
            In so vielen Wochen lag die richtige Region in unseren Top 3.
          </div>
        </div>

        <div className="bt-monument">
          <div className="label">PR-AUC Gesamt</div>
          <div className="num">{fmtPrAuc(prAuc)}</div>
          <div className="ref">
            vs. Persistenz{' '}
            <b>{fmtPrAuc(persistPrAuc)}</b>
            {' · '}
            {multiplier !== null ? (
              <span style={{ color: 'var(--signal)', fontWeight: 500 }}>
                {multiplier.toFixed(1)}×
              </span>
            ) : (
              '—'
            )}{' '}
            besser
          </div>
        </div>

        <div className="bt-monument">
          <div className="label">Median Lead-Zeit</div>
          <div className="num">
            {medianLead !== null ? medianLead : '—'}
            <span className="unit">d</span>
          </div>
          <div className="ref">
            gegen Meldewesen · Horizont <b>{data?.horizon_days ?? '—'}d</b>
          </div>
        </div>
      </div>

      <p className="backtest-ranking-note">
        Lies das Ranking als historische Modellgüte pro Region — nicht als
        heutige Welle. Hamburg steht heute oben (§I), historisch unten (hier).
        Das ist kein Widerspruch: das Ranking misst Vergangenheit, das Signal
        misst Gegenwart.
      </p>

      <div className="bt-controls">
        <div className="virus-switcher" role="tablist">
          {VIRUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={virusTyp === opt.value ? 'active' : ''}
              onClick={() => setVirusTyp(opt.value)}
              disabled={loading}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="bt-window">
          Fenster ·{' '}
          <b>
            {fmtDateDE(window?.start ?? null)} →{' '}
            {fmtDateDE(window?.end ?? null)}
          </b>
          {' · '}
          <b>{window?.folds ?? '—'}</b> Folds · Walk-forward
        </div>
      </div>

      <div className="roster">
        <div className="roster-row head">
          <span className="rank">#</span>
          <span>Bundesland</span>
          <span style={{ textAlign: 'right' }}>PR-AUC</span>
          <span />
          <span style={{ textAlign: 'right' }}>Lead-Days</span>
        </div>
        {roster.length === 0 && !loading && (
          <div
            style={{
              padding: '32px 0',
              fontStyle: 'italic',
              color: 'var(--ink-40)',
              fontFamily: "var(--font-display)",
            }}
          >
            Keine Backtest-Werte verfügbar — Roster leer.
          </div>
        )}
        {roster.map((r, i) => {
          const score = r.pr_auc ?? 0;
          const pct = maxPrAuc > 0 ? (score / maxPrAuc) * 100 : 0;
          return (
            <div className="roster-row" key={r.code}>
              <span className="rank">{String(i + 1).padStart(2, '0')}</span>
              <span className="name">{r.name}</span>
              <span className="score">{fmtPrAuc(r.pr_auc)}</span>
              <span className="bar-wrap">
                <span className="bar" style={{ width: `${pct}%` }} />
              </span>
              <span className="lead">—</span>
            </div>
          );
        })}
      </div>

      <div className="barcode-section">
        <div className="barcode-head">
          <div className="barcode-title">Wöchentlicher Hit-Barcode</div>
          <div className="instr-kicker">Hover für Kalenderwoche</div>
        </div>
        <p className="barcode-reader-note">
          <b>So liest du den Barcode:</b> Jeder Balken = eine Woche im
          Walk-forward-Backtest. <b style={{ color: 'var(--signal, #c2542a)' }}>Orange</b>{' '}
          = das Modell hatte die Welle in der Top-3.{' '}
          <b>Dunkel</b> = Top-3 verfehlt. <b>Grau</b> = <b>noch nicht
          bewertet</b> — die Backtest-Artefakte enden mit dem letzten
          Retraining-Zyklus. SURVSTAT-Vergleichsdaten sind aktuell, aber
          Wochen nach dem letzten Training-Stichtag warten auf den
          nächsten Monats-Retrain, um eingerechnet zu werden. Grau ist{' '}
          <b>kein Miss</b>.
        </p>
        {(() => {
          const hits = barcodeEntries.filter((e) => e.state === 'hit').length;
          const misses = barcodeEntries.filter((e) => e.state === 'miss').length;
          const nodata = barcodeEntries.filter((e) => e.state === 'nodata').length;
          const evaluable = hits + misses;
          const hitPct = evaluable > 0 ? Math.round((hits / evaluable) * 100) : null;
          return (
            <div className="barcode-scoreboard">
              <div className="score-cell hit-rate">
                <div className="score-label">Trefferquote · wo Vergleichsdaten existieren</div>
                <div className="score-value">
                  {hitPct !== null ? `${hitPct} %` : '—'}
                  <span className="score-denom">
                    {' '}({hits} von {evaluable})
                  </span>
                </div>
              </div>
              <div className="score-cell">
                <div className="score-label">Misses</div>
                <div className="score-value">
                  {misses}
                  {misses === 0 ? <span className="score-denom"> · keine</span> : null}
                </div>
              </div>
              <div className="score-cell gap">
                <div className="score-label">
                  Noch nicht bewertet · {nodata} Wochen
                </div>
                <div className="score-value small">
                  Retraining ausstehend
                  <span className="score-denom"> · nicht „Miss"</span>
                </div>
              </div>
            </div>
          );
        })()}
        <div className="barcode-wrap">
          {barcodeEntries.length === 0 && (
            <div
              style={{
                padding: 24,
                fontStyle: 'italic',
                color: 'var(--ink-40)',
                fontFamily: "var(--font-display)",
                width: '100%',
                textAlign: 'center',
              }}
            >
              Keine Backtest-Wochen verfügbar.
            </div>
          )}
          {barcodeEntries.map((e, i) => (
            <div
              key={i}
              className={`barcode-bar ${e.state}`}
              data-wk={e.label}
            />
          ))}
        </div>
        <div className="barcode-legend">
          <span>
            <span className="sw hit" />Hit · Top-3 traf Welle
          </span>
          <span>
            <span className="sw miss" />Miss · Top-3 verfehlt
          </span>
          <span>
            <span className="sw nodata" />Noch nicht bewertet · wartet auf Retraining
          </span>
        </div>
      </div>
    </section>
  );
};

export default BacktestSection;
