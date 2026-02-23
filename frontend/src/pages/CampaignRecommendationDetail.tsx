import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useToast } from '../App';
import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';

import { CampaignChannelPlanItem, DecisionFact, RecommendationDetail, WorkflowStatus } from '../types/media';

const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'Entwurf',
  READY: 'Bereit',
  APPROVED: 'Freigegeben',
  ACTIVATED: 'Aktiviert',
  DISMISSED: 'Verworfen',
  EXPIRED: 'Abgelaufen',
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

const mappingLabel = (value?: string | null) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'approved') return 'Freigegeben';
  if (normalized === 'needs_review') return 'Review noetig';
  if (normalized === 'not_applicable') return 'Nicht anwendbar';
  return normalized || 'Unbekannt';
};

const mappingToneClass = (value?: string | null) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'approved') return 'text-emerald-700 bg-emerald-500/10 border border-emerald-500/30';
  if (normalized === 'needs_review') return 'text-amber-700 bg-amber-500/10 border border-amber-500/30';
  return 'text-slate-500 bg-slate-100 border border-slate-300';
};

const renderFactValue = (value: DecisionFact['value']) => {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'boolean') return value ? 'Ja' : 'Nein';
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return String(value);
    return value.toFixed(2);
  }
  return String(value);
};

const CampaignRecommendationDetail: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const { toast } = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statusSaving, setStatusSaving] = useState(false);
  const [regenSaving, setRegenSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<RecommendationDetail | null>(null);

  const [showEditor, setShowEditor] = useState(false);
  const [showTechDetails, setShowTechDetails] = useState(false);

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
        throw new Error('Aktivierungsfenster ist unvollstaendig.');
      }
      if (new Date(activationStart).getTime() > new Date(activationEnd).getTime()) {
        throw new Error('Aktivierungsstart liegt nach dem Ende.');
      }
      if (Math.abs(channelShareSum - 100) > 0.2) {
        throw new Error('Channel-Shares muessen in Summe 100 ergeben.');
      }
      if (weeklyBudget < 0 || budgetShiftPct < 0) {
        throw new Error('Budgetwerte duerfen nicht negativ sein.');
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

      toast('Kampagnenplan gespeichert', 'success');
      await loadDetail();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unbekannter Fehler';
      setError(msg);
      toast(`Speichern fehlgeschlagen: ${msg}`, 'error');
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
      toast(`Status auf ${STATUS_LABELS[nextStatus] || nextStatus} gesetzt`, 'success');
      await loadDetail();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unbekannter Fehler';
      setError(msg);
      toast(`Statusaenderung fehlgeschlagen: ${msg}`, 'error');
    } finally {
      setStatusSaving(false);
    }
  };

  const regenerateAiPlan = async () => {
    if (!id) return;
    setRegenSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}/regenerate-ai`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      toast('KI-Plan regeneriert', 'success');
      await loadDetail();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Unbekannter Fehler';
      setError(msg);
      toast(`Regenerierung fehlgeschlagen: ${msg}`, 'error');
    } finally {
      setRegenSaving(false);
    }
  };

  if (loading) {
    return <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8 bg-slate-50 text-slate-500">Lade Kampagnen-Detail...</div>;
  }

  if (error && !detail) {
    return (
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8 bg-slate-50">
        <div className="card p-5 text-red-500">{error}</div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8 bg-slate-50">
        <div className="card p-5 text-slate-500">Recommendation nicht gefunden.</div>
      </div>
    );
  }

  const status = String(detail.status || 'DRAFT').toUpperCase();
  const nextTransitions = TRANSITIONS[status] || [];

  const decision = detail.decision_brief;
  const facts: DecisionFact[] = Array.isArray(decision?.facts) ? (decision?.facts as DecisionFact[]) : [];
  const derivedFactKeys = new Set(['trigger_event', 'lead_time_days', 'peix_score', 'impact_probability', 'confidence_pct']);
  const hasSnapshotFacts = facts.some((fact) => !derivedFactKeys.has(String(fact.key || '')));

  const horizonMin = Number(decision?.horizon?.min_days || 7);
  const horizonMax = Number(decision?.horizon?.max_days || 14);
  const modelLeadTimeDays = decision?.horizon?.model_lead_time_days;

  const expectation = decision?.expectation || {};
  const recommendation = decision?.recommendation || {};
  const mappingStatus = String(
    recommendation.mapping_status
      || detail.mapping_status
      || detail.campaign_pack?.product_mapping?.mapping_status
      || ''
  ).toLowerCase();

  const primaryProduct = String(
    recommendation.primary_product || detail.recommended_product || detail.product || 'Produktfreigabe ausstehend'
  );
  const primaryRegion = String(recommendation.primary_region || detail.region || 'Gesamt');
  const secondaryRegions = Array.isArray(recommendation.secondary_regions) ? recommendation.secondary_regions : [];
  const secondaryProducts = Array.isArray(recommendation.secondary_products) ? recommendation.secondary_products : [];
  const needsReview = recommendation.action_required === 'review_mapping' || mappingStatus === 'needs_review';

  const confidencePct = expectation.confidence_pct !== undefined
    ? Number(expectation.confidence_pct)
    : (detail.confidence !== undefined ? Math.round(Number(detail.confidence || 0) * 100) : undefined);

  const conditionLabel = String(expectation.condition_label || detail.condition_label || detail.condition_key || '-');
  const impactProbability = expectation.impact_probability !== undefined
    ? Number(expectation.impact_probability)
    : detail.peix_context?.impact_probability;
  const peixScore = expectation.peix_score !== undefined
    ? Number(expectation.peix_score)
    : detail.peix_context?.score;

  const expectationRegionCodes = Array.isArray(expectation.region_codes) ? expectation.region_codes : (detail.region_codes || []);

  const summarySentence = decision?.summary_sentence
    || `Auf Basis der aktuellen Signale erwarten wir in den naechsten 7-14 Tagen ${conditionLabel} in ${primaryRegion}; daher empfehlen wir ${primaryProduct}.`;

  const openMappingReview = () => {
    const params = new URLSearchParams({ tab: 'product-intel', focus: 'audit' });
    if (primaryProduct) {
      params.set('product', primaryProduct);
    }
    navigate(`/dashboard?${params.toString()}`);
  };

  return (
    <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-6 space-y-6">
      <div className="card decision-header p-5 space-y-4">
        <button onClick={() => navigate('/dashboard?tab=recommendations')} className="text-xs text-indigo-500 hover:text-indigo-400">
          {'<-'} Zurueck zu KI-Empfehlungen
        </button>

        <div className="flex flex-wrap gap-3 items-start justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-slate-900" style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}>
              {detail.campaign_name || detail.campaign_preview?.campaign_name || `${detail.brand} · ${primaryProduct}`}
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              {detail.type} · {detail.brand} · ID {detail.id}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-2 py-1 text-[11px] rounded-full bg-indigo-500/10 text-indigo-600 border border-indigo-400/30">
              Status: {STATUS_LABELS[status] || status}
            </span>
            <span className={`px-2 py-1 text-[11px] rounded-full ${mappingToneClass(mappingStatus)}`}>
              Mapping: {mappingLabel(mappingStatus)}
            </span>
          </div>
        </div>

        <p className="text-sm text-slate-700 leading-relaxed">{summarySentence}</p>

        <div className="decision-rail text-xs text-slate-600">
          <span>Horizont: {horizonMin}-{horizonMax} Tage</span>
          {modelLeadTimeDays !== undefined && modelLeadTimeDays !== null && (
            <span>Modell Lead-Time: {modelLeadTimeDays} Tage</span>
          )}
          {confidencePct !== undefined && !Number.isNaN(confidencePct) && (
            <span>Konfidenz: {Math.round(confidencePct)}%</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="card p-5 space-y-3">
          <h2 className="text-base font-semibold text-slate-900">A. Das sind die Fakten</h2>
          {facts.length === 0 ? (
            <div className="text-xs text-slate-500">
              Keine quantifizierten Fakten vorhanden. Bitte Trigger-Snapshot pruefen.
            </div>
          ) : (
            <div className="fact-table">
              <table>
                <thead>
                  <tr>
                    <th>Fakt</th>
                    <th>Wert</th>
                    <th>Quelle</th>
                  </tr>
                </thead>
                <tbody>
                  {facts.map((fact, idx) => (
                    <tr key={`${fact.key}-${idx}`}>
                      <td>{fact.label}</td>
                      <td>{renderFactValue(fact.value)}</td>
                      <td>{fact.source || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {facts.length > 0 && !hasSnapshotFacts && (
            <div className="text-xs text-slate-400">
              Keine quantifizierten Fakten im Trigger-Snapshot; Interpretation basiert auf Evidenztext und Score-Fusion.
            </div>
          )}
        </div>

        <div className="card expectation-card p-5 space-y-3">
          <h2 className="text-base font-semibold text-slate-900">B. Erwartete Lage in den naechsten 7-14 Tagen</h2>
          <div className="text-xs text-slate-600">
            <div>Lageklasse: <span className="text-slate-900 font-semibold">{conditionLabel}</span></div>
            <div className="mt-1">
              Regionen: <span className="text-slate-900 font-semibold">{expectationRegionCodes.length > 0 ? expectationRegionCodes.join(', ') : primaryRegion}</span>
            </div>
            <div className="mt-1">
              Impact: <span className="text-slate-900 font-semibold">{impactProbability !== undefined ? `${Number(impactProbability).toFixed(1)}%` : '-'}</span>
            </div>
            <div className="mt-1">
              PeixEpiScore: <span className="text-slate-900 font-semibold">{peixScore !== undefined ? Number(peixScore).toFixed(1) : '-'}</span>
            </div>
            <div className="mt-1">
              Konfidenz: <span className="text-slate-900 font-semibold">{confidencePct !== undefined ? `${Math.round(confidencePct)}%` : '-'}</span>
            </div>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            {expectation.rationale || detail.mapping_reason || detail.reason || detail.trigger_evidence?.details || '-'}
          </p>
        </div>

        <div className="card recommendation-card p-5 space-y-3">
          <h2 className="text-base font-semibold text-slate-900" style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}>C. Daher empfehlen wir</h2>

          {needsReview && (
            <div className="action-banner-warning text-xs">
              Produkt-Mapping ist noch nicht freigegeben. Bitte zuerst im Audit pruefen und freigeben.
              <div className="mt-3">
                <button onClick={openMappingReview} className="media-button secondary">
                  Produkt-Mapping pruefen
                </button>
              </div>
            </div>
          )}

          <div className="soft-panel p-3">
            <div className="text-[11px] uppercase tracking-wider text-slate-500">Primaere Empfehlung</div>
            <div className="text-lg font-semibold text-slate-900 mt-1">{primaryProduct}</div>
            <div className="text-sm text-slate-600 mt-1">Region: {primaryRegion}</div>
          </div>

          <div className="grid grid-cols-1 gap-2 text-xs text-slate-600">
            <div>
              Sekundaere Regionen: <span className="text-slate-900">{secondaryRegions.length > 0 ? secondaryRegions.join(', ') : '-'}</span>
            </div>
            <div>
              Sekundaere Produkte: <span className="text-slate-900">{secondaryProducts.length > 0 ? secondaryProducts.join(', ') : '-'}</span>
            </div>
            <div>
              Budget-Shift: <span className="text-slate-900">{recommendation.budget_shift_pct !== undefined ? `${Number(recommendation.budget_shift_pct).toFixed(1)}%` : `${Number(budgetShiftPct || 0).toFixed(1)}%`}</span>
            </div>
            <div>
              Mapping-Begruendung: <span className="text-slate-900">{recommendation.mapping_reason || detail.mapping_reason || '-'}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card p-5 space-y-3">
        <h2 className="text-base font-semibold text-slate-900">Workflow</h2>
        <div className="flex flex-wrap gap-2">
          {nextTransitions.map((next) => (
            <button key={next} onClick={() => updateStatus(next)} className="media-button secondary" disabled={statusSaving}>
              {statusSaving ? 'Aktualisiere...' : `Auf ${STATUS_LABELS[next] || next} setzen`}
            </button>
          ))}
          {nextTransitions.length === 0 && (
            <div className="text-xs text-slate-400">Keine weiteren Status-Transitionen verfuegbar.</div>
          )}
        </div>
      </div>

      <div className="card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-slate-900">Kampagnenplan bearbeiten</h2>
          <button
            onClick={() => setShowEditor((prev) => !prev)}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-50"
          >
            {showEditor ? 'Editor ausblenden' : 'Editor einblenden'}
          </button>
        </div>

        {!showEditor && (
          <p className="text-xs text-slate-400">
            Editor ist standardmaessig ausgeblendet. Erst die Entscheidungslogik pruefen, dann Kampagnenparameter anpassen.
          </p>
        )}

        {showEditor && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="text-xs text-slate-600">
                Aktivierung Start
                <input type="datetime-local" className="media-input mt-1" value={activationStart} onChange={(e) => setActivationStart(e.target.value)} />
              </label>
              <label className="text-xs text-slate-600">
                Aktivierung Ende
                <input type="datetime-local" className="media-input mt-1" value={activationEnd} onChange={(e) => setActivationEnd(e.target.value)} />
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="text-xs text-slate-600">
                Wochenbudget (EUR)
                <input type="number" min={0} className="media-input mt-1" value={weeklyBudget} onChange={(e) => setWeeklyBudget(Number(e.target.value))} />
              </label>
              <label className="text-xs text-slate-600">
                Budget-Shift (%)
                <input type="number" min={0} max={100} className="media-input mt-1" value={budgetShiftPct} onChange={(e) => setBudgetShiftPct(Number(e.target.value))} />
              </label>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-slate-900">Channel-Split</h3>
                <span className={`text-xs ${Math.abs(channelShareSum - 100) <= 0.2 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  Summe: {channelShareSum.toFixed(1)}%
                </span>
              </div>
              <div className="space-y-2">
                {channelPlan.map((row) => (
                  <div key={row.channel} className="grid grid-cols-[1fr_120px] items-center gap-3">
                    <div className="text-sm text-slate-600">{row.channel.toUpperCase()}</div>
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
              <label className="text-xs text-slate-600">
                Primary KPI
                <input className="media-input mt-1" value={primaryKpi} onChange={(e) => setPrimaryKpi(e.target.value)} />
              </label>
              <label className="text-xs text-slate-600">
                Secondary KPIs (comma-separated)
                <input className="media-input mt-1" value={secondaryKpis} onChange={(e) => setSecondaryKpis(e.target.value)} />
              </label>
              <label className="text-xs text-slate-600">
                Success Criteria
                <textarea className="media-input mt-1 min-h-[90px]" value={successCriteria} onChange={(e) => setSuccessCriteria(e.target.value)} />
              </label>
            </div>

            {error && <div className="text-xs text-red-500">{error}</div>}

            <div className="flex flex-wrap gap-2">
              <button onClick={saveCampaign} className="media-button" disabled={saving}>
                {saving ? 'Speichere...' : 'Kampagnenplan speichern'}
              </button>
              <button onClick={regenerateAiPlan} className="media-button secondary" disabled={regenSaving}>
                {regenSaving ? 'Regeneriere...' : 'Regenerate AI'}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-slate-900">Technische Details</h2>
          <button
            onClick={() => setShowTechDetails((prev) => !prev)}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-300 text-slate-700 hover:bg-slate-50"
          >
            {showTechDetails ? 'Details ausblenden' : 'Details einblenden'}
          </button>
        </div>

        {!showTechDetails && (
          <p className="text-xs text-slate-400">
            Trigger-Evidenz, KI-Plan, HWG-Botschaft und Quick-Facts sind standardmaessig ausgeblendet.
          </p>
        )}

        {showTechDetails && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="soft-panel p-4 space-y-2">
                <h3 className="text-sm font-semibold text-slate-900">Trigger-Evidenz</h3>
                {detail.playbook_title && (
                  <div className="inline-flex text-[11px] px-2 py-1 rounded-full bg-indigo-500/10 text-indigo-600 border border-indigo-400/30">
                    {detail.playbook_title}
                  </div>
                )}
                <div className="text-xs text-slate-500">Quelle: {detail.trigger_evidence?.source || '-'}</div>
                <div className="text-xs text-slate-500">Event: {detail.trigger_evidence?.event || '-'}</div>
                <div className="text-xs text-slate-500">Lead-Time: {detail.trigger_evidence?.lead_time_days ?? '-'} Tage</div>
                <div className="text-xs text-slate-500">
                  Confidence: {detail.trigger_evidence?.confidence ? `${Math.round(detail.trigger_evidence.confidence * 100)}%` : '-'}
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">{detail.trigger_evidence?.details || detail.reason || '-'}</p>
              </div>

              <div className="soft-panel p-4 space-y-2">
                <h3 className="text-sm font-semibold text-slate-900">KI-Plan</h3>
                <div className="text-xs text-slate-500">
                  Modell: {detail.campaign_pack?.ai_meta?.model || '-'} · Provider: {detail.campaign_pack?.ai_meta?.provider || '-'}
                </div>
                <div className="text-xs text-slate-500">
                  Fallback: {detail.campaign_pack?.ai_meta?.fallback_used ? 'Ja' : 'Nein'}
                </div>
                <div className="text-xs text-slate-500">
                  Keywords: {(detail.campaign_pack?.ai_plan?.keyword_clusters || []).slice(0, 4).join(' · ') || '-'}
                </div>
                <div className="text-xs text-slate-600">
                  Creatives: {(detail.campaign_pack?.ai_plan?.creative_angles || []).slice(0, 3).join(' · ') || '-'}
                </div>
                {Array.isArray(detail.campaign_pack?.guardrail_report?.applied_fixes) && (detail.campaign_pack?.guardrail_report?.applied_fixes?.length || 0) > 0 && (
                  <div className="rounded-lg px-3 py-2 text-[11px] bg-amber-500/10 text-amber-700 border border-amber-400/30">
                    Guardrails: {(detail.campaign_pack?.guardrail_report?.applied_fixes || []).slice(0, 3).join(' · ')}
                  </div>
                )}
              </div>

              <div className="soft-panel p-4 space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-900">Botschaft (HWG)</h3>
                  <div className="text-[11px] text-slate-400">
                    Copy-Status: <span className="text-slate-700 font-semibold">{detail.campaign_pack?.message_framework?.copy_status || '-'}</span>
                  </div>
                </div>
                <div className="text-xs text-slate-600">
                  Hero: <span className="text-slate-700 font-semibold">{detail.campaign_pack?.message_framework?.hero_message || '-'}</span>
                </div>
                {Array.isArray(detail.campaign_pack?.message_framework?.support_points) && (detail.campaign_pack?.message_framework?.support_points?.length || 0) > 0 && (
                  <div className="text-xs text-slate-500 leading-relaxed">
                    Support: {(detail.campaign_pack?.message_framework?.support_points || []).slice(0, 4).join(' · ')}
                  </div>
                )}
                <div className="text-xs text-slate-500">CTA: {detail.campaign_pack?.message_framework?.cta || '-'}</div>
                <div className="text-[11px] text-slate-400 leading-relaxed">
                  Compliance: {detail.campaign_pack?.message_framework?.compliance_note || '-'}
                </div>
              </div>

              <div className="soft-panel p-4 space-y-2">
                <h3 className="text-sm font-semibold text-slate-900">Quick Facts</h3>
                <div className="text-xs text-slate-500">Region: {detail.campaign_pack?.targeting?.region_scope || detail.region || '-'}</div>
                <div className="text-xs text-slate-500">Urgency Score: {detail.urgency_score ?? '-'}</div>
                <div className="text-xs text-slate-500">Empfohlenes Produkt: {detail.recommended_product || detail.product || '-'}</div>
                <div className="text-xs text-slate-500">Primary KPI: {detail.primary_kpi || detail.campaign_pack?.measurement_plan?.primary_kpi || '-'}</div>
                <div className="text-xs text-slate-500">
                  Created: {detail.created_at ? format(parseISO(detail.created_at), 'dd.MM.yyyy HH:mm', { locale: de }) : '-'}
                </div>
                <div className="text-xs text-slate-500">
                  Updated: {detail.updated_at ? format(parseISO(detail.updated_at), 'dd.MM.yyyy HH:mm', { locale: de }) : '-'}
                </div>
              </div>
            </div>

            {Array.isArray(detail.campaign_pack?.execution_checklist) && detail.campaign_pack.execution_checklist.length > 0 && (
              <div className="soft-panel p-4 space-y-2">
                <h3 className="text-sm font-semibold text-slate-900">Execution Checklist</h3>
                <ul className="space-y-2">
                  {detail.campaign_pack.execution_checklist.map((item, idx) => (
                    <li key={`${item.task}-${idx}`} className="text-xs text-slate-600">
                      <span className="text-slate-500">[{item.owner || 'Team'}]</span> {item.task}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default CampaignRecommendationDetail;
