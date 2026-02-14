import React, { useState, useEffect, useCallback } from 'react';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine, ComposedChart,
  Cell
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

interface DashboardData {
  current_viral_loads: Record<string, ViralLoad>;
  top_trends: Array<{ keyword: string; score: number }>;
  are_inzidenz: { value: number | null; date: string | null };
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
  const [data, setData] = useState<DashboardData | null>(null);
  const [selectedVirus, setSelectedVirus] = useState('Influenza A');
  const [timeseries, setTimeseries] = useState<{ historical: TimeseriesPoint[]; forecast: ForecastPoint[] } | null>(null);
  const [sparklines, setSparklines] = useState<Record<string, SparklinePoint[]>>({});
  const [showForecast, setShowForecast] = useState(true);
  const [loading, setLoading] = useState(true);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [recsLoading, setRecsLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

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

  useEffect(() => {
    fetchOverview();
    fetchSparklines();
  }, [fetchOverview, fetchSparklines]);

  useEffect(() => {
    fetchTimeseries();
  }, [fetchTimeseries]);

  // Run ML forecast
  const runForecast = async () => {
    setForecastLoading(true);
    try {
      await fetch('/api/v1/forecast/run', { method: 'POST' });
      // Poll for completion
      setTimeout(async () => {
        await fetchOverview();
        await fetchTimeseries();
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

  // Approve recommendation
  const approveRec = async (id: number) => {
    try {
      await fetch(`/api/v1/recommendations/${id}/approve`, { method: 'POST' });
      await fetchOverview();
    } catch (e) {
      console.error('Approve error:', e);
    }
  };

  // Build chart data
  const chartData = React.useMemo(() => {
    if (!timeseries) return [];
    const hist = (timeseries.historical || []).map((d) => ({
      date: format(new Date(d.date), 'dd. MMM', { locale: de }),
      rawDate: d.date,
      'Messwert': d.viral_load,
      'RKI Prognose': d.prediction,
    }));
    if (showForecast && timeseries.forecast && timeseries.forecast.length > 0) {
      const last = hist.length > 0 ? hist[hist.length - 1] : null;
      const forecasts = timeseries.forecast.map((d) => ({
        date: format(new Date(d.date), 'dd. MMM', { locale: de }),
        rawDate: d.date,
        'ML Prognose': d.predicted_value,
        'Obergrenze': d.upper_bound,
        'Untergrenze': d.lower_bound,
      }));
      // Connect last historical to first forecast
      if (last && forecasts.length > 0) {
        forecasts[0] = { ...forecasts[0], 'Messwert': last['Messwert'] } as any;
      }
      return [...hist, ...forecasts];
    }
    return hist;
  }, [timeseries, showForecast]);

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
              <h1 className="text-xl font-bold text-white tracking-tight">VirusRadar Pro</h1>
              <p className="text-xs text-slate-400">Intelligentes Fruehwarnsystem fuer Labordiagnostik</p>
            </div>
          </div>
          <div className="flex items-center gap-6">
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

        {/* ── Row 2: Main Chart + Forecast Toggle ── */}
        <div className="card p-6 fade-in">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-lg font-bold text-white">{selectedVirus} — Viruslast-Verlauf</h2>
              <p className="text-xs text-slate-500 mt-1">
                Abwasserdaten (AMELAG) {showForecast && data?.has_forecasts ? '+ ML-Prognose (Prophet)' : ''}
              </p>
            </div>
            <div className="flex items-center gap-4">
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
                {forecastLoading ? 'Berechne...' : 'Prophet ausfuehren'}
              </button>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={380}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#64748b', fontSize: 11 }}
                tickLine={{ stroke: '#334155' }}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: '#64748b', fontSize: 11 }}
                tickLine={{ stroke: '#334155' }}
                tickFormatter={(v: number) => fmt(v)}
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
                formatter={(value: number) => [value?.toFixed(0) + ' Genkopien/L', '']}
              />
              <Legend
                wrapperStyle={{ paddingTop: 16 }}
                formatter={(value: string) => <span style={{ color: '#94a3b8', fontSize: 12 }}>{value}</span>}
              />
              {/* Confidence band */}
              {showForecast && (
                <Area
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
                  type="monotone"
                  dataKey="Untergrenze"
                  stroke="none"
                  fill={VIRUS_COLORS[selectedVirus] || '#3b82f6'}
                  fillOpacity={0.08}
                  legendType="none"
                />
              )}
              <Line
                type="monotone"
                dataKey="Messwert"
                stroke={VIRUS_COLORS[selectedVirus] || '#3b82f6'}
                strokeWidth={2}
                dot={false}
                connectNulls={false}
              />
              <Line
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

          {!data?.has_forecasts && (
            <div className="mt-4 p-4 rounded-lg text-center" style={{ background: '#334155', border: '1px dashed #475569' }}>
              <p className="text-sm text-slate-400">
                Noch keine ML-Prognose vorhanden. Klicke "Prophet ausfuehren" um eine 14-Tage-Prognose zu erstellen.
              </p>
            </div>
          )}
        </div>

        {/* ── Row 3: Inventory + Recommendations ── */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

          {/* Testkit-Bestand */}
          <div className="card p-6 fade-in">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="text-lg font-bold text-white">Testkit-Bestand</h2>
                <p className="text-xs text-slate-500 mt-1">Aktueller Lagerbestand vs. Kapazitaet</p>
              </div>
              {!data?.has_inventory && (
                <button
                  onClick={seedInventory}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-700 text-slate-300 hover:bg-slate-600 transition"
                >
                  Demo-Daten laden
                </button>
              )}
            </div>

            {data?.has_inventory && data.inventory ? (
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
                      {/* Min threshold marker */}
                      <div
                        className="absolute top-0 bottom-0 w-0.5"
                        style={{
                          left: `${(inv.min / inv.max) * 100}%`,
                          background: '#ef4444',
                          opacity: 0.6,
                          zIndex: 2
                        }}
                      />
                      {/* Fill bar */}
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: `${Math.min(inv.fill_percentage, 100)}%`,
                          background: inv.status === 'critical' ? '#ef4444' :
                                     inv.status === 'warning' ? '#f59e0b' : '#10b981'
                        }}
                      />
                    </div>
                    <div className="flex justify-between mt-1">
                      <span className="text-[10px] text-slate-600">0</span>
                      <span className="text-[10px] text-slate-600">Min: {inv.min}</span>
                      <span className="text-[10px] text-slate-600">Max: {inv.max.toLocaleString('de-DE')}</span>
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
              <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
                {data.recommendations.map((rec) => {
                  const priority = rec.action?.priority || 'normal';
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
                      <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap" style={{ maxHeight: 120, overflow: 'hidden' }}>
                        {rec.text.replace(/\*\*/g, '').substring(0, 300)}{rec.text.length > 300 ? '...' : ''}
                      </div>
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
                  Klicke "Empfehlungen generieren" nach dem Ausfuehren der Prophet-Prognose.
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
            <h2 className="text-lg font-bold text-white mb-4">Prognose-Uebersicht</h2>
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
                <p className="text-sm text-slate-500">Prognose ausfuehren fuer Details</p>
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
              </div>
            </div>
          </div>
        </div>

      </main>

      {/* ── Footer ── */}
      <footer className="mt-8 py-4 text-center text-xs text-slate-600" style={{ borderTop: '1px solid #1e293b' }}>
        VirusRadar Pro v1.0 &mdash; Intelligentes Fruehwarnsystem fuer Labordiagnostik
      </footer>
    </div>
  );
};

export default Dashboard;
