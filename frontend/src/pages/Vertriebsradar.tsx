import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

// ─── Types ──────────────────────────────────────────────────────────────────
interface MarketingOpportunity {
  id: string;
  type: string;
  status: string;
  urgency_score: number;
  region_target: { country: string; states: string[]; plz_cluster: string };
  trigger_context: { source: string; event: string; details: string; detected_at: string };
  target_audience: string[];
  sales_pitch: { headline_email: string; script_phone: string; call_to_action: string };
  suggested_products: Array<{ sku: string; name: string; priority: string }>;
  created_at: string;
  expires_at: string | null;
  exported_at: string | null;
}

interface OpportunityStats {
  total: number;
  recent_7d: number;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  avg_urgency: number;
}

// ─── Constants ──────────────────────────────────────────────────────────────
const TYPE_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  RESOURCE_SCARCITY: { label: 'Engpass', color: '#ef4444', icon: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z' },
  SEASONAL_DEFICIENCY: { label: 'Saisonal', color: '#f59e0b', icon: 'M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z' },
  PREDICTIVE_SALES_SPIKE: { label: 'Nachfrage', color: '#8b5cf6', icon: 'M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941' },
  DIFFERENTIAL_DIAGNOSIS: { label: 'Differenzial', color: '#06b6d4', icon: 'M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5' },
};

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  NEW: { label: 'Neu', color: '#3b82f6' },
  URGENT: { label: 'Dringend', color: '#ef4444' },
  SENT: { label: 'Gesendet', color: '#10b981' },
  CONVERTED: { label: 'Konvertiert', color: '#8b5cf6' },
  EXPIRED: { label: 'Abgelaufen', color: '#64748b' },
  DISMISSED: { label: 'Verworfen', color: '#475569' },
};

const urgencyColor = (score: number) =>
  score >= 80 ? '#ef4444' : score >= 50 ? '#f59e0b' : '#3b82f6';

// ─── Component ──────────────────────────────────────────────────────────────
const Vertriebsradar: React.FC = () => {
  const navigate = useNavigate();
  const [opportunities, setOpportunities] = useState<MarketingOpportunity[]>([]);
  const [stats, setStats] = useState<OpportunityStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Filters
  const [filterType, setFilterType] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterUrgency, setFilterUrgency] = useState<number>(0);

  // Fetch opportunities
  const fetchOpportunities = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filterType) params.set('type', filterType);
      if (filterStatus) params.set('status', filterStatus);
      if (filterUrgency > 0) params.set('min_urgency', String(filterUrgency));
      params.set('limit', '100');

      const res = await fetch(`/api/v1/marketing/list?${params}`);
      if (res.ok) {
        const data = await res.json();
        setOpportunities(data.opportunities || []);
      }
    } catch (e) {
      console.error('Fetch opportunities error:', e);
    } finally {
      setLoading(false);
    }
  }, [filterType, filterStatus, filterUrgency]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/marketing/stats');
      if (res.ok) setStats(await res.json());
    } catch (_) {}
  }, []);

  useEffect(() => {
    fetchOpportunities();
    fetchStats();
  }, [fetchOpportunities, fetchStats]);

  // Generate new opportunities
  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await fetch('/api/v1/marketing/generate', { method: 'POST' });
      if (res.ok) {
        await fetchOpportunities();
        await fetchStats();
      }
    } catch (e) {
      console.error('Generate error:', e);
    } finally {
      setGenerating(false);
    }
  };

  // Export CRM JSON
  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await fetch('/api/v1/marketing/export/crm');
      if (!res.ok) throw new Error('Export failed');
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `GanzImmun_CRM_Export_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      await fetchOpportunities();
    } catch (e) {
      console.error('Export error:', e);
    } finally {
      setExporting(false);
    }
  };

  // Update status
  const updateStatus = async (id: string, status: string) => {
    try {
      await fetch(`/api/v1/marketing/${encodeURIComponent(id)}/status?status=${status}`, {
        method: 'PATCH',
      });
      await fetchOpportunities();
      await fetchStats();
    } catch (e) {
      console.error('Status update error:', e);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: '#0f172a' }}>

      {/* ── Header ── */}
      <header style={{ background: '#1e293b', borderBottom: '1px solid #334155' }}>
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="w-10 h-10 rounded-xl flex items-center justify-center transition hover:bg-slate-700"
              style={{ border: '1px solid #334155' }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
                  <path d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22" />
                  <path d="M16.06 6.22l5.94 2.28-2.28 5.94" />
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-white tracking-tight">Vertriebsradar</h1>
                <p className="text-xs text-slate-400">KI-gesteuerte Vertriebschancen für Ganz Immun</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleExport}
              disabled={exporting || opportunities.length === 0}
              className="px-4 py-2 text-xs font-medium rounded-lg transition-all hover:bg-slate-700"
              style={{
                color: '#f59e0b',
                border: '1px solid #f59e0b40',
                opacity: exporting || opportunities.length === 0 ? 0.5 : 1,
              }}
            >
              {exporting ? 'Exportiere...' : 'JSON Export'}
            </button>
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="px-5 py-2 text-xs font-semibold rounded-lg transition-all text-white"
              style={{
                background: generating ? '#334155' : 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
                opacity: generating ? 0.6 : 1,
              }}
            >
              {generating ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Generiere...
                </span>
              ) : (
                'Chancen generieren'
              )}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-5">

        {/* ── Stats Bar ── */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3 fade-in">
            <div className="card p-4 text-center">
              <div className="text-2xl font-bold text-white">{stats.total}</div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-1">Gesamt</div>
            </div>
            <div className="card p-4 text-center">
              <div className="text-2xl font-bold text-amber-400">{stats.avg_urgency}</div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-1">Avg. Urgency</div>
            </div>
            <div className="card p-4 text-center">
              <div className="text-2xl font-bold text-blue-400">{stats.recent_7d}</div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-1">Letzte 7 Tage</div>
            </div>
            {Object.entries(TYPE_CONFIG).map(([type, cfg]) => {
              const count = stats.by_type[type] || 0;
              return (
                <div key={type} className="card p-4 text-center" style={{ borderTop: `2px solid ${cfg.color}` }}>
                  <div className="text-2xl font-bold text-white">{count}</div>
                  <div className="text-[10px] uppercase tracking-wider mt-1" style={{ color: cfg.color }}>{cfg.label}</div>
                </div>
              );
            })}
          </div>
        )}

        {/* ── Filter Bar ── */}
        <div className="card px-5 py-3 flex flex-wrap items-center gap-4 fade-in">
          <div className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round"><path d="M3 4h18l-7 8v6l-4 2V12L3 4z" /></svg>
            <span className="text-xs text-slate-500 font-medium">Filter:</span>
          </div>

          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="text-xs px-3 py-1.5 rounded-lg appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-blue-500"
            style={{ background: '#0f172a', color: '#94a3b8', border: '1px solid #334155' }}
          >
            <option value="">Alle Typen</option>
            {Object.entries(TYPE_CONFIG).map(([type, cfg]) => (
              <option key={type} value={type}>{cfg.label}</option>
            ))}
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="text-xs px-3 py-1.5 rounded-lg appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-blue-500"
            style={{ background: '#0f172a', color: '#94a3b8', border: '1px solid #334155' }}
          >
            <option value="">Alle Status</option>
            {Object.entries(STATUS_CONFIG).map(([status, cfg]) => (
              <option key={status} value={status}>{cfg.label}</option>
            ))}
          </select>

          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500">Min. Urgency:</span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={filterUrgency}
              onChange={(e) => setFilterUrgency(Number(e.target.value))}
              className="w-24 h-1 rounded-full appearance-none cursor-pointer"
              style={{ background: `linear-gradient(to right, #3b82f6 ${filterUrgency}%, #334155 ${filterUrgency}%)` }}
            />
            <span className="text-xs font-mono text-slate-400 w-6">{filterUrgency}</span>
          </div>

          <div className="ml-auto text-xs text-slate-500">
            {opportunities.length} Ergebnis{opportunities.length !== 1 ? 'se' : ''}
          </div>
        </div>

        {/* ── Opportunity Cards ── */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-3 border-amber-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : opportunities.length === 0 ? (
          <div className="card p-12 text-center fade-in">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl flex items-center justify-center" style={{ background: '#f59e0b15' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round">
                <path d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22M16.06 6.22l5.94 2.28-2.28 5.94" />
              </svg>
            </div>
            <p className="text-sm text-slate-400 mb-1">Keine Opportunities vorhanden</p>
            <p className="text-xs text-slate-600">
              Klicke "Chancen generieren" um die Signale zu analysieren.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {opportunities.map((opp, idx) => {
              const typeConfig = TYPE_CONFIG[opp.type] || { label: opp.type, color: '#64748b', icon: '' };
              const statusConfig = STATUS_CONFIG[opp.status] || { label: opp.status, color: '#64748b' };
              const isExpanded = expandedId === opp.id;
              const uColor = urgencyColor(opp.urgency_score);

              return (
                <div
                  key={opp.id}
                  className="card overflow-hidden fade-in"
                  style={{
                    borderLeft: `3px solid ${typeConfig.color}`,
                    animationDelay: `${idx * 50}ms`,
                  }}
                >
                  {/* Urgency bar */}
                  <div className="h-1" style={{ background: '#0f172a' }}>
                    <div
                      className="h-full transition-all duration-700"
                      style={{ width: `${opp.urgency_score}%`, background: uColor }}
                    />
                  </div>

                  <div className="p-5">
                    {/* Top row: ID, badges, urgency */}
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-mono text-slate-500">{opp.id}</span>
                        <span
                          className="badge"
                          style={{ background: `${typeConfig.color}20`, color: typeConfig.color }}
                        >
                          {typeConfig.label}
                        </span>
                        <span
                          className="badge"
                          style={{ background: `${statusConfig.color}20`, color: statusConfig.color }}
                        >
                          {statusConfig.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="text-right">
                          <div className="text-lg font-black" style={{ color: uColor }}>{opp.urgency_score}</div>
                          <div className="text-[9px] text-slate-500 -mt-0.5">urgency</div>
                        </div>
                      </div>
                    </div>

                    {/* Trigger Context */}
                    <div className="p-3 rounded-lg mb-3" style={{ background: '#0f172a' }}>
                      <div className="flex items-center gap-3 mb-1.5">
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: '#334155', color: '#94a3b8' }}>
                          {opp.trigger_context.source}
                        </span>
                        <span className="text-xs font-medium" style={{ color: typeConfig.color }}>
                          {opp.trigger_context.event.replace(/_/g, ' ')}
                        </span>
                        <span className="text-[10px] text-slate-600 ml-auto">
                          {opp.trigger_context.detected_at}
                        </span>
                      </div>
                      <p className="text-sm text-slate-300 leading-relaxed">
                        {opp.trigger_context.details}
                      </p>
                    </div>

                    {/* Target Audience + Region */}
                    <div className="flex flex-wrap items-center gap-2 mb-3">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2"><path d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" /></svg>
                      {opp.target_audience.map((aud, i) => (
                        <span
                          key={i}
                          className="text-[10px] px-2 py-0.5 rounded-full"
                          style={{ background: '#334155', color: '#94a3b8' }}
                        >
                          {aud}
                        </span>
                      ))}
                      {opp.region_target.states.length > 0 && (
                        <>
                          <span className="text-slate-600">|</span>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2"><path d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" /><path d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" /></svg>
                          <span className="text-[10px] text-slate-500">
                            {opp.region_target.states.join(', ')}
                            {opp.region_target.plz_cluster !== 'ALL' && ` (${opp.region_target.plz_cluster})`}
                          </span>
                        </>
                      )}
                      {opp.region_target.plz_cluster !== 'ALL' && opp.region_target.states.length === 0 && (
                        <>
                          <span className="text-slate-600">|</span>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2"><path d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" /><path d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" /></svg>
                          <span className="text-[10px] text-slate-500">PLZ {opp.region_target.plz_cluster}</span>
                        </>
                      )}
                    </div>

                    {/* Suggested Products */}
                    {opp.suggested_products.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-3">
                        {opp.suggested_products.map((prod, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-1.5 text-[10px] px-2 py-1 rounded"
                            style={{
                              background: prod.priority === 'HIGH' ? '#3b82f615' : '#1e293b',
                              border: `1px solid ${prod.priority === 'HIGH' ? '#3b82f640' : '#334155'}`,
                              color: prod.priority === 'HIGH' ? '#93c5fd' : '#94a3b8',
                            }}
                          >
                            <span className="font-mono opacity-60">{prod.sku}</span>
                            <span>{prod.name}</span>
                            {prod.priority === 'HIGH' && (
                              <span className="text-[8px] font-bold text-blue-400">HIGH</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Sales Pitch (expandable) */}
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : opp.id)}
                      className="flex items-center gap-2 text-xs transition hover:text-amber-300 mb-2"
                      style={{ color: '#f59e0b' }}
                    >
                      <svg
                        width="12" height="12" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                        className="transition-transform"
                        style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                      >
                        <path d="M9 5l7 7-7 7" />
                      </svg>
                      Sales Pitch {isExpanded ? 'verbergen' : 'anzeigen'}
                    </button>

                    {isExpanded && (
                      <div className="space-y-3 p-4 rounded-lg slide-in" style={{ background: '#0f172a', border: '1px solid #334155' }}>
                        <div>
                          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">E-Mail Betreff</div>
                          <p className="text-sm text-white font-medium">{opp.sales_pitch.headline_email}</p>
                        </div>
                        <div>
                          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Telefon-Script</div>
                          <p className="text-sm text-slate-300 leading-relaxed italic">
                            "{opp.sales_pitch.script_phone}"
                          </p>
                        </div>
                        <div className="flex items-center gap-2 pt-2" style={{ borderTop: '1px solid #334155' }}>
                          <div className="text-[10px] text-slate-500 uppercase tracking-wider">CTA</div>
                          <span
                            className="text-xs font-semibold px-3 py-1 rounded-full"
                            style={{ background: `${typeConfig.color}20`, color: typeConfig.color }}
                          >
                            {opp.sales_pitch.call_to_action}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center justify-between mt-3 pt-3" style={{ borderTop: '1px solid #334155' }}>
                      <div className="flex items-center gap-2">
                        {opp.status === 'NEW' || opp.status === 'URGENT' ? (
                          <>
                            <button
                              onClick={() => updateStatus(opp.id, 'SENT')}
                              className="text-[10px] font-medium px-3 py-1 rounded-lg transition hover:opacity-80"
                              style={{ background: '#10b98120', color: '#10b981', border: '1px solid #10b98140' }}
                            >
                              Als gesendet markieren
                            </button>
                            <button
                              onClick={() => updateStatus(opp.id, 'DISMISSED')}
                              className="text-[10px] font-medium px-3 py-1 rounded-lg transition hover:opacity-80"
                              style={{ background: '#47556920', color: '#64748b', border: '1px solid #47556940' }}
                            >
                              Verwerfen
                            </button>
                          </>
                        ) : opp.status === 'SENT' ? (
                          <button
                            onClick={() => updateStatus(opp.id, 'CONVERTED')}
                            className="text-[10px] font-medium px-3 py-1 rounded-lg transition hover:opacity-80"
                            style={{ background: '#8b5cf620', color: '#8b5cf6', border: '1px solid #8b5cf640' }}
                          >
                            Als konvertiert markieren
                          </button>
                        ) : null}
                      </div>
                      <div className="flex items-center gap-3 text-[10px] text-slate-600">
                        {opp.created_at && (
                          <span>Erstellt: {format(new Date(opp.created_at), 'dd.MM.yy HH:mm', { locale: de })}</span>
                        )}
                        {opp.exported_at && (
                          <span className="text-green-600">Exportiert</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      {/* ── Footer ── */}
      <footer className="mt-8 py-4 text-center text-xs text-slate-600" style={{ borderTop: '1px solid #1e293b' }}>
        LabPulse Pro &mdash; Vertriebsradar v1.0 &mdash; Ganz Immun Diagnostics AG
      </footer>
    </div>
  );
};

export default Vertriebsradar;
