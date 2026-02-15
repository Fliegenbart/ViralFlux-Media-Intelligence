import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Area, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ComposedChart,
} from 'recharts';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

// ─── Types ──────────────────────────────────────────────────────────────────
interface ViralLoad {
  value: number;
  date: string;
  trend: string;
}

interface ForecastSummary {
  days: number;
  trend: string;
  confidence: number;
  next_7d: number;
  next_14d: number | null;
  model_version: string;
}

interface InventoryItem {
  current: number;
  min: number;
  max: number;
  recommended: number;
  lead_time_days: number;
  fill_percentage: number;
  status: string;
}

interface Recommendation {
  id: number;
  text: string;
  action: {
    action_type: string;
    recommended_quantity: number;
    priority: string;
    reason: string;
  };
  confidence: number;
  approved: boolean;
  created_at: string;
}

interface GrippeWebItem {
  value: number | null;
  date: string | null;
  kalenderwoche: number;
  trend: string;
}

interface DrugShortageSignals {
  risk_score: number;
  total_active: number;
  wave_type: string;
  categories: Record<string, number>;
  pediatric_count: number;
  pediatric_alert: boolean;
  summary: string;
}

interface GrippeWebTimeseriesPoint {
  date: string;
  kalenderwoche: number;
  inzidenz: number;
  meldungen: number | null;
}

interface OutbreakScoreData {
  overall_score: number;
  overall_risk_level: string;
  per_virus: Record<string, {
    final_risk_score: number;
    risk_level: string;
    leading_indicator: string;
    confidence_numeric: number;
    confidence_level: string;
    phase: string;
    data_source_mode: string;
    baseline_correction: string;
    component_scores: Record<string, number | null>;
    contributions: Record<string, number>;
  }>;
  timestamp: string;
}

interface DashboardData {
  current_viral_loads: Record<string, ViralLoad>;
  top_trends: Array<{ keyword: string; score: number }>;
  are_inzidenz: { value: number | null; date: string | null };
  grippeweb: Record<string, GrippeWebItem>;
  forecast_summary: Record<string, ForecastSummary>;
  weather: { avg_temperature: number; avg_humidity: number };
  inventory: Record<string, InventoryItem>;
  recommendations: Recommendation[];
  has_forecasts: boolean;
  has_inventory: boolean;
  timestamp: string;
}

interface TimeseriesPoint {
  date: string;
  viral_load: number;
  normalized: number | null;
  prediction: number | null;
  upper_bound: number | null;
  lower_bound: number | null;
}

interface ForecastPoint {
  date: string;
  predicted_value: number;
  upper_bound: number | null;
  lower_bound: number | null;
  confidence: number;
}

interface SparklinePoint {
  d: string;
  v: number;
}

// ─── Helpers ────────────────────────────────────────────────────────────────
const VIRUS_COLORS: Record<string, string> = {
  'Influenza A': '#3b82f6',
  'Influenza B': '#8b5cf6',
  'SARS-CoV-2': '#ef4444',
  'RSV A': '#10b981',
};

const VIRUS_ICONS: Record<string, string> = {
  'Influenza A': 'Flu A',
  'Influenza B': 'Flu B',
  'SARS-CoV-2': 'CoV-2',
  'RSV A': 'RSV',
};

const fmt = (n: number) => {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return n.toFixed(0);
};

const trendArrow = (t: string) =>
  t === 'steigend' ? '\u2197' : t === 'fallend' ? '\u2198' : '\u2192';

const trendColor = (t: string) =>
  t === 'steigend' ? '#ef4444' : t === 'fallend' ? '#10b981' : '#94a3b8';

// ─── Mini Sparkline ─────────────────────────────────────────────────────────
const Sparkline: React.FC<{ data: SparklinePoint[]; color: string }> = ({ data, color }) => {
  if (!data || data.length < 2) return null;
  const vals = data.map(d => d.v);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const w = 120;
  const h = 32;
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((d.v - min) / range) * h;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={`grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`0,${h} ${points} ${w},${h}`}
        fill={`url(#grad-${color.replace('#', '')})`}
      />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
};

// ─── Dashboard Component ────────────────────────────────────────────────────
const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [selectedVirus, setSelectedVirus] = useState('Influenza A');
  const [timeseries, setTimeseries] = useState<{ historical: TimeseriesPoint[]; forecast: ForecastPoint[]; inventory?: Array<{ date: string; bestand: number; min_bestand: number; max_bestand: number; empfohlen: number }>; test_typ?: string } | null>(null);
  const [allTimeseries, setAllTimeseries] = useState<Record<string, TimeseriesPoint[]>>({});
  const [zoomStart, setZoomStart] = useState<number | null>(null);
  const [zoomEnd, setZoomEnd] = useState<number | null>(null);
  const pinchRef = React.useRef<{ dist: number; start: number; end: number } | null>(null);
  const [sparklines, setSparklines] = useState<Record<string, SparklinePoint[]>>({});
  const [showForecast, setShowForecast] = useState(true);
  const [loading, setLoading] = useState(true);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [recsLoading, setRecsLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [stockoutData, setStockoutData] = useState<any>(null);
  const [orderLoading, setOrderLoading] = useState(false);
  const [expandedRec, setExpandedRec] = useState<number | null>(null);
  const [showGrippeWeb, setShowGrippeWeb] = useState(false);
  const [selectedGrippeWeb, setSelectedGrippeWeb] = useState<'ARE' | 'ILI'>('ARE');
  const [grippeWebSeries, setGrippeWebSeries] = useState<GrippeWebTimeseriesPoint[]>([]);
  const [drugShortageData, setDrugShortageData] = useState<DrugShortageSignals | null>(null);
  const [drugShortageLoading, setDrugShortageLoading] = useState(false);
  const [outbreakScore, setOutbreakScore] = useState<OutbreakScoreData | null>(null);
  const [outbreakLoading, setOutbreakLoading] = useState(false);

  // Fetch dashboard overview
  const fetchOverview = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/dashboard/overview');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json();
      if (result.current_viral_loads) {
        setData(result);
        setLastUpdate(new Date());
      }
    } catch (e) {
      console.error('Dashboard fetch error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch timeseries for selected virus
  const fetchTimeseries = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/dashboard/timeseries/${encodeURIComponent(selectedVirus)}?include_forecast=${showForecast}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json();
      setTimeseries(result);
    } catch (e) {
      console.error('Timeseries fetch error:', e);
    }
  }, [selectedVirus, showForecast]);

  // Fetch timeseries for ALL viruses (multi-curve chart)
  const fetchAllTimeseries = useCallback(async () => {
    const viruses = ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'];
    const results: Record<string, TimeseriesPoint[]> = {};
    await Promise.all(viruses.map(async (v) => {
      try {
        const res = await fetch(`/api/v1/dashboard/timeseries/${encodeURIComponent(v)}?include_forecast=false&days_back=90`);
        if (res.ok) {
          const json = await res.json();
          results[v] = json.historical || [];
        }
      } catch (_) {}
    }));
    setAllTimeseries(results);
  }, []);

  // Fetch sparklines for all viruses
  const fetchSparklines = useCallback(async () => {
    const viruses = ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'];
    const results: Record<string, SparklinePoint[]> = {};
    await Promise.all(viruses.map(async (v) => {
      try {
        const res = await fetch(`/api/v1/dashboard/sparkline/${encodeURIComponent(v)}?days=30`);
        if (res.ok) {
          const json = await res.json();
          results[v] = json.data;
        }
      } catch (_) {}
    }));
    setSparklines(results);
  }, []);

  // Fetch GrippeWeb timeseries
  const fetchGrippeWebTimeseries = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/dashboard/grippeweb-timeseries?erkrankung=${selectedGrippeWeb}&weeks_back=52`);
      if (res.ok) {
        const result = await res.json();
        setGrippeWebSeries(result.data || []);
      }
    } catch (e) {
      console.error('GrippeWeb fetch error:', e);
    }
  }, [selectedGrippeWeb]);

  // Fetch Drug Shortage signals
  const fetchDrugShortageSignals = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/drug-shortage/signals');
      if (res.ok) {
        const result = await res.json();
        setDrugShortageData(result);
      }
    } catch (_) {}
  }, []);

  // Fetch Outbreak Score
  const fetchOutbreakScore = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/outbreak-score/all');
      if (res.ok) {
        const result = await res.json();
        setOutbreakScore(result);
      }
    } catch (e) {
      console.error('Outbreak score fetch error:', e);
    }
  }, []);

  // Upload Drug Shortage CSV
  const uploadDrugShortageCSV = async (file: File) => {
    setDrugShortageLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch('/api/v1/drug-shortage/upload', { method: 'POST', body: formData });
      if (res.ok) {
        const result = await res.json();
        setDrugShortageData(result.signals);
      }
    } catch (e) {
      console.error('Drug shortage upload error:', e);
    } finally {
      setDrugShortageLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
    fetchSparklines();
    fetchAllTimeseries();
    fetchDrugShortageSignals();
    fetchOutbreakScore();
  }, [fetchOverview, fetchSparklines, fetchAllTimeseries, fetchDrugShortageSignals, fetchOutbreakScore]);

  useEffect(() => {
    fetchTimeseries();
  }, [fetchTimeseries]);

  useEffect(() => {
    if (showGrippeWeb) fetchGrippeWebTimeseries();
  }, [showGrippeWeb, fetchGrippeWebTimeseries]);

  // Re-fetch all data when page becomes visible (user returns to tab)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        fetchOverview();
        fetchAllTimeseries();
        fetchSparklines();
        fetchOutbreakScore();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [fetchOverview, fetchAllTimeseries, fetchSparklines, fetchOutbreakScore]);

  // Run ML forecast
  const runForecast = async () => {
    setForecastLoading(true);
    try {
      await fetch('/api/v1/forecast/run', { method: 'POST' });
      // Poll for completion
      setTimeout(async () => {
        await fetchOverview();
        await fetchTimeseries();
        await fetchOutbreakScore();
        setForecastLoading(false);
      }, 5000);
    } catch (e) {
      console.error('Forecast run error:', e);
      setForecastLoading(false);
    }
  };

  // Generate recommendations
  const generateRecs = async () => {
    setRecsLoading(true);
    try {
      await fetch('/api/v1/recommendations/generate', { method: 'POST' });
      setTimeout(async () => {
        await fetchOverview();
        setRecsLoading(false);
      }, 3000);
    } catch (e) {
      console.error('Recs generation error:', e);
      setRecsLoading(false);
    }
  };

  // Seed inventory
  const seedInventory = async () => {
    try {
      await fetch('/api/v1/inventory/seed', { method: 'POST' });
      await fetchOverview();
    } catch (e) {
      console.error('Seed error:', e);
    }
  };

  // Fetch stockout analysis
  const fetchStockout = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/ordering/stockout-analysis');
      if (res.ok) setStockoutData(await res.json());
    } catch (_) {}
  }, []);

  useEffect(() => { fetchStockout(); }, [fetchStockout]);

  // Generate and download SAP orders
  const downloadSAPOrders = async () => {
    setOrderLoading(true);
    try {
      const res = await fetch('/api/v1/ordering/export-sap');
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `LabPulse_Bestellung_${new Date().toISOString().slice(0,10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('SAP export error:', e);
    } finally {
      setOrderLoading(false);
    }
  };

  // Approve recommendation
  const approveRec = async (id: number) => {
    try {
      await fetch(`/api/v1/recommendations/${id}/approve`, { method: 'POST' });
      await fetchOverview();
    } catch (e) {
      console.error('Approve error:', e);
    }
  };

  // Build chart data for SELECTED virus + forecast/inventory
  const chartData = React.useMemo(() => {
    const points = allTimeseries[selectedVirus] || timeseries?.historical || [];

    // Inventory forward-fill
    const invEntries = (timeseries?.inventory || []).map(inv => ({
      date: new Date(inv.date).getTime(),
      bestand: inv.bestand,
      min_bestand: inv.min_bestand,
    })).sort((a, b) => a.date - b.date);

    const getInventoryAt = (dateStr: string) => {
      if (invEntries.length === 0) return null;
      const ts = new Date(dateStr).getTime();
      let best = invEntries[0];
      for (const inv of invEntries) {
        if (inv.date <= ts) best = inv;
        else break;
      }
      return best;
    };

    const hist = points.map((d) => {
      const inv = getInventoryAt(d.date);
      return {
        date: format(new Date(d.date), 'dd. MMM', { locale: de }),
        rawDate: d.date,
        'Messwert': d.viral_load,
        'RKI Prognose': d.prediction,
        ...(inv ? { 'Bestand': inv.bestand, 'Min-Bestand': inv.min_bestand } : {}),
      };
    });

    if (showForecast && timeseries?.forecast && timeseries.forecast.length > 0) {
      const last = hist.length > 0 ? hist[hist.length - 1] : null;
      const lastInv = invEntries.length > 0 ? invEntries[invEntries.length - 1] : null;
      const forecasts = timeseries.forecast.map((d) => ({
        date: format(new Date(d.date), 'dd. MMM', { locale: de }),
        rawDate: d.date,
        'ML Prognose': d.predicted_value,
        'Obergrenze': d.upper_bound,
        'Untergrenze': d.lower_bound,
        ...(lastInv ? { 'Bestand': lastInv.bestand, 'Min-Bestand': lastInv.min_bestand } : {}),
      }));
      if (last && forecasts.length > 0) {
        forecasts[0] = { ...forecasts[0], 'Messwert': last['Messwert'] } as any;
      }
      return [...hist, ...forecasts];
    }
    return hist;
  }, [allTimeseries, selectedVirus, timeseries, showForecast]);

  // Zoomed slice of chart data
  const visibleData = React.useMemo(() => {
    if (zoomStart !== null && zoomEnd !== null) {
      return chartData.slice(zoomStart, zoomEnd + 1);
    }
    return chartData;
  }, [chartData, zoomStart, zoomEnd]);

  // Reset zoom when virus changes
  useEffect(() => {
    setZoomStart(null);
    setZoomEnd(null);
  }, [selectedVirus]);

  // Scroll-to-zoom handler
  const handleChartWheel = useCallback((e: React.WheelEvent) => {
    if (chartData.length < 5) return;
    e.preventDefault();
    const total = chartData.length;
    const start = zoomStart ?? 0;
    const end = zoomEnd ?? total - 1;
    const range = end - start;

    const step = Math.max(1, Math.ceil(range * 0.12));
    const delta = e.deltaY > 0 ? step : -step;
    const newRange = range + delta * 2;

    if (newRange >= total - 1) {
      setZoomStart(null);
      setZoomEnd(null);
      return;
    }
    if (newRange < 4) return;

    const center = Math.round((start + end) / 2);
    const ns = Math.max(0, center - Math.round(newRange / 2));
    const ne = Math.min(total - 1, ns + newRange);
    setZoomStart(ns);
    setZoomEnd(ne);
  }, [chartData.length, zoomStart, zoomEnd]);

  // Pinch-to-zoom handlers
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY,
      );
      pinchRef.current = {
        dist,
        start: zoomStart ?? 0,
        end: zoomEnd ?? chartData.length - 1,
      };
    }
  }, [zoomStart, zoomEnd, chartData.length]);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2 && pinchRef.current) {
      e.preventDefault();
      const newDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY,
      );
      const scale = pinchRef.current.dist / newDist;
      const origRange = pinchRef.current.end - pinchRef.current.start;
      const newRange = Math.max(4, Math.round(origRange * scale));
      const total = chartData.length;

      if (newRange >= total - 1) {
        setZoomStart(null);
        setZoomEnd(null);
        return;
      }

      const center = Math.round((pinchRef.current.start + pinchRef.current.end) / 2);
      const ns = Math.max(0, center - Math.round(newRange / 2));
      const ne = Math.min(total - 1, ns + newRange);
      setZoomStart(ns);
      setZoomEnd(ne);
    }
  }, [chartData.length]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen" style={{ background: '#0f172a' }}>
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <div className="text-lg text-slate-400">Lade Dashboard...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: '#0f172a' }}>
      {/* ── Header ── */}
      <header style={{ background: '#1e293b', borderBottom: '1px solid #334155' }}>
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">LabPulse Pro</h1>
              <p className="text-xs text-slate-400">Intelligentes Frühwarnsystem für Labordiagnostik</p>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <button
              onClick={() => navigate('/vertriebsradar')}
              className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all hover:bg-slate-700"
              style={{ color: '#f59e0b', border: '1px solid #f59e0b40' }}
            >
              Vertriebsradar
            </button>
            <button
              onClick={() => navigate('/datenimport')}
              className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all hover:bg-slate-700"
              style={{ color: '#10b981', border: '1px solid #10b98140' }}
            >
              Datenimport
            </button>
            <button
              onClick={() => navigate('/calibration')}
              className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all hover:bg-slate-700"
              style={{ color: '#f59e0b', border: '1px solid #f59e0b40' }}
            >
              Kalibrierung
            </button>
            <button
              onClick={() => navigate('/map')}
              className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all hover:bg-slate-700"
              style={{ color: '#94a3b8', border: '1px solid #334155' }}
            >
              Deutschlandkarte
            </button>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
              <span className="text-xs text-slate-400">System aktiv</span>
            </div>
            <div className="text-xs text-slate-500">
              Update: {lastUpdate.toLocaleTimeString('de-DE')}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">

        {/* ── Outbreak Score Banner ── */}
        {outbreakScore && (
          <div className="card p-6 fade-in" style={{
            background: outbreakScore.overall_risk_level === 'RED'
              ? 'linear-gradient(135deg, rgba(239,68,68,0.15), rgba(30,41,59,1))'
              : outbreakScore.overall_risk_level === 'YELLOW'
              ? 'linear-gradient(135deg, rgba(245,158,11,0.15), rgba(30,41,59,1))'
              : 'linear-gradient(135deg, rgba(16,185,129,0.12), rgba(30,41,59,1))',
            border: `1px solid ${outbreakScore.overall_risk_level === 'RED' ? '#ef4444' : outbreakScore.overall_risk_level === 'YELLOW' ? '#f59e0b' : '#10b981'}40`,
          }}>
            <div className="flex items-center gap-8 flex-wrap">
              {/* Gauge */}
              <div className="flex items-center gap-6">
                <div className="relative" style={{ width: 100, height: 100 }}>
                  <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                    <circle cx="50" cy="50" r="42" fill="none" stroke="#334155" strokeWidth="8" />
                    <circle
                      cx="50" cy="50" r="42" fill="none"
                      stroke={outbreakScore.overall_risk_level === 'RED' ? '#ef4444' : outbreakScore.overall_risk_level === 'YELLOW' ? '#f59e0b' : '#10b981'}
                      strokeWidth="8"
                      strokeDasharray={`${outbreakScore.overall_score * 2.64} 264`}
                      strokeLinecap="round"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-black text-white">{outbreakScore.overall_score}</span>
                    <span className="text-[9px] text-slate-400 -mt-0.5">von 100</span>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">Outbreak Score</div>
                  <div className="flex items-center gap-2">
                    <span className={`text-lg font-bold ${
                      outbreakScore.overall_risk_level === 'RED' ? 'text-red-400'
                      : outbreakScore.overall_risk_level === 'YELLOW' ? 'text-amber-400'
                      : 'text-green-400'
                    }`}>
                      {outbreakScore.overall_risk_level === 'RED' ? 'Hohes Risiko'
                       : outbreakScore.overall_risk_level === 'YELLOW' ? 'Mittleres Risiko'
                       : 'Niedriges Risiko'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Per-Virus Breakdown */}
              <div className="flex-1 grid grid-cols-2 xl:grid-cols-4 gap-3">
                {outbreakScore.per_virus && Object.entries(outbreakScore.per_virus).map(([virus, vs]) => {
                  if ('error' in vs) return null;
                  const color = vs.risk_level === 'RED' ? '#ef4444' : vs.risk_level === 'YELLOW' ? '#f59e0b' : '#10b981';
                  return (
                    <div key={virus} className="p-3 rounded-lg" style={{ background: '#0f172a', border: '1px solid #334155' }}>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs text-slate-400 truncate">{virus}</span>
                        <span className="text-sm font-bold" style={{ color }}>{vs.final_risk_score}</span>
                      </div>
                      {/* Mini bar */}
                      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: '#334155' }}>
                        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${vs.final_risk_score}%`, background: color }} />
                      </div>
                      <div className="flex items-center justify-between mt-1.5">
                        <span className="text-[10px] text-slate-500">{vs.leading_indicator}</span>
                        <span className="text-[10px] text-slate-500">
                          {vs.confidence_level} | Phase {vs.phase}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Component breakdown */}
              {outbreakScore.per_virus?.[selectedVirus] && !('error' in outbreakScore.per_virus[selectedVirus]) && (
                <div className="w-48 space-y-1.5">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Signal-Beitrag ({selectedVirus.split(' ')[0]})</div>
                  {Object.entries(outbreakScore.per_virus[selectedVirus].contributions || {}).map(([name, val]) => (
                    <div key={name} className="flex items-center gap-2">
                      <span className="text-[10px] text-slate-400 w-24 truncate">{name}</span>
                      <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: '#334155' }}>
                        <div className="h-full rounded-full" style={{
                          width: `${Math.min(val as number, 100)}%`,
                          background: (val as number) > 5 ? '#3b82f6' : '#475569'
                        }} />
                      </div>
                      <span className="text-[10px] text-slate-500 w-6 text-right">{(val as number).toFixed(0)}</span>
                    </div>
                  ))}
                  {outbreakScore.per_virus[selectedVirus].data_source_mode === 'ESTIMATED_FROM_ORDERS' && (
                    <div className="text-[9px] text-amber-400 mt-1">Basierend auf Verkaufszahlen</div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Row 1: Virus Load Cards ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {data && data.current_viral_loads && Object.entries(data.current_viral_loads).map(([virus, info]) => {
            const color = VIRUS_COLORS[virus] || '#3b82f6';
            const isSelected = selectedVirus === virus;
            const forecast = data.forecast_summary?.[virus];
            return (
              <div
                key={virus}
                className={`card p-5 cursor-pointer fade-in ${isSelected ? 'card-selected' : ''}`}
                onClick={() => setSelectedVirus(virus)}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ background: color }}></div>
                    <span className="text-sm font-medium text-slate-300">{virus}</span>
                  </div>
                  <span className="text-xs font-mono px-2 py-0.5 rounded" style={{ background: `${color}20`, color }}>{VIRUS_ICONS[virus]}</span>
                </div>
                <div className="flex items-end justify-between">
                  <div>
                    <div className="text-3xl font-bold text-white tracking-tight">{fmt(info.value)}</div>
                    <div className="text-xs text-slate-500 mt-1">Genkopien/L</div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold" style={{ color: trendColor(info.trend) }}>
                      {trendArrow(info.trend)}
                    </div>
                    <div className="text-xs" style={{ color: trendColor(info.trend) }}>
                      {info.trend}
                    </div>
                  </div>
                </div>
                <div className="mt-3">
                  <Sparkline data={sparklines[virus] || []} color={color} />
                </div>
                {forecast && (
                  <div className="mt-3 pt-3" style={{ borderTop: '1px solid #334155' }}>
                    <div className="flex justify-between text-xs">
                      <span className="text-slate-500">7-Tage Prognose</span>
                      <span className="font-medium" style={{ color: forecast.trend === 'steigend' ? '#ef4444' : '#10b981' }}>
                        {fmt(forecast.next_7d)}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* ── GrippeWeb + Drug Shortage Cards ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {/* ARE Card */}
          {data?.grippeweb?.ARE && (
            <div
              className={`card p-5 cursor-pointer fade-in ${showGrippeWeb && selectedGrippeWeb === 'ARE' ? 'card-selected' : ''}`}
              onClick={() => {
                if (showGrippeWeb && selectedGrippeWeb === 'ARE') {
                  setShowGrippeWeb(false);
                } else {
                  setShowGrippeWeb(true);
                  setSelectedGrippeWeb('ARE');
                }
              }}
              style={{ borderLeft: '3px solid #f59e0b' }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ background: '#f59e0b' }}></div>
                  <span className="text-sm font-medium text-slate-300">ARE (Atemwegserkrankungen)</span>
                </div>
                <span className="text-xs font-mono px-2 py-0.5 rounded" style={{ background: '#f59e0b20', color: '#f59e0b' }}>GrippeWeb</span>
              </div>
              <div className="flex items-end justify-between">
                <div>
                  <div className="text-3xl font-bold text-white tracking-tight">
                    {data.grippeweb.ARE.value !== null ? (data.grippeweb.ARE.value / 1000).toFixed(1) : '—'}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">Inzidenz pro 100.000 (×1K)</div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-bold" style={{ color: trendColor(data.grippeweb.ARE.trend) }}>
                    {trendArrow(data.grippeweb.ARE.trend)}
                  </div>
                  <div className="text-xs" style={{ color: trendColor(data.grippeweb.ARE.trend) }}>
                    KW {data.grippeweb.ARE.kalenderwoche}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ILI Card */}
          {data?.grippeweb?.ILI && (
            <div
              className={`card p-5 cursor-pointer fade-in ${showGrippeWeb && selectedGrippeWeb === 'ILI' ? 'card-selected' : ''}`}
              onClick={() => {
                if (showGrippeWeb && selectedGrippeWeb === 'ILI') {
                  setShowGrippeWeb(false);
                } else {
                  setShowGrippeWeb(true);
                  setSelectedGrippeWeb('ILI');
                }
              }}
              style={{ borderLeft: '3px solid #ec4899' }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ background: '#ec4899' }}></div>
                  <span className="text-sm font-medium text-slate-300">ILI (Influenza-like Illness)</span>
                </div>
                <span className="text-xs font-mono px-2 py-0.5 rounded" style={{ background: '#ec489920', color: '#ec4899' }}>GrippeWeb</span>
              </div>
              <div className="flex items-end justify-between">
                <div>
                  <div className="text-3xl font-bold text-white tracking-tight">
                    {data.grippeweb.ILI.value !== null ? data.grippeweb.ILI.value.toFixed(1) : '—'}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">Inzidenz pro 100.000</div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-bold" style={{ color: trendColor(data.grippeweb.ILI.trend) }}>
                    {trendArrow(data.grippeweb.ILI.trend)}
                  </div>
                  <div className="text-xs" style={{ color: trendColor(data.grippeweb.ILI.trend) }}>
                    KW {data.grippeweb.ILI.kalenderwoche}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Drug Shortage Card */}
          <div
            className="card p-5 fade-in"
            style={{ borderLeft: '3px solid #ef4444' }}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ background: '#ef4444' }}></div>
                <span className="text-sm font-medium text-slate-300">Lieferengpässe (BfArM)</span>
              </div>
              <label className="text-xs font-mono px-2 py-0.5 rounded cursor-pointer transition hover:opacity-80" style={{ background: '#ef444420', color: '#ef4444' }}>
                {drugShortageLoading ? '...' : 'CSV laden'}
                <input
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) uploadDrugShortageCSV(file);
                    e.target.value = '';
                  }}
                />
              </label>
            </div>
            {drugShortageData ? (
              <div>
                <div className="flex items-end justify-between">
                  <div>
                    <div className="text-3xl font-bold tracking-tight" style={{
                      color: drugShortageData.risk_score > 60 ? '#ef4444' : drugShortageData.risk_score > 30 ? '#f59e0b' : '#10b981'
                    }}>
                      {drugShortageData.risk_score}
                    </div>
                    <div className="text-xs text-slate-500 mt-1">Risiko-Score (0–100)</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-slate-300">{drugShortageData.total_active}</div>
                    <div className="text-xs text-slate-500">aktive Engpässe</div>
                  </div>
                </div>
                <div className="mt-3 pt-3 space-y-1" style={{ borderTop: '1px solid #334155' }}>
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Wellentyp</span>
                    <span className="text-slate-300 font-medium">{drugShortageData.wave_type}</span>
                  </div>
                  {drugShortageData.pediatric_alert && (
                    <div className="text-xs text-amber-400 font-medium mt-1">
                      Pädiatrie-Warnung: {drugShortageData.pediatric_count} Engpässe
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center py-3">
                <p className="text-xs text-slate-500">BfArM CSV hochladen für Analyse</p>
              </div>
            )}
          </div>

          {/* GrippeWeb placeholder / no-data card */}
          {!data?.grippeweb?.ARE && !data?.grippeweb?.ILI && (
            <div className="card p-5 fade-in" style={{ borderLeft: '3px solid #475569' }}>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-3 h-3 rounded-full" style={{ background: '#475569' }}></div>
                <span className="text-sm font-medium text-slate-400">GrippeWeb (RKI)</span>
              </div>
              <p className="text-xs text-slate-500">Keine GrippeWeb-Daten. Import via Datenquellen starten.</p>
            </div>
          )}
        </div>

        {/* ── Row 2: Main Chart + Forecast Toggle ── */}
        <div className="card p-6 fade-in">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-lg font-bold text-white">
                <span style={{ color: VIRUS_COLORS[selectedVirus] }}>{selectedVirus}</span> — Viruslast vs. Testkit-Bestand
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Abwasserdaten (AMELAG) {showForecast && data?.has_forecasts ? '+ ML-Prognose' : ''}
                {timeseries?.test_typ ? ` | Bestand: ${timeseries.test_typ}` : ''}
                {zoomStart !== null ? ' | Scroll/Pinch zum Zoomen' : ''}
              </p>
            </div>
            <div className="flex items-center gap-4">
              {/* Zoom Reset */}
              {zoomStart !== null && (
                <button
                  onClick={() => { setZoomStart(null); setZoomEnd(null); }}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all hover:bg-slate-600"
                  style={{ background: '#334155', color: '#94a3b8' }}
                >
                  Zoom zurücksetzen
                </button>
              )}
              {/* Forecast Toggle */}
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-400">ML-Prognose</span>
                <div
                  className={`toggle-switch ${showForecast ? 'active' : ''}`}
                  onClick={() => setShowForecast(!showForecast)}
                />
              </div>
              {/* Run Forecast Button */}
              <button
                onClick={runForecast}
                disabled={forecastLoading}
                className="px-4 py-2 text-xs font-medium rounded-lg transition-all"
                style={{
                  background: forecastLoading ? '#334155' : 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
                  color: 'white',
                  opacity: forecastLoading ? 0.6 : 1
                }}
              >
                {forecastLoading ? 'Berechne...' : 'Prophet ausführen'}
              </button>
            </div>
          </div>

          <div
            onWheel={handleChartWheel}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            style={{ touchAction: 'pan-y' }}
          >
          <ResponsiveContainer width="100%" height={400}>
            <ComposedChart data={visibleData} margin={{ top: 5, right: 60, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#64748b', fontSize: 11 }}
                tickLine={{ stroke: '#334155' }}
                interval="preserveStartEnd"
              />
              {/* Left Y-axis: Viruslast */}
              <YAxis
                yAxisId="left"
                tick={{ fill: '#64748b', fontSize: 11 }}
                tickLine={{ stroke: '#334155' }}
                tickFormatter={(v: number) => fmt(v)}
                label={{ value: 'Genkopien/L', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 10 }, offset: 0 }}
              />
              {/* Right Y-axis: Testkit-Bestand */}
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fill: '#06b6d4', fontSize: 11 }}
                tickLine={{ stroke: '#06b6d4' }}
                axisLine={{ stroke: '#06b6d4', strokeOpacity: 0.4 }}
                tickFormatter={(v: number) => v >= 1000 ? (v / 1000).toFixed(1) + 'K' : String(v)}
                label={{ value: 'Testkits', angle: 90, position: 'insideRight', style: { fill: '#06b6d4', fontSize: 10 }, offset: 0 }}
              />
              <Tooltip
                contentStyle={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: 8,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)'
                }}
                labelStyle={{ color: '#f1f5f9' }}
                itemStyle={{ color: '#94a3b8' }}
                formatter={(value: number, name: string) => {
                  if (name === 'Bestand' || name === 'Min-Bestand') {
                    return [value?.toLocaleString('de-DE') + ' Testkits', name];
                  }
                  return [value?.toFixed(0) + ' Genkopien/L', name];
                }}
              />
              <Legend
                wrapperStyle={{ paddingTop: 16 }}
                formatter={(value: string) => <span style={{ color: '#94a3b8', fontSize: 12 }}>{value}</span>}
              />
              {/* Confidence band */}
              {showForecast && (
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="Obergrenze"
                  stroke="none"
                  fill={VIRUS_COLORS[selectedVirus] || '#3b82f6'}
                  fillOpacity={0.08}
                  legendType="none"
                />
              )}
              {showForecast && (
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="Untergrenze"
                  stroke="none"
                  fill={VIRUS_COLORS[selectedVirus] || '#3b82f6'}
                  fillOpacity={0.08}
                  legendType="none"
                />
              )}
              {/* Bestand area (right axis) */}
              <Area
                yAxisId="right"
                type="stepAfter"
                dataKey="Bestand"
                stroke="#06b6d4"
                strokeWidth={2}
                fill="#06b6d4"
                fillOpacity={0.06}
                dot={false}
                connectNulls
              />
              {/* Min-Bestand reference line (right axis) */}
              <Line
                yAxisId="right"
                type="stepAfter"
                dataKey="Min-Bestand"
                stroke="#ef4444"
                strokeWidth={1}
                strokeDasharray="4 2"
                dot={false}
                connectNulls
                legendType="none"
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="Messwert"
                stroke={VIRUS_COLORS[selectedVirus] || '#3b82f6'}
                strokeWidth={2}
                dot={false}
                connectNulls={false}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="RKI Prognose"
                stroke="#64748b"
                strokeWidth={1}
                strokeDasharray="4 4"
                dot={false}
                connectNulls={false}
              />
              {showForecast && (
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="ML Prognose"
                  stroke="#f59e0b"
                  strokeWidth={2.5}
                  strokeDasharray="6 3"
                  dot={false}
                  connectNulls={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
          </div>

          {!data?.has_forecasts && (
            <div className="mt-4 p-4 rounded-lg text-center" style={{ background: '#334155', border: '1px dashed #475569' }}>
              <p className="text-sm text-slate-400">
                Noch keine ML-Prognose vorhanden. Klicke "Prophet ausführen" um eine 14-Tage-Prognose zu erstellen.
              </p>
            </div>
          )}

          {/* GrippeWeb sub-chart */}
          {showGrippeWeb && grippeWebSeries.length > 0 && (
            <div className="mt-4 pt-4" style={{ borderTop: '1px solid #334155' }}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <h3 className="text-sm font-bold text-white">
                    GrippeWeb — {selectedGrippeWeb === 'ARE' ? 'Atemwegserkrankungen' : 'Influenza-like Illness'}
                  </h3>
                  <div className="flex items-center gap-1">
                    <button
                      className={`px-2 py-0.5 text-xs rounded-l ${selectedGrippeWeb === 'ARE' ? 'bg-amber-500/20 text-amber-400 font-medium' : 'bg-slate-700 text-slate-400'}`}
                      onClick={() => setSelectedGrippeWeb('ARE')}
                    >ARE</button>
                    <button
                      className={`px-2 py-0.5 text-xs rounded-r ${selectedGrippeWeb === 'ILI' ? 'bg-pink-500/20 text-pink-400 font-medium' : 'bg-slate-700 text-slate-400'}`}
                      onClick={() => setSelectedGrippeWeb('ILI')}
                    >ILI</button>
                  </div>
                </div>
                <button
                  onClick={() => setShowGrippeWeb(false)}
                  className="text-xs text-slate-500 hover:text-slate-300 transition"
                >Ausblenden</button>
              </div>
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={grippeWebSeries.map(d => ({
                  ...d,
                  label: `KW ${d.kalenderwoche}`,
                }))} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: '#64748b', fontSize: 10 }}
                    tickLine={{ stroke: '#334155' }}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fill: '#64748b', fontSize: 10 }}
                    tickLine={{ stroke: '#334155' }}
                    tickFormatter={(v: number) => v >= 1000 ? (v / 1000).toFixed(1) + 'K' : String(v.toFixed(0))}
                  />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                    labelStyle={{ color: '#f1f5f9' }}
                    formatter={(value: number) => [value?.toFixed(1) + ' pro 100.000', 'Inzidenz']}
                  />
                  <Area
                    type="monotone"
                    dataKey="inzidenz"
                    stroke={selectedGrippeWeb === 'ARE' ? '#f59e0b' : '#ec4899'}
                    strokeWidth={2}
                    fill={selectedGrippeWeb === 'ARE' ? '#f59e0b' : '#ec4899'}
                    fillOpacity={0.1}
                    dot={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* ── Row 3: Inventory + Recommendations ── */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

          {/* Testkit-Bestand + Stockout Analysis */}
          <div className="card p-6 fade-in">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="text-lg font-bold text-white">Testkit-Bestand &amp; Nachbestellung</h2>
                <p className="text-xs text-slate-500 mt-1">Prädiktive Bestandssteuerung mit ML-Prognose</p>
              </div>
              <div className="flex items-center gap-2">
                {!data?.has_inventory && (
                  <button
                    onClick={seedInventory}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-700 text-slate-300 hover:bg-slate-600 transition"
                  >
                    Demo-Daten laden
                  </button>
                )}
                {data?.has_inventory && (
                  <button
                    onClick={downloadSAPOrders}
                    disabled={orderLoading}
                    className="px-3 py-1.5 text-xs font-semibold rounded-lg transition-all"
                    style={{
                      background: orderLoading ? '#334155' : 'linear-gradient(135deg, #10b981, #059669)',
                      color: 'white',
                      opacity: orderLoading ? 0.6 : 1
                    }}
                  >
                    {orderLoading ? 'Exportiere...' : 'SAP-Bestellung exportieren'}
                  </button>
                )}
              </div>
            </div>

            {/* Stockout Alert Banner */}
            {stockoutData && stockoutData.critical_items > 0 && (
              <div className="mb-4 p-3 rounded-lg flex items-center gap-3" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)' }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01"/></svg>
                <div>
                  <span className="text-sm font-bold text-red-400">{stockoutData.critical_items} kritische{stockoutData.critical_items > 1 ? ' Artikel' : 'r Artikel'}</span>
                  <span className="text-xs text-slate-400 ml-2">|</span>
                  <span className="text-xs text-slate-400 ml-2">{stockoutData.items_needing_reorder} Nachbestellungen empfohlen</span>
                </div>
              </div>
            )}

            {data?.has_inventory && stockoutData?.analyses ? (
              <div className="space-y-3">
                {stockoutData.analyses.map((item: any) => (
                  <div key={item.test_typ} className="slide-in p-3 rounded-lg" style={{ background: '#0f172a', border: '1px solid #334155' }}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-slate-300 font-medium">{item.test_typ}</span>
                        <span className={`badge badge-${item.risk_level === 'critical' ? 'critical' : item.risk_level === 'high' ? 'high' : item.risk_level === 'medium' ? 'warning' : 'good'}`}>
                          {item.risk_level}
                        </span>
                      </div>
                      <span className="text-sm font-bold text-white">{item.current_stock.toLocaleString('de-DE')} St.</span>
                    </div>
                    <div className="relative h-2.5 rounded-full overflow-hidden mb-2" style={{ background: '#334155' }}>
                      <div
                        className="absolute top-0 bottom-0 w-0.5"
                        style={{ left: `${(item.min_stock / item.max_stock) * 100}%`, background: '#ef4444', opacity: 0.6, zIndex: 2 }}
                      />
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: `${Math.min((item.current_stock / item.max_stock) * 100, 100)}%`,
                          background: item.risk_level === 'critical' ? '#ef4444' : item.risk_level === 'high' ? '#f59e0b' : '#10b981'
                        }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-500">
                        Stockout in <strong className={item.days_until_stockout < 14 ? 'text-red-400' : 'text-slate-400'}>{item.days_until_stockout.toFixed(0)} Tagen</strong>
                      </span>
                      <span className="text-slate-500">
                        Verbrauch: {item.adjusted_daily_consumption}/Tag
                        {item.forecast_multiplier !== 1.0 && (
                          <span className={item.forecast_multiplier > 1 ? 'text-amber-400 ml-1' : 'text-green-400 ml-1'}>
                            ({item.forecast_multiplier.toFixed(1)}x ML)
                          </span>
                        )}
                      </span>
                    </div>
                    {item.needs_reorder && (
                      <div className="mt-2 pt-2 flex items-center justify-between" style={{ borderTop: '1px solid #334155' }}>
                        <span className="text-xs text-amber-400 font-medium">
                          Empfehlung: {item.optimal_order_quantity.toLocaleString('de-DE')} St. nachbestellen
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : data?.has_inventory ? (
              <div className="space-y-4">
                {Object.entries(data.inventory).map(([name, inv]) => (
                  <div key={name} className="slide-in">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm text-slate-300 truncate" style={{ maxWidth: '60%' }}>{name}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-white">{inv.current.toLocaleString('de-DE')}</span>
                        <span className={`badge badge-${inv.status}`}>{inv.status}</span>
                      </div>
                    </div>
                    <div className="relative h-3 rounded-full overflow-hidden" style={{ background: '#334155' }}>
                      <div className="absolute top-0 bottom-0 w-0.5" style={{ left: `${(inv.min / inv.max) * 100}%`, background: '#ef4444', opacity: 0.6, zIndex: 2 }} />
                      <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.min(inv.fill_percentage, 100)}%`, background: inv.status === 'critical' ? '#ef4444' : inv.status === 'warning' ? '#f59e0b' : '#10b981' }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center rounded-lg" style={{ background: '#0f172a' }}>
                <p className="text-sm text-slate-500">Keine Bestandsdaten vorhanden</p>
              </div>
            )}
          </div>

          {/* LLM Empfehlungen */}
          <div className="card p-6 fade-in">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="text-lg font-bold text-white">KI-Empfehlungen</h2>
                <p className="text-xs text-slate-500 mt-1">Automatische Handlungsempfehlungen</p>
              </div>
              <button
                onClick={generateRecs}
                disabled={recsLoading}
                className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all"
                style={{
                  background: recsLoading ? '#334155' : 'linear-gradient(135deg, #10b981, #06b6d4)',
                  color: 'white',
                  opacity: recsLoading ? 0.6 : 1
                }}
              >
                {recsLoading ? 'Generiere...' : 'Empfehlungen generieren'}
              </button>
            </div>

            {data?.recommendations && data.recommendations.length > 0 ? (
              <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1" style={{ scrollbarWidth: 'thin' }}>
                {data.recommendations.map((rec) => {
                  const priority = rec.action?.priority || 'normal';
                  const isExpanded = expandedRec === rec.id;
                  const textClean = rec.text.replace(/\*\*/g, '');
                  const isLong = textClean.length > 200;
                  return (
                    <div key={rec.id} className="p-4 rounded-lg slide-in" style={{ background: '#0f172a', border: '1px solid #334155' }}>
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className={`badge badge-${priority}`}>{priority}</span>
                          {rec.action?.action_type && (
                            <span className="text-xs text-slate-500">{rec.action.action_type}</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {rec.approved ? (
                            <span className="text-xs text-green-400 flex items-center gap-1">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 6L9 17l-5-5"/></svg>
                              Genehmigt
                            </span>
                          ) : (
                            <button
                              onClick={() => approveRec(rec.id)}
                              className="text-xs px-2 py-1 rounded bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition"
                            >
                              Genehmigen
                            </button>
                          )}
                        </div>
                      </div>
                      <div
                        className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap"
                        style={isExpanded ? {} : { maxHeight: 80, overflow: 'hidden', maskImage: isLong ? 'linear-gradient(to bottom, black 60%, transparent 100%)' : undefined, WebkitMaskImage: isLong ? 'linear-gradient(to bottom, black 60%, transparent 100%)' : undefined }}
                      >
                        {isExpanded ? textClean : textClean.substring(0, 250)}
                      </div>
                      {isLong && (
                        <button
                          onClick={() => setExpandedRec(isExpanded ? null : rec.id)}
                          className="text-xs text-blue-400 hover:text-blue-300 mt-1 transition"
                        >
                          {isExpanded ? 'Weniger anzeigen' : 'Mehr anzeigen...'}
                        </button>
                      )}
                      <div className="flex items-center justify-between mt-2 pt-2" style={{ borderTop: '1px solid #334155' }}>
                        <span className="text-[10px] text-slate-600">
                          Konfidenz: {(rec.confidence * 100).toFixed(0)}%
                        </span>
                        <span className="text-[10px] text-slate-600">
                          {format(new Date(rec.created_at), 'dd.MM.yy HH:mm', { locale: de })}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-8 text-center rounded-lg" style={{ background: '#0f172a' }}>
                <p className="text-sm text-slate-500 mb-3">Noch keine Empfehlungen generiert</p>
                <p className="text-xs text-slate-600">
                  Klicke "Empfehlungen generieren" nach dem Ausführen der Prophet-Prognose.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* ── Row 4: Trends + Forecast Summary + Weather ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Google Trends */}
          <div className="card p-6 fade-in">
            <h2 className="text-lg font-bold text-white mb-4">Google Trends</h2>
            <p className="text-xs text-slate-500 mb-4">Suchinteresse Deutschland (letzte 30 Tage)</p>
            {data?.top_trends && data.top_trends.length > 0 ? (
              <div className="space-y-3">
                {data.top_trends.map((trend, idx) => {
                  const barColors = ['#3b82f6', '#8b5cf6', '#06b6d4', '#f59e0b', '#10b981'];
                  const barColor = barColors[idx % barColors.length];
                  return (
                    <div key={idx} className="slide-in">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-slate-300">{trend.keyword}</span>
                        <span className="text-xs font-mono text-slate-500">{trend.score.toFixed(0)}</span>
                      </div>
                      <div className="h-2 rounded-full overflow-hidden" style={{ background: '#334155' }}>
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{ width: `${trend.score}%`, background: barColor }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-4">Keine Trends-Daten</p>
            )}
          </div>

          {/* Forecast Summary */}
          <div className="card p-6 fade-in">
            <h2 className="text-lg font-bold text-white mb-4">Prognose-Übersicht</h2>
            <p className="text-xs text-slate-500 mb-4">Prophet ML-Modell (14 Tage)</p>
            {data?.has_forecasts && data.forecast_summary ? (
              <div className="space-y-4">
                {Object.entries(data.forecast_summary).map(([virus, fc]) => (
                  <div key={virus} className="flex items-center justify-between p-3 rounded-lg slide-in" style={{ background: '#0f172a' }}>
                    <div className="flex items-center gap-3">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ background: VIRUS_COLORS[virus] || '#3b82f6' }}></div>
                      <div>
                        <div className="text-sm font-medium text-slate-300">{virus}</div>
                        <div className="text-[10px] text-slate-600">{fc.days} Tage | {fc.model_version}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold" style={{ color: trendColor(fc.trend) }}>
                        {trendArrow(fc.trend)} {fc.trend}
                      </div>
                      <div className="text-[10px] text-slate-600">
                        Konfidenz: {(fc.confidence * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center rounded-lg" style={{ background: '#0f172a' }}>
                <p className="text-sm text-slate-500">Prognose ausführen für Details</p>
              </div>
            )}
          </div>

          {/* Weather + Meta */}
          <div className="space-y-6">
            <div className="card p-6 fade-in">
              <h2 className="text-lg font-bold text-white mb-4">Wetter</h2>
              <p className="text-xs text-slate-500 mb-4">Durchschnitt Deutschland</p>
              {data?.weather && (
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 rounded-lg text-center" style={{ background: '#0f172a' }}>
                    <div className="text-2xl font-bold text-white">
                      {data.weather.avg_temperature.toFixed(1)}&deg;C
                    </div>
                    <div className="text-xs text-slate-500 mt-1">Temperatur</div>
                  </div>
                  <div className="p-3 rounded-lg text-center" style={{ background: '#0f172a' }}>
                    <div className="text-2xl font-bold text-white">
                      {data.weather.avg_humidity.toFixed(0)}%
                    </div>
                    <div className="text-xs text-slate-500 mt-1">Luftfeuchtigkeit</div>
                  </div>
                </div>
              )}
            </div>

            <div className="card p-6 fade-in">
              <h2 className="text-sm font-bold text-white mb-3">Datenquellen</h2>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between text-slate-400">
                  <span>AMELAG Abwasser (RKI)</span>
                  <span className="text-green-400">aktiv</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>GrippeWeb (RKI)</span>
                  <span className={data?.grippeweb?.ARE ? 'text-green-400' : 'text-slate-600'}>
                    {data?.grippeweb?.ARE ? 'aktiv' : 'keine Daten'}
                  </span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>BfArM Engpässe</span>
                  <span className={drugShortageData ? 'text-green-400' : 'text-slate-600'}>
                    {drugShortageData ? 'geladen' : 'nicht geladen'}
                  </span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Google Trends</span>
                  <span className="text-green-400">aktiv</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>OpenWeather API</span>
                  <span className={data?.weather?.avg_temperature ? 'text-green-400' : 'text-amber-400'}>
                    {data?.weather?.avg_temperature ? 'aktiv' : 'kein API Key'}
                  </span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Schulferien</span>
                  <span className="text-green-400">aktiv</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Prophet ML</span>
                  <span className={data?.has_forecasts ? 'text-green-400' : 'text-slate-600'}>
                    {data?.has_forecasts ? 'aktiv' : 'nicht gestartet'}
                  </span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Fusion Engine</span>
                  <span className={outbreakScore ? 'text-green-400' : 'text-slate-600'}>
                    {outbreakScore ? `Score: ${outbreakScore.overall_score}` : 'berechne...'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

      </main>

      {/* ── Footer ── */}
      <footer className="mt-8 py-4 text-center text-xs text-slate-600" style={{ borderTop: '1px solid #1e293b' }}>
        LabPulse Pro v1.0 &mdash; Intelligentes Frühwarnsystem für Labordiagnostik
      </footer>
    </div>
  );
};

export default Dashboard;
