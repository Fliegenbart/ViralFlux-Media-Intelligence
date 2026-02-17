import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';
import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  BentoTile,
  PeixScoreSummary,
  RecommendationCard,
  RegionRecommendationRef,
  SourceStatusSummary,
} from '../types/media';

const BUNDESLAND_PATHS: Record<string, { d: string; cx: number; cy: number }> = {
  SH: { d: 'M195,10 L230,5 L250,25 L260,60 L240,80 L215,90 L190,80 L180,55 L185,30Z', cx: 220, cy: 48 },
  HH: { d: 'M220,90 L240,88 L245,100 L235,108 L218,105Z', cx: 232, cy: 98 },
  MV: { d: 'M260,20 L340,10 L370,30 L365,55 L340,70 L300,75 L270,65 L255,50Z', cx: 315, cy: 42 },
  HB: { d: 'M190,105 L210,100 L215,115 L200,120 L188,115Z', cx: 202, cy: 110 },
  NI: { d: 'M140,80 L190,75 L220,90 L225,115 L250,130 L260,165 L230,190 L200,195 L160,185 L130,160 L110,130 L120,100Z', cx: 185, cy: 140 },
  BB: { d: 'M310,80 L370,85 L385,110 L380,160 L355,185 L310,190 L290,170 L285,130 L295,100Z', cx: 335, cy: 135 },
  BE: { d: 'M325,120 L345,118 L348,135 L340,142 L322,138Z', cx: 335, cy: 130 },
  ST: { d: 'M260,130 L290,125 L310,140 L305,185 L280,200 L255,195 L240,175 L245,150Z', cx: 275, cy: 162 },
  NW: { d: 'M80,170 L140,160 L170,180 L175,215 L160,250 L130,265 L90,255 L65,230 L60,200Z', cx: 118, cy: 215 },
  HE: { d: 'M150,220 L190,210 L210,230 L205,275 L190,300 L160,305 L140,285 L135,250Z', cx: 172, cy: 260 },
  TH: { d: 'M220,200 L280,195 L300,215 L295,250 L270,265 L235,260 L215,240Z', cx: 258, cy: 228 },
  SN: { d: 'M300,200 L365,195 L380,220 L370,255 L340,270 L305,260 L295,235Z', cx: 338, cy: 230 },
  RP: { d: 'M60,265 L100,255 L125,275 L130,310 L120,340 L90,355 L60,340 L45,310 L48,280Z', cx: 88, cy: 305 },
  SL: { d: 'M55,345 L80,338 L90,360 L78,375 L55,370Z', cx: 72, cy: 358 },
  BW: { d: 'M95,340 L145,310 L185,320 L200,355 L190,400 L160,430 L120,435 L85,415 L70,385 L80,360Z', cx: 140, cy: 380 },
  BY: { d: 'M185,270 L240,260 L290,275 L320,310 L330,360 L310,410 L270,440 L230,445 L195,430 L175,400 L170,350 L175,310Z', cx: 250, cy: 360 },
};

const VIRUS_OPTIONS = ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'];
const TARGET_OPTIONS = [
  { value: 'RKI_ARE', label: 'RKI ARE' },
  { value: 'MYCOPLASMA', label: 'SURVSTAT Mycoplasma' },
  { value: 'KEUCHHUSTEN', label: 'SURVSTAT Keuchhusten' },
  { value: 'PNEUMOKOKKEN', label: 'SURVSTAT Pneumokokken' },
];

interface MapRegion {
  name: string;
  avg_viruslast: number;
  intensity: number;
  trend: string;
  change_pct: number;
  n_standorte: number;
  peix_score?: number;
  peix_band?: string;
  impact_probability?: number;
  recommendation_ref?: RegionRecommendationRef | null;
}

interface CockpitResponse {
  bento: {
    tiles: BentoTile[];
    count: number;
  };
  peix_epi_score: PeixScoreSummary;
  source_status: SourceStatusSummary;
  map: {
    has_data: boolean;
    date: string | null;
    max_viruslast: number;
    regions: Record<string, MapRegion>;
    top_regions: Array<{ code: string } & MapRegion>;
    activation_suggestions: Array<{
      region: string;
      region_name: string;
      priority: string;
      budget_shift_pct: number;
      channel_mix: Record<string, number>;
      reason: string;
    }>;
  };
  recommendations: {
    total: number;
    cards: RecommendationCard[];
  };
  backtest_summary: {
    latest_market: any;
    latest_customer: any;
    recent_runs: Array<any>;
  };
  data_freshness: Record<string, string | null>;
}

const intensityColor = (intensity: number) => {
  const a = 0.2 + Math.min(1, Math.max(0, intensity)) * 0.8;
  return `rgba(27, 83, 155, ${a})`;
};

const trendIcon = (trend: string) => (trend === 'steigend' ? '\u2197' : trend === 'fallend' ? '\u2198' : '\u2192');
const mappingLabel = (status?: string) => {
  if (!status) return 'Unbekannt';
  if (status === 'approved') return 'Freigegeben';
  if (status === 'needs_review') return 'Review ausstehend';
  if (status === 'not_applicable') return 'N/A';
  return status;
};

const MediaCockpit: React.FC = () => {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const initialTab = params.get('tab') || 'map';

  const [tab, setTab] = useState<'map' | 'recommendations' | 'backtest'>(
    initialTab === 'recommendations' || initialTab === 'backtest' ? (initialTab as any) : 'map'
  );
  const [virus, setVirus] = useState('Influenza A');
  const [targetSource, setTargetSource] = useState('RKI_ARE');
  const [cockpit, setCockpit] = useState<CockpitResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [openingRegion, setOpeningRegion] = useState<string | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);

  const [recLoading, setRecLoading] = useState(false);
  const [recCards, setRecCards] = useState<RecommendationCard[]>([]);
  const [brand, setBrand] = useState('GeloMyrtol');
  const [product, setProduct] = useState('GeloMyrtol forte');
  const [goal, setGoal] = useState('Top-of-Mind vor Erkältungswelle');
  const [weeklyBudget, setWeeklyBudget] = useState(120000);
  const [recStatusFilter, setRecStatusFilter] = useState<string>('all');
  const [recBrandFilter, setRecBrandFilter] = useState<string>('');
  const [recMinUrgency, setRecMinUrgency] = useState<number>(0);
  const [recRegionFilter, setRecRegionFilter] = useState<string>('');
  const [recConditionFilter, setRecConditionFilter] = useState<string>('');

  const [marketRun, setMarketRun] = useState<any | null>(null);
  const [marketRunning, setMarketRunning] = useState(false);
  const [customerRun, setCustomerRun] = useState<any | null>(null);
  const [customerRunning, setCustomerRunning] = useState(false);
  const [runs, setRuns] = useState<any[]>([]);
  const [customerFile, setCustomerFile] = useState<File | null>(null);

  const activeMap = cockpit?.map;

  const loadCockpit = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ virus_typ: virus, target_source: targetSource });
      const res = await fetch(`/api/v1/media/cockpit?${qs.toString()}`);
      const data = await res.json();
      setCockpit(data);
      setRuns(data?.backtest_summary?.recent_runs || []);
    } catch (e) {
      console.error('Cockpit fetch error', e);
    } finally {
      setLoading(false);
    }
  }, [virus, targetSource]);

  const loadRuns = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/backtest/runs?limit=30');
      if (!res.ok) return;
      const data = await res.json();
      setRuns(data.runs || []);
    } catch (e) {
      console.error('Runs fetch error', e);
    }
  }, []);

  useEffect(() => {
    loadCockpit();
  }, [loadCockpit]);

  useEffect(() => {
    const next = params.get('tab');
    if (next === 'map' || next === 'recommendations' || next === 'backtest') {
      setTab(next);
    }
  }, [params]);

  const loadRecommendations = useCallback(async () => {
    const qs = new URLSearchParams();
    if (recStatusFilter !== 'all') qs.set('status', recStatusFilter);
    if (recBrandFilter.trim()) qs.set('brand', recBrandFilter.trim());
    if (recMinUrgency > 0) qs.set('min_urgency', String(recMinUrgency));
    if (recRegionFilter.trim()) qs.set('region', recRegionFilter.trim());
    if (recConditionFilter.trim()) qs.set('condition_key', recConditionFilter.trim());
    qs.set('limit', '100');
    qs.set('with_campaign_preview', 'true');
    try {
      const res = await fetch(`/api/v1/media/recommendations/list?${qs.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      const sorted = [...(data.cards || [])].sort((a, b) => {
        const urgencyDelta = Number(b.urgency_score || 0) - Number(a.urgency_score || 0);
        if (urgencyDelta !== 0) return urgencyDelta;
        return Number(b.confidence || 0) - Number(a.confidence || 0);
      });
      setRecCards(sorted);
    } catch (e) {
      console.error('Recommendation list error', e);
    }
  }, [recStatusFilter, recBrandFilter, recMinUrgency, recRegionFilter, recConditionFilter]);

  useEffect(() => {
    if (tab === 'recommendations') {
      loadRecommendations();
    }
  }, [tab, loadRecommendations]);

  const switchTab = (next: 'map' | 'recommendations' | 'backtest') => {
    setTab(next);
    setParams({ tab: next });
  };

  const openRecommendationForRegion = async (regionCode: string) => {
    setSelectedRegion(regionCode);
    setOpeningRegion(regionCode);
    try {
      const res = await fetch('/api/v1/media/recommendations/open-region', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_code: regionCode,
          brand,
          product,
          campaign_goal: goal,
          weekly_budget: weeklyBudget,
          virus_typ: virus,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      if (data?.detail_url) {
        navigate(data.detail_url);
      }
    } catch (e) {
      console.error('Region open recommendation error', e);
    } finally {
      setOpeningRegion(null);
    }
  };

  const triggerRecommendations = async () => {
    setRecLoading(true);
    try {
      const res = await fetch('/api/v1/media/recommendations/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brand,
          product,
          campaign_goal: goal,
          weekly_budget: weeklyBudget,
          channel_pool: ['programmatic', 'social', 'search', 'ctv'],
        }),
      });
      const data = await res.json();
      const sorted = [...(data.cards || [])].sort((a, b) => {
        const urgencyDelta = Number(b.urgency_score || 0) - Number(a.urgency_score || 0);
        if (urgencyDelta !== 0) return urgencyDelta;
        return Number(b.confidence || 0) - Number(a.confidence || 0);
      });
      setRecCards(sorted);
      if (data?.auto_open_url) {
        navigate(data.auto_open_url);
      } else if (data?.top_card_id) {
        navigate(`/dashboard/recommendations/${encodeURIComponent(data.top_card_id)}`);
      } else {
        await loadRecommendations();
      }
      await loadCockpit();
    } catch (e) {
      console.error('Generate recommendation error', e);
    } finally {
      setRecLoading(false);
    }
  };

  const runMarketBacktest = async () => {
    setMarketRunning(true);
    try {
      const qs = new URLSearchParams({
        target_source: targetSource,
        virus_typ: virus,
        days_back: '730',
        horizon_days: '14',
      });
      const res = await fetch(`/api/v1/backtest/market?${qs.toString()}`, { method: 'POST' });
      const data = await res.json();
      setMarketRun(data);
      await loadRuns();
    } catch (e) {
      console.error('Market backtest error', e);
    } finally {
      setMarketRunning(false);
    }
  };

  const runCustomerBacktest = async () => {
    if (!customerFile) return;
    setCustomerRunning(true);
    try {
      const fd = new FormData();
      fd.append('file', customerFile);
      const qs = new URLSearchParams({ virus_typ: virus, horizon_days: '14' });
      const res = await fetch(`/api/v1/backtest/customer?${qs.toString()}`, {
        method: 'POST',
        body: fd,
      });
      const data = await res.json();
      setCustomerRun(data);
      await loadRuns();
    } catch (e) {
      console.error('Customer backtest error', e);
    } finally {
      setCustomerRunning(false);
    }
  };

  const mapRanking = useMemo(() => (activeMap?.top_regions || []), [activeMap]);
  const bentoTiles = useMemo(() => (cockpit?.bento?.tiles || []), [cockpit]);
  const sourceStatus = useMemo(() => (cockpit?.source_status?.items || []), [cockpit]);
  const peixSummary = cockpit?.peix_epi_score;
  const chartData = useMemo(() => {
    if (!marketRun?.chart_data) return [];
    return marketRun.chart_data.map((row: any) => ({
      ...row,
      dateLabel: row.date ? format(parseISO(row.date), 'dd.MM.yy', { locale: de }) : row.date,
    }));
  }, [marketRun]);

  const renderTileValue = (tile: BentoTile) => {
    if (tile.value === null || tile.value === undefined || tile.value === '') return '-';
    if (typeof tile.value === 'number') {
      return `${Math.round(tile.value * 10) / 10}` + (tile.unit ? ` ${tile.unit}` : '');
    }
    return String(tile.value) + (tile.unit ? ` ${tile.unit}` : '');
  };

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <header className="media-header">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-4 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="media-logo">VF</div>
            <div>
              <h1 className="text-xl font-semibold text-white tracking-tight">ViralFlux Media Cockpit</h1>
              <p className="text-xs text-slate-400">Deutschlandkarte + KI-Empfehlungen + Backtest Proof Engine</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {VIRUS_OPTIONS.map((v) => (
              <button
                key={v}
                onClick={() => setVirus(v)}
                className={`tab-chip ${virus === v ? 'active' : ''}`}
              >
                {v}
              </button>
            ))}
            <button onClick={() => navigate('/datenimport')} className="tab-chip">Datenimport</button>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 py-6 space-y-6">
        <div className="media-tabs">
          <button onClick={() => switchTab('map')} className={`media-tab ${tab === 'map' ? 'active' : ''}`}>Lagekarte</button>
          <button onClick={() => switchTab('recommendations')} className={`media-tab ${tab === 'recommendations' ? 'active' : ''}`}>KI-Empfehlungen</button>
          <button onClick={() => switchTab('backtest')} className={`media-tab ${tab === 'backtest' ? 'active' : ''}`}>Backtest</button>
        </div>

        {loading && (
          <div className="card p-8 text-center text-slate-400">Lade Media Cockpit...</div>
        )}

        {!loading && tab === 'map' && activeMap && (
          <div className="space-y-6">
            <div className="card p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-white">Bento-Übersicht aller relevanten Messwerte</h2>
                  <p className="text-xs text-slate-500">Sortiert nach Impact-Wahrscheinlichkeit. PeixEpiScore bleibt intern geschützt.</p>
                </div>
                <div className="text-xs text-slate-400">
                  Nationaler PeixEpiScore: <span className="text-cyan-300 font-semibold">{peixSummary?.national_score ?? '-'} / 100</span>
                  {' · '}
                  Band: <span className="text-slate-200">{peixSummary?.national_band ?? '-'}</span>
                  {' · '}
                  Impact: <span className="text-slate-200">{peixSummary?.national_impact_probability ?? '-'}%</span>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                {bentoTiles.map((tile) => (
                  <div key={tile.id} className="rounded-xl p-3" style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155' }}>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="text-xs text-slate-400">{tile.title}</div>
                      <span
                        className="inline-flex w-2.5 h-2.5 rounded-full"
                        style={{ background: tile.is_live ? '#22c55e' : '#ef4444' }}
                        title={tile.is_live ? 'Live' : 'Nicht live'}
                      />
                    </div>
                    <div className="text-base font-semibold text-white">{renderTileValue(tile)}</div>
                    <div className="text-[11px] text-slate-500 mt-1">{tile.subtitle || tile.data_source || '-'}</div>
                    <div className="text-[11px] text-cyan-300 mt-1">Impact: {Math.round(tile.impact_probability || 0)}%</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              <div className="xl:col-span-2 card p-5">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                  <div>
                    <h2 className="text-lg font-semibold text-white">Deutschlandkarte: {virus}</h2>
                    <p className="text-xs text-slate-500">
                      {activeMap.date ? `Stand ${format(parseISO(activeMap.date), 'dd.MM.yyyy', { locale: de })}` : 'Kein Datenstand'}
                    </p>
                  </div>
                  <div className="text-xs text-slate-500">Max {activeMap.max_viruslast?.toLocaleString('de-DE')} Genkopien/L</div>
                </div>

                {!activeMap.has_data ? (
                  <div className="py-16 text-center text-slate-500">Keine Kartendaten vorhanden.</div>
                ) : (
                  <svg viewBox="0 0 420 460" className="w-full max-h-[560px]">
                    {Object.entries(BUNDESLAND_PATHS).map(([code, geo]) => {
                      const region = activeMap.regions?.[code];
                      const fill = region ? intensityColor(region.intensity) : 'rgba(51,65,85,0.3)';
                      const isSelected = selectedRegion === code;
                      return (
                        <g
                          key={code}
                          style={{ cursor: region ? 'pointer' : 'default' }}
                          onClick={() => region && openRecommendationForRegion(code)}
                        >
                          <path d={geo.d} fill={fill} stroke={isSelected ? '#7dd3fc' : '#4b5563'} strokeWidth={isSelected ? 2 : 1} />
                          <text x={geo.cx} y={geo.cy - 5} textAnchor="middle" fill="#e2e8f0" fontSize="9" fontWeight="700">{code}</text>
                          {region && (
                            <text x={geo.cx} y={geo.cy + 8} textAnchor="middle" fill="#94a3b8" fontSize="7">
                              {Math.round(region.avg_viruslast).toLocaleString('de-DE')}
                            </text>
                          )}
                          {openingRegion === code && (
                            <text x={geo.cx} y={geo.cy + 18} textAnchor="middle" fill="#7dd3fc" fontSize="6">
                              öffne...
                            </text>
                          )}
                        </g>
                      );
                    })}
                  </svg>
                )}
              </div>

              <div className="space-y-6">
                <div className="card p-4">
                  <h3 className="text-sm font-semibold text-white mb-3">Top Regionen nach Impact</h3>
                  <div className="space-y-2">
                    {mapRanking.slice(0, 8).map((r, idx) => (
                      <button
                        key={r.code}
                        type="button"
                        onClick={() => openRecommendationForRegion(r.code)}
                        className="w-full text-left rounded-lg px-3 py-2 hover:brightness-110 transition"
                        style={{ background: 'rgba(15,23,42,0.65)' }}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-sm text-slate-200">{idx + 1}. {r.name}</div>
                            <div className="text-xs text-slate-500">{r.n_standorte} Messstellen · Impact {Math.round(r.impact_probability || 0)}%</div>
                          </div>
                          <div className="text-right">
                            <div className="text-sm text-white font-medium">{Math.round(r.avg_viruslast).toLocaleString('de-DE')}</div>
                            <div className="text-xs text-slate-500">{trendIcon(r.trend)} {r.change_pct > 0 ? '+' : ''}{r.change_pct}%</div>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="card p-4">
                  <h3 className="text-sm font-semibold text-white mb-3">Datenquellen Live-Status</h3>
                  <div className="space-y-2">
                    {sourceStatus.map((item) => (
                      <div key={item.source_key} className="rounded-lg px-3 py-2" style={{ background: 'rgba(15,23,42,0.65)' }}>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-slate-300">{item.label}</span>
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                                item.feed_reachable ? 'text-emerald-400 bg-emerald-500/10' : 'text-red-400 bg-red-500/10'
                              }`}
                            >
                              Feed {item.feed_reachable ? 'erreichbar' : 'nicht erreichbar'}
                            </span>
                            <span
                              className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                                item.is_live ? 'text-emerald-400 bg-emerald-500/10' : 'text-red-400 bg-red-500/10'
                              }`}
                            >
                              Datenstand {item.is_live ? 'aktuell' : item.last_updated ? 'älter' : 'kein Datum'}
                            </span>
                          </div>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-1">
                          {item.last_updated
                            ? `Messdatum: ${format(parseISO(item.last_updated), 'dd.MM.yyyy HH:mm', { locale: de })}`
                            : 'Messdatum: kein Zeitstempel'}
                          {' · '}
                          {item.age_days !== null && item.age_days !== undefined ? `Alter: ${item.age_days.toFixed(1)} Tage` : 'Alter: -'}
                          {' · '}SLA {item.sla_days}d
                        </div>
                      </div>
                    ))}
                    {sourceStatus.length === 0 && <div className="text-xs text-slate-500">Keine Quellenstatus verfügbar.</div>}
                  </div>
                </div>

                <div className="card p-4">
                  <h3 className="text-sm font-semibold text-white mb-3">Activation-Vorschläge</h3>
                  <div className="space-y-3">
                    {(activeMap.activation_suggestions || []).slice(0, 5).map((s, idx) => (
                      <div key={idx} className="rounded-lg p-3" style={{ background: 'rgba(15,23,42,0.75)', border: '1px solid #334155' }}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-white">{s.region_name}</span>
                          <span className="text-xs text-cyan-400">+{s.budget_shift_pct}%</span>
                        </div>
                        <p className="text-xs text-slate-400">{s.reason}</p>
                      </div>
                    ))}
                    {(!activeMap.activation_suggestions || activeMap.activation_suggestions.length === 0) && (
                      <p className="text-xs text-slate-500">Keine aktuellen Vorschläge.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {!loading && tab === 'recommendations' && (
          <div className="space-y-6">
            <div className="card p-5">
              <h2 className="text-lg font-semibold text-white mb-4">KI Action Cards</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3 mb-3">
                <input value={brand} onChange={(e) => setBrand(e.target.value)} className="media-input" placeholder="Brand" />
                <input value={product} onChange={(e) => setProduct(e.target.value)} className="media-input" placeholder="Produkt" />
                <input value={goal} onChange={(e) => setGoal(e.target.value)} className="media-input" placeholder="Kampagnenziel" />
                <input value={weeklyBudget} onChange={(e) => setWeeklyBudget(Number(e.target.value))} className="media-input" type="number" placeholder="Budget" />
                <button onClick={triggerRecommendations} className="media-button" disabled={recLoading}>
                  {recLoading ? 'Berechne...' : 'Empfehlungen erzeugen'}
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
                <select className="media-input" value={recStatusFilter} onChange={(e) => setRecStatusFilter(e.target.value)}>
                  <option value="all">Alle Status</option>
                  <option value="DRAFT">Draft</option>
                  <option value="READY">Ready</option>
                  <option value="APPROVED">Approved</option>
                  <option value="ACTIVATED">Activated</option>
                  <option value="DISMISSED">Dismissed</option>
                  <option value="EXPIRED">Expired</option>
                </select>
                <input
                  value={recBrandFilter}
                  onChange={(e) => setRecBrandFilter(e.target.value)}
                  className="media-input"
                  placeholder="Brand Filter"
                />
                <input
                  value={recMinUrgency}
                  onChange={(e) => setRecMinUrgency(Number(e.target.value))}
                  type="number"
                  min={0}
                  max={100}
                  className="media-input"
                  placeholder="Min Urgency"
                />
                <input
                  value={recRegionFilter}
                  onChange={(e) => setRecRegionFilter(e.target.value)}
                  className="media-input"
                  placeholder="Region (z.B. HH)"
                />
                <input
                  value={recConditionFilter}
                  onChange={(e) => setRecConditionFilter(e.target.value)}
                  className="media-input"
                  placeholder="Lageklasse"
                />
                <button onClick={loadRecommendations} className="media-button secondary">Liste aktualisieren</button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {recCards.map((card) => (
                <button
                  key={card.id}
                  type="button"
                  onClick={() => navigate(`/dashboard/recommendations/${encodeURIComponent(card.id)}`)}
                  className="card p-4 text-left hover:brightness-110 transition"
                >
                  <div className="flex items-center justify-between mb-2 gap-3">
                    <span className="text-xs text-slate-500">{card.type}</span>
                    <span className="text-xs text-emerald-400">Conf. {Math.round((card.confidence || 0) * 100)}%</span>
                  </div>
                  <h3 className="text-base text-white font-semibold">{card.campaign_name || `${card.brand} · ${card.product}`}</h3>
                  <p className="text-xs text-slate-500 mb-2">Status: {card.status} · Urgency: {Math.round(card.urgency_score || 0)}</p>
                  <div className="mb-2 text-xs">
                    <span
                      className="inline-flex items-center px-2 py-1 rounded-full"
                      style={{
                        background: card.mapping_status === 'approved'
                          ? 'rgba(16,185,129,0.15)'
                          : card.mapping_status === 'needs_review'
                          ? 'rgba(245,158,11,0.15)'
                          : 'rgba(71,85,105,0.2)',
                        color: card.mapping_status === 'approved'
                          ? '#34d399'
                          : card.mapping_status === 'needs_review'
                          ? '#f59e0b'
                          : '#94a3b8',
                      }}
                    >
                      {mappingLabel(card.mapping_status)}
                    </span>
                    <span className="text-slate-400 ml-2">
                      Produkt: {card.recommended_product || card.product}
                    </span>
                  </div>
                  {card.peix_context?.score !== undefined && (
                    <div className="mb-2 text-xs text-slate-400">
                      PeixEpiScore {card.peix_context.score} ({card.peix_context.band}) · Impact {card.peix_context.impact_probability ?? '-'}%
                    </div>
                  )}
                  <div className="mb-2 text-sm text-cyan-400 font-medium">
                    Budget-Shift: +{card.budget_shift_pct}% · KPI: {card.primary_kpi || card.campaign_preview?.primary_kpi || '-'}
                  </div>
                  <div className="mb-2 text-xs text-slate-500">
                    Weekly: {card.campaign_preview?.budget?.weekly_budget_eur ? `${Math.round(card.campaign_preview.budget.weekly_budget_eur).toLocaleString('de-DE')} EUR` : '-'}
                    {' · '}
                    Flight: {card.campaign_preview?.budget?.total_flight_budget_eur ? `${Math.round(card.campaign_preview.budget.total_flight_budget_eur).toLocaleString('de-DE')} EUR` : '-'}
                  </div>
                  <div className="mb-2 text-xs text-slate-400">
                    Aktivierung: {card.campaign_preview?.activation_window?.start ? format(parseISO(card.campaign_preview.activation_window.start), 'dd.MM.yy', { locale: de }) : '-'}{' '}
                    bis {card.campaign_preview?.activation_window?.end ? format(parseISO(card.campaign_preview.activation_window.end), 'dd.MM.yy', { locale: de }) : '-'}
                  </div>
                  <div className="mb-2 text-xs text-slate-400">{card.reason || 'Epidemiologischer Trigger'}</div>
                  {card.mapping_reason && (
                    <div className="mb-3 text-xs text-amber-300/90">
                      Mapping ({card.mapping_rule_source || 'auto'}): {card.mapping_reason}
                    </div>
                  )}
                  <div className="text-xs text-slate-500">
                    Kanalmix: {Object.entries(card.channel_mix || {}).map(([k, v]) => `${k} ${v}%`).join(' · ')}
                  </div>
                </button>
              ))}
              {recCards.length === 0 && <div className="text-slate-500 text-sm">Noch keine Action Cards vorhanden.</div>}
            </div>
          </div>
        )}

        {!loading && tab === 'backtest' && (
          <div className="space-y-6">
            <div className="card p-5">
              <h2 className="text-lg font-semibold text-white mb-4">Twin-Mode Backtest</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                <select value={targetSource} onChange={(e) => setTargetSource(e.target.value)} className="media-input">
                  {TARGET_OPTIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
                <button onClick={runMarketBacktest} className="media-button" disabled={marketRunning}>
                  {marketRunning ? 'Läuft...' : 'Markt-Check starten'}
                </button>
                <button onClick={loadRuns} className="media-button secondary">Historie aktualisieren</button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <input type="file" accept=".csv,.xlsx" onChange={(e) => setCustomerFile(e.target.files?.[0] || null)} className="media-input" />
                <button onClick={runCustomerBacktest} className="media-button" disabled={customerRunning || !customerFile}>
                  {customerRunning ? 'Läuft...' : 'Realitäts-Check (CSV)'}
                </button>
                <div className="text-xs text-slate-500 flex items-center">Pflichtspalten: `datum`, `menge` · optional: `region`</div>
              </div>
            </div>

            {marketRun?.metrics && (
              <div className="card p-5">
                <h3 className="text-white font-semibold mb-3">Markt-Check Ergebnis</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <div className="metric-box"><span>R²</span><strong>{marketRun.metrics.r2_score}</strong></div>
                  <div className="metric-box"><span>Korrelation</span><strong>{marketRun.metrics.correlation_pct}%</strong></div>
                  <div className="metric-box"><span>sMAPE</span><strong>{marketRun.metrics.smape}</strong></div>
                  <div className="metric-box"><span>Lead/Lag</span><strong>{marketRun.lead_lag?.best_lag_days || 0}d</strong></div>
                </div>
                {chartData.length > 0 && (
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="dateLabel" tick={{ fill: '#64748b', fontSize: 10 }} />
                      <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
                      <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #334155' }} />
                      <Legend />
                      <Line type="monotone" dataKey="real_qty" stroke="#ef4444" dot={false} name="Proxy (Ist)" />
                      <Line type="monotone" dataKey="predicted_qty" stroke="#38bdf8" dot={false} name="ViralFlux" />
                      <Line type="monotone" dataKey="baseline_seasonal" stroke="#64748b" dot={false} name="Seasonal" />
                    </LineChart>
                  </ResponsiveContainer>
                )}
                <p className="text-xs text-slate-400 mt-3">{marketRun.proof_text}</p>
              </div>
            )}

            {customerRun?.metrics && (
              <div className="card p-5">
                <h3 className="text-white font-semibold mb-2">Realitäts-Check Ergebnis</h3>
                <div className="text-sm text-slate-300">R² {customerRun.metrics.r2_score} · Korrelation {customerRun.metrics.correlation_pct}% · MAE {customerRun.metrics.mae}</div>
                <p className="text-xs text-slate-400 mt-2">{customerRun.proof_text}</p>
              </div>
            )}

            <div className="card p-5">
              <h3 className="text-white font-semibold mb-3">Backtest-Historie</h3>
              <div className="overflow-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-700">
                      <th className="text-left py-2">Zeit</th>
                      <th className="text-left py-2">Mode</th>
                      <th className="text-left py-2">Target</th>
                      <th className="text-left py-2">Virus</th>
                      <th className="text-right py-2">R²</th>
                      <th className="text-right py-2">Corr%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr key={r.run_id} className="border-b border-slate-800">
                        <td className="py-2 text-slate-400">{r.created_at ? format(parseISO(r.created_at), 'dd.MM.yy HH:mm', { locale: de }) : '-'}</td>
                        <td className="py-2 text-slate-200">{r.mode}</td>
                        <td className="py-2 text-slate-300">{r.target_source}</td>
                        <td className="py-2 text-slate-300">{r.virus_typ}</td>
                        <td className="py-2 text-right text-white">{r.metrics?.r2_score ?? '-'}</td>
                        <td className="py-2 text-right text-white">{r.metrics?.correlation_pct ?? '-'}</td>
                      </tr>
                    ))}
                    {runs.length === 0 && (
                      <tr><td colSpan={6} className="py-4 text-slate-500 text-center">Noch keine Backtest-Runs gespeichert.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default MediaCockpit;
