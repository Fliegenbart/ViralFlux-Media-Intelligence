import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';

import { CampaignChannelPlanItem, RecommendationDetail, WorkflowStatus } from '../types/media';

const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'Draft',
  READY: 'Ready',
  APPROVED: 'Approved',
  ACTIVATED: 'Activated',
  DISMISSED: 'Dismissed',
  EXPIRED: 'Expired',
};

const TRANSITIONS: Record<string, WorkflowStatus[]> = {
  DRAFT: ['READY', 'DISMISSED'],
  READY: ['APPROVED', 'DISMISSED'],
  APPROVED: ['ACTIVATED', 'DISMISSED'],
  ACTIVATED: ['EXPIRED', 'DISMISSED'],
  DISMISSED: [],
  EXPIRED: [],
};

const toLocalInput = (iso?: string | null) => {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
};

const CampaignRecommendationDetail: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statusSaving, setStatusSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<RecommendationDetail | null>(null);

  const [activationStart, setActivationStart] = useState('');
  const [activationEnd, setActivationEnd] = useState('');
  const [weeklyBudget, setWeeklyBudget] = useState<number>(0);
  const [budgetShiftPct, setBudgetShiftPct] = useState<number>(0);
  const [channelPlan, setChannelPlan] = useState<CampaignChannelPlanItem[]>([]);
  const [primaryKpi, setPrimaryKpi] = useState('');
  const [secondaryKpis, setSecondaryKpis] = useState('');
  const [successCriteria, setSuccessCriteria] = useState('');

  const hydrateEditor = useCallback((payload: RecommendationDetail) => {
    const pack = payload.campaign_pack || {};
    const activation = pack.activation_window || {};
    const budget = pack.budget_plan || {};
    const measurement = pack.measurement_plan || {};

    setActivationStart(toLocalInput(activation.start));
    setActivationEnd(toLocalInput(activation.end));
    setWeeklyBudget(Number(budget.weekly_budget_eur || 0));
    setBudgetShiftPct(Number(budget.budget_shift_pct || payload.budget_shift_pct || 0));

    if (Array.isArray(pack.channel_plan) && pack.channel_plan.length > 0) {
      setChannelPlan(pack.channel_plan.map((row) => ({
        channel: row.channel,
        role: row.role || 'reach',
        share_pct: Number(row.share_pct || 0),
        formats: row.formats || [],
        message_angle: row.message_angle,
        kpi_primary: row.kpi_primary,
        kpi_secondary: row.kpi_secondary || [],
      })));
    } else {
      const fallback = Object.entries(payload.channel_mix || {}).map(([channel, share]) => ({
        channel,
        role: 'reach',
        share_pct: Number(share),
        formats: [],
        message_angle: '',
        kpi_primary: '',
        kpi_secondary: [],
      }));
      setChannelPlan(fallback);
    }

    setPrimaryKpi(measurement.primary_kpi || '');
    setSecondaryKpis((measurement.secondary_kpis || []).join(', '));
    setSuccessCriteria(measurement.success_criteria || '');
  }, []);

  const loadDetail = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setDetail(data);
      hydrateEditor(data);
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : 'Unbekannter Fehler');
    } finally {
      setLoading(false);
    }
  }, [hydrateEditor, id]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const channelShareSum = useMemo(
    () => channelPlan.reduce((sum, row) => sum + Number(row.share_pct || 0), 0),
    [channelPlan]
  );

  const updateChannelShare = (channel: string, value: number) => {
    setChannelPlan((prev) =>
      prev.map((row) => (row.channel === channel ? { ...row, share_pct: Number(value) } : row))
    );
  };

  const saveCampaign = async () => {
    if (!id || !detail) return;
    setSaving(true);
    setError(null);

    try {
      if (!activationStart || !activationEnd) {
        throw new Error('Aktivierungsfenster ist unvollständig.');
      }
      if (new Date(activationStart).getTime() > new Date(activationEnd).getTime()) {
        throw new Error('Aktivierungsstart liegt nach dem Ende.');
      }
      if (Math.abs(channelShareSum - 100) > 0.2) {
        throw new Error('Channel-Shares müssen in Summe 100 ergeben.');
      }
      if (weeklyBudget < 0 || budgetShiftPct < 0) {
        throw new Error('Budgetwerte dürfen nicht negativ sein.');
      }

      const payload = {
        activation_window: {
          start: new Date(activationStart).toISOString(),
          end: new Date(activationEnd).toISOString(),
        },
        budget: {
          weekly_budget_eur: Number(weeklyBudget),
          budget_shift_pct: Number(budgetShiftPct),
        },
        channel_plan: channelPlan.map((row) => ({
          channel: row.channel,
          role: row.role || 'reach',
          share_pct: Number(row.share_pct),
          formats: row.formats || [],
          message_angle: row.message_angle || '',
          kpi_primary: row.kpi_primary || '',
          kpi_secondary: row.kpi_secondary || [],
        })),
        kpi_targets: {
          primary_kpi: primaryKpi,
          secondary_kpis: secondaryKpis
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean),
          success_criteria: successCriteria,
        },
      };

      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}/campaign`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${res.status}`);
      }

      await loadDetail();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unbekannter Fehler');
    } finally {
      setSaving(false);
    }
  };

  const updateStatus = async (nextStatus: WorkflowStatus) => {
    if (!id) return;
    setStatusSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      await loadDetail();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unbekannter Fehler');
    } finally {
      setStatusSaving(false);
    }
  };

  if (loading) {
    return <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8 text-slate-400">Lade Kampagnen-Detail...</div>;
  }

  if (error && !detail) {
    return (
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8">
        <div className="card p-5 text-red-400">{error}</div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8">
        <div className="card p-5 text-slate-400">Recommendation nicht gefunden.</div>
      </div>
    );
  }

  const status = String(detail.status || 'DRAFT').toUpperCase();
  const nextTransitions = TRANSITIONS[status] || [];

  return (
    <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="card p-4 sm:p-5">
        <div className="flex flex-wrap gap-3 items-center justify-between">
          <div>
            <button onClick={() => navigate('/dashboard?tab=recommendations')} className="text-xs text-cyan-300 hover:text-cyan-200 mb-2">
              ← Zurück zu KI-Empfehlungen
            </button>
            <h1 className="text-xl font-semibold text-white">{detail.campaign_name || detail.campaign_preview?.campaign_name || `${detail.brand} · ${detail.product}`}</h1>
            <p className="text-xs text-slate-400 mt-1">
              {detail.type} · {detail.brand} · {detail.product} · ID {detail.id}
            </p>
          </div>
          <div className="text-right">
            <div className="text-[11px] text-slate-500">Status</div>
            <div className="text-sm font-semibold text-cyan-300">{STATUS_LABELS[status] || status}</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="card p-5 space-y-4">
            <h2 className="text-base font-semibold text-white">Kampagnen-Editor</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="text-xs text-slate-300">
                Aktivierung Start
                <input type="datetime-local" className="media-input mt-1" value={activationStart} onChange={(e) => setActivationStart(e.target.value)} />
              </label>
              <label className="text-xs text-slate-300">
                Aktivierung Ende
                <input type="datetime-local" className="media-input mt-1" value={activationEnd} onChange={(e) => setActivationEnd(e.target.value)} />
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="text-xs text-slate-300">
                Wochenbudget (EUR)
                <input type="number" min={0} className="media-input mt-1" value={weeklyBudget} onChange={(e) => setWeeklyBudget(Number(e.target.value))} />
              </label>
              <label className="text-xs text-slate-300">
                Budget-Shift (%)
                <input type="number" min={0} max={100} className="media-input mt-1" value={budgetShiftPct} onChange={(e) => setBudgetShiftPct(Number(e.target.value))} />
              </label>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-white">Channel-Split</h3>
                <span className={`text-xs ${Math.abs(channelShareSum - 100) <= 0.2 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  Summe: {channelShareSum.toFixed(1)}%
                </span>
              </div>
              <div className="space-y-2">
                {channelPlan.map((row) => (
                  <div key={row.channel} className="grid grid-cols-[1fr_120px] items-center gap-3">
                    <div className="text-sm text-slate-300">{row.channel.toUpperCase()}</div>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={0.1}
                      className="media-input"
                      value={row.share_pct}
                      onChange={(e) => updateChannelShare(row.channel, Number(e.target.value))}
                    />
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3">
              <label className="text-xs text-slate-300">
                Primary KPI
                <input className="media-input mt-1" value={primaryKpi} onChange={(e) => setPrimaryKpi(e.target.value)} />
              </label>
              <label className="text-xs text-slate-300">
                Secondary KPIs (comma-separated)
                <input className="media-input mt-1" value={secondaryKpis} onChange={(e) => setSecondaryKpis(e.target.value)} />
              </label>
              <label className="text-xs text-slate-300">
                Success Criteria
                <textarea className="media-input mt-1 min-h-[90px]" value={successCriteria} onChange={(e) => setSuccessCriteria(e.target.value)} />
              </label>
            </div>

            {error && <div className="text-xs text-red-400">{error}</div>}

            <div className="flex flex-wrap gap-2">
              <button onClick={saveCampaign} className="media-button" disabled={saving}>
                {saving ? 'Speichere...' : 'Kampagnenplan speichern'}
              </button>
            </div>
          </div>

          <div className="card p-5 space-y-3">
            <h2 className="text-base font-semibold text-white">Workflow</h2>
            <div className="flex flex-wrap gap-2">
              {nextTransitions.map((next) => (
                <button key={next} onClick={() => updateStatus(next)} className="media-button secondary" disabled={statusSaving}>
                  {statusSaving ? 'Aktualisiere...' : `Auf ${STATUS_LABELS[next] || next} setzen`}
                </button>
              ))}
              {nextTransitions.length === 0 && (
                <div className="text-xs text-slate-500">Keine weiteren Status-Transitionen verfügbar.</div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="card p-5 space-y-3">
            <h2 className="text-sm font-semibold text-white">Trigger-Evidenz (read-only)</h2>
            <div className="text-xs text-slate-400">Quelle: {detail.trigger_evidence?.source || '-'}</div>
            <div className="text-xs text-slate-400">Event: {detail.trigger_evidence?.event || '-'}</div>
            <div className="text-xs text-slate-400">Lead-Time: {detail.trigger_evidence?.lead_time_days ?? '-'} Tage</div>
            <div className="text-xs text-slate-400">Confidence: {detail.trigger_evidence?.confidence ? `${Math.round(detail.trigger_evidence.confidence * 100)}%` : '-'}</div>
            <div className="text-xs text-slate-400">
              PeixEpiScore: {detail.peix_context?.score ?? detail.campaign_pack?.peix_context?.score ?? '-'}
              {' '}({detail.peix_context?.band ?? detail.campaign_pack?.peix_context?.band ?? '-'})
            </div>
            <div className="text-xs text-slate-400">
              Impact: {detail.peix_context?.impact_probability ?? detail.campaign_pack?.peix_context?.impact_probability ?? '-'}%
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">{detail.trigger_evidence?.details || detail.reason || '-'}</p>
            {Array.isArray(detail.peix_context?.drivers || detail.campaign_pack?.peix_context?.drivers) && (
              <div className="text-xs text-slate-400">
                Treiber:{' '}
                {(detail.peix_context?.drivers || detail.campaign_pack?.peix_context?.drivers || [])
                  .slice(0, 3)
                  .map((driver) => `${driver.label} ${driver.strength_pct}%`)
                  .join(' · ')}
              </div>
            )}
          </div>

          <div className="card p-5 space-y-3">
            <h2 className="text-sm font-semibold text-white">Quick Facts</h2>
            <div className="text-xs text-slate-400">Region: {detail.campaign_pack?.targeting?.region_scope || '-'}</div>
            <div className="text-xs text-slate-400">Urgency Score: {detail.urgency_score ?? '-'}</div>
            <div className="text-xs text-slate-400">Empfohlenes Produkt: {detail.recommended_product || detail.product || '-'}</div>
            <div className="text-xs text-slate-400">
              Mapping-Status: {detail.mapping_status || detail.campaign_pack?.product_mapping?.mapping_status || '-'}
            </div>
            <div className="text-xs text-slate-400">
              Lageklasse: {detail.condition_label || detail.campaign_pack?.product_mapping?.condition_label || '-'}
            </div>
            <div className="text-xs text-slate-400">Primary KPI: {detail.primary_kpi || detail.campaign_pack?.measurement_plan?.primary_kpi || '-'}</div>
            <div className="text-xs text-slate-400">
              Created: {detail.created_at ? format(parseISO(detail.created_at), 'dd.MM.yyyy HH:mm', { locale: de }) : '-'}
            </div>
            <div className="text-xs text-slate-400">
              Updated: {detail.updated_at ? format(parseISO(detail.updated_at), 'dd.MM.yyyy HH:mm', { locale: de }) : '-'}
            </div>
          </div>

          {Array.isArray(detail.campaign_pack?.execution_checklist) && detail.campaign_pack.execution_checklist.length > 0 && (
            <div className="card p-5 space-y-3">
              <h2 className="text-sm font-semibold text-white">Execution Checklist</h2>
              <ul className="space-y-2">
                {detail.campaign_pack.execution_checklist.map((item, idx) => (
                  <li key={`${item.task}-${idx}`} className="text-xs text-slate-300">
                    <span className="text-slate-400">[{item.owner || 'Team'}]</span> {item.task}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CampaignRecommendationDetail;
