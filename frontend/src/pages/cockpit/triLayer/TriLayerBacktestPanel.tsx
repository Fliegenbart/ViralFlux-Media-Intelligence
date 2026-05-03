import React, { useEffect, useMemo, useState } from 'react';

import type { TriLayerBacktestReport, TriLayerBacktestStatus } from './types';

const BASELINES = [
  'persistence',
  'clinical_only',
  'wastewater_only',
  'wastewater_plus_clinical',
  'forecast_proxy_only',
  'tri_layer_epi_no_sales',
];
const POLL_INTERVAL_MS = 250;

const METRICS: Array<[keyof TriLayerBacktestReport['metrics'], string]> = [
  ['number_of_cutoffs', 'number_of_cutoffs'],
  ['onset_detection_gain', 'onset_detection_gain'],
  ['peak_lead_time', 'peak_lead_time'],
  ['false_early_warning_rate', 'false_early_warning_rate'],
  ['phase_accuracy', 'phase_accuracy'],
  ['precision_at_top3', 'precision_at_top3'],
  ['recall_at_top3', 'recall_at_top3'],
  ['pr_auc', 'pr_auc'],
  ['brier_score', 'brier_score'],
  ['ece', 'ece'],
  ['sales_lift_predictiveness', 'sales_lift_predictiveness'],
  ['budget_regret_reduction', 'budget_regret_reduction'],
  ['calibration_error', 'calibration_error'],
];

function formatMetric(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'not evaluated';
  return Number.isInteger(value) ? String(value) : value.toFixed(3);
}

function formatText(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'not evaluated';
  if (typeof value === 'number') return formatMetric(value);
  return String(value);
}

const MODEL_METRICS: Array<[string, string]> = [
  ['onset_detection_rate', 'onset detection'],
  ['false_early_warning_rate', 'false warnings'],
  ['precision_at_top3', 'precision top3'],
  ['recall_at_top3', 'recall top3'],
  ['brier_score', 'brier'],
  ['pr_auc', 'PR AUC'],
];

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: 'include',
    headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} — Tri-Layer backtest request failed`);
  }
  return (await response.json()) as T;
}

export const TriLayerBacktestPanel: React.FC = () => {
  const [virusTyp, setVirusTyp] = useState('Influenza A');
  const [horizonDays, setHorizonDays] = useState<3 | 7 | 14>(7);
  const [startDate, setStartDate] = useState('2024-10-01');
  const [endDate, setEndDate] = useState('2026-04-30');
  const [includeSales, setIncludeSales] = useState(false);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<TriLayerBacktestReport | null>(null);

  const latestUrl = useMemo(() => {
    const params = new URLSearchParams();
    params.set('virus_typ', virusTyp);
    params.set('horizon_days', String(horizonDays));
    return `/api/v1/media/cockpit/tri-layer/backtest/latest?${params.toString()}`;
  }, [virusTyp, horizonDays]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    void fetchJson<{ report: TriLayerBacktestReport | null }>(latestUrl)
      .then((payload) => {
        if (!cancelled) setReport(payload.report ?? null);
      })
      .catch((exc: Error) => {
        if (!cancelled) setError(exc.message);
      });
    return () => {
      cancelled = true;
    };
  }, [latestUrl]);

  const pollStatus = async (statusUrl: string): Promise<void> => {
    const payload = await fetchJson<TriLayerBacktestStatus>(statusUrl);
    setStatus(payload.status);
    if (payload.status === 'SUCCESS' && payload.report) {
      setReport(payload.report);
      return;
    }
    if (payload.status === 'FAILURE') {
      setError(payload.error || 'Tri-Layer backtest failed.');
      return;
    }
    window.setTimeout(() => {
      void pollStatus(statusUrl);
    }, POLL_INTERVAL_MS);
  };

  const startBacktest = async () => {
    setStatus('starting');
    setError(null);
    const payload = await fetchJson<{ status: string; run_id: string; status_url: string }>(
      '/api/v1/media/cockpit/tri-layer/backtest',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          virus_typ: virusTyp,
          brand: 'gelo',
          horizon_days: horizonDays,
          start_date: startDate,
          end_date: endDate,
          mode: 'historical_cutoff',
          include_sales: includeSales,
        }),
      },
    );
    setStatus(payload.status);
    await pollStatus(payload.status_url);
  };

  return (
    <section className="tri-layer-panel tri-layer-backtest">
      <div className="tri-layer-section-head">
        <div>
          <div className="tri-layer-kicker">Backtest</div>
          <h2>Research backtest report</h2>
        </div>
        <p>Research backtest only. Does not affect live cockpit decisions.</p>
      </div>

      <div className="tri-layer-backtest-copy">
        <p>include_sales=false means Budget Permission cannot exceed shadow_only.</p>
        <p>Budget Isolation comparison measures whether the gate reduces false budget triggers.</p>
      </div>

      <div className="tri-layer-backtest-controls">
        <label>
          Virus
          <select value={virusTyp} onChange={(event) => setVirusTyp(event.target.value)}>
            <option>Influenza A</option>
            <option>Influenza B</option>
            <option>RSV A</option>
            <option>SARS-CoV-2</option>
          </select>
        </label>
        <label>
          Horizon
          <select value={horizonDays} onChange={(event) => setHorizonDays(Number(event.target.value) as 3 | 7 | 14)}>
            <option value={3}>3</option>
            <option value={7}>7</option>
            <option value={14}>14</option>
          </select>
        </label>
        <label>
          Start date
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          End date
          <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
        <label className="tri-layer-checkbox">
          <input
            type="checkbox"
            checked={includeSales}
            onChange={(event) => setIncludeSales(event.target.checked)}
          />
          include_sales
        </label>
        <button type="button" onClick={() => void startBacktest()} disabled={status === 'starting' || status === 'STARTED'}>
          Start backtest
        </button>
      </div>

      <div className="tri-layer-backtest-status">Status: {status}</div>
      {error ? <div className="tri-layer-backtest-error" role="alert">{error}</div> : null}

      {!report ? (
        <div className="tri-layer-empty">No completed Tri-Layer backtest report yet.</div>
      ) : (
        <>
          <div className="tri-layer-table-wrap">
            <table className="tri-layer-table">
              <thead>
                <tr>
                  <th scope="col">Metric</th>
                  <th scope="col">Value</th>
                </tr>
              </thead>
              <tbody>
                {METRICS.map(([key, label]) => (
                  <tr key={key}>
                    <td>{label}</td>
                    <td>{formatMetric(report.metrics[key] as number | null | undefined)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section className="tri-layer-validation" aria-label="Scientific Validation">
            <div className="tri-layer-section-head">
              <div>
                <div className="tri-layer-kicker">Scientific Validation</div>
                <h2>Scientific Validation</h2>
              </div>
              <p>Source ablations show whether a source adds value. Null metrics are shown as not evaluated.</p>
            </div>

            <div className="tri-layer-validation-grid">
              {Object.entries(report.source_availability || {}).map(([source, item]) => (
                <div key={source} className="tri-layer-validation-source">
                  <strong>{source}</strong>
                  <span>{formatText(item.status)}</span>
                  <span>rows {formatMetric(item.rows as number | null | undefined)}</span>
                </div>
              ))}
            </div>

            <div className="tri-layer-table-wrap">
              <table className="tri-layer-table tri-layer-table--compact">
                <thead>
                  <tr>
                    <th scope="col">Model</th>
                    {MODEL_METRICS.map(([, label]) => (
                      <th key={label} scope="col">{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {BASELINES.map((modelName) => {
                    const item = report.models?.[modelName] ?? {};
                    return (
                      <tr key={modelName}>
                        <td>{modelName}</td>
                        {MODEL_METRICS.map(([key]) => (
                          <td key={key}>{formatMetric(item[key as keyof typeof item] as number | null | undefined)}</td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="tri-layer-claims">
              <div>
                <h3>Allowed Claims</h3>
                {report.allowed_claims?.length ? (
                  <ul>
                    {report.allowed_claims.map((claim) => <li key={claim}>{claim}</li>)}
                  </ul>
                ) : (
                  <p>not evaluated</p>
                )}
              </div>
              <div>
                <h3>Forbidden Claims</h3>
                {report.forbidden_claims?.length ? (
                  <ul>
                    {report.forbidden_claims.map((claim) => <li key={claim}>{claim}</li>)}
                  </ul>
                ) : (
                  <p>not evaluated</p>
                )}
              </div>
            </div>
          </section>

          <div className="tri-layer-gate-counts">
            {Object.entries(report.metrics.gate_transition_counts || {}).map(([gate, counts]) => (
              <div key={gate} className="tri-layer-gate-count">
                <strong>{gate}</strong>
                <span>pass {counts.pass ?? 0}</span>
                <span>watch {counts.watch ?? 0}</span>
                <span>fail {counts.fail ?? 0}</span>
                <span>not_available {counts.not_available ?? 0}</span>
              </div>
            ))}
          </div>

          <div className="tri-layer-table-wrap">
            <table className="tri-layer-table">
              <thead>
                <tr>
                  <th scope="col">Baseline</th>
                  <th scope="col">False budget triggers</th>
                  <th scope="col">Description</th>
                </tr>
              </thead>
              <tbody>
                {[
                  'persistence',
                  'clinical_only',
                  'wastewater_plus_clinical',
                  'tri_layer_without_budget_isolation',
                  'tri_layer_with_budget_isolation',
                ].map((baseline) => {
                  const item = report.baselines?.[baseline] ?? {};
                  return (
                    <tr key={baseline}>
                      <td>{baseline}</td>
                      <td>{formatMetric(item.false_budget_triggers as number | null | undefined)}</td>
                      <td>{String(item.description ?? '—')}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
};

export default TriLayerBacktestPanel;
