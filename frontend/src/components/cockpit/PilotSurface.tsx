import React from 'react';

import LoadingSkeleton from '../LoadingSkeleton';
import {
  PilotReadoutRegion,
  PilotReadoutResponse,
  PilotReadoutStatus,
  PilotSurfaceScope,
  PilotSurfaceStageFilter,
} from '../../types/media';
import { VIRUS_OPTIONS, formatCurrency, formatDateShort, formatDateTime, formatPercent } from './cockpitUtils';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  horizonDays: number;
  onHorizonChange: (value: number) => void;
  scope: PilotSurfaceScope;
  onScopeChange: (value: PilotSurfaceScope) => void;
  stage: PilotSurfaceStageFilter;
  onStageChange: (value: PilotSurfaceStageFilter) => void;
  pilotReadout: PilotReadoutResponse | null;
  loading: boolean;
}

const HORIZON_OPTIONS = [3, 5, 7] as const;
const STAGE_OPTIONS: Array<{ key: PilotSurfaceStageFilter; label: string }> = [
  { key: 'ALL', label: 'Alle Stages' },
  { key: 'Activate', label: 'Activate' },
  { key: 'Prepare', label: 'Prepare' },
  { key: 'Watch', label: 'Watch' },
];
const SCOPE_OPTIONS: Array<{ key: PilotSurfaceScope; label: string; copy: string }> = [
  { key: 'forecast', label: 'Forecast', copy: 'Epidemiologische Lage und Priorisierung' },
  { key: 'allocation', label: 'Allocation', copy: 'Budgetlogik und Freigabestatus' },
  { key: 'recommendation', label: 'Recommendation', copy: 'Produkt-, Keyword- und Kampagnenplan' },
  { key: 'evidence', label: 'Evidence', copy: 'Pilot-Evidenz, Gates und Readiness' },
];

function normalizeStage(value?: string | null): string {
  return String(value || '').trim().toLowerCase();
}

function matchesStage(value: string | undefined, filter: PilotSurfaceStageFilter): boolean {
  if (filter === 'ALL') return true;
  return normalizeStage(value) === normalizeStage(filter);
}

function readinessTone(value?: PilotReadoutStatus | null): React.CSSProperties {
  if (value === 'GO') {
    return {
      background: 'rgba(5, 150, 105, 0.12)',
      color: 'var(--status-success)',
      border: '1px solid rgba(5, 150, 105, 0.22)',
    };
  }
  if (value === 'WATCH') {
    return {
      background: 'rgba(245, 158, 11, 0.12)',
      color: 'var(--status-warning)',
      border: '1px solid rgba(245, 158, 11, 0.24)',
    };
  }
  return {
    background: 'rgba(239, 68, 68, 0.12)',
    color: 'var(--status-danger)',
    border: '1px solid rgba(239, 68, 68, 0.24)',
  };
}

function stageTone(value?: string | null): React.CSSProperties {
  const normalized = normalizeStage(value);
  if (normalized === 'activate') return readinessTone('GO');
  if (normalized === 'prepare') return readinessTone('WATCH');
  return {
    background: 'rgba(59, 130, 246, 0.10)',
    color: 'var(--status-info)',
    border: '1px solid rgba(59, 130, 246, 0.22)',
  };
}

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const normalized = value <= 1 ? value * 100 : value;
  return formatPercent(normalized, digits);
}

function scopeCopy(scope: PilotSurfaceScope): string {
  return SCOPE_OPTIONS.find((item) => item.key === scope)?.copy || '';
}

function sectionReadiness(
  pilotReadout: PilotReadoutResponse | null,
  scope: PilotSurfaceScope,
): PilotReadoutStatus {
  return pilotReadout?.run_context?.scope_readiness_by_section?.[scope] || 'NO_GO';
}

function RegionRow({ row }: { row: PilotReadoutRegion }) {
  return (
    <article
      style={{
        display: 'grid',
        gap: 12,
        padding: 16,
        borderRadius: 18,
        border: '1px solid rgba(148, 163, 184, 0.18)',
        background: 'rgba(255, 255, 255, 0.88)',
        boxShadow: '0 14px 40px rgba(15, 23, 42, 0.06)',
      }}
    >
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 18 }}>{row.region_name || row.region_code || '-'}</strong>
        <span style={{ ...stageTone(row.decision_stage), borderRadius: 999, padding: '5px 10px', fontSize: 12, fontWeight: 700 }}>
          {row.decision_stage || 'Watch'}
        </span>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 10,
        }}
      >
        <div>
          <div className="cockpit-label">Priority Score</div>
          <div className="cockpit-value">{formatFractionPercent(row.priority_score, row.priority_score != null && row.priority_score <= 1 ? 0 : 0)}</div>
        </div>
        <div>
          <div className="cockpit-label">Wave Chance</div>
          <div className="cockpit-value">{formatFractionPercent(row.event_probability, 0)}</div>
        </div>
        <div>
          <div className="cockpit-label">Budget</div>
          <div className="cockpit-value">{formatCurrency(row.budget_amount_eur)}</div>
        </div>
        <div>
          <div className="cockpit-label">Confidence</div>
          <div className="cockpit-value">{formatFractionPercent(row.confidence, 0)}</div>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 12,
        }}
      >
        <div>
          <div className="cockpit-label">Produktfokus</div>
          <div>{row.recommended_product || '-'}</div>
        </div>
        <div>
          <div className="cockpit-label">Keyword-/Campaign-Fokus</div>
          <div>{row.recommended_keywords || row.campaign_recommendation || '-'}</div>
        </div>
      </div>

      <div>
        <div className="cockpit-label">Warum jetzt?</div>
        <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
          {(row.reason_trace || []).slice(0, 3).map((item) => (
            <li key={item}>{item}</li>
          ))}
          {(!row.reason_trace || row.reason_trace.length === 0) && <li>Keine zusätzliche Klartext-Begründung vorhanden.</li>}
        </ul>
      </div>

      {(row.uncertainty_summary || row.budget_release_recommendation) && (
        <div
          style={{
            display: 'grid',
            gap: 6,
            padding: 12,
            borderRadius: 14,
            background: 'rgba(15, 23, 42, 0.04)',
          }}
        >
          {row.uncertainty_summary && (
            <div>
              <div className="cockpit-label">Unsicherheit</div>
              <div>{row.uncertainty_summary}</div>
            </div>
          )}
          {row.budget_release_recommendation && (
            <div>
              <div className="cockpit-label">Budget-Hinweis</div>
              <div>{row.budget_release_recommendation}</div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

const PilotSurface: React.FC<Props> = ({
  virus,
  onVirusChange,
  horizonDays,
  onHorizonChange,
  scope,
  onScopeChange,
  stage,
  onStageChange,
  pilotReadout,
  loading,
}) => {
  const regions = (pilotReadout?.operational_recommendations?.regions || []).filter((item) => matchesStage(item.decision_stage, stage));
  const visibleRegions = regions.length > 0
    ? regions
    : (pilotReadout?.operational_recommendations?.regions || []);
  const executive = pilotReadout?.executive_summary;
  const evidence = pilotReadout?.pilot_evidence;
  const gateSnapshot = pilotReadout?.run_context?.gate_snapshot;
  const currentScopeStatus = sectionReadiness(pilotReadout, scope);
  const evaluationRows = (evidence?.evaluation?.comparison_table || []) as Array<Record<string, unknown>>;

  if (loading) {
    return <LoadingSkeleton lines={10} />;
  }

  return (
    <div style={{ display: 'grid', gap: 24 }}>
      <section
        style={{
          display: 'grid',
          gap: 18,
          padding: 24,
          borderRadius: 28,
          background: 'linear-gradient(135deg, rgba(255,255,255,0.96), rgba(238, 244, 255, 0.94))',
          border: '1px solid rgba(148, 163, 184, 0.18)',
          boxShadow: '0 20px 50px rgba(15, 23, 42, 0.08)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'grid', gap: 8 }}>
            <span className="cockpit-label">PEIX / GELO Pilot Surface</span>
            <h1 style={{ margin: 0, fontSize: 32, lineHeight: 1.1 }}>Regional viral-wave guidance with one honest decision chain.</h1>
            <div style={{ color: 'var(--text-muted)' }}>
              {scopeCopy(scope)}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <span style={{ ...readinessTone(pilotReadout?.run_context?.scope_readiness), borderRadius: 999, padding: '8px 14px', fontSize: 12, fontWeight: 700 }}>
              {pilotReadout?.run_context?.scope_readiness || 'NO_GO'}
            </span>
            <span style={{ ...stageTone(executive?.decision_stage), borderRadius: 999, padding: '8px 14px', fontSize: 12, fontWeight: 700 }}>
              {executive?.decision_stage || 'Watch'}
            </span>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 12,
          }}
        >
          <label style={{ display: 'grid', gap: 6 }}>
            <span className="cockpit-label">Virus</span>
            <select value={virus} onChange={(event) => onVirusChange(event.target.value)}>
              {VIRUS_OPTIONS.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span className="cockpit-label">Horizon</span>
            <select value={horizonDays} onChange={(event) => onHorizonChange(Number(event.target.value))}>
              {HORIZON_OPTIONS.map((item) => (
                <option key={item} value={item}>{`h${item}`}</option>
              ))}
            </select>
          </label>
          <div style={{ display: 'grid', gap: 6 }}>
            <span className="cockpit-label">Scope</span>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {SCOPE_OPTIONS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => onScopeChange(item.key)}
                  style={{
                    borderRadius: 999,
                    padding: '8px 12px',
                    border: scope === item.key ? '1px solid rgba(10, 132, 255, 0.34)' : '1px solid rgba(148, 163, 184, 0.18)',
                    background: scope === item.key ? 'rgba(10, 132, 255, 0.10)' : '#fff',
                    color: 'inherit',
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: 'grid', gap: 6 }}>
            <span className="cockpit-label">Stage</span>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {STAGE_OPTIONS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => onStageChange(item.key)}
                  style={{
                    borderRadius: 999,
                    padding: '8px 12px',
                    border: stage === item.key ? '1px solid rgba(10, 132, 255, 0.34)' : '1px solid rgba(148, 163, 184, 0.18)',
                    background: stage === item.key ? 'rgba(10, 132, 255, 0.10)' : '#fff',
                    color: 'inherit',
                    fontWeight: 700,
                    cursor: 'pointer',
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 12,
          }}
        >
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Forecast</div>
            <div className="cockpit-value">{sectionReadiness(pilotReadout, 'forecast')}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Allocation</div>
            <div className="cockpit-value">{sectionReadiness(pilotReadout, 'allocation')}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Recommendation</div>
            <div className="cockpit-value">{sectionReadiness(pilotReadout, 'recommendation')}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Evidence</div>
            <div className="cockpit-value">{sectionReadiness(pilotReadout, 'evidence')}</div>
          </div>
        </div>
      </section>

      {pilotReadout?.empty_state?.code && pilotReadout.empty_state.code !== 'ready' && (
        <section
          style={{
            display: 'grid',
            gap: 8,
            padding: 18,
            borderRadius: 20,
            ...readinessTone(pilotReadout?.run_context?.scope_readiness),
          }}
        >
          <strong>{pilotReadout.empty_state.title}</strong>
          <span>{pilotReadout.empty_state.body}</span>
        </section>
      )}

      <section
        style={{
          display: 'grid',
          gap: 18,
          padding: 22,
          borderRadius: 24,
          background: '#fff',
          border: '1px solid rgba(148, 163, 184, 0.18)',
        }}
      >
        <div style={{ display: 'grid', gap: 6 }}>
          <span className="cockpit-label">Executive Summary</span>
          <h2 style={{ margin: 0 }}>What should we do now?</h2>
          <div style={{ color: 'var(--text-muted)' }}>{executive?.what_should_we_do_now || 'No executive summary is available yet.'}</div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 12,
          }}
        >
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Lead Region</div>
            <div className="cockpit-value">{executive?.top_regions?.[0]?.region_name || '-'}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Decision Stage</div>
            <div className="cockpit-value">{executive?.decision_stage || '-'}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Budget Release</div>
            <div className="cockpit-value">
              {executive?.budget_recommendation?.spend_enabled ? 'enabled' : 'hold'}
            </div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Recommended Budget</div>
            <div className="cockpit-value">
              {formatCurrency(executive?.budget_recommendation?.recommended_active_budget_eur)}
            </div>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: 12,
          }}
        >
          {(executive?.top_regions || []).slice(0, 3).map((item) => (
            <div
              key={item.region_code || item.region_name}
              style={{
                display: 'grid',
                gap: 8,
                padding: 16,
                borderRadius: 18,
                background: 'rgba(15, 23, 42, 0.03)',
                border: '1px solid rgba(148, 163, 184, 0.14)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                <strong>{item.region_name || item.region_code}</strong>
                <span style={{ ...stageTone(item.decision_stage), borderRadius: 999, padding: '4px 8px', fontSize: 12, fontWeight: 700 }}>
                  {item.decision_stage || 'Watch'}
                </span>
              </div>
              <div>Priority Score: {formatFractionPercent(item.priority_score, item.priority_score != null && item.priority_score <= 1 ? 0 : 0)}</div>
              <div>Wave Chance: {formatFractionPercent(item.event_probability, 0)}</div>
              <div>Budget: {formatCurrency(item.budget_amount_eur)}</div>
            </div>
          ))}
        </div>

        {(executive?.reason_trace || []).length > 0 && (
          <div>
            <div className="cockpit-label">Reason Trace</div>
            <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
              {(executive?.reason_trace || []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section
        style={{
          display: 'grid',
          gap: 18,
          padding: 22,
          borderRadius: 24,
          background: '#fff',
          border: '1px solid rgba(148, 163, 184, 0.18)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'grid', gap: 6 }}>
            <span className="cockpit-label">Operational Recommendations</span>
            <h2 style={{ margin: 0 }}>{pilotReadout?.operational_recommendations?.summary?.headline || 'Current recommendation chain'}</h2>
            <div style={{ color: 'var(--text-muted)' }}>{scopeCopy(scope)}</div>
          </div>
          <span style={{ ...readinessTone(currentScopeStatus), borderRadius: 999, padding: '8px 14px', fontSize: 12, fontWeight: 700 }}>
            {currentScopeStatus}
          </span>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 12,
          }}
        >
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Aktive Regionen</div>
            <div className="cockpit-value">{pilotReadout?.operational_recommendations?.summary?.activate_regions ?? '-'}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Prepare Regionen</div>
            <div className="cockpit-value">{pilotReadout?.operational_recommendations?.summary?.prepare_regions ?? '-'}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Watch Regionen</div>
            <div className="cockpit-value">{pilotReadout?.operational_recommendations?.summary?.watch_regions ?? '-'}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Bereite Empfehlungen</div>
            <div className="cockpit-value">{pilotReadout?.operational_recommendations?.summary?.ready_recommendations ?? '-'}</div>
          </div>
        </div>

        <div style={{ display: 'grid', gap: 14 }}>
          {visibleRegions.map((row) => (
            <RegionRow key={row.region_code || row.region_name} row={row} />
          ))}
          {visibleRegions.length === 0 && (
            <div
              style={{
                padding: 18,
                borderRadius: 18,
                border: '1px dashed rgba(148, 163, 184, 0.3)',
                color: 'var(--text-muted)',
              }}
            >
              Kein Regions-Output passt aktuell zum gewählten Stage-Filter.
            </div>
          )}
        </div>
      </section>

      <section
        style={{
          display: 'grid',
          gap: 18,
          padding: 22,
          borderRadius: 24,
          background: '#fff',
          border: '1px solid rgba(148, 163, 184, 0.18)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'grid', gap: 6 }}>
            <span className="cockpit-label">Pilot Evidence / Readiness</span>
            <h2 style={{ margin: 0 }}>Can PEIX defend this recommendation with GELO-facing evidence?</h2>
          </div>
          <span style={{ ...readinessTone(evidence?.scope_readiness), borderRadius: 999, padding: '8px 14px', fontSize: 12, fontWeight: 700 }}>
            {evidence?.scope_readiness || 'NO_GO'}
          </span>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 12,
          }}
        >
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Epidemiology</div>
            <div className="cockpit-value">{gateSnapshot?.epidemiology_status || '-'}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Commercial Data</div>
            <div className="cockpit-value">{gateSnapshot?.commercial_data_status || '-'}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Holdout</div>
            <div className="cockpit-value">{gateSnapshot?.holdout_status || '-'}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Budget Release</div>
            <div className="cockpit-value">{gateSnapshot?.budget_release_status || '-'}</div>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 16,
          }}
        >
          <div
            style={{
              display: 'grid',
              gap: 10,
              padding: 18,
              borderRadius: 18,
              background: 'rgba(15, 23, 42, 0.03)',
              border: '1px solid rgba(148, 163, 184, 0.14)',
            }}
          >
            <div className="cockpit-label">Letzte Live-Evaluation</div>
            <div>
              Variante: <strong>{evidence?.evaluation?.selected_experiment_name || 'noch keine archivierte Evaluation'}</strong>
            </div>
            <div>Gate: {evidence?.evaluation?.gate_outcome || '-'}</div>
            <div>Retained: {String(Boolean(evidence?.evaluation?.retained))}</div>
            <div>Calibrated Mode: {evidence?.evaluation?.calibration_mode || '-'}</div>
            <div>Generiert: {formatDateTime(evidence?.evaluation?.generated_at)}</div>
          </div>

          <div
            style={{
              display: 'grid',
              gap: 10,
              padding: 18,
              borderRadius: 18,
              background: 'rgba(15, 23, 42, 0.03)',
              border: '1px solid rgba(148, 163, 184, 0.14)',
            }}
          >
            <div className="cockpit-label">Aktuelle Blocker</div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {(gateSnapshot?.missing_requirements || []).map((item) => (
                <li key={item}>{item}</li>
              ))}
              {(gateSnapshot?.missing_requirements || []).length === 0 && <li>Keine zusätzlichen Produkt-Blocker gemeldet.</li>}
            </ul>
          </div>
        </div>

        {evaluationRows.length > 0 && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {['Role', 'Variant', 'P@Top3', 'AFP Rate', 'ECE', 'Brier', 'Gate', 'Retained'].map((label) => (
                    <th key={label} style={{ textAlign: 'left', padding: '10px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.18)' }}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {evaluationRows.map((row) => (
                  <tr key={`${String(row.role)}-${String(row.name)}`}>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.12)' }}>{String(row.role || '-')}</td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.12)' }}>{String(row.name || '-')}</td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.12)' }}>{typeof row.precision_at_top3 === 'number' ? row.precision_at_top3.toFixed(6) : '-'}</td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.12)' }}>{typeof row.activation_false_positive_rate === 'number' ? row.activation_false_positive_rate.toFixed(6) : '-'}</td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.12)' }}>{typeof row.ece === 'number' ? row.ece.toFixed(6) : '-'}</td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.12)' }}>{typeof row.brier === 'number' ? row.brier.toFixed(6) : '-'}</td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.12)' }}>{String(row.gate_outcome || '-')}</td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid rgba(148, 163, 184, 0.12)' }}>{String(row.retained ?? '-')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 12,
          }}
        >
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Coverage Weeks</div>
            <div className="cockpit-value">{gateSnapshot?.coverage_weeks ?? '-'}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Truth Freshness</div>
            <div className="cockpit-value">{String(gateSnapshot?.truth_freshness_state || '-')}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Validation Status</div>
            <div className="cockpit-value">{String(gateSnapshot?.validation_status || '-')}</div>
          </div>
          <div className="cockpit-stat-card">
            <div className="cockpit-label">Legacy Sunset</div>
            <div className="cockpit-value">{formatDateShort(evidence?.legacy_context?.sunset_date)}</div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default PilotSurface;
