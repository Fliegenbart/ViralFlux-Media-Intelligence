import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import { apiFetch } from '../lib/api';
import { useToast } from '../lib/useToast';

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
  is_conquesting_active?: boolean;
  competitor_shortage_ingredient?: string;
  recommended_bid_modifier?: number;
  conquesting_product?: string;
}

interface OpportunityStats {
  total: number;
  recent_7d: number;
  daily_counts_7d?: number[];
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  avg_urgency: number;
}

// ─── Constants ──────────────────────────────────────────────────────────────
const TYPE_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  RESOURCE_SCARCITY: { label: 'Engpass', color: '#ef4444', icon: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z' },
  SEASONAL_DEFICIENCY: { label: 'Saisonal', color: '#f59e0b', icon: 'M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z' },
  PREDICTIVE_SALES_SPIKE: { label: 'Nachfrage', color: '#4338ca', icon: 'M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941' },
  DIFFERENTIAL_DIAGNOSIS: { label: 'Differenzial', color: '#06b6d4', icon: 'M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5' },
  WEATHER_FORECAST: { label: 'Wetter', color: '#0ea5e9', icon: 'M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z' },
  COMPETITOR_SHORTAGE: { label: 'Conquesting', color: '#d97706', icon: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z' },
};

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  NEW: { label: 'Neu', color: '#3b82f6' },
  URGENT: { label: 'Dringend', color: '#ef4444' },
  SENT: { label: 'Gesendet', color: '#10b981' },
  CONVERTED: { label: 'Konvertiert', color: '#4338ca' },
  EXPIRED: { label: 'Abgelaufen', color: '#64748b' },
  DISMISSED: { label: 'Verworfen', color: '#475569' },
};

const urgencyColor = (score: number) =>
  score >= 80 ? '#ef4444' : score >= 50 ? '#f59e0b' : '#3b82f6';

// ─── Mini Components ────────────────────────────────────────────────────────

const UrgencyRing: React.FC<{ score: number; size?: number }> = ({ score, size = 64 }) => {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = urgencyColor(score);
  return (
    <svg width={size} height={size} className="flex-shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth="5" />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth="5" strokeLinecap="round"
        strokeDasharray={circ} strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 1s ease' }}
      />
      <text x={size / 2} y={size / 2 + 1} textAnchor="middle" dominantBaseline="middle"
        fill={color} fontSize={size * 0.28} fontWeight="800" fontFamily="monospace">
        {score}
      </text>
    </svg>
  );
};

const TypeIcon: React.FC<{ type: string; size?: number }> = ({ type, size = 16 }) => {
  const cfg = TYPE_CONFIG[type];
  if (!cfg) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={cfg.color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d={cfg.icon} />
    </svg>
  );
};

// Sparkline SVG for 7-day trend
const Sparkline: React.FC<{ data: number[]; color: string; w?: number; h?: number }> = ({
  data, color, w = 80, h = 28,
}) => {
  if (data.length < 2) return null;
  const max = Math.max(...data, 1);
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / max) * (h - 4) - 2}`).join(' ');
  return (
    <svg width={w} height={h} className="flex-shrink-0">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {data.length > 0 && (() => {
        const lastX = w;
        const lastY = h - (data[data.length - 1] / max) * (h - 4) - 2;
        return <circle cx={lastX} cy={lastY} r="2.5" fill={color} />;
      })()}
    </svg>
  );
};

const ConquestingBadge: React.FC<{ opp: MarketingOpportunity; compact?: boolean }> = ({ opp, compact }) => {
  if (!opp.is_conquesting_active) return null;
  return (
    <div className="rounded-lg border border-amber-400 bg-amber-50 px-3 py-2 mt-2">
      <div className="flex items-center gap-2">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#d97706" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
        </svg>
        <span className="text-[11px] font-bold text-amber-800 uppercase tracking-wider">Conquesting</span>
      </div>
      {!compact && (
        <div className="mt-1.5 text-[11px] text-amber-700 leading-relaxed">
          Engpass: <span className="font-bold">{opp.competitor_shortage_ingredient || '—'}</span>.
          {' '}Bid-Multiplikator: <span className="font-bold">{opp.recommended_bid_modifier?.toFixed(1) || '1.0'}x</span>.
          {opp.conquesting_product && (
            <span className="ml-1 text-amber-600">({opp.conquesting_product})</span>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Toast Container ────────────────────────────────────────────────────────
const ToastContainer: React.FC<{ toasts: Array<{ id: number; message: string; type: string }>; onRemove: (id: number) => void }> = ({ toasts, onRemove }) => {
  if (toasts.length === 0) return null;
  const colors: Record<string, string> = {
    success: 'bg-emerald-600 text-white',
    error: 'bg-red-600 text-white',
    info: 'bg-slate-700 text-white',
  };
  return (
    <div className="fixed bottom-6 right-6 z-[9999] flex flex-col gap-2" style={{ maxWidth: 380 }}>
      {toasts.map(t => (
        <div key={t.id} className={`${colors[t.type] || colors.info} rounded-lg px-4 py-3 shadow-xl text-sm flex items-center gap-3 animate-[slideUp_0.3s_ease-out]`}>
          <span className="flex-1">{t.message}</span>
          <button onClick={() => onRemove(t.id)} className="opacity-60 hover:opacity-100 text-lg leading-none">&times;</button>
        </div>
      ))}
    </div>
  );
};

// ─── Component ──────────────────────────────────────────────────────────────
const SalesRadar: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [opportunities, setOpportunities] = useState<MarketingOpportunity[]>([]);
  const [stats, setStats] = useState<OpportunityStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [detailOpp, setDetailOpp] = useState<MarketingOpportunity | null>(null);
  const [showTechDetails, setShowTechDetails] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const pageSize = 50;
  const { toasts, addToast, removeToast } = useToast();

  // Fetch
  const fetchOpportunities = useCallback(async (page = 1) => {
    try {
      setFetchError(null);
      const skip = (page - 1) * pageSize;
      const params = new URLSearchParams({ limit: String(pageSize), skip: String(skip) });
      const res = await apiFetch(`/api/v1/marketing/list?${params}`);
      if (res.ok) {
        const data = await res.json();
        setOpportunities(data.opportunities || []);
        setTotalCount(data.total ?? 0);
        setTotalPages(data.pages ?? 1);
        setCurrentPage(data.page ?? 1);
      } else {
        setFetchError(`Fehler beim Laden: ${res.status}`);
      }
    } catch (e) {
      setFetchError('Verbindung zum Server fehlgeschlagen');
      console.error('Fetch error:', e);
    }
    finally { setLoading(false); }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await apiFetch('/api/v1/marketing/stats');
      if (res.ok) setStats(await res.json());
    } catch (_) {}
  }, []);

  useEffect(() => { fetchOpportunities(); fetchStats(); }, [fetchOpportunities, fetchStats]);

  // Deep-Link: open opportunity from URL ?opp=...
  useEffect(() => {
    const oppId = searchParams.get('opp');
    if (oppId && opportunities.length > 0 && !detailOpp) {
      const match = opportunities.find(o => o.id === oppId);
      if (match) setDetailOpp(match);
    }
  }, [searchParams, opportunities, detailOpp]);

  // Open/close detail panel with URL sync
  const openDetail = useCallback((opp: MarketingOpportunity | null) => {
    setDetailOpp(opp);
    if (opp) {
      setSearchParams(prev => { prev.set('opp', opp.id); return prev; }, { replace: true });
    } else {
      setSearchParams(prev => { prev.delete('opp'); return prev; }, { replace: true });
    }
  }, [setSearchParams]);

  // Page navigation
  const goToPage = useCallback((page: number) => {
    if (page < 1 || page > totalPages) return;
    setLoading(true);
    fetchOpportunities(page);
  }, [fetchOpportunities, totalPages]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await apiFetch('/api/v1/marketing/generate', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        const count = data?.new_opportunities ?? data?.total ?? 0;
        addToast(`${count} Opportunities generiert`, 'success');
        await fetchOpportunities();
        await fetchStats();
      } else {
        addToast(`Generate fehlgeschlagen: ${res.status}`, 'error');
      }
    } catch (e) {
      addToast('Generate fehlgeschlagen — Server nicht erreichbar', 'error');
      console.error('Generate error:', e);
    }
    finally { setGenerating(false); }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await apiFetch('/api/v1/marketing/export/crm');
      if (!res.ok) throw new Error(`Export failed: ${res.status}`);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ViralFlux_CRM_Export_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      addToast('CRM-Export heruntergeladen', 'success');
      await fetchOpportunities();
    } catch (e) {
      addToast('Export fehlgeschlagen', 'error');
      console.error('Export error:', e);
    }
    finally { setExporting(false); }
  };

  const updateStatus = async (id: string, status: string) => {
    try {
      const res = await apiFetch(`/api/v1/marketing/${encodeURIComponent(id)}/status?status=${status}`, { method: 'PATCH' });
      if (res.ok) {
        const label = status === 'APPROVED' ? 'freigegeben' : status === 'DISMISSED' ? 'verworfen' : status;
        addToast(`Opportunity ${label}`, 'success');
      } else {
        addToast(`Status-Update fehlgeschlagen: ${res.status}`, 'error');
      }
      await fetchOpportunities();
      await fetchStats();
      if (detailOpp?.id === id) openDetail(null);
    } catch (e) {
      addToast('Status-Update fehlgeschlagen', 'error');
      console.error('Status update error:', e);
    }
  };

  // ─── Derived data ───
  const urgent = useMemo(() =>
    opportunities.filter(o => (o.status === 'URGENT' || o.status === 'NEW') && o.urgency_score >= 80)
      .sort((a, b) => b.urgency_score - a.urgency_score),
    [opportunities]
  );

  const newByType = useMemo(() => {
    const items = opportunities
      .filter(o => (o.status === 'NEW' || o.status === 'URGENT') && o.urgency_score < 80)
      .sort((a, b) => b.urgency_score - a.urgency_score);
    const grouped: Record<string, MarketingOpportunity[]> = {};
    items.forEach(o => {
      if (!grouped[o.type]) grouped[o.type] = [];
      grouped[o.type].push(o);
    });
    return grouped;
  }, [opportunities]);

  const pipeline = useMemo(() =>
    opportunities.filter(o => ['SENT', 'CONVERTED', 'EXPIRED', 'DISMISSED'].includes(o.status))
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [opportunities]
  );

  const conversionRate = useMemo(() => {
    const sent = opportunities.filter(o => o.status === 'SENT').length;
    const converted = opportunities.filter(o => o.status === 'CONVERTED').length;
    const total = sent + converted;
    return total > 0 ? Math.round((converted / total) * 100) : 0;
  }, [opportunities]);

  // 7-day sparkline from real daily counts
  const sparkData = useMemo(() => {
    if (!stats?.daily_counts_7d) return [0, 0, 0, 0, 0, 0, 0];
    return stats.daily_counts_7d;
  }, [stats]);

  return (
    <div className="min-h-screen bg-slate-50">

      {/* ── Header ── */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="w-10 h-10 rounded-xl border border-slate-200 flex items-center justify-center transition hover:bg-slate-100"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round">
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
                <h1 className="text-xl font-bold text-slate-900 tracking-tight" style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}>Vertriebsradar</h1>
                <p className="text-xs text-slate-400">KI-gesteuerte Vertriebschancen</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {urgent.length > 0 && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg mr-2"
                style={{ background: '#ef444410', border: '1px solid #ef444430' }}>
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <span className="text-xs font-semibold text-red-500">{urgent.length} dringend</span>
              </div>
            )}
            <button
              onClick={handleExport}
              disabled={exporting || opportunities.length === 0}
              className="px-4 py-2 text-xs font-medium rounded-lg border border-amber-300 text-amber-600 transition-all hover:bg-amber-50"
              style={{ opacity: exporting || opportunities.length === 0 ? 0.5 : 1 }}
            >
              {exporting ? 'Exportiere...' : 'CRM Export'}
            </button>
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="px-5 py-2 text-xs font-semibold rounded-lg transition-all text-white"
              style={{ background: generating ? '#cbd5e1' : 'linear-gradient(135deg, #3b82f6, #4338ca)', opacity: generating ? 0.6 : 1 }}
            >
              {generating ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Generiere...
                </span>
              ) : 'Chancen generieren'}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">

        {/* ── Business-First: Top Actions ── */}
        <div
          className="card p-6 fade-in"
          style={{
            background:
              'radial-gradient(900px 220px at 20% 0%, rgba(67,56,202,0.06), transparent 60%), linear-gradient(135deg, #ffffff, #f8fafc)',
          }}
        >
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
            <div className="min-w-0">
              <div className="text-[10px] text-slate-400 uppercase tracking-wider">Heute</div>
              <h2 className="text-2xl font-black text-slate-900 tracking-tight mt-1" style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}>Top Aktionen (Marketing)</h2>
              <p className="text-sm text-slate-500 mt-2 max-w-2xl">
                Automatisch generierte Marketing-Opportunities auf Basis von Echtzeit-Signalen.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowTechDetails((s) => !s)}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 text-slate-500 transition hover:bg-slate-100"
              >
                {showTechDetails ? 'Pipeline ausblenden' : 'Pipeline anzeigen'}
              </button>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-4">
            {(urgent.slice(0, 3).length ? urgent.slice(0, 3) : [null, null, null]).map((opp: any, idx: number) => {
              if (!opp) {
                return (
                  <div key={`s-${idx}`} className="rounded-xl p-4 bg-slate-50 border border-slate-200">
                    <div className="h-3 w-24 bg-slate-200 rounded mb-3" />
                    <div className="h-5 w-2/3 bg-slate-200 rounded mb-2" />
                    <div className="h-3 w-full bg-slate-100 rounded mb-6" />
                    <div className="h-9 bg-slate-100 rounded" />
                  </div>
                );
              }
              const tc = TYPE_CONFIG[opp.type] || { label: opp.type, color: '#64748b', icon: '' };
              const topProduct = opp.suggested_products?.find((p: any) => p.priority === 'HIGH') || opp.suggested_products?.[0];
              const region = opp.region_target?.states?.length ? opp.region_target.states.join(', ') : 'Bundesweit';
              return (
                <div key={opp.id} className="rounded-xl p-4 bg-white border border-slate-200 shadow-sm">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-wider font-bold" style={{ color: tc.color }}>
                        {tc.label}
                      </div>
                      <div className="text-base font-bold text-slate-900 mt-1 line-clamp-2">{opp.trigger_context?.details}</div>
                      <div className="text-xs text-slate-400 mt-1">
                        Region: <span className="text-slate-600">{region}</span>
                      </div>
                    </div>
                    <div className="flex-shrink-0 text-right">
                      <div className="text-[10px] text-slate-400 uppercase tracking-wider">Produkt</div>
                      <div className="text-sm font-bold text-slate-700 mt-1">{topProduct?.name || '—'}</div>
                    </div>
                  </div>
                  <ConquestingBadge opp={opp} compact />
                  <div className="mt-4 flex items-center justify-between gap-3">
                    <div className="text-[11px] text-slate-400">Output: HWG-safe Copy + CTA</div>
                    <button
                      onClick={() => openDetail(opp)}
                      className="px-4 py-2 text-xs font-bold rounded-lg transition hover:brightness-110"
                      style={{ background: 'linear-gradient(135deg, #22c55e, #10b981)', color: '#052e1b' }}
                    >
                      Aktivieren
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── KPI Header ── */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 fade-in">
            {/* Total Opportunities */}
            <div className="card p-5 flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: '#3b82f610', border: '1px solid #3b82f625' }}>
                <span className="text-xl font-black text-blue-500">{stats.total}</span>
              </div>
              <div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider">Gesamt</div>
                <div className="text-sm text-slate-600">{stats.recent_7d} diese Woche</div>
              </div>
            </div>

            {/* Avg Urgency */}
            <div className="card p-5 flex items-center gap-4">
              <UrgencyRing score={stats.avg_urgency} size={48} />
              <div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider">Ø Dringlichkeit</div>
                <div className="text-sm text-slate-600">
                  {stats.avg_urgency >= 70 ? 'Hoher Handlungsdruck' : stats.avg_urgency >= 40 ? 'Mittleres Niveau' : 'Niedrig'}
                </div>
              </div>
            </div>

            {/* 7-Day Trend */}
            <div className="card p-5 flex items-center gap-4">
              <Sparkline data={sparkData} color="#f59e0b" w={72} h={36} />
              <div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider">7-Tage-Trend</div>
                <div className="text-sm text-amber-500 font-semibold">{stats.recent_7d} neue</div>
              </div>
            </div>

            {/* Konversionsrate */}
            <div className="card p-5 flex items-center gap-4">
              <UrgencyRing score={conversionRate} size={48} />
              <div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider">Konversionsrate</div>
                <div className="text-sm text-slate-600">
                  {stats.by_status?.CONVERTED || 0} von {(stats.by_status?.SENT || 0) + (stats.by_status?.CONVERTED || 0)}
                </div>
              </div>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-3 border-amber-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : opportunities.length === 0 ? (
          <div className="card p-16 text-center fade-in">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl flex items-center justify-center" style={{ background: '#f59e0b10' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round">
                <path d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22M16.06 6.22l5.94 2.28-2.28 5.94" />
              </svg>
            </div>
            <p className="text-sm text-slate-500 mb-1">Keine Opportunities vorhanden</p>
            <p className="text-xs text-slate-400">Klicke "Chancen generieren" um die Signale zu analysieren.</p>
          </div>
        ) : (
          <>
            {/* ZONE 1: SOFORT HANDELN */}
            {urgent.length > 0 && (
              <section className="fade-in">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                  <h2 className="text-sm font-bold text-red-500 uppercase tracking-wider">Sofort handeln</h2>
                  <div className="flex-1 h-px" style={{ background: 'linear-gradient(to right, #ef444440, transparent)' }} />
                  <span className="text-xs text-slate-400">{urgent.length} dringend{urgent.length !== 1 ? 'e' : ''} Chance{urgent.length !== 1 ? 'n' : ''}</span>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
                  {urgent.map((opp, idx) => {
                    const tc = TYPE_CONFIG[opp.type] || { label: opp.type, color: '#64748b', icon: '' };
                    const topProduct = opp.suggested_products.find(p => p.priority === 'HIGH') || opp.suggested_products[0];
                    return (
                      <div
                        key={opp.id}
                        className="card overflow-hidden cursor-pointer transition-all hover:scale-[1.01] hover:shadow-lg bg-white"
                        style={{
                          borderTop: `3px solid ${tc.color}`,
                          animationDelay: `${idx * 60}ms`,
                        }}
                        onClick={() => openDetail(opp)}
                      >
                        <div className="p-5">
                          <div className="flex items-start gap-4">
                            <UrgencyRing score={opp.urgency_score} size={72} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-2">
                                <TypeIcon type={opp.type} size={14} />
                                <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: tc.color }}>
                                  {tc.label}
                                </span>
                                {opp.status === 'URGENT' && (
                                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: '#ef444415', color: '#ef4444' }}>
                                    URGENT
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-slate-700 leading-relaxed line-clamp-2 mb-2">
                                {opp.trigger_context.details}
                              </p>
                              <div className="flex items-center gap-2 text-[10px] text-slate-400">
                                <span className="font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
                                  {opp.trigger_context.source.replace(/_/g, ' ')}
                                </span>
                                {opp.region_target.states.length > 0 && (
                                  <span>{opp.region_target.states.join(', ')}</span>
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Conquesting Badge */}
                          <ConquestingBadge opp={opp} />

                          {/* Top Product + Actions */}
                          <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-200">
                            {topProduct ? (
                              <div className="flex items-center gap-2">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2">
                                  <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                                </svg>
                                <span className="text-[10px] text-slate-500">{topProduct.name}</span>
                              </div>
                            ) : <div />}
                            <div className="flex items-center gap-2">
                              <button
                                onClick={(e) => { e.stopPropagation(); updateStatus(opp.id, 'SENT'); }}
                                className="text-[10px] font-semibold px-3 py-1.5 rounded-lg transition hover:opacity-80"
                                style={{ background: '#10b98115', color: '#10b981', border: '1px solid #10b98130' }}
                              >
                                Gesendet
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); updateStatus(opp.id, 'DISMISSED'); }}
                                className="text-[10px] px-2.5 py-1.5 rounded-lg border border-slate-200 text-slate-400 transition hover:opacity-80"
                              >
                                ✕
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* ZONE 2: NEUE CHANCEN */}
            {Object.keys(newByType).length > 0 && (
              <section className="fade-in">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-2 h-2 rounded-full bg-blue-500" />
                  <h2 className="text-sm font-bold text-blue-500 uppercase tracking-wider">Neue Chancen</h2>
                  <div className="flex-1 h-px" style={{ background: 'linear-gradient(to right, #3b82f640, transparent)' }} />
                  <span className="text-xs text-slate-400">
                    {Object.values(newByType).reduce((sum, arr) => sum + arr.length, 0)} offen
                  </span>
                </div>

                <div className="space-y-5">
                  {Object.entries(newByType).map(([type, items]) => {
                    const tc = TYPE_CONFIG[type] || { label: type, color: '#64748b', icon: '' };
                    return (
                      <div key={type}>
                        {/* Type Section Header */}
                        <div className="flex items-center gap-2 mb-3">
                          <div className="w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: `${tc.color}10` }}>
                            <TypeIcon type={type} size={13} />
                          </div>
                          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: tc.color }}>
                            {tc.label}
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono">{items.length}</span>
                          <div className="flex-1 h-px" style={{ background: `${tc.color}15` }} />
                        </div>

                        {/* Compact Card Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                          {items.map((opp) => {
                            const topProduct = opp.suggested_products.find(p => p.priority === 'HIGH') || opp.suggested_products[0];
                            return (
                              <div
                                key={opp.id}
                                className="card p-4 cursor-pointer transition-all hover:scale-[1.01] hover:shadow-md"
                                style={{ borderLeft: `3px solid ${tc.color}` }}
                                onClick={() => openDetail(opp)}
                              >
                                <div className="flex items-start justify-between mb-2">
                                  <p className="text-xs text-slate-600 leading-relaxed line-clamp-2 flex-1 mr-3">
                                    {opp.trigger_context.details}
                                  </p>
                                  <div className="flex-shrink-0 text-right">
                                    <div className="text-base font-black font-mono" style={{ color: urgencyColor(opp.urgency_score) }}>
                                      {opp.urgency_score}
                                    </div>
                                  </div>
                                </div>

                                <ConquestingBadge opp={opp} compact />

                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2">
                                    {topProduct && (
                                      <span className="text-[9px] px-2 py-0.5 rounded bg-slate-100 text-slate-500">
                                        {topProduct.name}
                                      </span>
                                    )}
                                    {opp.region_target.states.length > 0 && (
                                      <span className="text-[9px] text-slate-400">{opp.region_target.states[0]}</span>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <button
                                      onClick={(e) => { e.stopPropagation(); updateStatus(opp.id, 'SENT'); }}
                                      className="text-[9px] font-medium px-2 py-1 rounded transition hover:opacity-80"
                                      style={{ background: '#10b98110', color: '#10b981' }}
                                    >
                                      Senden
                                    </button>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); updateStatus(opp.id, 'DISMISSED'); }}
                                      className="text-[9px] px-1.5 py-1 rounded text-slate-400 transition hover:opacity-80"
                                    >
                                      ✕
                                    </button>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* ZONE 3: PIPELINE */}
            {showTechDetails && pipeline.length > 0 && (
              <section className="fade-in">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-2 h-2 rounded-full bg-emerald-500" />
                  <h2 className="text-sm font-bold text-emerald-500 uppercase tracking-wider">Pipeline</h2>
                  <div className="flex-1 h-px" style={{ background: 'linear-gradient(to right, #10b98140, transparent)' }} />

                  {/* Mini Funnel */}
                  <div className="flex items-center gap-2 text-[10px]">
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full" style={{ background: '#10b981' }} />
                      <span className="text-slate-400">Gesendet</span>
                      <span className="text-slate-700 font-mono font-bold">{pipeline.filter(o => o.status === 'SENT').length}</span>
                    </span>
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" strokeWidth="2"><path d="M9 5l7 7-7 7" /></svg>
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full" style={{ background: '#4338ca' }} />
                      <span className="text-slate-400">Konvertiert</span>
                      <span className="text-slate-700 font-mono font-bold">{pipeline.filter(o => o.status === 'CONVERTED').length}</span>
                    </span>
                    <span className="text-slate-300 ml-2">|</span>
                    <span className="text-slate-400">
                      {pipeline.filter(o => o.status === 'DISMISSED').length} verworfen,{' '}
                      {pipeline.filter(o => o.status === 'EXPIRED').length} abgelaufen
                    </span>
                  </div>
                </div>

                {/* Pipeline Table */}
                <div className="card overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-slate-100">
                          <th className="text-left px-4 py-3 text-[10px] text-slate-500 uppercase tracking-wider font-medium">Status</th>
                          <th className="text-left px-4 py-3 text-[10px] text-slate-500 uppercase tracking-wider font-medium">Typ</th>
                          <th className="text-left px-4 py-3 text-[10px] text-slate-500 uppercase tracking-wider font-medium">Trigger</th>
                          <th className="text-left px-4 py-3 text-[10px] text-slate-500 uppercase tracking-wider font-medium">Urgency</th>
                          <th className="text-left px-4 py-3 text-[10px] text-slate-500 uppercase tracking-wider font-medium">Conquesting</th>
                          <th className="text-left px-4 py-3 text-[10px] text-slate-500 uppercase tracking-wider font-medium">Erstellt</th>
                          <th className="text-right px-4 py-3 text-[10px] text-slate-500 uppercase tracking-wider font-medium">Aktion</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pipeline.map((opp) => {
                          const tc = TYPE_CONFIG[opp.type] || { label: opp.type, color: '#64748b', icon: '' };
                          const sc = STATUS_CONFIG[opp.status] || { label: opp.status, color: '#64748b' };
                          return (
                            <tr key={opp.id}
                              className="cursor-pointer transition hover:bg-slate-50 border-b border-slate-200"
                              onClick={() => openDetail(opp)}
                            >
                              <td className="px-4 py-3">
                                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                                  style={{ background: `${sc.color}12`, color: sc.color }}>
                                  {sc.label}
                                </span>
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex items-center gap-2">
                                  <TypeIcon type={opp.type} size={12} />
                                  <span className="text-slate-500">{tc.label}</span>
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <span className="text-slate-700 line-clamp-1 max-w-[300px] inline-block">
                                  {opp.trigger_context.details}
                                </span>
                              </td>
                              <td className="px-4 py-3">
                                <span className="font-mono font-bold" style={{ color: urgencyColor(opp.urgency_score) }}>
                                  {opp.urgency_score}
                                </span>
                              </td>
                              <td className="px-4 py-3">
                                {opp.is_conquesting_active ? (
                                  <span className="text-[9px] font-bold px-2 py-0.5 rounded border-2 border-red-400 bg-red-50 text-red-700">
                                    {opp.recommended_bid_modifier?.toFixed(1) || '1.5'}x BID
                                  </span>
                                ) : (
                                  <span className="text-[10px] text-slate-300">—</span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-slate-400">
                                {opp.created_at ? format(new Date(opp.created_at), 'dd.MM.yy', { locale: de }) : '—'}
                              </td>
                              <td className="px-4 py-3 text-right">
                                {opp.status === 'SENT' && (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); updateStatus(opp.id, 'CONVERTED'); }}
                                    className="text-[10px] font-medium px-2.5 py-1 rounded-lg transition hover:opacity-80"
                                    style={{ background: '#4338ca15', color: '#4338ca', border: '1px solid #4338ca30' }}
                                  >
                                    Konvertiert
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </section>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-6 px-1">
                <span className="text-xs text-slate-400">
                  {totalCount} Opportunities gesamt
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => goToPage(currentPage - 1)}
                    disabled={currentPage <= 1}
                    className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-xs text-slate-500 transition hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    &laquo;
                  </button>
                  {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                    let page: number;
                    if (totalPages <= 7) {
                      page = i + 1;
                    } else if (currentPage <= 4) {
                      page = i + 1;
                    } else if (currentPage >= totalPages - 3) {
                      page = totalPages - 6 + i;
                    } else {
                      page = currentPage - 3 + i;
                    }
                    return (
                      <button
                        key={page}
                        onClick={() => goToPage(page)}
                        className={`w-8 h-8 rounded-lg text-xs font-medium transition ${
                          page === currentPage
                            ? 'bg-indigo-600 text-white shadow-sm'
                            : 'border border-slate-200 text-slate-500 hover:bg-slate-100'
                        }`}
                      >
                        {page}
                      </button>
                    );
                  })}
                  <button
                    onClick={() => goToPage(currentPage + 1)}
                    disabled={currentPage >= totalPages}
                    className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center text-xs text-slate-500 transition hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    &raquo;
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* DETAIL SLIDE-OUT */}
      {detailOpp && (() => {
        const opp = detailOpp;
        const tc = TYPE_CONFIG[opp.type] || { label: opp.type, color: '#64748b', icon: '' };
        const sc = STATUS_CONFIG[opp.status] || { label: opp.status, color: '#64748b' };
        return (
          <>
            {/* Backdrop */}
            <div
              className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
              onClick={() => openDetail(null)}
            />
            {/* Panel */}
            <div className="fixed top-0 right-0 bottom-0 z-50 w-full max-w-lg overflow-y-auto slide-in bg-white border-l border-slate-200 shadow-2xl">

              {/* Panel Header */}
              <div className="sticky top-0 z-10 px-6 py-4 flex items-center justify-between bg-white"
                style={{ borderBottom: `2px solid ${tc.color}` }}>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `${tc.color}10` }}>
                    <TypeIcon type={opp.type} size={16} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold uppercase tracking-wider" style={{ color: tc.color }}>{tc.label}</span>
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                        style={{ background: `${sc.color}12`, color: sc.color }}>{sc.label}</span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-400">{opp.id}</span>
                  </div>
                </div>
                <button
                  onClick={() => openDetail(null)}
                  className="w-8 h-8 rounded-lg border border-slate-200 flex items-center justify-center transition hover:bg-slate-100"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="p-6 space-y-6">
                {/* Urgency + Trigger */}
                <div className="flex items-start gap-5">
                  <UrgencyRing score={opp.urgency_score} size={88} />
                  <div className="flex-1">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Auslöser</div>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
                        {opp.trigger_context.source.replace(/_/g, ' ')}
                      </span>
                      <span className="text-[10px]" style={{ color: tc.color }}>
                        {opp.trigger_context.event.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <p className="text-sm text-slate-700 leading-relaxed">{opp.trigger_context.details}</p>
                    <div className="text-[10px] text-slate-400 mt-2">{opp.trigger_context.detected_at}</div>
                  </div>
                </div>

                {/* Conquesting Badge (Detail) */}
                <ConquestingBadge opp={opp} />

                {/* Region + Audience */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 rounded-lg bg-slate-50">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-2">Region</div>
                    <div className="text-xs text-slate-700">
                      {opp.region_target.states.length > 0 ? opp.region_target.states.join(', ') : 'Bundesweit'}
                      {opp.region_target.plz_cluster !== 'ALL' && (
                        <span className="text-slate-400 ml-1">(PLZ {opp.region_target.plz_cluster})</span>
                      )}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-50">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-2">Zielgruppe</div>
                    <div className="flex flex-wrap gap-1">
                      {opp.target_audience.map((aud, i) => (
                        <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-200 text-slate-600">
                          {aud}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Produkte */}
                {opp.suggested_products.length > 0 && (
                  <div>
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-2">Empfohlene Produkte</div>
                    <div className="space-y-2">
                      {opp.suggested_products.map((prod, i) => (
                        <div key={i} className="flex items-center gap-3 p-2.5 rounded-lg"
                          style={{
                            background: prod.priority === 'HIGH' ? '#3b82f608' : '#f8fafc',
                            border: `1px solid ${prod.priority === 'HIGH' ? '#3b82f625' : '#e2e8f0'}`,
                          }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                            stroke={prod.priority === 'HIGH' ? '#3b82f6' : '#94a3b8'} strokeWidth="2">
                            <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                          </svg>
                          <div className="flex-1">
                            <div className="text-xs text-slate-700">{prod.name}</div>
                            <div className="text-[10px] font-mono text-slate-400">{prod.sku}</div>
                          </div>
                          {prod.priority === 'HIGH' && (
                            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: '#3b82f615', color: '#3b82f6' }}>
                              HIGH
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Sales Pitch */}
                <div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-3">Sales Pitch</div>
                  <div className="space-y-4 p-4 rounded-lg bg-slate-50 border border-slate-200">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2">
                          <path d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                        </svg>
                        <span className="text-[10px] font-semibold text-amber-500">E-Mail Betreff</span>
                      </div>
                      <p className="text-sm text-slate-900 font-medium">{opp.sales_pitch.headline_email}</p>
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2">
                          <path d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
                        </svg>
                        <span className="text-[10px] font-semibold text-amber-500">Telefon-Script</span>
                      </div>
                      <p className="text-sm text-slate-600 leading-relaxed italic">"{opp.sales_pitch.script_phone}"</p>
                    </div>
                    <div className="pt-3 border-t border-slate-200">
                      <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Call-to-Action</div>
                      <span className="text-xs font-semibold px-3 py-1.5 rounded-full inline-block"
                        style={{ background: `${tc.color}15`, color: tc.color }}>
                        {opp.sales_pitch.call_to_action}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-3 pt-2">
                  {(opp.status === 'NEW' || opp.status === 'URGENT') && (
                    <>
                      <button
                        onClick={() => updateStatus(opp.id, 'SENT')}
                        className="flex-1 py-2.5 text-xs font-semibold rounded-lg transition hover:opacity-90 text-center"
                        style={{ background: 'linear-gradient(135deg, #10b981, #059669)', color: 'white' }}
                      >
                        Als gesendet markieren
                      </button>
                      <button
                        onClick={() => updateStatus(opp.id, 'DISMISSED')}
                        className="py-2.5 px-4 text-xs rounded-lg border border-slate-200 text-slate-500 transition hover:opacity-80"
                      >
                        Verwerfen
                      </button>
                    </>
                  )}
                  {opp.status === 'SENT' && (
                    <button
                      onClick={() => updateStatus(opp.id, 'CONVERTED')}
                      className="flex-1 py-2.5 text-xs font-semibold rounded-lg transition hover:opacity-90 text-center"
                      style={{ background: 'linear-gradient(135deg, #4338ca, #4f46e5)', color: 'white' }}
                    >
                      Als konvertiert markieren
                    </button>
                  )}
                </div>

                {/* PDF Briefing Download */}
                <button
                  onClick={async () => {
                    try {
                      const res = await apiFetch(`/api/v1/marketing/briefing/${encodeURIComponent(opp.id)}.pdf`);
                      if (!res.ok) { addToast('PDF-Download fehlgeschlagen', 'error'); return; }
                      const blob = await res.blob();
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `Briefing_${opp.type}_${opp.id.slice(0, 8)}.pdf`;
                      a.click();
                      URL.revokeObjectURL(url);
                      addToast('Briefing PDF heruntergeladen', 'success');
                    } catch { addToast('PDF-Download fehlgeschlagen', 'error'); }
                  }}
                  className="w-full py-2.5 text-xs font-semibold rounded-lg border-2 border-dashed border-slate-300 text-slate-500 transition hover:border-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 flex items-center justify-center gap-2"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                    <path d="M14 2v6h6M12 18v-6M9 15l3 3 3-3" />
                  </svg>
                  Briefing PDF herunterladen
                </button>

                {/* Meta */}
                <div className="flex items-center justify-between text-[10px] text-slate-400 pt-2 border-t border-slate-100">
                  <span>Erstellt: {opp.created_at ? format(new Date(opp.created_at), 'dd.MM.yy HH:mm', { locale: de }) : '—'}</span>
                  {opp.expires_at && <span>Läuft ab: {format(new Date(opp.expires_at), 'dd.MM.yy', { locale: de })}</span>}
                  {opp.exported_at && <span className="text-green-600">Exportiert</span>}
                </div>
              </div>
            </div>
          </>
        );
      })()}

      {/* ── Error Banner ── */}
      {fetchError && (
        <div className="max-w-[1600px] mx-auto px-6 mt-6">
          <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 flex items-center gap-3">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
            </svg>
            <span className="text-sm text-red-700 flex-1">{fetchError}</span>
            <button onClick={() => { setFetchError(null); setLoading(true); fetchOpportunities(); fetchStats(); }}
              className="text-xs font-medium text-red-600 hover:text-red-800 px-3 py-1 rounded-lg border border-red-200 hover:bg-red-100 transition">
              Erneut versuchen
            </button>
          </div>
        </div>
      )}

      {/* ── Toast Notifications ── */}
      <ToastContainer toasts={toasts} onRemove={removeToast} />

      {/* ── Footer ── */}
      <footer className="mt-8 py-4 text-center text-xs text-slate-400 border-t border-slate-200">
        ViralFlux Media Intelligence &mdash; Vertriebsradar v2.0
      </footer>
    </div>
  );
};

export default SalesRadar;
