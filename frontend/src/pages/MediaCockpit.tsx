import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';
import { geoMercator, geoPath } from 'd3-geo';
import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  BentoTile,
  PeixScoreSummary,
  RecommendationCard,
  RegionRecommendationRef,
  SourceStatusSummary,
} from '../types/media';
import deBundeslaenderGeo from '../assets/maps/de-bundeslaender.geo.json';
import ProductCatalogPanel from './ProductCatalog';

interface GeoBundeslandFeature {
  type: 'Feature';
  properties?: {
    code?: string;
    name?: string;
  };
  geometry: any;
}

interface GeoBundeslandCollection {
  type: 'FeatureCollection';
  features: GeoBundeslandFeature[];
}

interface GeoBundeslandShape {
  code?: string;
  name: string;
  d: string;
  cx: number;
  cy: number;
}

const BUNDESLAND_NAME_TO_CODE: Record<string, string> = {
  'Baden-Württemberg': 'BW',
  Bayern: 'BY',
  Berlin: 'BE',
  Brandenburg: 'BB',
  Bremen: 'HB',
  Hamburg: 'HH',
  Hessen: 'HE',
  'Mecklenburg-Vorpommern': 'MV',
  Niedersachsen: 'NI',
  'Nordrhein-Westfalen': 'NW',
  'Rheinland-Pfalz': 'RP',
  Saarland: 'SL',
  Sachsen: 'SN',
  'Sachsen-Anhalt': 'ST',
  'Schleswig-Holstein': 'SH',
  Thüringen: 'TH',
};

const DE_BUNDESLAENDER = deBundeslaenderGeo as GeoBundeslandCollection;

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

type RefinementTaskStatus = 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | 'PROGRESS';

interface RefinementTaskState {
  card_id: string;
  task_id: string;
  status: RefinementTaskStatus;
  result?: {
    opportunity_id?: string;
    success?: boolean;
    ai_generation_status?: string;
    updated_at?: string;
  };
  error?: string;
}

const intensityColor = (intensity: number) => {
  const a = 0.2 + Math.min(1, Math.max(0, intensity)) * 0.8;
  return `rgba(27, 83, 155, ${a})`;
};

const eur = (n: number) =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(Math.round(n || 0));

const trendIcon = (trend: string) => (trend === 'steigend' ? '\u2197' : trend === 'fallend' ? '\u2198' : '\u2192');
const mappingLabel = (status?: string) => {
  if (!status) return 'Unbekannt';
  if (status === 'approved') return 'Freigegeben';
  if (status === 'needs_review') return 'Review ausstehend';
  if (status === 'not_applicable') return 'N/A';
  return status;
};

const pillToneClass = (tone?: 'green' | 'amber' | 'red') => {
  if (tone === 'green') return 'text-emerald-400 bg-emerald-500/10';
  if (tone === 'amber') return 'text-amber-300 bg-amber-500/10';
  return 'text-red-400 bg-red-500/10';
};

const MediaCockpit: React.FC = () => {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const initialTab = params.get('tab') || 'map';

  const [tab, setTab] = useState<
    'map' | 'recommendations' | 'backtest' | 'product-intel'
  >(
    initialTab === 'recommendations'
      || initialTab === 'backtest'
      || initialTab === 'product-intel'
      ? (initialTab as any)
      : 'map'
  );
  const [virus, setVirus] = useState('Influenza A');
  const [targetSource, setTargetSource] = useState('RKI_ARE');
  const [cockpit, setCockpit] = useState<CockpitResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [openingRegion, setOpeningRegion] = useState<string | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [horizonDays, setHorizonDays] = useState(0);
  const [showTechDetails, setShowTechDetails] = useState(false);
  const [productMappingLoading, setProductMappingLoading] = useState(false);
  const [productMappingCount, setProductMappingCount] = useState(0);
  const [productMappingApprovedCount, setProductMappingApprovedCount] = useState(0);

  const [recLoading, setRecLoading] = useState(false);
  const [recCards, setRecCards] = useState<RecommendationCard[]>([]);
  const [highlightCardId, setHighlightCardId] = useState<string | null>(null);
  const [refinementTasks, setRefinementTasks] = useState<RefinementTaskState[]>([]);
  const [refinementPollSeconds, setRefinementPollSeconds] = useState(5);
  const [refinementStartedAt, setRefinementStartedAt] = useState<number | null>(null);
  const [refinementNotice, setRefinementNotice] = useState<string | null>(null);
  const [brand, setBrand] = useState('gelo');
  const [product, setProduct] = useState('GeloMyrtol forte');
  const [goal, setGoal] = useState('Top-of-Mind vor Erkältungswelle');
  const [weeklyBudget, setWeeklyBudget] = useState(120000);
  const [strategyMode] = useState('PLAYBOOK_AI');
  const [maxCards, setMaxCards] = useState(4);
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
  const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
  const projectedIntensity = (r?: MapRegion | null) => {
    if (!r) return 0;
    const base = Number(r.intensity || 0);
    const change = Number(r.change_pct || 0) / 100;
    const factor = 1 + change * (horizonDays / 14) * 0.9;
    return clamp01(base * factor);
  };
  const regionCodeByName = useMemo(() => {
    const lookup: Record<string, string> = {};
    Object.entries(activeMap?.regions || {}).forEach(([code, region]) => {
      if (region?.name) {
        lookup[region.name.toLowerCase()] = code;
      }
    });
    return lookup;
  }, [activeMap?.regions]);

  const mapShapes = useMemo(() => {
    const projection = geoMercator().fitSize([420, 460], DE_BUNDESLAENDER as any);
    const pathBuilder = geoPath(projection);
    return DE_BUNDESLAENDER.features
      .map((feature) => {
        const props = feature.properties || {};
        const fallbackCode = props.name ? BUNDESLAND_NAME_TO_CODE[props.name] : undefined;
        const code = (props.code || fallbackCode || '').toUpperCase() || undefined;
        const d = pathBuilder(feature as any);
        if (!d) return null;
        const [cx, cy] = pathBuilder.centroid(feature as any);
        if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null;
        return {
          code,
          name: props.name || code || 'Unbekannt',
          d,
          cx,
          cy,
        } as GeoBundeslandShape;
      })
      .filter((shape): shape is GeoBundeslandShape => Boolean(shape));
  }, []);

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

  const loadProductFlowStatus = useCallback(async () => {
    setProductMappingLoading(true);
    try {
      const tryEndpoints = ['/api/v1/media/product-mapping?brand=gelo&only_pending=false', '/api/v1/media/product-mapping?brand=GeloMyrtol&only_pending=false'];
      let payload: any = null;
      for (const endpoint of tryEndpoints) {
        const res = await fetch(endpoint);
        if (res.ok) {
          payload = await res.json();
          if (payload) {
            break;
          }
        }
      }
      if (!payload) {
        return;
      }
      const rows = Array.isArray(payload?.mappings) ? payload.mappings : [];
      const approved = rows.filter((row: any) => row?.is_approved === true);
      setProductMappingCount(rows.length);
      setProductMappingApprovedCount(approved.length);
    } catch (e) {
      console.error('Product mapping status error', e);
      setProductMappingCount(0);
      setProductMappingApprovedCount(0);
    } finally {
      setProductMappingLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCockpit();
  }, [loadCockpit]);

  useEffect(() => {
    void loadProductFlowStatus();
  }, [loadProductFlowStatus]);

  useEffect(() => {
    const next = params.get('tab');
    if (next === 'map' || next === 'recommendations' || next === 'backtest' || next === 'product-intel') {
      setTab(next);
      if (next === 'product-intel') {
        void loadProductFlowStatus();
      }
    }
  }, [params, loadProductFlowStatus]);

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

  useEffect(() => {
    if (!refinementStartedAt || refinementTasks.length === 0) return;

    const openTasks = refinementTasks.filter((task) => task.status !== 'SUCCESS' && task.status !== 'FAILURE');
    if (openTasks.length === 0) {
      setRefinementStartedAt(null);
      setRefinementNotice('KI-Verfeinerung abgeschlossen.');
      void loadRecommendations();
      return;
    }

    if (Date.now() - refinementStartedAt > 120000) {
      setRefinementStartedAt(null);
      setRefinementNotice('KI-Verfeinerung dauert länger als erwartet. Bitte Liste manuell aktualisieren.');
      return;
    }

    const timer = window.setTimeout(async () => {
      try {
        const updates = await Promise.all(
          openTasks.map(async (task) => {
            const res = await fetch(`/api/v1/media/recommendations/refinement-task/${encodeURIComponent(task.task_id)}`);
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
              return {
                task_id: task.task_id,
                status: 'FAILURE',
                error: data.detail || `HTTP ${res.status}`,
              };
            }
            return data;
          })
        );

        setRefinementTasks((prev) =>
          prev.map((task) => {
            const update = updates.find((item) => item.task_id === task.task_id);
            if (!update) return task;
            return {
              ...task,
              status: String(update.status || task.status) as RefinementTaskStatus,
              result: update.result || task.result,
              error: update.error || task.error,
            };
          })
        );
      } catch (e) {
        console.error('Refinement polling error', e);
      }
    }, Math.max(1, refinementPollSeconds) * 1000);

    return () => window.clearTimeout(timer);
  }, [refinementTasks, refinementStartedAt, refinementPollSeconds, loadRecommendations]);

  const switchTab = (next: 'map' | 'recommendations' | 'backtest' | 'product-intel') => {
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
    setRefinementNotice(null);
    setRefinementTasks([]);
    setRefinementStartedAt(null);
    setHighlightCardId(null);
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
          strategy_mode: strategyMode,
          max_cards: maxCards,
          virus_typ: virus,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      const sorted = [...(data.cards || [])].sort((a, b) => {
        const urgencyDelta = Number(b.urgency_score || 0) - Number(a.urgency_score || 0);
        if (urgencyDelta !== 0) return urgencyDelta;
        return Number(b.confidence || 0) - Number(a.confidence || 0);
      });
      setRecCards(sorted);

      const topCardId = String(data?.top_card_id || sorted[0]?.id || '').trim();
      if (topCardId) {
        setHighlightCardId(topCardId);
      }

      const taskRefs = Array.isArray(data?.refinement_tasks) ? data.refinement_tasks : [];
      const pollHint = Math.max(1, Number(data?.refinement_poll_hint_seconds || 5));
      setRefinementPollSeconds(pollHint);

      if (taskRefs.length > 0) {
        setRefinementTasks(
          taskRefs
            .filter((item: any) => item?.card_id && item?.task_id)
            .map((item: any) => ({
              card_id: String(item.card_id),
              task_id: String(item.task_id),
              status: 'PENDING' as RefinementTaskStatus,
            }))
        );
        setRefinementStartedAt(Date.now());
        setRefinementNotice(`KI verfeinert ${taskRefs.length} Top-Card(s) im Hintergrund...`);
      } else if (sorted.length > 0) {
        setRefinementNotice('Cards erzeugt. Keine asynchrone KI-Verfeinerung gestartet.');
      }
      await loadCockpit();
    } catch (e) {
      console.error('Generate recommendation error', e);
      setRefinementNotice('Generierung fehlgeschlagen. Bitte erneut versuchen.');
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
  const executiveActions = useMemo(() => (activeMap?.activation_suggestions || []).slice(0, 3), [activeMap]);
  const mapReady = Boolean(activeMap?.has_data);
  const regionSuggestionReady = Boolean((activeMap?.activation_suggestions || []).length > 0);
  const recCardsReady = recCards.length > 0;
  const productMappingReady = productMappingCount > 0 && productMappingApprovedCount > 0;
  const flowProgress = [mapReady, regionSuggestionReady, recCardsReady, productMappingReady].filter(Boolean).length;
  const currentFlow = {
    map: {
      title: 'Lage analysieren',
      detail: 'Öffne die Top-Regionen und prüfe den Signalausgleich.',
      actionLabel: 'Zu den Regionen',
      actionHint: 'Karte öffnen',
    },
    recommendations: {
      title: 'Kampagnen ableiten',
      detail: 'Erzeuge Karten und verifiziere den Produktfit pro Region.',
      actionLabel: 'Empfehlungen erzeugen',
      actionHint: 'Karten neu berechnen',
    },
    'product-intel': {
      title: 'Produkt-Match freigeben',
      detail: 'Produktdaten prüfen, Mapping freigeben und erst danach ausspielen.',
      actionLabel: 'Produkt-Intelligence öffnen',
      actionHint: 'Zum Produktbereich',
    },
    backtest: {
      title: 'Signale validieren',
      detail: 'Backtest ausführen, um Lead-Zeit und Korrelation zu prüfen.',
      actionLabel: 'Markt-Check starten',
      actionHint: 'Backtest öffnen',
    },
  };
  const currentFlowStep = currentFlow[tab];
  const flowChips = [
    { label: 'Schritt 1: Lageanalyse', done: mapReady },
    { label: 'Schritt 2: Regionen auswählen', done: regionSuggestionReady },
    { label: 'Schritt 3: Kampagnenkandidaten', done: recCardsReady },
    { label: 'Schritt 4: Mapping-Freigabe', done: productMappingReady },
  ];
  const flowTotal = flowChips.length;
  const executiveShiftEur = useMemo(() => {
    return executiveActions.reduce((sum, s) => sum + (weeklyBudget * (Number(s.budget_shift_pct || 0) / 100)), 0);
  }, [executiveActions, weeklyBudget]);
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

  const refinementByCard = useMemo(() => {
    const map = new Map<string, RefinementTaskState>();
    refinementTasks.forEach((task) => {
      map.set(task.card_id, task);
    });
    return map;
  }, [refinementTasks]);

  const refinementBadge = (card: RecommendationCard) => {
    const task = refinementByCard.get(card.id);
    if (!task) return null;

    if (task.status === 'PENDING') return { label: 'KI queued', tone: 'queued' as const };
    if (task.status === 'STARTED' || task.status === 'PROGRESS') return { label: 'KI läuft', tone: 'running' as const };
    if (task.status === 'FAILURE') return { label: 'KI failed', tone: 'failed' as const };
    if (task.status === 'SUCCESS') {
      const aiStatus = String(task.result?.ai_generation_status || '').toLowerCase();
      if (aiStatus === 'fallback_template') return { label: 'KI fallback', tone: 'fallback' as const };
      return { label: 'KI success', tone: 'success' as const };
    }
    return null;
  };

  const refinementBadgeStyle = (tone: 'queued' | 'running' | 'success' | 'fallback' | 'failed') => {
    if (tone === 'queued') return { background: 'rgba(148,163,184,0.2)', color: '#cbd5e1' };
    if (tone === 'running') return { background: 'rgba(56,189,248,0.2)', color: '#7dd3fc' };
    if (tone === 'success') return { background: 'rgba(34,197,94,0.2)', color: '#86efac' };
    if (tone === 'fallback') return { background: 'rgba(245,158,11,0.2)', color: '#fcd34d' };
    return { background: 'rgba(239,68,68,0.2)', color: '#fca5a5' };
  };

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
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 py-6 space-y-6">
        <div className="media-tabs">
          <button onClick={() => switchTab('map')} className={`media-tab ${tab === 'map' ? 'active' : ''}`}>Lagekarte</button>
          <button onClick={() => switchTab('recommendations')} className={`media-tab ${tab === 'recommendations' ? 'active' : ''}`}>KI-Empfehlungen</button>
          <button onClick={() => switchTab('product-intel')} className={`media-tab ${tab === 'product-intel' ? 'active' : ''}`}>Produkt-Intelligence</button>
          <button onClick={() => switchTab('backtest')} className={`media-tab ${tab === 'backtest' ? 'active' : ''}`}>Backtest</button>
        </div>

        <section className="card p-4 focus-card">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
            <div>
              <div className="text-xs text-slate-400 uppercase tracking-wider">Leitplanke</div>
              <h2 className="text-white text-lg font-bold mt-0.5">{currentFlowStep.title}</h2>
              <p className="text-slate-400 text-xs mt-1">{currentFlowStep.detail}</p>
            </div>
            <div className="text-xs text-slate-500">
              Fortschritt: <span className="text-cyan-300">{flowProgress}/{flowTotal}</span>
              {productMappingLoading && <span className="ml-2 text-slate-400">· Mapping-Status wird geprüft</span>}
            </div>
          </div>

          <div className="flex flex-wrap gap-2 mb-3">
            {flowChips.map((item) => (
              <span key={item.label} className={`step-chip ${item.done ? 'step-chip-done' : ''}`}>
                {item.label}
              </span>
            ))}
          </div>

          <div className="rounded-lg p-3 soft-panel">
            <div className="text-xs text-slate-400 uppercase tracking-wider">Nächster Schritt</div>
            <div className="text-slate-200 mt-1">{currentFlowStep.actionHint}</div>
          </div>
        </section>

        {loading && (
          <div className="card p-8 text-center text-slate-400">Lade Media Cockpit...</div>
        )}

        {!loading && tab === 'map' && activeMap && (
          <div className="space-y-6">
            {/* Executive summary + action cards */}
            <div
              className="card p-6"
              style={{
                background:
                  'radial-gradient(900px 220px at 20% 0%, rgba(34,197,94,0.12), transparent 60%), linear-gradient(135deg, rgba(30,41,59,1), rgba(15,23,42,1))',
                border: '1px solid rgba(148,163,184,0.22)',
              }}
            >
              <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
                <div className="min-w-0">
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">Media Cockpit</div>
                  <h2 className="text-2xl font-black text-white tracking-tight mt-1">
                    Action Radar fuer {virus}
                  </h2>
                  <p className="text-sm text-slate-400 mt-2 max-w-2xl">
                    Kein Zahlenfriedhof. Du siehst zuerst, wo Budget aktivieren sollte und welche Botschaft HWG-sicher passt.
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      onClick={() => switchTab('recommendations')}
                      className="px-3 py-1.5 text-xs font-semibold rounded-full transition hover:brightness-110"
                      style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)', color: 'white' }}
                    >
                      Kampagnenvorschlaege
                    </button>
                    <button
                      onClick={triggerRecommendations}
                      disabled={recLoading}
                      className="px-3 py-1.5 text-xs font-semibold rounded-full transition hover:brightness-110 disabled:opacity-60"
                      style={{ background: 'linear-gradient(135deg, #22c55e, #10b981)', color: '#052e1b' }}
                      title="Erzeugt neue Cards und startet KI-Verfeinerung asynchron"
                    >
                      {recLoading ? 'Berechne...' : 'Jetzt Cards erzeugen'}
                    </button>
                    <span
                      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs"
                      style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155', color: '#94a3b8' }}
                      title="Die genaue Score-Metrik ist absichtlich hinter Tech Details verborgen."
                    >
                      Lage: <span className="text-slate-200">{peixSummary?.national_band || '—'}</span>
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 w-full lg:w-[420px]">
                  <div className="rounded-xl p-4" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #334155' }}>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">Re-Allocation</div>
                    <div className="text-xl font-black text-white mt-1">{eur(executiveShiftEur)}</div>
                    <div className="text-[11px] text-slate-500 mt-1">aus Top-Aktionen (heuristisch)</div>
                  </div>
                  <div className="rounded-xl p-4" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #334155' }}>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">Waste Reduction</div>
                    <div className="text-xl font-black text-white mt-1">{eur(weeklyBudget * 0.12)}</div>
                    <div className="text-[11px] text-slate-500 mt-1">in gesunden Regionen</div>
                  </div>
                  <div className="rounded-xl p-4" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #334155' }}>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">Zeitfenster</div>
                    <div className="text-xl font-black text-white mt-1">7-10 Tage</div>
                    <div className="text-[11px] text-slate-500 mt-1">kurz, konzentriert, messbar</div>
                  </div>
                  <div className="rounded-xl p-4" style={{ background: 'rgba(15,23,42,0.6)', border: '1px solid #334155' }}>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">Budget (Woche)</div>
                    <div className="text-xl font-black text-white mt-1">{eur(weeklyBudget)}</div>
                    <div className="text-[11px] text-slate-500 mt-1">fuer Demo/Planung</div>
                  </div>
                </div>
              </div>

              <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
                {(executiveActions.length ? executiveActions : []).map((s, idx) => (
                  <div
                    key={`${s.region}-${idx}`}
                    className="rounded-xl p-4"
                    style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155' }}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-[10px] text-slate-500 uppercase tracking-wider">Aktion</div>
                        <div className="text-base font-bold text-white mt-1 truncate">{s.region_name}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-[10px] text-slate-500 uppercase tracking-wider">Shift</div>
                        <div className="text-sm font-bold text-cyan-300 mt-1">+{s.budget_shift_pct}%</div>
                      </div>
                    </div>
                    <p className="text-xs text-slate-400 mt-2 line-clamp-3">{s.reason}</p>
                    <div className="mt-3 flex items-center justify-between gap-3">
                      <div className="text-[11px] text-slate-500">Ziel: HWG-safe Copy Pack</div>
                      <button
                        onClick={() => openRecommendationForRegion(s.region)}
                        className="px-3 py-1.5 text-xs font-bold rounded-lg transition hover:brightness-110"
                        style={{ background: 'linear-gradient(135deg, #22c55e, #10b981)', color: '#052e1b' }}
                      >
                        Aktivieren
                      </button>
                    </div>
                  </div>
                ))}
                {executiveActions.length === 0 && (
                  <div className="md:col-span-3 text-sm text-slate-500">
                    Noch keine Aktivierungs-Aktionen vorhanden. Erzeuge KI-Empfehlungen oder lade Kartendaten.
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div className="text-xs text-slate-500">Rohdaten sind hinter “Tech Details” verborgen.</div>
              <button
                onClick={() => setShowTechDetails((s) => !s)}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg transition hover:bg-slate-700"
                style={{ border: '1px solid #334155', color: '#94a3b8' }}
              >
                {showTechDetails ? 'Tech Details ausblenden' : 'Tech Details anzeigen'}
              </button>
            </div>

            {showTechDetails && (
              <div className="card p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-white">Tech Details: Bento-Übersicht</h2>
                    <p className="text-xs text-slate-500">Für Analyse/Revision. Nicht die Default-Ansicht.</p>
                  </div>
                  <div className="text-xs text-slate-400 flex flex-col items-start sm:items-end gap-2">
                    <div>
                      Nationaler PeixEpiScore: <span className="text-cyan-300 font-semibold">{peixSummary?.national_score ?? '-'} / 100</span>
                      {' · '}
                      Band: <span className="text-slate-200">{peixSummary?.national_band ?? '-'}</span>
                      {' · '}
                      Impact: <span className="text-slate-200">{peixSummary?.national_impact_probability ?? '-'}%</span>
                    </div>
                    <button onClick={() => navigate('/data-integration')} className="secondary-link-muted">
                      Integrationen verwalten
                    </button>
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
            )}

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              <div className="xl:col-span-2 card p-5">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                  <div>
                    <h2 className="text-lg font-semibold text-white">
                      Deutschland Radar: {virus}{' '}
                      <span className="text-slate-400 font-normal">
                        {horizonDays === 0 ? '(Heute)' : `( +${horizonDays} Tage )`}
                      </span>
                    </h2>
                    <p className="text-xs text-slate-500">
                      {activeMap.date ? `Stand ${format(parseISO(activeMap.date), 'dd.MM.yyyy', { locale: de })}` : 'Kein Datenstand'}
                    </p>
                    <div className="mt-3">
                      <div className="text-[10px] text-slate-400 uppercase tracking-wider">VIRUSFILTER LAGEKARTE</div>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {VIRUS_OPTIONS.map((v) => (
                          <button
                            key={v}
                            type="button"
                            onClick={(e) => {
                              e.preventDefault();
                              setVirus(v);
                            }}
                            className={`tab-chip ${virus === v ? 'active' : ''}`}
                          >
                            {v}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                    <div className="flex items-center gap-3">
                      <div className="text-[11px] text-slate-500">
                        Forecast-Slider
                      </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-500">0</span>
                      <input
                        type="range"
                        min={0}
                        max={14}
                        value={horizonDays}
                        onChange={(e) => setHorizonDays(Number(e.target.value))}
                        className="w-44 accent-cyan-400"
                        title="Visualisierte 14-Tage-Entwicklung (heuristisch aus Trend/Change%)."
                      />
                      <span className="text-[11px] text-slate-500">14</span>
                    </div>
                    {showTechDetails && (
                      <div className="text-xs text-slate-500">
                        Max {activeMap.max_viruslast?.toLocaleString('de-DE')} Genkopien/L
                      </div>
                    )}
                  </div>
                </div>

                {!activeMap.has_data ? (
                  <div className="py-16 text-center text-slate-500">Keine Kartendaten vorhanden.</div>
                ) : (
                  <div
                    className="rounded-2xl p-3"
                    style={{
                      background:
                        'radial-gradient(800px 260px at 12% 0%, rgba(14,165,233,0.09), transparent 58%), linear-gradient(160deg, rgba(15,23,42,0.9), rgba(8,17,31,0.86))',
                      border: '1px solid rgba(51,65,85,0.75)',
                    }}
                  >
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                      <div className="text-[11px] text-slate-400">
                        Klick auf ein Bundesland öffnet direkt den passenden Kampagnenvorschlag.
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="px-2 py-1 rounded-full text-[10px] uppercase tracking-wider" style={{ background: 'rgba(34,197,94,0.15)', color: '#86efac', border: '1px solid rgba(34,197,94,0.35)' }}>
                          Niedrig
                        </span>
                        <span className="px-2 py-1 rounded-full text-[10px] uppercase tracking-wider" style={{ background: 'rgba(250,204,21,0.15)', color: '#fcd34d', border: '1px solid rgba(250,204,21,0.35)' }}>
                          Mittel
                        </span>
                        <span className="px-2 py-1 rounded-full text-[10px] uppercase tracking-wider" style={{ background: 'rgba(239,68,68,0.15)', color: '#fca5a5', border: '1px solid rgba(239,68,68,0.35)' }}>
                          Hoch
                        </span>
                      </div>
                    </div>

                    <svg viewBox="0 0 420 460" className="w-full max-h-[560px]">
                      <defs>
                        <filter id="vf-map-shadow" x="-20%" y="-20%" width="140%" height="140%">
                          <feDropShadow dx="0" dy="4" stdDeviation="4" floodColor="#020617" floodOpacity="0.55" />
                        </filter>
                        <filter id="vf-selected-glow" x="-30%" y="-30%" width="160%" height="160%">
                          <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor="#67e8f9" floodOpacity="0.5" />
                        </filter>
                        <pattern id="vf-map-grid" width="14" height="14" patternUnits="userSpaceOnUse">
                          <path d="M 14 0 L 0 0 0 14" fill="none" stroke="rgba(100,116,139,0.18)" strokeWidth="0.6" />
                        </pattern>
                      </defs>

                      <rect x="0" y="0" width="420" height="460" rx="14" fill="rgba(2,6,23,0.3)" />
                      <rect x="0" y="0" width="420" height="460" rx="14" fill="url(#vf-map-grid)" />

                      {mapShapes.map((shape) => {
                        const codeFromName = shape.name ? regionCodeByName[shape.name.toLowerCase()] : undefined;
                        const code = shape.code || codeFromName;
                        const region = code ? activeMap.regions?.[code] : undefined;
                        const intensity = region ? projectedIntensity(region) : 0;
                        const fill = region ? intensityColor(intensity) : 'rgba(51,65,85,0.28)';
                        const isSelected = Boolean(code && selectedRegion === code);
                        const band = !region ? '' : intensity >= 0.7 ? 'Hoch' : intensity >= 0.4 ? 'Mittel' : 'Niedrig';
                        return (
                          <g
                            key={`${shape.name}-${shape.code || 'na'}`}
                            style={{ cursor: region && code ? 'pointer' : 'default' }}
                            onClick={() => region && code && openRecommendationForRegion(code)}
                          >
                            <path
                              d={shape.d}
                              fill={fill}
                              stroke={isSelected ? '#67e8f9' : 'rgba(148,163,184,0.7)'}
                              strokeWidth={isSelected ? 2.4 : 1.1}
                              filter={isSelected ? 'url(#vf-selected-glow)' : 'url(#vf-map-shadow)'}
                              style={{ transition: 'all 180ms ease' }}
                            />
                            <circle
                              cx={shape.cx}
                              cy={shape.cy - 5}
                              r={8.5}
                              fill="rgba(2,6,23,0.78)"
                              stroke={isSelected ? 'rgba(103,232,249,0.85)' : 'rgba(100,116,139,0.65)'}
                              strokeWidth={isSelected ? 1.2 : 0.8}
                            />
                            <text x={shape.cx} y={shape.cy - 2.5} textAnchor="middle" fill="#e2e8f0" fontSize="8" fontWeight="700">{code || '--'}</text>
                            {region && (
                              <text x={shape.cx} y={shape.cy + 11} textAnchor="middle" fill="#94a3b8" fontSize="6.6">
                                {band}
                              </text>
                            )}
                            {openingRegion === code && (
                              <text x={shape.cx} y={shape.cy + 20} textAnchor="middle" fill="#7dd3fc" fontSize="6">
                                oeffne...
                              </text>
                            )}
                          </g>
                        );
                      })}
                    </svg>

                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
                      <div>
                        Intensität basiert auf PeixEpiScore + Trendprojektion (0-14 Tage).
                      </div>
                      <div>
                        Aktive Auswahl: <span className="text-slate-300">{selectedRegion || 'keine'}</span>
                      </div>
                    </div>
                  </div>
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
                            <div className="text-xs text-slate-500">Impact {Math.round(r.impact_probability || 0)}% · Trend {trendIcon(r.trend)} {r.change_pct > 0 ? '+' : ''}{r.change_pct}%</div>
                          </div>
                          <div className="text-right">
                            <div className="text-sm text-white font-medium">Radar</div>
                            <div className="text-xs text-slate-500">Click to activate</div>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                {showTechDetails && (
                  <div className="card p-4">
                    <h3 className="text-sm font-semibold text-white mb-3">Tech Details: Datenquellen Live-Status</h3>
                    <div className="space-y-2">
                      {sourceStatus.map((item) => (
                        <div key={item.source_key} className="rounded-lg px-3 py-2" style={{ background: 'rgba(15,23,42,0.65)' }}>
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-slate-300">{item.label}</span>
                            <div className="flex items-center gap-2">
                              <span
                                className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${pillToneClass(item.feed_status_color)}`}
                              >
                                Feed {item.feed_reachable ? 'mit Daten erreichbar' : 'noch ohne Zeitstempel'}
                              </span>
                              <span
                                className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${pillToneClass(item.status_color)}`}
                              >
                                Datenstand {
                                  item.freshness_state === 'live'
                                    ? 'aktuell'
                                    : item.freshness_state === 'stale'
                                      ? 'verzoegert'
                                      : 'kein Datum'
                                }
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
                )}

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
            <div
              className="card p-6"
              style={{
                background:
                  'radial-gradient(900px 220px at 20% 0%, rgba(59,130,246,0.16), transparent 60%), linear-gradient(135deg, rgba(30,41,59,1), rgba(15,23,42,1))',
                border: '1px solid rgba(148,163,184,0.22)',
              }}
            >
              <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
                <div className="min-w-0">
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">Kampagnenvorschlaege</div>
                  <h2 className="text-2xl font-black text-white tracking-tight mt-1">Action Cards</h2>
                  <p className="text-sm text-slate-400 mt-2 max-w-2xl">
                    Erst sehen, was du tun sollst. Dann (optional) die Details. Copy ist HWG-safe aus der Gelo-Playbook-Library.
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <span className="px-3 py-1.5 rounded-full text-xs" style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155', color: '#94a3b8' }}>
                      Brand: <span className="text-slate-200">{brand}</span>
                    </span>
                    <span className="px-3 py-1.5 rounded-full text-xs" style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155', color: '#94a3b8' }}>
                      Produkt: <span className="text-slate-200">{product}</span>
                    </span>
                    <span className="px-3 py-1.5 rounded-full text-xs" style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155', color: '#94a3b8' }}>
                      Budget/Woche: <span className="text-slate-200">{eur(weeklyBudget)}</span>
                    </span>
                    <span className="px-3 py-1.5 rounded-full text-xs" style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155', color: '#94a3b8' }}>
                      Virus: <span className="text-slate-200">{virus}</span>
                    </span>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center gap-2">
                  <button
                    onClick={triggerRecommendations}
                    className="px-4 py-2 text-xs font-bold rounded-lg transition hover:brightness-110 disabled:opacity-60"
                    style={{ background: 'linear-gradient(135deg, #22c55e, #10b981)', color: '#052e1b' }}
                    disabled={recLoading}
                    title="Erzeugt neue Cards und startet KI-Verfeinerung asynchron"
                  >
                    {recLoading ? 'Berechne...' : 'Empfehlungen erzeugen'}
                  </button>
                  <button
                    onClick={() => highlightCardId && navigate(`/dashboard/recommendations/${encodeURIComponent(highlightCardId)}`)}
                    className="px-4 py-2 text-xs font-semibold rounded-lg transition hover:bg-slate-700 disabled:opacity-60"
                    style={{ border: '1px solid rgba(148,163,184,0.25)', color: '#e2e8f0' }}
                    disabled={!highlightCardId}
                    title="Oeffnet die aktuell priorisierte Top-Empfehlung"
                  >
                    Top-Empfehlung öffnen
                  </button>
                  <button
                    onClick={loadRecommendations}
                    className="px-4 py-2 text-xs font-semibold rounded-lg transition hover:bg-slate-700"
                    style={{ border: '1px solid rgba(148,163,184,0.25)', color: '#e2e8f0' }}
                    title="Listet gespeicherte Cards (schnell)"
                  >
                    Liste aktualisieren
                  </button>
                  <button
                    onClick={() => setShowTechDetails((s) => !s)}
                    className="px-4 py-2 text-xs font-semibold rounded-lg transition hover:bg-slate-700"
                    style={{ border: '1px solid rgba(148,163,184,0.25)', color: '#94a3b8' }}
                  >
                    {showTechDetails ? 'Tech Details ausblenden' : 'Tech Details anzeigen'}
                  </button>
                </div>
              </div>

              {refinementNotice && (
                <div
                  className="mt-4 rounded-lg px-3 py-2 text-xs"
                  style={{ background: 'rgba(15,23,42,0.65)', border: '1px solid #334155', color: '#94a3b8' }}
                >
                  {refinementNotice}
                </div>
              )}

              {showTechDetails && (
                <div className="mt-5 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3">
                    <input value={brand} onChange={(e) => setBrand(e.target.value)} className="media-input" placeholder="Brand" />
                    <input value={product} onChange={(e) => setProduct(e.target.value)} className="media-input" placeholder="Produkt" />
                    <input value={goal} onChange={(e) => setGoal(e.target.value)} className="media-input" placeholder="Kampagnenziel" />
                    <input value={weeklyBudget} onChange={(e) => setWeeklyBudget(Number(e.target.value))} className="media-input" type="number" placeholder="Budget" />
                    <select className="media-input" value={maxCards} onChange={(e) => setMaxCards(Number(e.target.value))}>
                      <option value={1}>1 Card</option>
                      <option value={2}>2 Cards</option>
                      <option value={3}>3 Cards</option>
                      <option value={4}>4 Cards</option>
                    </select>
                    <div className="text-xs text-slate-500 flex items-center">
                      Mode: {strategyMode}
                    </div>
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
                    <div className="text-xs text-slate-500 flex items-center">
                      max_cards: {maxCards}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {recCards.map((card) => {
                const isHighlighted = highlightCardId === card.id;
                const badge = refinementBadge(card);
                return (
                  <button
                    key={card.id}
                    type="button"
                    onClick={() => navigate(`/dashboard/recommendations/${encodeURIComponent(card.id)}`)}
                    className="card p-5 text-left hover:brightness-110 transition"
                    style={
                      isHighlighted
                        ? {
                            border: '1px solid rgba(34,197,94,0.7)',
                            boxShadow: '0 0 0 1px rgba(34,197,94,0.25), 0 10px 30px rgba(16,185,129,0.12)',
                          }
                        : undefined
                    }
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <div className="text-[10px] text-slate-500 uppercase tracking-wider">KI-Erkenntnis</div>
                          {isHighlighted && (
                            <span className="px-2 py-0.5 text-[10px] rounded-full" style={{ background: 'rgba(34,197,94,0.2)', color: '#86efac' }}>
                              Top-Empfehlung
                            </span>
                          )}
                          {badge && (
                            <span
                              className="px-2 py-0.5 text-[10px] rounded-full"
                              style={refinementBadgeStyle(badge.tone)}
                            >
                              {badge.label}
                            </span>
                          )}
                        </div>
                        <div className="text-base font-bold text-white mt-1 truncate">
                          {card.playbook_title || card.campaign_preview?.playbook_title || card.campaign_name || `${card.brand} · ${card.product}`}
                        </div>
                        <div className="text-xs text-slate-400 mt-1 line-clamp-2">{card.reason || card.trigger_snapshot?.details || 'Signal erkannt.'}</div>
                      </div>
                      <div className="flex-shrink-0 text-right">
                        <div className="text-[10px] text-slate-500 uppercase tracking-wider">Urgency</div>
                        <div className="text-sm font-bold text-slate-200 mt-1">{Math.round(card.urgency_score || 0)}</div>
                        {card.confidence !== undefined && (
                          <div className="text-[11px] text-emerald-300 mt-1">Conf {Math.round((card.confidence || 0) * 100)}%</div>
                        )}
                      </div>
                    </div>

                    <div className="mt-4 grid grid-cols-2 gap-3">
                      <div className="rounded-lg p-3" style={{ background: 'rgba(15,23,42,0.7)', border: '1px solid #334155' }}>
                        <div className="text-[10px] text-slate-500 uppercase tracking-wider">Produkt</div>
                        <div className="text-sm font-semibold text-white mt-1 truncate" title={card.recommended_product || card.product}>
                          {card.recommended_product || card.product}
                        </div>
                        <div className="text-[11px] text-slate-500 mt-1">HWG-safe Copy Pack</div>
                      </div>
                      <div className="rounded-lg p-3" style={{ background: 'rgba(15,23,42,0.7)', border: '1px solid #334155' }}>
                        <div className="text-[10px] text-slate-500 uppercase tracking-wider">Budget</div>
                        <div className="text-sm font-semibold text-white mt-1">
                          +{card.budget_shift_pct}%{' '}
                          <span className="text-slate-400">
                            ({card.campaign_preview?.budget?.shift_value_eur ? eur(card.campaign_preview.budget.shift_value_eur) : 'Shift'})
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-1">KPI: {card.primary_kpi || card.campaign_preview?.primary_kpi || '-'}</div>
                      </div>
                    </div>

                    <div className="mt-4 flex items-center justify-between gap-3">
                      <div className="text-[11px] text-slate-500">
                        Status: <span className="text-slate-300">{String(card.status || 'DRAFT')}</span>
                        {showTechDetails && (
                          <>
                            {' · '}
                            <span className="text-slate-400">{mappingLabel(card.mapping_status)}</span>
                          </>
                        )}
                      </div>
                      <span
                        className="px-3 py-1.5 text-xs font-bold rounded-lg"
                        style={{ background: 'linear-gradient(135deg, #22c55e, #10b981)', color: '#052e1b' }}
                      >
                        Aktivieren
                      </span>
                    </div>

                    {showTechDetails && (
                      <div className="mt-3 text-xs text-slate-500">
                        Kanalmix: {Object.entries(card.channel_mix || {}).map(([k, v]) => `${k} ${v}%`).join(' · ')}
                      </div>
                    )}
                  </button>
                );
              })}
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

        {!loading && tab === 'product-intel' && (
          <ProductCatalogPanel />
        )}
      </main>
    </div>
  );
};

export default MediaCockpit;
