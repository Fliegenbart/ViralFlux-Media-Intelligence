import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTheme, useToast } from '../App';
import { geoMercator, geoPath } from 'd3-geo';
import { differenceInCalendarDays, format, isValid, parseISO, subDays } from 'date-fns';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  CartesianGrid,
  Legend,
  Brush,
  ReferenceLine,
  ReferenceArea,
} from 'recharts';
import { de } from 'date-fns/locale';
import {
  BacktestChartMode,
  BacktestChartPoint,
  BacktestResponse,
  BentoTile,
  PeixScoreSummary,
  RecommendationCard,
  RecommendationDetail,
  RegionRecommendationRef,
  RegionTooltipData,
  SourceStatusSummary,
  DecisionFact,
} from '../types/media';
import deBundeslaenderGeo from '../assets/maps/de-bundeslaender.geo.json';

/* ─── Geo types ─── */

interface GeoBundeslandFeature {
  type: 'Feature';
  properties?: { code?: string; name?: string };
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

/* ─── Constants ─── */

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

/* ─── Shared interfaces ─── */

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
  tooltip?: RegionTooltipData | null;
}

interface CockpitResponse {
  bento: { tiles: BentoTile[]; count: number };
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
  recommendations: { total: number; cards: RecommendationCard[] };
  backtest_summary: {
    latest_market: BacktestResponse | null;
    latest_customer: BacktestResponse | null;
    recent_runs: Array<any>;
  };
  data_freshness: Record<string, string | null>;
}

/* ─── Utility helpers ─── */

const intensityColor = (intensity: number) => {
  const a = 0.25 + Math.min(1, Math.max(0, intensity)) * 0.65;
  return `rgba(27, 83, 155, ${a})`;
};

const trendIcon = (trend: string) =>
  trend === 'steigend' ? '\u2197' : trend === 'fallend' ? '\u2198' : '\u2192';

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

/* Callout positions for city-states */
const CALLOUT_TARGETS: Record<string, { tx: number; ty: number }> = {
  HH: { tx: 385, ty: 52 },
  BE: { tx: 395, ty: 138 },
  HB: { tx: 385, ty: 92 },
};

const SIGNAL_TILE_KEYS = ['are', 'abwasser', 'survstat', 'wetter'];
const SECONDARY_SIGNAL_KEYS = ['pollen', 'bfarm', 'google_trends'];

const WORKFLOW_TRANSITIONS: Record<string, string> = {
  DRAFT: 'READY',
  READY: 'APPROVED',
  APPROVED: 'ACTIVATED',
};

/* ─── Component ─── */

interface Props {
  view: 'lagebild' | 'empfehlungen' | 'backtest';
}

const MediaCockpit: React.FC<Props> = ({ view }) => {
  useTheme();
  const { toast } = useToast();

  /* ── Shared state ── */
  const [virus, setVirus] = useState('Influenza A');
  const [cockpit, setCockpit] = useState<CockpitResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const hasLoadedCockpitRef = useRef(false);

  /* ── Lagebild state ── */
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const mapContainerRef = useRef<HTMLDivElement>(null);

  /* ── Empfehlungen state ── */
  const [recLoading, setRecLoading] = useState(false);
  const [recCards, setRecCards] = useState<RecommendationCard[]>([]);
  const [recFilter, setRecFilter] = useState<'active' | 'all'>('all');
  const [selectedRecommendationId, setSelectedRecommendationId] = useState<string | null>(null);
  const [slideOverData, setSlideOverData] = useState<RecommendationDetail | null>(null);
  const [slideOverLoading, setSlideOverLoading] = useState(false);
  const [slideOverAdvanced, setSlideOverAdvanced] = useState(false);
  const [statusTransitioning, setStatusTransitioning] = useState(false);

  /* ── Backtest state ── */
  const [btTargetSource, setBtTargetSource] = useState('ATEMWEGSINDEX');
  const [btBundesland, setBtBundesland] = useState('');
  const [btHorizonDays, setBtHorizonDays] = useState<7 | 14 | 21>(14);
  const [btRunning, setBtRunning] = useState(false);
  const [btResult, setBtResult] = useState<BacktestResponse | null>(null);
  const [topRegions, setTopRegions] = useState<any>(null);
  const [btChartMode, setBtChartMode] = useState<BacktestChartMode>('validation');
  const [btCustomerChartMode, setBtCustomerChartMode] = useState<BacktestChartMode>('validation');
  const [btCustomerResult, setBtCustomerResult] = useState<BacktestResponse | null>(null);
  const [btCustomerRunning, setBtCustomerRunning] = useState(false);
  const [btRuns, setBtRuns] = useState<any[]>([]);
  const btFileRef = useRef<HTMLInputElement>(null);

  /* ── Wave Radar state ── */
  const [waveDisease, setWaveDisease] = useState('influenza');
  const [waveSeason, setWaveSeason] = useState('');
  const [waveData, setWaveData] = useState<any>(null);
  const [waveLoading, setWaveLoading] = useState(false);
  const [waveWeekIdx, setWaveWeekIdx] = useState(0);
  const [waveAnimating, setWaveAnimating] = useState(false);

  /* ── Outbreak Alert state ── */
  const [alertData, setAlertData] = useState<any>(null);
  const [alertLoading, setAlertLoading] = useState(false);

  /* ── Derived data ── */
  const activeMap = cockpit?.map;
  const peixSummary = cockpit?.peix_epi_score;
  const dataFreshness = cockpit?.data_freshness;
  const bentoTiles = useMemo(() => cockpit?.bento?.tiles || [], [cockpit]);

  /* ── Map projection (memoised) ── */
  const mapProjection = useMemo(
    () => geoMercator().fitSize([420, 460], DE_BUNDESLAENDER as any),
    [],
  );

  const regionCodeByName = useMemo(() => {
    const lookup: Record<string, string> = {};
    Object.entries(activeMap?.regions || {}).forEach(([code, region]) => {
      if (region?.name) lookup[region.name.toLowerCase()] = code;
    });
    return lookup;
  }, [activeMap?.regions]);

  const mapShapes = useMemo(() => {
    const pathBuilder = geoPath(mapProjection);
    return DE_BUNDESLAENDER.features
      .map((feature) => {
        const props = feature.properties || {};
        const fallbackCode = props.name ? BUNDESLAND_NAME_TO_CODE[props.name] : undefined;
        const code = (props.code || fallbackCode || '').toUpperCase() || undefined;
        const d = pathBuilder(feature as any);
        if (!d) return null;
        const [cx, cy] = pathBuilder.centroid(feature as any);
        if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null;
        return { code, name: props.name || code || 'Unbekannt', d, cx, cy } as GeoBundeslandShape;
      })
      .filter((shape): shape is GeoBundeslandShape => Boolean(shape));
  }, []);

  const mapRanking = useMemo(() => (activeMap?.top_regions || []).slice(0, 5), [activeMap]);

  /* ── Signal tile helpers ── */
  const signalTiles = useMemo(() => {
    return bentoTiles.filter((t) => SIGNAL_TILE_KEYS.some((k) => t.id.toLowerCase().includes(k)));
  }, [bentoTiles]);

  const secondarySignals = useMemo(() => {
    return bentoTiles.filter((t) => SECONDARY_SIGNAL_KEYS.some((k) => t.id.toLowerCase().includes(k)));
  }, [bentoTiles]);

  /* ── Data fetching ── */
  const loadCockpit = useCallback(async () => {
    const showBlocking = !hasLoadedCockpitRef.current;
    if (showBlocking) setLoading(true);
    try {
      const qs = new URLSearchParams({ virus_typ: virus });
      const res = await fetch(`/api/v1/media/cockpit?${qs.toString()}`);
      const data = await res.json();
      setCockpit(data);
      hasLoadedCockpitRef.current = true;
    } catch (e) {
      console.error('Cockpit fetch error', e);
      toast('Daten konnten nicht geladen werden', 'error');
    } finally {
      if (showBlocking) setLoading(false);
    }
  }, [virus]);

  useEffect(() => {
    loadCockpit();
  }, [loadCockpit]);

  const loadRecommendations = useCallback(async () => {
    const qs = new URLSearchParams();
    if (recFilter === 'active') qs.set('status', 'ACTIVATED');
    qs.set('limit', '100');
    qs.set('with_campaign_preview', 'true');
    try {
      const res = await fetch(`/api/v1/media/recommendations/list?${qs.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      const sorted = [...(data.cards || [])].sort((a: RecommendationCard, b: RecommendationCard) => {
        const urgencyDelta = Number(b.urgency_score || 0) - Number(a.urgency_score || 0);
        if (urgencyDelta !== 0) return urgencyDelta;
        return Number(b.confidence || 0) - Number(a.confidence || 0);
      });
      setRecCards(sorted);
    } catch (e) {
      console.error('Recommendation list error', e);
    }
  }, [recFilter]);

  useEffect(() => {
    if (view === 'empfehlungen') loadRecommendations();
  }, [view, loadRecommendations]);

  const triggerRecommendations = async () => {
    setRecLoading(true);
    try {
      const res = await fetch('/api/v1/media/recommendations/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brand: 'gelo',
          product: 'Alle Gelo-Produkte',
          campaign_goal: 'Top-of-Mind vor Erkältungswelle',
          weekly_budget: 120000,
          channel_pool: ['programmatic', 'social', 'search', 'ctv'],
          strategy_mode: 'PLAYBOOK_AI',
          max_cards: 8,
          virus_typ: virus,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      const sorted = [...(data.cards || [])].sort((a: RecommendationCard, b: RecommendationCard) => {
        const urgencyDelta = Number(b.urgency_score || 0) - Number(a.urgency_score || 0);
        if (urgencyDelta !== 0) return urgencyDelta;
        return Number(b.confidence || 0) - Number(a.confidence || 0);
      });
      setRecCards(sorted);
      toast(`${sorted.length} Empfehlungen erzeugt`, 'success');
      await loadCockpit();
    } catch (e) {
      console.error('Generate recommendation error', e);
      const msg = e instanceof Error ? e.message : 'Unbekannter Fehler';
      toast(`Generierung fehlgeschlagen: ${msg}`, 'error');
    } finally {
      setRecLoading(false);
    }
  };

  /* ── Slide-over: load recommendation detail ── */
  const openSlideOver = useCallback(async (id: string) => {
    setSelectedRecommendationId(id);
    setSlideOverData(null);
    setSlideOverLoading(true);
    setSlideOverAdvanced(false);
    try {
      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSlideOverData(data);
    } catch (e) {
      console.error('Slide-over fetch error', e);
      toast('Details konnten nicht geladen werden', 'error');
    } finally {
      setSlideOverLoading(false);
    }
  }, [toast]);

  const closeSlideOver = () => {
    setSelectedRecommendationId(null);
    setSlideOverData(null);
    setSlideOverAdvanced(false);
  };

  const transitionStatus = async (id: string, newStatus: string) => {
    setStatusTransitioning(true);
    try {
      const res = await fetch(`/api/v1/media/recommendations/${encodeURIComponent(id)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const updated = await res.json();
      setSlideOverData((prev) => (prev ? { ...prev, status: updated.status || newStatus } : prev));
      setRecCards((prev) =>
        prev.map((c) => (c.id === id ? { ...c, status: updated.status || newStatus } : c)),
      );
      toast(`Status auf ${newStatus} gesetzt`, 'success');
    } catch (e) {
      console.error('Status transition error', e);
      const msg = e instanceof Error ? e.message : 'Fehler';
      toast(`Status-Wechsel fehlgeschlagen: ${msg}`, 'error');
    } finally {
      setStatusTransitioning(false);
    }
  };

  /* ── Map click handler for lagebild ── */
  const handleRegionClick = (code: string) => {
    setSelectedRegion(code);
    // In lagebild view: clicking a region opens the slide-over for the region's recommendation
    const region = activeMap?.regions?.[code];
    if (region?.recommendation_ref?.card_id) {
      openSlideOver(region.recommendation_ref.card_id);
    }
  };

  /* ── Render helpers ── */
  const renderTileValue = (tile: BentoTile) => {
    if (tile.value === null || tile.value === undefined || tile.value === '') return '-';
    if (typeof tile.value === 'number') {
      return `${Math.round(tile.value * 10) / 10}` + (tile.unit ? ` ${tile.unit}` : '');
    }
    return String(tile.value) + (tile.unit ? ` ${tile.unit}` : '');
  };

  /* ─────────────────────────────────────────────────────────────────────────
   *  LAGEBILD VIEW
   * ───────────────────────────────────────────────────────────────────────── */
  const renderLagebild = () => {
    if (loading) {
      return <div className="card p-8 text-center text-slate-400">Lade Lagebild...</div>;
    }
    if (!activeMap) {
      return <div className="card p-8 text-center text-slate-400">Keine Kartendaten vorhanden.</div>;
    }
    const latestMarketDecision = cockpit?.backtest_summary?.latest_market?.decision_metrics;
    const latestMarketGate = cockpit?.backtest_summary?.latest_market?.quality_gate;
    const latestReadiness = latestMarketDecision?.readiness_score_0_100;
    const latestReadinessLabel = latestMarketGate?.overall_passed ? 'GO' : 'WATCH';

    return (
      <div className="space-y-6">
        {/* Header row: Virus filter + PeixEpiScore */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 24, flexWrap: 'wrap' }}>
          {/* Virus filter chips */}
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">
              Virusfilter Lagekarte
            </div>
            <div className="flex flex-wrap items-center gap-2">
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

          {/* PeixEpiScore + Planungsreife — oben rechts */}
          {(peixSummary || latestMarketDecision) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 220, maxWidth: 340 }}>
              {peixSummary && (
                <div style={{
                  background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                  borderRadius: 12, padding: '14px 20px',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <span style={{
                      fontSize: 28, fontWeight: 800, color: 'var(--accent-violet)', lineHeight: 1,
                    }}>
                      {peixSummary.national_score ?? '\u2014'}
                    </span>
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.2 }}>
                        PeixEpiScore
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                        Band: {peixSummary.national_band ?? '\u2014'} &middot; Impact: {peixSummary.national_impact_probability ?? '\u2014'}%
                      </div>
                    </div>
                  </div>
                  <p style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
                    Fusionsindex aus 6 Dimensionen (Epidemiologie, Abwasser, Wetter, Suchtrends, Versorgungslage, Prognose). Zeigt die Gesamtlage f&uuml;r Atemwegsinfekte in Deutschland als Zahl von 0&ndash;100.
                  </p>
                </div>
              )}
              {latestMarketDecision && (
                <div style={{
                  background: 'var(--bg-card)',
                  border: `1px solid ${latestMarketGate?.overall_passed ? 'rgba(39,174,96,0.3)' : 'var(--border-color)'}`,
                  borderRadius: 12,
                  padding: '10px 14px',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
                      Planungsreife
                    </span>
                    <span style={{
                      fontSize: 11,
                      fontWeight: 700,
                      color: latestMarketGate?.overall_passed ? '#27ae60' : '#b7791f',
                    }}>
                      {latestReadinessLabel}
                    </span>
                  </div>
                  <div style={{ marginTop: 4, fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {latestReadiness != null ? `${Math.round(latestReadiness)}/100` : '\u2014'}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 10, color: 'var(--text-muted)' }}>
                    TTD {latestMarketDecision.median_ttd_days ?? 0}T · Hit-Rate {latestMarketDecision.hit_rate_pct ?? 0}% · False Alarms {latestMarketDecision.false_alarm_rate_pct ?? 0}%
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Main grid: map + sidebar */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Map */}
          <div className="xl:col-span-2 card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  Deutschland Radar: {virus}
                </h2>
                <p className="text-xs text-slate-400">
                  {activeMap.date
                    ? `Stand ${format(parseISO(activeMap.date), 'dd.MM.yyyy', { locale: de })}`
                    : 'Kein Datenstand'}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className="px-2 py-1 rounded-full text-[10px] uppercase tracking-wider"
                  style={{
                    background: 'rgba(34,197,94,0.1)',
                    color: '#16a34a',
                    border: '1px solid rgba(34,197,94,0.25)',
                  }}
                >
                  Niedrig
                </span>
                <span
                  className="px-2 py-1 rounded-full text-[10px] uppercase tracking-wider"
                  style={{
                    background: 'rgba(250,204,21,0.1)',
                    color: '#ca8a04',
                    border: '1px solid rgba(250,204,21,0.25)',
                  }}
                >
                  Mittel
                </span>
                <span
                  className="px-2 py-1 rounded-full text-[10px] uppercase tracking-wider"
                  style={{
                    background: 'rgba(239,68,68,0.1)',
                    color: '#dc2626',
                    border: '1px solid rgba(239,68,68,0.25)',
                  }}
                >
                  Hoch
                </span>
              </div>
            </div>

            {!activeMap.has_data ? (
              <div className="py-16 text-center">
                <div className="text-sm font-medium text-slate-500 mb-1">
                  Keine Kartendaten vorhanden
                </div>
                <div className="text-xs text-slate-400">
                  Starte einen Datenimport oder warte auf den täglichen Sync (06:00 Uhr).
                </div>
              </div>
            ) : (
              <div
                ref={mapContainerRef}
                className="rounded-2xl p-3"
                style={{
                  position: 'relative',
                  background:
                    'radial-gradient(800px 260px at 12% 0%, rgba(67,56,202,0.06), transparent 58%), linear-gradient(160deg, #ffffff, #f1f5f9)',
                  border: '1px solid rgba(226,232,240,0.9)',
                }}
              >
                <div className="mb-3 text-[11px] text-slate-500">
                  Klick auf ein Bundesland öffnet den Kampagnenvorschlag.
                </div>

                <svg viewBox="0 0 420 460" className="w-full max-h-[560px]">
                  <defs>
                    <filter id="vf-map-shadow" x="-20%" y="-20%" width="140%" height="140%">
                      <feDropShadow
                        dx="0"
                        dy="2"
                        stdDeviation="3"
                        floodColor="#94a3b8"
                        floodOpacity="0.2"
                      />
                    </filter>
                    <filter id="vf-selected-glow" x="-30%" y="-30%" width="160%" height="160%">
                      <feDropShadow
                        dx="0"
                        dy="0"
                        stdDeviation="3"
                        floodColor="#4338ca"
                        floodOpacity="0.45"
                      />
                    </filter>
                    <pattern
                      id="vf-map-grid"
                      width="14"
                      height="14"
                      patternUnits="userSpaceOnUse"
                    >
                      <path
                        d="M 14 0 L 0 0 0 14"
                        fill="none"
                        stroke="rgba(148,163,184,0.2)"
                        strokeWidth="0.6"
                      />
                    </pattern>
                  </defs>

                  <rect
                    x="0"
                    y="0"
                    width="420"
                    height="460"
                    rx="14"
                    fill="rgba(248,250,252,0.8)"
                  />
                  <rect
                    x="0"
                    y="0"
                    width="420"
                    height="460"
                    rx="14"
                    fill="url(#vf-map-grid)"
                  />

                  {/* Bundesland shapes */}
                  {mapShapes.map((shape) => {
                    const codeFromName = shape.name
                      ? regionCodeByName[shape.name.toLowerCase()]
                      : undefined;
                    const code = shape.code || codeFromName;
                    const region = code ? activeMap.regions?.[code] : undefined;
                    const intensity = region ? Number(region.intensity || 0) : 0;
                    const fill = region ? intensityColor(intensity) : 'rgba(226,232,240,0.5)';
                    const isSelected = Boolean(code && selectedRegion === code);
                    const band = !region
                      ? ''
                      : intensity >= 0.7
                        ? 'Hoch'
                        : intensity >= 0.4
                          ? 'Mittel'
                          : 'Niedrig';
                    return (
                      <g
                        key={`${shape.name}-${shape.code || 'na'}`}
                        tabIndex={region && code ? 0 : undefined}
                        role={region && code ? 'button' : undefined}
                        aria-label={
                          region && code
                            ? `${shape.name}: Intensität ${band}, Impact ${Math.round(region.impact_probability || 0)}%`
                            : shape.name
                        }
                        style={{
                          cursor: region && code ? 'pointer' : 'default',
                          outline: 'none',
                        }}
                        onClick={() => region && code && handleRegionClick(code)}
                        onKeyDown={(e) => {
                          if (!region || !code) return;
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            handleRegionClick(code);
                          }
                        }}
                        onFocus={() => {
                          if (region && code) setHoveredRegion(code);
                        }}
                        onBlur={() => setHoveredRegion(null)}
                        onMouseEnter={(e) => {
                          if (!region || !code) return;
                          setHoveredRegion(code);
                          const rect = mapContainerRef.current?.getBoundingClientRect();
                          if (rect)
                            setTooltipPos({
                              x: e.clientX - rect.left,
                              y: e.clientY - rect.top,
                            });
                        }}
                        onMouseMove={(e) => {
                          if (!region || !code) return;
                          const rect = mapContainerRef.current?.getBoundingClientRect();
                          if (rect)
                            setTooltipPos({
                              x: e.clientX - rect.left,
                              y: e.clientY - rect.top,
                            });
                        }}
                        onMouseLeave={() => setHoveredRegion(null)}
                      >
                        <path
                          d={shape.d}
                          fill={fill}
                          stroke={isSelected ? '#4338ca' : 'rgba(203,213,225,0.9)'}
                          strokeWidth={isSelected ? 2.4 : 1.1}
                          filter={
                            isSelected ? 'url(#vf-selected-glow)' : 'url(#vf-map-shadow)'
                          }
                          style={{ transition: 'all 180ms ease' }}
                        />
                        {/* Label circles for non-callout Bundesländer */}
                        {!(code && CALLOUT_TARGETS[code]) && (
                          <>
                            <circle
                              cx={shape.cx}
                              cy={shape.cy - 5}
                              r={8.5}
                              fill="rgba(255,255,255,0.92)"
                              stroke={
                                isSelected
                                  ? 'rgba(67,56,202,0.85)'
                                  : 'rgba(203,213,225,0.7)'
                              }
                              strokeWidth={isSelected ? 1.2 : 0.8}
                            />
                            <text
                              x={shape.cx}
                              y={shape.cy - 2.5}
                              textAnchor="middle"
                              fill="#334155"
                              fontSize="8"
                              fontWeight="700"
                            >
                              {code || '--'}
                            </text>
                            {region && (
                              <text
                                x={shape.cx}
                                y={shape.cy + 11}
                                textAnchor="middle"
                                fill="#64748b"
                                fontSize="6.6"
                              >
                                {band}
                              </text>
                            )}
                          </>
                        )}
                      </g>
                    );
                  })}

                  {/* Callout lines for city-states */}
                  {mapShapes.map((shape) => {
                    const code =
                      shape.code ||
                      (shape.name ? regionCodeByName[shape.name.toLowerCase()] : undefined);
                    if (!code) return null;
                    const callout = CALLOUT_TARGETS[code];
                    if (!callout) return null;
                    const region = activeMap.regions?.[code];
                    const intensity = region ? Number(region.intensity || 0) : 0;
                    const fill = region
                      ? intensityColor(intensity)
                      : 'rgba(226,232,240,0.5)';
                    const isSelected = selectedRegion === code;
                    const isHovered = hoveredRegion === code;
                    const band = !region
                      ? ''
                      : intensity >= 0.7
                        ? 'Hoch'
                        : intensity >= 0.4
                          ? 'Mittel'
                          : 'Niedrig';
                    return (
                      <g
                        key={`callout-${code}`}
                        style={{ cursor: region ? 'pointer' : 'default' }}
                        tabIndex={region ? 0 : undefined}
                        role={region ? 'button' : undefined}
                        aria-label={`${shape.name} Callout`}
                        onClick={() => region && handleRegionClick(code)}
                        onKeyDown={(e) => {
                          if (!region) return;
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            handleRegionClick(code);
                          }
                        }}
                        onMouseEnter={(e) => {
                          if (!region) return;
                          setHoveredRegion(code);
                          const rect = mapContainerRef.current?.getBoundingClientRect();
                          if (rect)
                            setTooltipPos({
                              x: e.clientX - rect.left,
                              y: e.clientY - rect.top,
                            });
                        }}
                        onMouseMove={(e) => {
                          if (!region) return;
                          const rect = mapContainerRef.current?.getBoundingClientRect();
                          if (rect)
                            setTooltipPos({
                              x: e.clientX - rect.left,
                              y: e.clientY - rect.top,
                            });
                        }}
                        onMouseLeave={() => setHoveredRegion(null)}
                      >
                        <line
                          x1={shape.cx}
                          y1={shape.cy}
                          x2={callout.tx}
                          y2={callout.ty}
                          stroke={isSelected || isHovered ? '#4338ca' : '#94a3b8'}
                          strokeWidth={isSelected || isHovered ? 1.2 : 0.8}
                          strokeDasharray="3 2"
                          style={{ transition: 'all 180ms ease' }}
                        />
                        <circle
                          cx={callout.tx}
                          cy={callout.ty}
                          r={14}
                          fill={fill}
                          stroke={
                            isSelected
                              ? '#4338ca'
                              : isHovered
                                ? 'rgba(67,56,202,0.6)'
                                : 'rgba(203,213,225,0.9)'
                          }
                          strokeWidth={isSelected ? 2 : 1.2}
                          filter={isSelected ? 'url(#vf-selected-glow)' : undefined}
                          style={{ transition: 'all 180ms ease' }}
                        />
                        <text
                          x={callout.tx}
                          y={callout.ty + 1}
                          textAnchor="middle"
                          dominantBaseline="middle"
                          fill={intensity >= 0.5 ? '#fff' : '#334155'}
                          fontSize="8.5"
                          fontWeight="700"
                          style={{ pointerEvents: 'none' }}
                        >
                          {code}
                        </text>
                        {region && (
                          <text
                            x={callout.tx}
                            y={callout.ty + 22}
                            textAnchor="middle"
                            fill="#64748b"
                            fontSize="6.6"
                            style={{ pointerEvents: 'none' }}
                          >
                            {band}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </svg>

                {/* Region hover tooltip */}
                {hoveredRegion &&
                  activeMap.regions?.[hoveredRegion]?.tooltip &&
                  (() => {
                    const tip = activeMap.regions[hoveredRegion].tooltip!;
                    const containerW = mapContainerRef.current?.offsetWidth || 600;
                    const containerH = mapContainerRef.current?.offsetHeight || 500;
                    const flipX = tooltipPos.x > containerW - 380;
                    const flipY = tooltipPos.y > containerH - 200;
                    const bandColors: Record<
                      string,
                      { bg: string; border: string; text: string }
                    > = {
                      critical: {
                        bg: 'rgba(239,68,68,0.08)',
                        border: 'rgba(239,68,68,0.3)',
                        text: '#dc2626',
                      },
                      high: {
                        bg: 'rgba(245,158,11,0.08)',
                        border: 'rgba(245,158,11,0.3)',
                        text: '#d97706',
                      },
                      elevated: {
                        bg: 'rgba(250,204,21,0.08)',
                        border: 'rgba(250,204,21,0.3)',
                        text: '#ca8a04',
                      },
                      low: {
                        bg: 'rgba(34,197,94,0.08)',
                        border: 'rgba(34,197,94,0.3)',
                        text: '#16a34a',
                      },
                    };
                    const c = bandColors[tip.peix_band] || bandColors.low;
                    return (
                      <div
                        style={{
                          position: 'absolute',
                          left: flipX ? tooltipPos.x - 360 : tooltipPos.x + 16,
                          top: flipY ? tooltipPos.y - 180 : tooltipPos.y - 10,
                          zIndex: 50,
                          pointerEvents: 'none',
                          maxWidth: 370,
                          minWidth: 290,
                          transition: 'opacity 120ms ease, transform 120ms ease',
                        }}
                      >
                        <div
                          style={{
                            background: '#ffffff',
                            border: `1px solid ${c.border}`,
                            borderRadius: 12,
                            boxShadow:
                              '0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)',
                            padding: '14px 16px',
                          }}
                        >
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              marginBottom: 8,
                            }}
                          >
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>
                              {tip.region_name}
                            </div>
                            <span
                              style={{
                                fontSize: 10,
                                fontWeight: 600,
                                padding: '2px 8px',
                                borderRadius: 999,
                                background: c.bg,
                                color: c.text,
                                border: `1px solid ${c.border}`,
                                textTransform: 'uppercase',
                                letterSpacing: '0.05em',
                              }}
                            >
                              {tip.urgency_label}
                            </span>
                          </div>

                          <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
                            <div style={{ fontSize: 11, color: '#64748b' }}>
                              Score:{' '}
                              <span style={{ fontWeight: 600, color: '#334155' }}>
                                {tip.peix_score?.toFixed(1)}
                              </span>
                            </div>
                            <div style={{ fontSize: 11, color: '#64748b' }}>
                              Impact:{' '}
                              <span style={{ fontWeight: 600, color: '#334155' }}>
                                {tip.impact_probability?.toFixed(0)}%
                              </span>
                            </div>
                            <div style={{ fontSize: 11, color: '#64748b' }}>
                              Trend:{' '}
                              <span
                                style={{
                                  fontWeight: 600,
                                  color:
                                    tip.trend === 'steigend'
                                      ? '#dc2626'
                                      : tip.trend === 'fallend'
                                        ? '#16a34a'
                                        : '#64748b',
                                }}
                              >
                                {tip.trend === 'steigend'
                                  ? '\u2197'
                                  : tip.trend === 'fallend'
                                    ? '\u2198'
                                    : '\u2192'}{' '}
                                {tip.change_pct > 0 ? '+' : ''}
                                {tip.change_pct}%
                              </span>
                            </div>
                          </div>

                          <div
                            style={{
                              fontSize: 12,
                              lineHeight: '1.55',
                              color: '#334155',
                              padding: '8px 10px',
                              background: 'rgba(248,250,252,0.8)',
                              borderRadius: 8,
                              border: '1px solid rgba(226,232,240,0.7)',
                            }}
                          >
                            {tip.recommendation_text}
                          </div>

                          <div
                            style={{
                              marginTop: 8,
                              display: 'flex',
                              alignItems: 'center',
                              gap: 6,
                            }}
                          >
                            <span
                              style={{
                                fontSize: 10,
                                fontWeight: 600,
                                padding: '3px 8px',
                                borderRadius: 999,
                                background:
                                  'linear-gradient(135deg, rgba(34,197,94,0.1), rgba(16,185,129,0.08))',
                                color: '#16a34a',
                                border: '1px solid rgba(34,197,94,0.2)',
                              }}
                            >
                              {tip.recommended_product}
                            </span>
                            <span style={{ fontSize: 10, color: '#94a3b8' }}>
                              Klick für Details
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })()}

                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                  <div>Hover für Empfehlung · Klick für Kampagne</div>
                  <div>
                    Aktive Auswahl:{' '}
                    <span className="text-slate-600">{selectedRegion || 'keine'}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right sidebar: Top-5 regions */}
          <div className="space-y-4">
            <div className="card p-4">
              <h3 className="text-sm font-semibold text-slate-900 mb-3">
                Top Regionen nach Impact
              </h3>
              <div className="space-y-2">
                {mapRanking.map((r, idx) => (
                  <button
                    key={r.code}
                    type="button"
                    onClick={() => handleRegionClick(r.code)}
                    className="w-full text-left rounded-lg px-3 py-2 hover:bg-slate-100 transition bg-slate-50 border border-slate-100"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm text-slate-700">
                          {idx + 1}. {r.name}
                        </div>
                        <div className="text-xs text-slate-400">
                          Impact {Math.round(r.impact_probability || 0)}% · Trend{' '}
                          {trendIcon(r.trend)} {r.change_pct > 0 ? '+' : ''}
                          {r.change_pct}%
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm text-slate-900 font-medium">Radar</div>
                        <div className="text-xs text-slate-400">Details</div>
                      </div>
                    </div>
                  </button>
                ))}
                {mapRanking.length === 0 && (
                  <div className="text-xs text-slate-400 text-center py-3">
                    Keine Regionsdaten vorhanden.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* 4 signal tiles below map */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {signalTiles.slice(0, 4).map((tile) => (
            <div key={tile.id} className="card p-4">
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="text-xs text-slate-500 font-medium">{tile.title}</div>
                <span
                  className="inline-flex w-2.5 h-2.5 rounded-full"
                  style={{ background: tile.is_live ? '#22c55e' : '#ef4444' }}
                  title={tile.is_live ? 'Live' : 'Nicht live'}
                />
              </div>
              <div className="text-lg font-bold text-slate-900">{renderTileValue(tile)}</div>
              <div className="text-[11px] text-indigo-500 mt-1">
                Impact: {Math.round(tile.impact_probability || 0)}%
              </div>
            </div>
          ))}
          {/* If fewer than 4 signal tiles matched, fill from remaining bento tiles */}
          {signalTiles.length < 4 &&
            bentoTiles
              .filter(
                (t) =>
                  !SIGNAL_TILE_KEYS.some((k) => t.id.toLowerCase().includes(k)) &&
                  !SECONDARY_SIGNAL_KEYS.some((k) => t.id.toLowerCase().includes(k)),
              )
              .slice(0, 4 - signalTiles.length)
              .map((tile) => (
                <div key={tile.id} className="card p-4">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="text-xs text-slate-500 font-medium">{tile.title}</div>
                    <span
                      className="inline-flex w-2.5 h-2.5 rounded-full"
                      style={{ background: tile.is_live ? '#22c55e' : '#ef4444' }}
                    />
                  </div>
                  <div className="text-lg font-bold text-slate-900">
                    {renderTileValue(tile)}
                  </div>
                  <div className="text-[11px] text-indigo-500 mt-1">
                    Impact: {Math.round(tile.impact_probability || 0)}%
                  </div>
                </div>
              ))}
        </div>

        {/* Secondary signals as small badges */}
        {secondarySignals.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider mr-1">
              Sekundärsignale
            </span>
            {secondarySignals.map((tile) => (
              <span
                key={tile.id}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs bg-slate-50 border border-slate-200 text-slate-600"
              >
                <span
                  className="inline-flex w-2 h-2 rounded-full"
                  style={{ background: tile.is_live ? '#22c55e' : '#ef4444' }}
                />
                <span className="font-medium">{tile.title}</span>
                <span className="text-slate-900 font-semibold">{renderTileValue(tile)}</span>
              </span>
            ))}
          </div>
        )}

        {/* Data freshness timestamp line */}
        {dataFreshness && Object.keys(dataFreshness).length > 0 && (
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
            <span className="uppercase tracking-wider font-medium">Datenstand</span>
            {Object.entries(dataFreshness).map(([key, ts]) => {
              const label = key
                .replace(/_/g, ' ')
                .replace(/\b\w/g, (c) => c.toUpperCase());
              let ageDays = -1;
              if (ts) {
                try {
                  ageDays = Math.round(
                    (Date.now() - new Date(ts).getTime()) / 86400000,
                  );
                } catch {
                  /* ignore */
                }
              }
              const fresh = ageDays >= 0 && ageDays <= 3;
              const stale = ageDays > 3 && ageDays <= 7;
              return (
                <span key={key}>
                  <span className="text-slate-500">{label}: </span>
                  {ts ? (
                    <span
                      className={`font-semibold ${fresh ? 'text-emerald-600' : stale ? 'text-amber-600' : 'text-red-500'}`}
                    >
                      {ageDays === 0
                        ? 'heute'
                        : ageDays === 1
                          ? 'gestern'
                          : `${ageDays}d`}
                    </span>
                  ) : (
                    <span className="text-slate-400">{'\u2014'}</span>
                  )}
                </span>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  /* ─────────────────────────────────────────────────────────────────────────
   *  EMPFEHLUNGEN VIEW
   * ───────────────────────────────────────────────────────────────────────── */
  const renderEmpfehlungen = () => {
    return (
      <div className="space-y-6">
        {/* Header bar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              onClick={triggerRecommendations}
              className="px-4 py-2 text-xs font-bold rounded-lg transition hover:brightness-110 disabled:opacity-60"
              style={{
                background: 'linear-gradient(135deg, #4ade80, #22c55e)',
                color: '#052e1b',
              }}
              disabled={recLoading}
            >
              {recLoading ? 'Berechne...' : 'Empfehlungen generieren'}
            </button>
            <button
              onClick={loadRecommendations}
              className="media-button secondary px-3 py-2 text-xs font-semibold rounded-lg transition"
            >
              Aktualisieren
            </button>
          </div>
          <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-0.5">
            <button
              onClick={() => setRecFilter('active')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
                recFilter === 'active'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Aktiv
            </button>
            <button
              onClick={() => setRecFilter('all')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
                recFilter === 'all'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Alle
            </button>
          </div>
        </div>

        {/* 2-column card grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {recCards.map((card) => (
            <button
              key={card.id}
              type="button"
              onClick={() => openSlideOver(card.id)}
              className="card p-5 text-left hover:shadow-lg transition"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-base font-bold text-slate-900 truncate">
                    {card.playbook_title ||
                      card.campaign_name ||
                      `${card.brand} · ${card.product}`}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {card.region || (card.region_codes || []).join(', ') || 'National'}
                  </div>
                </div>
                <div className="flex-shrink-0 text-right">
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider">
                    Dringlichkeit
                  </div>
                  <div className="text-sm font-bold text-slate-700 mt-0.5">
                    {Math.round(card.urgency_score || 0)}
                  </div>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                {(card.recommended_product || card.product) && (
                  <span
                    className="px-2 py-0.5 text-[10px] rounded-full font-semibold"
                    style={{
                      background: 'rgba(99,102,241,0.1)',
                      color: '#4f46e5',
                      border: '1px solid rgba(99,102,241,0.2)',
                    }}
                  >
                    {card.recommended_product || card.product}
                  </span>
                )}
                <span className="text-[11px] text-slate-400">
                  Budget: +{Number(card.budget_shift_pct).toFixed(1)}%
                </span>
                {card.confidence !== undefined && (
                  <span className="text-[11px] text-emerald-500">
                    Konf. {Math.round((card.confidence || 0) * 100)}%
                  </span>
                )}
                <span
                  className="px-2 py-0.5 text-[10px] rounded-full"
                  style={{
                    background: 'rgba(148,163,184,0.1)',
                    color: '#64748b',
                    border: '1px solid rgba(148,163,184,0.2)',
                  }}
                >
                  {String(card.status || 'DRAFT')}
                </span>
              </div>
            </button>
          ))}

          {recCards.length === 0 && (
            <div className="md:col-span-2 text-center py-8 rounded-xl bg-slate-50 border border-slate-100">
              <div className="text-sm font-medium text-slate-500">
                Noch keine KI-Empfehlungen
              </div>
              <div className="text-xs text-slate-400 mt-1">
                Klicke oben auf "Empfehlungen generieren" um neue Vorschläge zu erstellen.
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  /* ─────────────────────────────────────────────────────────────────────────
   *  SLIDE-OVER PANEL (used by both views)
   * ───────────────────────────────────────────────────────────────────────── */
  const renderSlideOver = () => {
    if (!selectedRecommendationId) return null;

    const currentStatus = slideOverData?.status || 'DRAFT';
    const nextStatus = WORKFLOW_TRANSITIONS[currentStatus as string];
    const facts: DecisionFact[] = slideOverData?.decision_brief?.facts || [];
    const pack = slideOverData?.campaign_pack;

    return (
      <>
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-black/20 z-40"
          onClick={closeSlideOver}
        />
        {/* Panel */}
        <div
          className="fixed top-0 right-0 h-full z-50 bg-white shadow-2xl border-l border-slate-200 overflow-y-auto"
          style={{ width: 600, maxWidth: '100vw' }}
        >
          {/* Close button */}
          <div className="sticky top-0 bg-white border-b border-slate-100 px-5 py-3 flex items-center justify-between z-10">
            <h3 className="text-sm font-semibold text-slate-900">Empfehlung Detail</h3>
            <button
              onClick={closeSlideOver}
              className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-100 transition text-slate-500"
              aria-label="Schliessen"
            >
              &#x2715;
            </button>
          </div>

          <div className="p-5 space-y-5">
            {slideOverLoading && (
              <div className="text-center py-8 text-slate-400">Lade Details...</div>
            )}

            {!slideOverLoading && slideOverData && (
              <>
                {/* Campaign name + region */}
                <div>
                  <div className="text-lg font-bold text-slate-900">
                    {slideOverData.campaign_name ||
                      slideOverData.playbook_title ||
                      `${slideOverData.brand} · ${slideOverData.product}`}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {slideOverData.region ||
                      (slideOverData.region_codes || []).join(', ') ||
                      'National'}
                  </div>
                </div>

                {/* Reason */}
                {slideOverData.reason && (
                  <div className="text-sm text-slate-600 leading-relaxed">
                    {slideOverData.reason}
                  </div>
                )}

                {/* Key metrics */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg p-3 bg-slate-50 border border-slate-100">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider">
                      Produkt
                    </div>
                    <div className="text-sm font-semibold text-slate-900 mt-1">
                      {slideOverData.recommended_product || slideOverData.product}
                    </div>
                  </div>
                  <div className="rounded-lg p-3 bg-slate-50 border border-slate-100">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider">
                      Budget Shift
                    </div>
                    <div className="text-sm font-semibold text-slate-900 mt-1">
                      +{Number(slideOverData.budget_shift_pct).toFixed(2)}%
                    </div>
                  </div>
                  <div className="rounded-lg p-3 bg-slate-50 border border-slate-100">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider">
                      Dringlichkeit
                    </div>
                    <div className="text-sm font-semibold text-slate-900 mt-1">
                      {Math.round(slideOverData.urgency_score || 0)}
                    </div>
                  </div>
                  <div className="rounded-lg p-3 bg-slate-50 border border-slate-100">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider">
                      Konfidenz
                    </div>
                    <div className="text-sm font-semibold text-slate-900 mt-1">
                      {slideOverData.confidence !== undefined
                        ? `${Math.round((slideOverData.confidence || 0) * 100)}%`
                        : '\u2014'}
                    </div>
                  </div>
                </div>

                {/* Decision facts table */}
                {facts.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-slate-700 mb-2 uppercase tracking-wider">
                      Entscheidungsfakten
                    </h4>
                    <div className="rounded-lg border border-slate-200 overflow-hidden">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-slate-50 text-slate-500">
                            <th className="text-left px-3 py-2">Faktor</th>
                            <th className="text-left px-3 py-2">Wert</th>
                            <th className="text-left px-3 py-2">Quelle</th>
                          </tr>
                        </thead>
                        <tbody>
                          {facts.map((fact, idx) => (
                            <tr
                              key={fact.key || idx}
                              className="border-t border-slate-100"
                            >
                              <td className="px-3 py-2 text-slate-600">
                                {fact.label}
                              </td>
                              <td className="px-3 py-2 text-slate-900 font-medium">
                                {String(fact.value ?? '\u2014')}
                              </td>
                              <td className="px-3 py-2 text-slate-400">
                                {fact.source || '\u2014'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Workflow status transitions */}
                <div>
                  <h4 className="text-xs font-semibold text-slate-700 mb-2 uppercase tracking-wider">
                    Workflow
                  </h4>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className="px-2.5 py-1 text-xs rounded-full font-medium"
                      style={{
                        background: 'rgba(99,102,241,0.1)',
                        color: '#4f46e5',
                        border: '1px solid rgba(99,102,241,0.2)',
                      }}
                    >
                      Aktuell: {currentStatus}
                    </span>
                    {nextStatus && (
                      <button
                        onClick={() =>
                          transitionStatus(selectedRecommendationId!, nextStatus)
                        }
                        disabled={statusTransitioning}
                        className="px-3 py-1.5 text-xs font-bold rounded-lg transition hover:brightness-110 disabled:opacity-60"
                        style={{
                          background: 'linear-gradient(135deg, #4ade80, #22c55e)',
                          color: '#052e1b',
                        }}
                      >
                        {statusTransitioning
                          ? 'Wird gesetzt...'
                          : `Auf ${nextStatus} setzen`}
                      </button>
                    )}
                    {currentStatus === 'ACTIVATED' && (
                      <span className="text-xs text-emerald-600 font-medium">
                        Bereits aktiviert
                      </span>
                    )}
                  </div>
                </div>

                {/* Advanced toggle: Kampagnenplan bearbeiten */}
                <div>
                  <button
                    onClick={() => setSlideOverAdvanced((s) => !s)}
                    className="text-xs text-slate-500 hover:text-slate-700 transition underline"
                  >
                    {slideOverAdvanced ? 'Erweitert ausblenden' : 'Erweitert'}
                  </button>
                  {slideOverAdvanced && pack && (
                    <div className="mt-3 space-y-3">
                      <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                        Kampagnenplan bearbeiten
                      </h4>
                      {pack.campaign && (
                        <div className="rounded-lg p-3 bg-slate-50 border border-slate-100 text-xs space-y-1">
                          <div>
                            <span className="text-slate-500">Name: </span>
                            <span className="text-slate-900 font-medium">
                              {pack.campaign.campaign_name || '\u2014'}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500">Ziel: </span>
                            <span className="text-slate-900">
                              {pack.campaign.objective || '\u2014'}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500">Priorität: </span>
                            <span className="text-slate-900">
                              {pack.campaign.priority || '\u2014'}
                            </span>
                          </div>
                        </div>
                      )}
                      {pack.budget_plan && (
                        <div className="rounded-lg p-3 bg-slate-50 border border-slate-100 text-xs space-y-1">
                          <div>
                            <span className="text-slate-500">Wochenbudget: </span>
                            <span className="text-slate-900 font-medium">
                              {pack.budget_plan.weekly_budget_eur?.toLocaleString(
                                'de-DE',
                              ) || '\u2014'}{' '}
                              EUR
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500">Shift: </span>
                            <span className="text-slate-900">
                              {pack.budget_plan.budget_shift_pct?.toFixed(2) || '\u2014'}%
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500">Flugbudget: </span>
                            <span className="text-slate-900">
                              {pack.budget_plan.total_flight_budget_eur?.toLocaleString(
                                'de-DE',
                              ) || '\u2014'}{' '}
                              EUR
                            </span>
                          </div>
                        </div>
                      )}
                      {pack.channel_plan && pack.channel_plan.length > 0 && (
                        <div className="rounded-lg p-3 bg-slate-50 border border-slate-100 text-xs">
                          <div className="text-slate-500 mb-1">Kanalmix:</div>
                          {pack.channel_plan.map((ch, idx) => (
                            <div key={idx} className="flex items-center justify-between py-0.5">
                              <span className="text-slate-700 font-medium">
                                {ch.channel}
                              </span>
                              <span className="text-slate-500">{ch.share_pct}%</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {pack.message_framework && (
                        <div className="rounded-lg p-3 bg-slate-50 border border-slate-100 text-xs space-y-1">
                          <div>
                            <span className="text-slate-500">Hero-Message: </span>
                            <span className="text-slate-900">
                              {pack.message_framework.hero_message || '\u2014'}
                            </span>
                          </div>
                          {pack.message_framework.compliance_note && (
                            <div>
                              <span className="text-slate-500">Compliance: </span>
                              <span className="text-amber-600">
                                {pack.message_framework.compliance_note}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}

            {!slideOverLoading && !slideOverData && (
              <div className="text-center py-8 text-slate-400">
                Keine Daten für diese Empfehlung verfügbar.
              </div>
            )}
          </div>
        </div>
      </>
    );
  };

  /* ─────────────────────────────────────────────────────────────────────────
   *  BACKTEST
   * ───────────────────────────────────────────────────────────────────────── */

  const TARGET_OPTIONS = [
    { value: 'ATEMWEGSINDEX', label: 'Atemwegsindex (alle Erreger)' },
    { value: 'RKI_ARE', label: 'RKI ARE (Arztbesuche)' },
    { value: 'SURVSTAT', label: 'Influenza (Detail)' },
    { value: 'MYCOPLASMA', label: 'Mycoplasma (Detail)' },
    { value: 'KEUCHHUSTEN', label: 'Keuchhusten (Detail)' },
    { value: 'PNEUMOKOKKEN', label: 'Pneumokokken (Detail)' },
    { value: 'H_INFLUENZAE', label: 'Parainfluenza (Detail)' },
  ];

  const BUNDESLAENDER_OPTIONS = [
    '', 'Baden-Württemberg', 'Bayern', 'Berlin', 'Brandenburg', 'Bremen',
    'Hamburg', 'Hessen', 'Mecklenburg-Vorpommern', 'Niedersachsen',
    'Nordrhein-Westfalen', 'Rheinland-Pfalz', 'Saarland', 'Sachsen',
    'Sachsen-Anhalt', 'Schleswig-Holstein', 'Thüringen',
  ];

  // ── Signal Detection for Backtest Chart ──
  const btSignals = useMemo(() => {
    const data = btResult?.chart_data;
    if (!data || data.length < 5) return { peaks: [] as number[], surges: [] as number[], earlyWarnings: [] as { start: number; end: number }[] };

    const real = data.map((d: any) => d.real_qty ?? 0);
    const pred = data.map((d: any) => d.predicted_qty ?? 0);
    const seasonal = data.map((d: any) => d.baseline_seasonal ?? 0);

    // Median + std for thresholding
    const sorted = [...real].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    const mean = real.reduce((s: number, v: number) => s + v, 0) / real.length;
    const std = Math.sqrt(real.reduce((s: number, v: number) => s + (v - mean) ** 2, 0) / real.length);
    const peakThreshold = median + 1.5 * std;

    // 1) Peaks: local maxima above threshold (within ±2 window)
    const peaks: number[] = [];
    for (let i = 2; i < real.length - 2; i++) {
      if (real[i] >= peakThreshold
        && real[i] >= real[i - 1] && real[i] >= real[i - 2]
        && real[i] >= real[i + 1] && real[i] >= real[i + 2]) {
        // Avoid marking peaks too close together (min 4 apart)
        if (peaks.length === 0 || i - peaks[peaks.length - 1] >= 4) {
          peaks.push(i);
        }
      }
    }

    // 2) Surges: week-over-week increase > 50% AND absolute jump > 0.3 * std
    const surges: number[] = [];
    for (let i = 1; i < real.length; i++) {
      const prev = real[i - 1];
      const curr = real[i];
      if (prev > 0 && curr > median * 0.5 && (curr - prev) / prev > 0.5 && (curr - prev) > 0.3 * std) {
        if (surges.length === 0 || i - surges[surges.length - 1] >= 3) {
          surges.push(i);
        }
      }
    }

    // 3) Early Warnings: zones where model predicted rise ≥3 weeks before real peak
    const earlyWarnings: { start: number; end: number }[] = [];
    for (const peakIdx of peaks) {
      // Look back: when did predicted first exceed seasonal by >20%?
      let firstSignal = -1;
      for (let j = Math.max(0, peakIdx - 12); j < peakIdx; j++) {
        const s = seasonal[j] || 0;
        if (s > 0 && pred[j] > s * 1.2 && pred[j] > median * 0.3) {
          firstSignal = j;
          break;
        }
      }
      if (firstSignal >= 0 && peakIdx - firstSignal >= 3) {
        earlyWarnings.push({ start: firstSignal, end: peakIdx });
      }
    }

    return { peaks, surges, earlyWarnings };
  }, [btResult]);

  const buildBacktestChartData = useCallback(
    (result: BacktestResponse | null, mode: BacktestChartMode): BacktestChartPoint[] => {
      const chartData = result?.chart_data || [];
      if (!chartData.length) return [];

      if (mode === 'planning' && result?.planning_curve?.curve?.length) {
        const dateMap: Record<string, BacktestChartPoint> = {};
        for (const row of chartData.filter((p) => !p.is_forecast)) {
          const targetDate = row.target_date || row.date;
          if (!dateMap[targetDate]) dateMap[targetDate] = { date: targetDate };
          dateMap[targetDate].target_date = targetDate;
          if (row.real_qty != null) dateMap[targetDate].real_qty = row.real_qty;
        }

        const lastRealDate = chartData
          .filter((p) => !p.is_forecast && p.real_qty != null)
          .map((p) => p.target_date || p.date)
          .sort((a, b) => a.localeCompare(b))
          .pop() || '';

        for (const point of result.planning_curve.curve) {
          const issueDate = point.issue_date || point.based_on;
          const targetDate = point.target_date || point.date;
          if (!issueDate || !targetDate) continue;

          if (!dateMap[issueDate]) dateMap[issueDate] = { date: issueDate };
          dateMap[issueDate].issue_date = issueDate;
          dateMap[issueDate].target_date = targetDate;
          dateMap[issueDate].based_on = point.based_on || issueDate;
          dateMap[issueDate].predicted_qty = point.planning_qty ?? null;

          if (!dateMap[targetDate]) {
            dateMap[targetDate] = { date: targetDate, target_date: targetDate };
          }

          if (targetDate > lastRealDate) {
            dateMap[issueDate].forecast_qty = point.planning_qty ?? null;
          }
        }

        return Object.values(dateMap).sort((a, b) => a.date.localeCompare(b.date));
      }

      if (mode === 'vintage') {
        const dateMap: Record<string, BacktestChartPoint> = {};
        const records = result?.forecast_records || [];
        const configuredLeadDays = result?.vintage_metrics?.configured_horizon_days
          || result?.walk_forward?.horizon_days
          || 14;

        const resolveLeadDays = (
          issueDate?: string,
          targetDate?: string,
          explicitLead?: number | null,
        ): number => {
          if (typeof explicitLead === 'number' && Number.isFinite(explicitLead)) {
            return Math.round(explicitLead);
          }
          if (issueDate && targetDate) {
            const issue = parseISO(issueDate);
            const target = parseISO(targetDate);
            if (isValid(issue) && isValid(target)) {
              return differenceInCalendarDays(target, issue);
            }
          }
          return configuredLeadDays;
        };

        const resolvePlotDate = (
          targetDate?: string,
          leadDays?: number,
          fallbackIssueDate?: string,
        ): string | null => {
          if (targetDate && typeof leadDays === 'number' && Number.isFinite(leadDays)) {
            const target = parseISO(targetDate);
            if (isValid(target)) {
              return format(subDays(target, leadDays), 'yyyy-MM-dd');
            }
          }
          return fallbackIssueDate || targetDate || null;
        };

        if (records.length) {
          for (const rec of records) {
            const issueDate = rec.issue_date;
            const targetDate = rec.target_date;
            if (!targetDate) continue;
            const leadDays = resolveLeadDays(issueDate, targetDate, rec.lead_days);
            const plotDate = resolvePlotDate(targetDate, leadDays, issueDate);

            if (plotDate) {
              if (!dateMap[plotDate]) dateMap[plotDate] = { date: plotDate };
              dateMap[plotDate].plot_date = plotDate;
              dateMap[plotDate].issue_date = issueDate || plotDate;
              dateMap[plotDate].target_date = targetDate;
              dateMap[plotDate].lead_days = leadDays;
              dateMap[plotDate].predicted_qty = rec.y_hat ?? null;
            }

            if (!dateMap[targetDate]) dateMap[targetDate] = { date: targetDate };
            dateMap[targetDate].target_date = targetDate;
            dateMap[targetDate].real_qty = rec.y_true ?? null;
            if (!dateMap[targetDate].issue_date_hint) {
              dateMap[targetDate].issue_date_hint = issueDate;
            }
          }
        } else {
          for (const row of chartData.filter((p) => !p.is_forecast && p.issue_date)) {
            const issueDate = row.issue_date as string;
            const targetDate = row.target_date || row.date;
            const leadDays = resolveLeadDays(issueDate, targetDate, row.lead_days ?? null);
            const plotDate = resolvePlotDate(targetDate, leadDays, issueDate);

            if (plotDate) {
              if (!dateMap[plotDate]) dateMap[plotDate] = { date: plotDate };
              dateMap[plotDate].plot_date = plotDate;
              dateMap[plotDate].issue_date = issueDate;
              dateMap[plotDate].target_date = targetDate;
              dateMap[plotDate].lead_days = leadDays;
              dateMap[plotDate].predicted_qty = row.predicted_qty ?? null;
            }

            if (!dateMap[targetDate]) dateMap[targetDate] = { date: targetDate };
            dateMap[targetDate].target_date = targetDate;
            dateMap[targetDate].real_qty = row.real_qty ?? null;
            dateMap[targetDate].issue_date_hint = issueDate;
          }
        }

        for (const row of chartData.filter((p) => p.is_forecast)) {
          const issueDate = row.issue_date || row.date;
          const targetDate = row.target_date || row.date;
          if (!issueDate || !targetDate) continue;
          const leadDays = resolveLeadDays(issueDate, targetDate, row.lead_days ?? null);
          const plotDate = resolvePlotDate(targetDate, leadDays, issueDate);
          if (!plotDate) continue;

          if (!dateMap[plotDate]) dateMap[plotDate] = { date: plotDate };
          dateMap[plotDate].plot_date = plotDate;
          dateMap[plotDate].issue_date = issueDate;
          dateMap[plotDate].target_date = targetDate;
          dateMap[plotDate].lead_days = leadDays;
          dateMap[plotDate].forecast_qty = row.forecast_qty ?? null;
          dateMap[plotDate].ci_80_lower = row.ci_80_lower ?? null;
          dateMap[plotDate].ci_80_upper = row.ci_80_upper ?? null;
          dateMap[plotDate].ci_95_lower = row.ci_95_lower ?? null;
          dateMap[plotDate].ci_95_upper = row.ci_95_upper ?? null;
          dateMap[plotDate].is_future_vintage = true;
        }

        return Object.values(dateMap).sort((a, b) => a.date.localeCompare(b.date));
      }

      return chartData.map((point) => ({
        ...point,
        ci_95_base: point.ci_95_lower ?? null,
        ci_95_range:
          point.ci_95_upper != null && point.ci_95_lower != null
            ? point.ci_95_upper - point.ci_95_lower
            : null,
        ci_80_base: point.ci_80_lower ?? null,
        ci_80_range:
          point.ci_80_upper != null && point.ci_80_lower != null
            ? point.ci_80_upper - point.ci_80_lower
            : null,
      }));
    },
    [],
  );

  const buildPlanningConnectors = useCallback((rows: BacktestChartPoint[]) => {
    const candidates = rows.filter((row) =>
      typeof row.predicted_qty === 'number'
      && !!row.issue_date
      && !!row.target_date,
    );
    if (!candidates.length) return [];
    return candidates
      .slice(-80)
      .filter((_, idx) => idx % 2 === 0)
      .slice(-40)
      .map((row) => ({
        issue_date: row.issue_date as string,
        target_date: row.target_date as string,
        planning_qty: row.predicted_qty as number,
      }));
  }, []);

  const buildVintageConnectors = useCallback((rows: BacktestChartPoint[]) => {
    const candidates = rows.filter((row) =>
      !!row.target_date
      && !!row.date
      && (typeof row.predicted_qty === 'number' || typeof row.forecast_qty === 'number'),
    );
    if (!candidates.length) return [];
    return candidates
      .slice(-80)
      .filter((_, idx) => idx % 2 === 0)
      .slice(-40)
      .map((row) => ({
        plot_date: row.date,
        target_date: row.target_date as string,
        vintage_qty: (typeof row.predicted_qty === 'number' ? row.predicted_qty : row.forecast_qty) as number,
      }));
  }, []);

  const loadBacktestRuns = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/backtest/runs?limit=30');
      if (!res.ok) return;
      const data = await res.json();
      setBtRuns(data.runs || []);
    } catch (e) {
      console.error('Backtest runs fetch error', e);
    }
  }, []);

  useEffect(() => {
    if (view === 'backtest') {
      loadBacktestRuns();
      // Seed from cockpit data if available
      if (cockpit?.backtest_summary) {
        const bs = cockpit.backtest_summary;
        if (bs.latest_market && !btResult) setBtResult(bs.latest_market);
        if (bs.latest_customer && !btCustomerResult) setBtCustomerResult(bs.latest_customer);
        if (bs.recent_runs?.length && btRuns.length === 0) setBtRuns(bs.recent_runs);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, cockpit?.backtest_summary]);

  const fetchTopRegions = async (target: string) => {
    try {
      const res = await fetch(`/api/v1/backtest/top-regions?target_source=${encodeURIComponent(target)}&n=5`);
      const data = await res.json();
      if (!data.error) setTopRegions(data);
    } catch { /* best-effort */ }
  };

  const runMarketBacktest = async () => {
    setBtRunning(true);
    setBtResult(null);
    setBtChartMode('validation');
    fetchTopRegions(btTargetSource);
    try {
      const qs = new URLSearchParams({
        target_source: btTargetSource,
        virus_typ: virus,
        horizon_days: String(btHorizonDays),
      });
      if (btBundesland) qs.set('bundesland', btBundesland);
      const res = await fetch(`/api/v1/backtest/market?${qs.toString()}`, { method: 'POST' });
      const data = await res.json();
      if (data.error) {
        toast(`Backtest Fehler: ${data.error}`, 'error');
      } else {
        setBtResult(data);
        toast('Markt-Check abgeschlossen', 'success');
        loadBacktestRuns();
      }
    } catch (e) {
      toast('Markt-Check fehlgeschlagen', 'error');
    } finally {
      setBtRunning(false);
    }
  };

  const runCustomerBacktest = async () => {
    const fileInput = btFileRef.current;
    if (!fileInput?.files?.length) {
      toast('Bitte CSV/XLSX Datei auswählen', 'error');
      return;
    }
    setBtCustomerRunning(true);
    setBtCustomerResult(null);
    setBtCustomerChartMode('validation');
    try {
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      const qs = new URLSearchParams({
        virus_typ: virus,
        horizon_days: String(btHorizonDays),
      });
      const res = await fetch(`/api/v1/backtest/customer?${qs.toString()}`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (data.error) {
        toast(`Realitäts-Check Fehler: ${data.error}`, 'error');
      } else {
        setBtCustomerResult(data);
        toast('Realitäts-Check abgeschlossen', 'success');
        loadBacktestRuns();
      }
    } catch (e) {
      toast('Realitäts-Check fehlgeschlagen', 'error');
    } finally {
      setBtCustomerRunning(false);
    }
  };

  // ── Wave Radar ──
  const fetchWaveRadar = async () => {
    setWaveLoading(true);
    setWaveData(null);
    setWaveWeekIdx(0);
    setWaveAnimating(false);
    try {
      const qs = new URLSearchParams({ disease: waveDisease });
      if (waveSeason) qs.set('season', waveSeason);
      const res = await fetch(`/api/v1/backtest/wave-radar?${qs.toString()}`);
      const data = await res.json();
      if (data.error) {
        toast(`Wellen-Radar Fehler: ${data.error}`, 'error');
      } else {
        setWaveData(data);
        toast('Wellen-Radar geladen', 'success');
      }
    } catch (e) {
      toast('Wellen-Radar fehlgeschlagen', 'error');
    } finally {
      setWaveLoading(false);
    }
  };

  // Fetch outbreak alerts
  const fetchAlerts = useCallback(async () => {
    setAlertLoading(true);
    try {
      const res = await fetch('/api/v1/backtest/outbreak-alerts');
      const data = await res.json();
      if (!data.error) setAlertData(data);
    } catch (e) {
      console.error('Alert fetch error', e);
    } finally {
      setAlertLoading(false);
    }
  }, []);

  // Auto-load alerts when backtest tab is active
  useEffect(() => {
    if (view === 'backtest' && !alertData && !alertLoading) {
      fetchAlerts();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  // Animation timer
  useEffect(() => {
    if (!waveAnimating || !waveData?.heatmap?.length) return;
    const maxIdx = waveData.heatmap.length - 1;
    if (waveWeekIdx >= maxIdx) { setWaveAnimating(false); return; }
    const timer = setTimeout(() => setWaveWeekIdx((i: number) => Math.min(i + 1, maxIdx)), 400);
    return () => clearTimeout(timer);
  }, [waveAnimating, waveWeekIdx, waveData]);

  // Compute map colors for current week
  const waveMapColors = useMemo(() => {
    if (!waveData?.heatmap?.length) return {} as Record<string, { intensity: number; incidence: number }>;
    const week = waveData.heatmap[waveWeekIdx] || {};
    const colors: Record<string, { intensity: number; incidence: number }> = {};

    // Find max incidence across all weeks for normalization
    let globalMax = 0;
    for (const w of waveData.heatmap) {
      for (const bl of Object.keys(BUNDESLAND_NAME_TO_CODE)) {
        const v = w[bl] || 0;
        if (v > globalMax) globalMax = v;
      }
    }
    if (globalMax === 0) globalMax = 1;

    for (const bl of Object.keys(BUNDESLAND_NAME_TO_CODE)) {
      const inc = week[bl] || 0;
      colors[bl] = { intensity: inc / globalMax, incidence: inc };
    }
    return colors;
  }, [waveData, waveWeekIdx]);

  const renderBacktest = () => {
    const cardStyle: React.CSSProperties = {
      background: 'var(--bg-card)', borderRadius: 12, border: '1px solid var(--border-color)',
      padding: 24, marginBottom: 20,
    };
    const metricBoxStyle: React.CSSProperties = {
      background: 'var(--bg-secondary)', borderRadius: 8, padding: '12px 16px',
      textAlign: 'center' as const, minWidth: 120,
    };
    const btnPrimary: React.CSSProperties = {
      padding: '8px 20px', borderRadius: 8, border: 'none',
      background: 'var(--accent-violet)', color: '#fff',
      fontSize: 13, fontWeight: 600, cursor: 'pointer',
    };
    const btnSecondary: React.CSSProperties = {
      ...btnPrimary,
      background: 'var(--bg-secondary)', color: 'var(--text-primary)',
      border: '1px solid var(--border-color)',
    };

    return (
      <>
        {/* ── Header ── */}
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
            Backtest & Validierung
          </h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
            Prüfe die Vorhersagequalität des ViralFlux-Modells gegen historische Daten.
          </p>
        </div>

        {/* ── Market Check ── */}
        <div style={cardStyle}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>
            Markt-Check
          </h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
            <select
              value={btTargetSource}
              onChange={(e) => setBtTargetSource(e.target.value)}
              style={{
                padding: '8px 12px', borderRadius: 8, fontSize: 13,
                border: '1px solid var(--border-color)', background: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
              }}
            >
              {TARGET_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <select
              value={btBundesland}
              onChange={(e) => setBtBundesland(e.target.value)}
              style={{
                padding: '8px 12px', borderRadius: 8, fontSize: 13,
                border: '1px solid var(--border-color)', background: 'var(--bg-secondary)',
                color: 'var(--text-primary)', minWidth: 140,
              }}
            >
              {BUNDESLAENDER_OPTIONS.map((bl) => (
                <option key={bl || '__bw'} value={bl}>{bl || 'Bundesweit'}</option>
              ))}
            </select>
            <div
              style={{
                display: 'flex',
                gap: 4,
                padding: 2,
                borderRadius: 8,
                border: '1px solid var(--border-color)',
                background: 'var(--bg-secondary)',
              }}
            >
              {[7, 14, 21].map((days) => (
                <button
                  key={days}
                  onClick={() => setBtHorizonDays(days as 7 | 14 | 21)}
                  style={{
                    padding: '6px 10px',
                    borderRadius: 6,
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 11,
                    fontWeight: 600,
                    background: btHorizonDays === days ? 'var(--accent-violet)' : 'transparent',
                    color: btHorizonDays === days ? '#fff' : 'var(--text-muted)',
                  }}
                >
                  {days}T
                </button>
              ))}
            </div>
            <button
              onClick={runMarketBacktest}
              disabled={btRunning}
              style={{ ...btnPrimary, opacity: btRunning ? 0.6 : 1 }}
            >
              {btRunning ? 'Läuft\u2026' : 'Markt-Check starten'}
            </button>
          </div>

          {/* Market result */}
          {btResult?.metrics && (
            <div>
              {/* Actionable insight banner */}
              {(() => {
                const r2 = btResult.metrics.r2_score || 0;
                const horizon = btResult.walk_forward?.horizon_days || 14;
                const fcWeeks = btResult.forecast_weeks || 0;
                const decision = btResult.decision_metrics;
                const gate = btResult.quality_gate;
                const hasDecisionLayer = Boolean(decision);

                const allRows = btResult.chart_data || [];
                const fcData = allRows
                  .filter((d: any) => d.is_forecast && typeof d.forecast_qty === 'number');
                const histData = allRows
                  .filter((d: any) => !d.is_forecast && typeof d.real_qty === 'number');

                const forecastNext2 = fcData.slice(0, 2).map((d: any) => Number(d.forecast_qty || 0));
                const actualLast4 = histData.slice(-4).map((d: any) => Number(d.real_qty || 0));
                const meanForecast2 = forecastNext2.length
                  ? forecastNext2.reduce((a, b) => a + b, 0) / forecastNext2.length
                  : 0;
                const meanActual4 = actualLast4.length
                  ? actualLast4.reduce((a, b) => a + b, 0) / actualLast4.length
                  : 0;
                const predGrowth2w = meanActual4 > 0 ? (meanForecast2 - meanActual4) / meanActual4 : 0;
                const baseShiftPct = clamp(8 + 60 * predGrowth2w, 8, 35);
                const p90AbsError = Number(decision?.p90_abs_error ?? btResult.vintage_metrics?.p90_abs_error ?? 0);
                const uncertaintyPenalty = meanActual4 > 0
                  ? clamp(p90AbsError / meanActual4, 0, 0.5)
                  : 0.5;
                let finalShiftPct = Math.round(baseShiftPct * (1 - uncertaintyPenalty) * 10) / 10;
                if (hasDecisionLayer && !gate?.overall_passed) finalShiftPct = Math.min(finalShiftPct, 12);
                const gatePassed = hasDecisionLayer ? Boolean(gate?.overall_passed) : r2 >= 0.3;

                const trendUp = predGrowth2w > 0.1;
                const trendDown = predGrowth2w < -0.1;

                let signal = 'beobachten';
                let signalColor = 'var(--text-muted)';
                let signalBg = 'var(--bg-secondary)';
                let signalIcon = '\u23F3';
                if (gatePassed && trendUp) {
                  signal = 'Jetzt Media aktivieren';
                  signalColor = '#c0392b';
                  signalBg = 'rgba(192,57,43,0.06)';
                  signalIcon = '\u26A0\uFE0F';
                } else if (gatePassed && trendDown) {
                  signal = 'Welle klingt ab';
                  signalColor = '#27ae60';
                  signalBg = 'rgba(39,174,96,0.06)';
                  signalIcon = '\u2705';
                } else if (gatePassed) {
                  signal = 'Stabil — beobachten';
                  signalColor = 'var(--accent-violet)';
                  signalBg = 'rgba(139,92,246,0.06)';
                  signalIcon = '\uD83D\uDD0D';
                }

                return (
                  <div style={{
                    display: 'flex', gap: 16, alignItems: 'stretch', marginBottom: 20, flexWrap: 'wrap',
                  }}>
                    {/* Signal card — big */}
                    <div style={{
                      flex: '1 1 200px', padding: '16px 20px', borderRadius: 12,
                      background: signalBg, border: `1px solid ${signalColor}22`,
                    }}>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                        Handlungsempfehlung
                      </div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: signalColor }}>
                        {signalIcon} {signal}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                        Modellgüte R²={r2.toFixed(2)} — Prognose {horizon}T Vorlauf — {fcWeeks > 0 ? `${fcWeeks} Wochen Forecast` : 'kein Forecast'}.
                        {' '}Empfohlener nationaler Budget-Shift: <strong>+{finalShiftPct.toFixed(1)}%</strong>.
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                        {hasDecisionLayer
                          ? 'Diese Empfehlung basiert auf OOS-TTD + Hit-Rate + Fehlerrisiko.'
                          : 'Legacy-Fallback ohne Decision-Layer: Bewertung basiert auf OOS-Modellgüte.'}
                      </div>
                    </div>

                    {/* Decision KPI strip */}
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                      {[
                        {
                          label: 'TTD median',
                          value: decision?.median_ttd_days != null ? `${decision.median_ttd_days}T` : '-',
                          sub: 'Lead bis Ereignis',
                        },
                        {
                          label: 'Hit-Rate',
                          value: decision?.hit_rate_pct != null ? `${decision.hit_rate_pct.toFixed(0)}%` : '-',
                          sub: 'Treffer / Alerts',
                        },
                        {
                          label: 'False Alarms',
                          value: decision?.false_alarm_rate_pct != null ? `${decision.false_alarm_rate_pct.toFixed(0)}%` : '-',
                          sub: 'Fehlalarme',
                        },
                        {
                          label: 'Readiness',
                          value: decision?.readiness_score_0_100 != null ? `${Math.round(decision.readiness_score_0_100)}` : '-',
                          sub: gate?.overall_passed ? 'GO' : 'WATCH',
                        },
                      ].map((m) => (
                        <div key={m.label} style={{
                          padding: '10px 14px', borderRadius: 10,
                          background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                          textAlign: 'center' as const, minWidth: 90,
                        }}>
                          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>{m.value}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{m.sub}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Top-5 Regions card */}
              {topRegions?.regions?.length > 0 && (
                <div style={{
                  marginBottom: 16, padding: '12px 16px', borderRadius: 10,
                  background: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                    Top-{topRegions.regions.length} Regionen — {topRegions.disease} (KW {topRegions.week?.split('_')[1]})
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {topRegions.regions.map((r: any, i: number) => {
                      const maxInc = topRegions.regions[0]?.incidence || 1;
                      const pct = Math.round((r.incidence / maxInc) * 100);
                      return (
                        <button
                          key={r.bundesland}
                          onClick={() => { setBtBundesland(r.bundesland); }}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '6px 10px', borderRadius: 8, fontSize: 12, cursor: 'pointer',
                            border: btBundesland === r.bundesland ? '2px solid var(--accent-violet)' : '1px solid var(--border-color)',
                            background: btBundesland === r.bundesland ? 'rgba(139,92,246,0.08)' : 'var(--bg-card)',
                            color: 'var(--text-primary)',
                          }}
                        >
                          <span style={{ fontWeight: 700, color: 'var(--text-muted)', fontSize: 10, minWidth: 14 }}>{i + 1}.</span>
                          <span style={{ fontWeight: 500 }}>{r.bundesland}</span>
                          <span style={{
                            display: 'inline-block', width: 32, height: 6, borderRadius: 3,
                            background: `linear-gradient(90deg, var(--accent-violet) ${pct}%, var(--border-color) ${pct}%)`,
                          }} />
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{r.incidence.toFixed(1)}</span>
                        </button>
                      );
                    })}
                    {btBundesland && (
                      <button
                        onClick={() => setBtBundesland('')}
                        style={{
                          padding: '6px 10px', borderRadius: 8, fontSize: 12, cursor: 'pointer',
                          border: '1px solid var(--border-color)', background: 'var(--bg-card)',
                          color: 'var(--text-muted)',
                        }}
                      >
                        ✕ Bundesweit
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Chart with zoom + signal annotations */}
              {(btResult.chart_data?.length ?? 0) > 0 && (() => {
                const planningAvailable = Boolean(btResult.planning_curve?.curve?.length);
                const modes: BacktestChartMode[] = planningAvailable
                  ? ['validation', 'vintage', 'planning']
                  : ['validation', 'vintage'];
                const activeMode = modes.includes(btChartMode) ? btChartMode : 'validation';
                const chartRows = buildBacktestChartData(btResult, activeMode);
                const firstForecast = btResult.chart_data?.find((row) => row.is_forecast);
                const dividerDate = activeMode === 'vintage'
                  ? (firstForecast?.issue_date || firstForecast?.date)
                  : firstForecast?.date;
                const planningConnectors = activeMode === 'planning'
                  ? buildPlanningConnectors(chartRows)
                  : [];
                const vintageConnectors = activeMode === 'vintage'
                  ? buildVintageConnectors(chartRows)
                  : [];
                const chartLineType: 'linear' | 'monotone' = activeMode === 'vintage' ? 'linear' : 'monotone';

                return (
                  <div style={{ width: '100%', marginBottom: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <div style={{ display: 'flex', gap: 4, background: 'var(--bg-secondary)', borderRadius: 8, padding: 2 }}>
                        {modes.map((mode) => (
                          <button
                            key={mode}
                            onClick={() => setBtChartMode(mode)}
                            style={{
                              padding: '5px 12px', borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                              border: 'none',
                              background: activeMode === mode ? 'var(--accent-violet)' : 'transparent',
                              color: activeMode === mode ? '#fff' : 'var(--text-muted)',
                            }}
                          >
                            {mode === 'validation' && 'Validierung'}
                            {mode === 'vintage' && 'Forecast-Vintage'}
                            {mode === 'planning' && 'Planung (Bio-Vorlauf)'}
                          </button>
                        ))}
                      </div>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                        {activeMode === 'validation' && 'Ist vs. Prognose am gleichen Datum'}
                        {activeMode === 'vintage' && 'Strict Shift Overlay (blau links = echter Vorlauf)'}
                        {activeMode === 'planning' && 'Messdatum (X) -> erwartetes Ereignisdatum (Y)'}
                      </span>
                    </div>

                    {btResult.vintage_metrics && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
                        Vintage: Vorlauf median {btResult.vintage_metrics.median_lead_days ?? btResult.walk_forward?.horizon_days ?? btHorizonDays}T ·
                        p90 |Fehler| {btResult.vintage_metrics.p90_abs_error ?? '-'} ·
                        OOS Punkte {btResult.vintage_metrics.oos_points ?? btResult.metrics?.data_points ?? '-'} ·
                        Modell {btResult.model_type || 'GradientBoosting/Ridge'}
                      </div>
                    )}
                    {btResult.decision_metrics && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
                        Trigger-Proof: P(Event|Alert) {Number(btResult.decision_metrics.hit_rate_pct ?? 0).toFixed(1)}% ·
                        False Alarm Rate {Number(btResult.decision_metrics.false_alarm_rate_pct ?? 0).toFixed(1)}% ·
                        TTD median {btResult.decision_metrics.median_ttd_days ?? 0}T ·
                        Readiness {Number(btResult.decision_metrics.readiness_score_0_100 ?? 0).toFixed(0)}/100 ({btResult.quality_gate?.overall_passed ? 'GO' : 'WATCH'})
                      </div>
                    )}

                    {(activeMode === 'validation') && (btSignals.peaks.length > 0 || btSignals.surges.length > 0 || btSignals.earlyWarnings.length > 0) && (
                      <div style={{ display: 'flex', gap: 16, marginBottom: 10, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-muted)' }}>
                        {btSignals.earlyWarnings.length > 0 && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ width: 14, height: 10, background: 'rgba(46, 204, 113, 0.15)', border: '1px solid rgba(46, 204, 113, 0.4)', borderRadius: 2, display: 'inline-block' }} />
                            Frühwarnung ({btSignals.earlyWarnings.length})
                          </span>
                        )}
                        {btSignals.peaks.length > 0 && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#c0392b', display: 'inline-block' }} />
                            Peak ({btSignals.peaks.length})
                          </span>
                        )}
                        {btSignals.surges.length > 0 && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ width: 0, height: 0, borderLeft: '5px solid transparent', borderRight: '5px solid transparent', borderBottom: '10px solid #e67e22', display: 'inline-block' }} />
                            Surge ({btSignals.surges.length})
                          </span>
                        )}
                      </div>
                    )}

                    <div style={{ width: '100%', height: 420 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart
                          data={chartRows}
                          margin={{ top: 8, right: 12, left: 0, bottom: 4 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" opacity={0.5} />
                          <XAxis
                            dataKey="date"
                            tickFormatter={(d: string) => {
                              try { return format(parseISO(d), 'dd.MM.yy'); } catch { return d; }
                            }}
                            tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                          />
                          <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                          <RechartsTooltip
                            contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 8, fontSize: 12 }}
                            labelFormatter={(d: string, payload: any[]) => {
                              try {
                                const label = format(parseISO(d), 'dd.MM.yyyy');
                                const point = payload?.[0]?.payload || {};
                                if (activeMode === 'planning') {
                                  const issue = point.issue_date || point.based_on || d;
                                  const target = point.target_date || d;
                                  return `Messdatum: ${format(parseISO(issue), 'dd.MM.yyyy')} · erwartetes Ereignis: ${format(parseISO(target), 'dd.MM.yyyy')}`;
                                }
                                if (activeMode === 'validation') {
                                  const target = point.target_date || d;
                                  if (point.is_forecast && point.issue_date && target) {
                                    return `Prognose erstellt am: ${format(parseISO(point.issue_date), 'dd.MM.yyyy')} · für: ${format(parseISO(target), 'dd.MM.yyyy')}`;
                                  }
                                  if (target && point.issue_date) {
                                    return `Ist-Datum: ${format(parseISO(target), 'dd.MM.yyyy')} · Prognose hierfür erstellt am: ${format(parseISO(point.issue_date), 'dd.MM.yyyy')}`;
                                  }
                                  return `Ist-Datum: ${format(parseISO(target || d), 'dd.MM.yyyy')}`;
                                }
                                if (activeMode === 'vintage') {
                                  const issue = point.issue_date || point.issue_date_hint;
                                  const target = point.target_date || d;
                                  const leadDays = typeof point.lead_days === 'number' ? point.lead_days : null;
                                  const hasPred = typeof point.predicted_qty === 'number' || typeof point.forecast_qty === 'number';
                                  if (hasPred && issue && target) {
                                    const leadText = leadDays != null ? ` (Vorlauf ${leadDays} Tage)` : '';
                                    return `Erstellt am ${format(parseISO(issue), 'dd.MM.yyyy')} -> für ${format(parseISO(target), 'dd.MM.yyyy')}${leadText}`;
                                  }
                                  if (typeof point.real_qty === 'number' && target) {
                                    return `Ist am ${format(parseISO(target), 'dd.MM.yyyy')}`;
                                  }
                                }
                                return label;
                              } catch { return d; }
                            }}
                            formatter={(value: any, name: string) => {
                              if (name === 'ci_95_base' || name === 'ci_95_range' || name === 'ci_80_base' || name === 'ci_80_range') return [null, null];
                              return [typeof value === 'number' ? value.toFixed(2) : value, name];
                            }}
                          />
                          <Legend
                            wrapperStyle={{ fontSize: 12, paddingTop: 4 }}
                            payload={
                              activeMode === 'planning'
                                ? [
                                  { value: 'Tatsächliche Inzidenz (target_date)', type: 'line', color: '#c0392b' },
                                  { value: `Abwasser-Prognose (issue_date, Bio-Vorlauf, +${btResult.planning_curve?.lead_days || 7}T)`, type: 'line', color: 'var(--accent-violet)' },
                                  { value: 'Zukunft (issue_date)', type: 'line', color: 'var(--accent-violet)' },
                                ]
                                : activeMode === 'vintage'
                                  ? [
                                    { value: 'Tatsächliche Inzidenz (target_date)', type: 'line', color: '#c0392b' },
                                    { value: `ML-Prognose (strict shift, issue_date, ${btResult.walk_forward?.horizon_days || btHorizonDays}T)`, type: 'line', color: 'var(--accent-violet)' },
                                    { value: 'Zukunft (strict shift)', type: 'line', color: 'var(--accent-violet)' },
                                  ]
                                  : [
                                    { value: 'Tatsächliche Inzidenz (target_date)', type: 'line', color: '#c0392b' },
                                    { value: `ML-Prognose (target_date, ${btResult.walk_forward?.horizon_days || btHorizonDays}T)`, type: 'line', color: 'var(--accent-violet)' },
                                    { value: 'Zukunft (issue_date→target_date)', type: 'line', color: 'var(--accent-violet)' },
                                    { value: '80% KI', type: 'rect', color: 'rgba(139,92,246,0.25)' },
                                    { value: '95% KI', type: 'rect', color: 'rgba(139,92,246,0.1)' },
                                  ]
                            }
                          />

                          {activeMode === 'validation' && (
                            <>
                              <Area type="monotone" dataKey="ci_95_base" stackId="ci95" fill="transparent" stroke="none" activeDot={false} legendType="none" />
                              <Area type="monotone" dataKey="ci_95_range" stackId="ci95" fill="rgba(139,92,246,0.1)" stroke="none" activeDot={false} legendType="none" />
                              <Area type="monotone" dataKey="ci_80_base" stackId="ci80" fill="transparent" stroke="none" activeDot={false} legendType="none" />
                              <Area type="monotone" dataKey="ci_80_range" stackId="ci80" fill="rgba(139,92,246,0.25)" stroke="none" activeDot={false} legendType="none" />
                            </>
                          )}

                          {(activeMode === 'validation') && btSignals.earlyWarnings.map((ew, i) => (
                            <ReferenceArea
                              key={`ew-${i}`}
                              x1={btResult.chart_data?.[ew.start]?.date}
                              x2={btResult.chart_data?.[ew.end]?.date}
                              fill="#2ecc71"
                              fillOpacity={0.1}
                              stroke="#2ecc71"
                              strokeOpacity={0.3}
                              strokeDasharray="3 3"
                            />
                          ))}

                          {(activeMode === 'validation') && btSignals.peaks.map((idx) => (
                            <ReferenceLine
                              key={`pk-${idx}`}
                              x={btResult.chart_data?.[idx]?.date}
                              stroke="#c0392b"
                              strokeWidth={1.5}
                              strokeDasharray="4 2"
                              label={{ value: 'Peak', position: 'top', fontSize: 9, fill: '#c0392b', fontWeight: 600 }}
                            />
                          ))}

                          {(activeMode === 'validation') && btSignals.surges.map((idx) => (
                            <ReferenceLine
                              key={`sg-${idx}`}
                              x={btResult.chart_data?.[idx]?.date}
                              stroke="#e67e22"
                              strokeWidth={1}
                              strokeDasharray="2 3"
                              label={{ value: '\u25B2', position: 'top', fontSize: 10, fill: '#e67e22' }}
                            />
                          ))}

                          {activeMode === 'vintage' && vintageConnectors.map((seg, idx) => (
                            <ReferenceLine
                              key={`vintage-seg-${seg.plot_date}-${seg.target_date}-${idx}`}
                              segment={[
                                { x: seg.plot_date, y: seg.vintage_qty },
                                { x: seg.target_date, y: seg.vintage_qty },
                              ]}
                              stroke="rgba(139,92,246,0.28)"
                              strokeWidth={1}
                              strokeDasharray="3 3"
                            />
                          ))}

                          {activeMode === 'planning' && planningConnectors.map((seg, idx) => (
                            <ReferenceLine
                              key={`planning-seg-${seg.issue_date}-${seg.target_date}-${idx}`}
                              segment={[
                                { x: seg.issue_date, y: seg.planning_qty },
                                { x: seg.target_date, y: seg.planning_qty },
                              ]}
                              stroke="rgba(139,92,246,0.28)"
                              strokeWidth={1}
                              strokeDasharray="3 3"
                            />
                          ))}

                          {dividerDate && (
                            <ReferenceLine
                              x={dividerDate}
                              stroke="var(--text-muted)"
                              strokeWidth={1}
                              strokeDasharray="6 3"
                              label={{ value: 'Forecast', position: 'insideTopRight', fontSize: 10, fill: 'var(--text-muted)', fontWeight: 600 }}
                            />
                          )}

                          <Line type={chartLineType} dataKey="real_qty" name="Tatsächliche Inzidenz (target_date)" stroke="#c0392b" strokeWidth={2} dot={false} connectNulls={false} />
                          <Line
                            type={chartLineType}
                            dataKey="predicted_qty"
                            name={activeMode === 'planning'
                              ? 'Abwasser-Prognose (issue_date, Bio-Vorlauf)'
                              : activeMode === 'vintage'
                                ? `ML-Prognose (strict shift, issue_date, ${btResult.walk_forward?.horizon_days || btHorizonDays}T)`
                                : `ML-Prognose (target_date, ${btResult.walk_forward?.horizon_days || btHorizonDays}T)`}
                            stroke="var(--accent-violet)"
                            strokeWidth={2}
                            dot={false}
                            connectNulls={false}
                          />
                          <Line type={chartLineType} dataKey="forecast_qty" name={activeMode === 'planning' ? 'Zukunft (issue_date)' : activeMode === 'vintage' ? 'Zukunft (strict shift)' : 'Zukunft'} stroke="var(--accent-violet)" strokeWidth={2} dot={false} strokeDasharray="8 4" connectNulls={false} />

                          <Brush
                            dataKey="date"
                            height={28}
                            stroke="var(--accent-violet)"
                            fill="var(--bg-card)"
                            tickFormatter={(d: string) => {
                              try { return format(parseISO(d), 'MM/yy'); } catch { return ''; }
                            }}
                            travellerWidth={8}
                          />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                    <div style={{
                      marginTop: 8, padding: '8px 12px', borderRadius: 8,
                      background: 'rgba(139,92,246,0.04)', border: '1px solid rgba(139,92,246,0.12)',
                      fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5,
                    }}>
                      {activeMode === 'validation' && (
                        <>
                          <strong>Validierung:</strong> Beide Linien am gleichen Datum — je näher violett an rot, desto besser die {(btResult.walk_forward?.horizon_days || btHorizonDays)}-Tage-Prognose.
                          {' '}Ist bleibt am Zielzeitpunkt; der Erstellzeitpunkt wird nur sekundär im Tooltip angezeigt.
                        </>
                      )}
                      {activeMode === 'vintage' && (
                        <>
                          <strong>Forecast-Vintage:</strong> Blau ist strikt um den echten Vorlauf nach links geplottet (strict shift), Rot bleibt am Ereignisdatum.
                          {' '}Connectoren zeigen den Prognosezeitpunkt X → Ereigniszeitpunkt Y.
                          {' '}Medianer Vorlauf: <strong>{btResult.vintage_metrics?.median_lead_days ?? btResult.walk_forward?.horizon_days ?? btHorizonDays} Tage</strong>.
                          {btResult.decision_metrics && (
                            <>
                              {' '}Wenn Trigger feuert, trat in <strong>{Number(btResult.decision_metrics.hit_rate_pct ?? 0).toFixed(1)}%</strong> der OOS-Fälle
                              {' '}innerhalb von <strong>{btResult.vintage_metrics?.configured_horizon_days ?? btResult.walk_forward?.horizon_days ?? btHorizonDays}T</strong> ein Event ein;
                              {' '}Fehlalarme: <strong>{Number(btResult.decision_metrics.false_alarm_rate_pct ?? 0).toFixed(1)}%</strong>
                              {' '}({btResult.quality_gate?.overall_passed ? 'GO' : 'WATCH'}).
                            </>
                          )}
                        </>
                      )}
                      {activeMode === 'planning' && (
                        <>
                          <strong>Planung (Bio-Vorlauf):</strong> Blau = <strong>Messdatum</strong> (links), Rot = <strong>Ereignisdatum</strong> (rechts).
                          {' '}Die Connector-Linien zeigen explizit X→Y (Messung → erwartetes Ereignis) bei
                          {' '}<strong>{btResult.planning_curve?.lead_days || 7} Tagen</strong> empirischem Vorlauf
                          {' '}(Cross-Korrelation r={btResult.planning_curve?.correlation || '?'}).
                        </>
                      )}
                      {btResult.forecast_weeks && btResult.forecast_weeks > 0 && (
                        <> Die gestrichelte Linie zeigt den <strong>{btResult.forecast_weeks}-Wochen-Forecast</strong>.</>
                      )}
                    </div>
                  </div>
                );
              })()}

              {btResult.proof_text && (
                <details style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
                  <summary style={{ cursor: 'pointer', userSelect: 'none' as const }}>Technische Details</summary>
                  <p style={{ marginTop: 6, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                    {btResult.proof_text}
                  </p>
                </details>
              )}
            </div>
          )}
        </div>

        {/* ── Customer Check ── */}
        <div style={cardStyle}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>
            Realitäts-Check (Kundendaten)
          </h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
            <input
              ref={btFileRef}
              type="file"
              accept=".csv,.xlsx"
              style={{ fontSize: 13, color: 'var(--text-primary)' }}
            />
            <div
              style={{
                display: 'flex',
                gap: 4,
                padding: 2,
                borderRadius: 8,
                border: '1px solid var(--border-color)',
                background: 'var(--bg-secondary)',
              }}
            >
              {[7, 14, 21].map((days) => (
                <button
                  key={`customer-${days}`}
                  onClick={() => setBtHorizonDays(days as 7 | 14 | 21)}
                  style={{
                    padding: '6px 10px',
                    borderRadius: 6,
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 11,
                    fontWeight: 600,
                    background: btHorizonDays === days ? 'var(--accent-violet)' : 'transparent',
                    color: btHorizonDays === days ? '#fff' : 'var(--text-muted)',
                  }}
                >
                  {days}T
                </button>
              ))}
            </div>
            <button
              onClick={runCustomerBacktest}
              disabled={btCustomerRunning}
              style={{ ...btnSecondary, opacity: btCustomerRunning ? 0.6 : 1 }}
            >
              {btCustomerRunning ? 'Läuft\u2026' : 'Realitäts-Check (CSV)'}
            </button>
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>
            Pflichtspalten: <code>datum</code>, <code>menge</code> — optional: <code>region</code>
          </p>

          {btCustomerResult?.metrics && (
            <div style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
                {[
                  { label: 'R²', value: btCustomerResult.metrics.r2_score?.toFixed(3) },
                  { label: 'Korrelation', value: `${btCustomerResult.metrics.correlation_pct?.toFixed(1)}%` },
                  { label: 'MAE', value: btCustomerResult.metrics.mae?.toFixed(1) },
                ].map((m) => (
                  <div key={m.label} style={metricBoxStyle}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>
                      {m.label}
                    </div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {m.value}
                    </div>
                  </div>
                ))}
              </div>

              {btCustomerResult.chart_data?.length ? (() => {
                const planningAvailable = Boolean(btCustomerResult.planning_curve?.curve?.length);
                const modes: BacktestChartMode[] = planningAvailable
                  ? ['validation', 'vintage', 'planning']
                  : ['validation', 'vintage'];
                const activeMode = modes.includes(btCustomerChartMode) ? btCustomerChartMode : 'validation';
                const chartRows = buildBacktestChartData(btCustomerResult, activeMode);
                const firstForecast = btCustomerResult.chart_data?.find((row) => row.is_forecast);
                const dividerDate = activeMode === 'vintage'
                  ? (firstForecast?.issue_date || firstForecast?.date)
                  : firstForecast?.date;
                const planningConnectors = activeMode === 'planning'
                  ? buildPlanningConnectors(chartRows)
                  : [];
                const vintageConnectors = activeMode === 'vintage'
                  ? buildVintageConnectors(chartRows)
                  : [];
                const chartLineType: 'linear' | 'monotone' = activeMode === 'vintage' ? 'linear' : 'monotone';

                return (
                  <div style={{ width: '100%', marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <div style={{ display: 'flex', gap: 4, background: 'var(--bg-secondary)', borderRadius: 8, padding: 2 }}>
                        {modes.map((mode) => (
                          <button
                            key={`cust-${mode}`}
                            onClick={() => setBtCustomerChartMode(mode)}
                            style={{
                              padding: '5px 12px', borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                              border: 'none',
                              background: activeMode === mode ? 'var(--accent-violet)' : 'transparent',
                              color: activeMode === mode ? '#fff' : 'var(--text-muted)',
                            }}
                          >
                            {mode === 'validation' && 'Validierung'}
                            {mode === 'vintage' && 'Forecast-Vintage'}
                            {mode === 'planning' && 'Planung (Bio-Vorlauf)'}
                          </button>
                        ))}
                      </div>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                        {activeMode === 'validation' && 'Ist vs. Prognose am gleichen Datum'}
                        {activeMode === 'vintage' && 'Strict Shift Overlay (blau links = echter Vorlauf)'}
                        {activeMode === 'planning' && 'Messdatum (X) -> erwartetes Ereignisdatum (Y)'}
                      </span>
                    </div>

                    <div style={{ width: '100%', height: 320 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={chartRows} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" opacity={0.5} />
                          <XAxis
                            dataKey="date"
                            tickFormatter={(d: string) => {
                              try { return format(parseISO(d), 'dd.MM.yy'); } catch { return d; }
                            }}
                            tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                          />
                          <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                          <RechartsTooltip
                            contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 8, fontSize: 12 }}
                            labelFormatter={(d: string, payload: any[]) => {
                              try {
                                const label = format(parseISO(d), 'dd.MM.yyyy');
                                const point = payload?.[0]?.payload || {};
                                if (activeMode === 'planning') {
                                  const issue = point.issue_date || point.based_on || d;
                                  const target = point.target_date || d;
                                  return `Messdatum: ${format(parseISO(issue), 'dd.MM.yyyy')} · erwartetes Ereignis: ${format(parseISO(target), 'dd.MM.yyyy')}`;
                                }
                                if (activeMode === 'validation') {
                                  const target = point.target_date || d;
                                  if (point.is_forecast && point.issue_date && target) {
                                    return `Prognose erstellt am: ${format(parseISO(point.issue_date), 'dd.MM.yyyy')} · für: ${format(parseISO(target), 'dd.MM.yyyy')}`;
                                  }
                                  if (target && point.issue_date) {
                                    return `Ist-Datum: ${format(parseISO(target), 'dd.MM.yyyy')} · Prognose hierfür erstellt am: ${format(parseISO(point.issue_date), 'dd.MM.yyyy')}`;
                                  }
                                  return `Ist-Datum: ${format(parseISO(target || d), 'dd.MM.yyyy')}`;
                                }
                                if (activeMode === 'vintage') {
                                  const issue = point.issue_date || point.issue_date_hint;
                                  const target = point.target_date || d;
                                  const leadDays = typeof point.lead_days === 'number' ? point.lead_days : null;
                                  const hasPred = typeof point.predicted_qty === 'number' || typeof point.forecast_qty === 'number';
                                  if (hasPred && issue && target) {
                                    const leadText = leadDays != null ? ` (Vorlauf ${leadDays} Tage)` : '';
                                    return `Erstellt am ${format(parseISO(issue), 'dd.MM.yyyy')} -> für ${format(parseISO(target), 'dd.MM.yyyy')}${leadText}`;
                                  }
                                  if (typeof point.real_qty === 'number' && target) {
                                    return `Ist am ${format(parseISO(target), 'dd.MM.yyyy')}`;
                                  }
                                }
                                return label;
                              } catch { return d; }
                            }}
                            formatter={(value: any, name: string) => {
                              if (name === 'ci_95_base' || name === 'ci_95_range' || name === 'ci_80_base' || name === 'ci_80_range') return [null, null];
                              return [typeof value === 'number' ? value.toFixed(2) : value, name];
                            }}
                          />
                          <Legend
                            wrapperStyle={{ fontSize: 12, paddingTop: 4 }}
                            payload={
                              activeMode === 'planning'
                                ? [
                                  { value: 'Tatsächliche Menge (target_date)', type: 'line', color: '#c0392b' },
                                  { value: `Abwasser-Prognose (issue_date, Bio-Vorlauf, +${btCustomerResult.planning_curve?.lead_days || 7}T)`, type: 'line', color: 'var(--accent-violet)' },
                                  { value: 'Zukunft (issue_date)', type: 'line', color: 'var(--accent-violet)' },
                                ]
                                : activeMode === 'vintage'
                                  ? [
                                    { value: 'Tatsächliche Menge (target_date)', type: 'line', color: '#c0392b' },
                                    { value: `ML-Prognose (strict shift, issue_date, ${btCustomerResult.walk_forward?.horizon_days || btHorizonDays}T)`, type: 'line', color: 'var(--accent-violet)' },
                                    { value: 'Zukunft (strict shift)', type: 'line', color: 'var(--accent-violet)' },
                                  ]
                                  : [
                                    { value: 'Tatsächliche Menge (target_date)', type: 'line', color: '#c0392b' },
                                    { value: `ML-Prognose (target_date, ${btCustomerResult.walk_forward?.horizon_days || btHorizonDays}T)`, type: 'line', color: 'var(--accent-violet)' },
                                    { value: 'Zukunft (issue_date→target_date)', type: 'line', color: 'var(--accent-violet)' },
                                  ]
                            }
                          />

                          {activeMode === 'validation' && (
                            <>
                              <Area type="monotone" dataKey="ci_95_base" stackId="ci95" fill="transparent" stroke="none" activeDot={false} legendType="none" />
                              <Area type="monotone" dataKey="ci_95_range" stackId="ci95" fill="rgba(139,92,246,0.1)" stroke="none" activeDot={false} legendType="none" />
                              <Area type="monotone" dataKey="ci_80_base" stackId="ci80" fill="transparent" stroke="none" activeDot={false} legendType="none" />
                              <Area type="monotone" dataKey="ci_80_range" stackId="ci80" fill="rgba(139,92,246,0.25)" stroke="none" activeDot={false} legendType="none" />
                            </>
                          )}

                          {activeMode === 'vintage' && vintageConnectors.map((seg, idx) => (
                            <ReferenceLine
                              key={`cust-vintage-seg-${seg.plot_date}-${seg.target_date}-${idx}`}
                              segment={[
                                { x: seg.plot_date, y: seg.vintage_qty },
                                { x: seg.target_date, y: seg.vintage_qty },
                              ]}
                              stroke="rgba(139,92,246,0.28)"
                              strokeWidth={1}
                              strokeDasharray="3 3"
                            />
                          ))}

                          {activeMode === 'planning' && planningConnectors.map((seg, idx) => (
                            <ReferenceLine
                              key={`cust-planning-seg-${seg.issue_date}-${seg.target_date}-${idx}`}
                              segment={[
                                { x: seg.issue_date, y: seg.planning_qty },
                                { x: seg.target_date, y: seg.planning_qty },
                              ]}
                              stroke="rgba(139,92,246,0.28)"
                              strokeWidth={1}
                              strokeDasharray="3 3"
                            />
                          ))}

                          {dividerDate && (
                            <ReferenceLine
                              x={dividerDate}
                              stroke="var(--text-muted)"
                              strokeWidth={1}
                              strokeDasharray="6 3"
                              label={{ value: 'Forecast', position: 'insideTopRight', fontSize: 10, fill: 'var(--text-muted)', fontWeight: 600 }}
                            />
                          )}

                          <Line type={chartLineType} dataKey="real_qty" name="Tatsächliche Menge (target_date)" stroke="#c0392b" strokeWidth={2} dot={false} connectNulls={false} />
                          <Line
                            type={chartLineType}
                            dataKey="predicted_qty"
                            name={activeMode === 'planning'
                              ? 'Abwasser-Prognose (issue_date, Bio-Vorlauf)'
                              : activeMode === 'vintage'
                                ? `ML-Prognose (strict shift, issue_date, ${btCustomerResult.walk_forward?.horizon_days || btHorizonDays}T)`
                                : `ML-Prognose (target_date, ${btCustomerResult.walk_forward?.horizon_days || btHorizonDays}T)`}
                            stroke="var(--accent-violet)"
                            strokeWidth={2}
                            dot={false}
                            connectNulls={false}
                          />
                          <Line type={chartLineType} dataKey="forecast_qty" name={activeMode === 'planning' ? 'Zukunft (issue_date)' : activeMode === 'vintage' ? 'Zukunft (strict shift)' : 'Zukunft (issue_date→target_date)'} stroke="var(--accent-violet)" strokeWidth={2} dot={false} strokeDasharray="8 4" connectNulls={false} />

                          <Brush
                            dataKey="date"
                            height={28}
                            stroke="var(--accent-violet)"
                            fill="var(--bg-card)"
                            tickFormatter={(d: string) => {
                              try { return format(parseISO(d), 'MM/yy'); } catch { return ''; }
                            }}
                            travellerWidth={8}
                          />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                    <div style={{
                      marginTop: 8, padding: '8px 12px', borderRadius: 8,
                      background: 'rgba(139,92,246,0.04)', border: '1px solid rgba(139,92,246,0.12)',
                      fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5,
                    }}>
                      {activeMode === 'validation' && (
                        <>
                          <strong>Validierung:</strong> Klassische OOS-Güte am Zielzeitpunkt.
                        </>
                      )}
                      {activeMode === 'vintage' && (
                        <>
                          <strong>Forecast-Vintage:</strong> Blau ist strikt um den echten Vorlauf nach links geplottet (strict shift), Rot bleibt am Ereignisdatum.
                          {' '}Connectoren zeigen den Prognosezeitpunkt X → Ereigniszeitpunkt Y.
                          {btCustomerResult.decision_metrics && (
                            <>
                              {' '}Wenn Trigger feuert, trat in <strong>{Number(btCustomerResult.decision_metrics.hit_rate_pct ?? 0).toFixed(1)}%</strong> der OOS-Fälle
                              {' '}innerhalb von <strong>{btCustomerResult.vintage_metrics?.configured_horizon_days ?? btCustomerResult.walk_forward?.horizon_days ?? btHorizonDays}T</strong> ein Event ein;
                              {' '}Fehlalarme: <strong>{Number(btCustomerResult.decision_metrics.false_alarm_rate_pct ?? 0).toFixed(1)}%</strong>
                              {' '}({btCustomerResult.quality_gate?.overall_passed ? 'GO' : 'WATCH'}).
                            </>
                          )}
                        </>
                      )}
                      {activeMode === 'planning' && (
                        <>
                          <strong>Planung (Bio-Vorlauf):</strong> Blau = <strong>Messdatum</strong> (links), Rot = <strong>Ereignisdatum</strong> (rechts).
                          {' '}Connector-Linien zeigen X→Y (Messung → erwartetes Ereignis) bei
                          {' '}<strong>{btCustomerResult.planning_curve?.lead_days || 7} Tagen</strong> empirischem Vorlauf.
                        </>
                      )}
                      {btCustomerResult.vintage_metrics && (
                        <> OOS {btCustomerResult.vintage_metrics.oos_points ?? btCustomerResult.metrics?.data_points ?? '-'} Punkte ·
                          medianer Vorlauf {btCustomerResult.vintage_metrics.median_lead_days ?? btCustomerResult.walk_forward?.horizon_days ?? btHorizonDays}T ·
                          p90 |Fehler| {btCustomerResult.vintage_metrics.p90_abs_error ?? '-'}.</>
                      )}
                      {btCustomerResult.decision_metrics && (
                        <> Trigger-Proof: P(Event|Alert) {Number(btCustomerResult.decision_metrics.hit_rate_pct ?? 0).toFixed(1)}% ·
                          False Alarm Rate {Number(btCustomerResult.decision_metrics.false_alarm_rate_pct ?? 0).toFixed(1)}% ·
                          TTD median {btCustomerResult.decision_metrics.median_ttd_days ?? 0}T ·
                          Readiness {Number(btCustomerResult.decision_metrics.readiness_score_0_100 ?? 0).toFixed(0)}/100 ({btCustomerResult.quality_gate?.overall_passed ? 'GO' : 'WATCH'}).</>
                      )}
                    </div>
                  </div>
                );
              })() : null}

              {btCustomerResult.proof_text && (
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
                  {btCustomerResult.proof_text}
                </p>
              )}
            </div>
          )}
        </div>

        {/* ── Wellen-Radar ── */}
        <div style={cardStyle}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>
            Wellen-Radar — Wo beginnt die Welle?
          </h2>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
            <select
              value={waveDisease}
              onChange={(e) => setWaveDisease(e.target.value)}
              style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13 }}
            >
              {[
                { value: 'influenza', label: 'Influenza' },
                { value: 'mycoplasma', label: 'Mycoplasma' },
                { value: 'keuchhusten', label: 'Keuchhusten' },
                { value: 'pneumokokken', label: 'Pneumokokken' },
                { value: 'parainfluenza', label: 'Parainfluenza' },
                { value: 'rsv', label: 'RSV' },
                { value: 'covid', label: 'COVID-19' },
                { value: 'norovirus', label: 'Norovirus' },
              ].map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Saison (z.B. 2024/2025)"
              value={waveSeason}
              onChange={(e) => setWaveSeason(e.target.value)}
              style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13, width: 160 }}
            />
            <button
              onClick={fetchWaveRadar}
              disabled={waveLoading}
              style={{ ...btnPrimary, opacity: waveLoading ? 0.6 : 1 }}
            >
              {waveLoading ? 'Lädt\u2026' : 'Wellen-Radar laden'}
            </button>
          </div>

          {waveData && (
            <div>
              {/* Summary */}
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
                {[
                  { label: 'Saison', value: waveData.season },
                  { label: 'Erster Ausbruch', value: waveData.summary?.first_onset?.bundesland ? `${waveData.summary.first_onset.bundesland} (${waveData.summary.first_onset.date})` : '–' },
                  { label: 'Ausbreitung', value: `${waveData.summary?.spread_days ?? '?'} Tage` },
                  { label: 'Betroffen', value: `${waveData.summary?.regions_affected ?? '?'}/${waveData.summary?.regions_total ?? 16} Regionen` },
                ].map((m) => (
                  <div key={m.label} style={metricBoxStyle}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>
                      {m.label}
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {m.value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Map + Timeline */}
              {waveData.heatmap?.length > 0 && (
                <div>
                  {/* Playback controls */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                    <button
                      onClick={() => { setWaveWeekIdx(0); setWaveAnimating(true); }}
                      style={{ ...btnSecondary, fontSize: 12, padding: '4px 12px' }}
                    >
                      Abspielen
                    </button>
                    <button
                      onClick={() => setWaveAnimating(false)}
                      style={{ ...btnSecondary, fontSize: 12, padding: '4px 12px', opacity: waveAnimating ? 1 : 0.5 }}
                    >
                      Stopp
                    </button>
                    <input
                      type="range"
                      min={0}
                      max={waveData.heatmap.length - 1}
                      value={waveWeekIdx}
                      onChange={(e) => { setWaveAnimating(false); setWaveWeekIdx(Number(e.target.value)); }}
                      style={{ flex: 1 }}
                    />
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', minWidth: 80 }}>
                      {waveData.heatmap[waveWeekIdx]?.week_label?.replace('_', '-KW') || ''}
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                    {/* Map */}
                    <div style={{ position: 'relative', width: 420, height: 460, flexShrink: 0 }}>
                      <svg viewBox="0 0 420 460" style={{ width: '100%', height: '100%' }}>
                        {mapShapes.map((shape) => {
                          const blName = shape.name;
                          const data = waveMapColors[blName];
                          const intensity = data?.intensity || 0;
                          // Color: transparent → yellow → orange → red
                          const r = Math.round(180 + 75 * Math.min(intensity * 2, 1));
                          const g = Math.round(220 * Math.max(0, 1 - intensity * 1.5));
                          const b = Math.round(60 * Math.max(0, 1 - intensity * 2));
                          const fill = intensity > 0.01
                            ? `rgb(${r}, ${g}, ${b})`
                            : 'var(--bg-secondary)';

                          // Check if this region has wave onset at or before current week
                          const regionInfo = waveData.regions?.find((reg: any) => reg.bundesland === blName);
                          const hasOnset = regionInfo?.wave_week && waveData.heatmap.findIndex((w: any) => w.week_label === regionInfo.wave_week) <= waveWeekIdx;

                          return (
                            <g key={shape.code || blName}>
                              <path
                                d={shape.d}
                                fill={fill}
                                stroke="var(--border-color)"
                                strokeWidth={hasOnset ? 2 : 0.8}
                                style={{ transition: 'fill 0.3s ease, stroke-width 0.3s ease' }}
                              />
                              {hasOnset && (
                                <circle
                                  cx={shape.cx}
                                  cy={shape.cy}
                                  r={4 + intensity * 8}
                                  fill="rgba(192, 57, 43, 0.7)"
                                  stroke="white"
                                  strokeWidth={1.5}
                                  style={{ transition: 'r 0.3s ease' }}
                                />
                              )}
                              {intensity > 0.15 && (
                                <text
                                  x={shape.cx}
                                  y={shape.cy + (hasOnset ? 16 : 4)}
                                  textAnchor="middle"
                                  fontSize={9}
                                  fontWeight={600}
                                  fill="var(--text-primary)"
                                  style={{ pointerEvents: 'none' }}
                                >
                                  {data?.incidence?.toFixed(1)}
                                </text>
                              )}
                            </g>
                          );
                        })}
                      </svg>
                    </div>

                    {/* Ranking list */}
                    <div style={{ flex: 1, minWidth: 260 }}>
                      <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
                        Ausbreitungs-Reihenfolge
                      </h3>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {(waveData.regions || []).filter((r: any) => r.wave_rank).map((region: any) => {
                          const isActive = region.wave_week && waveData.heatmap.findIndex((w: any) => w.week_label === region.wave_week) <= waveWeekIdx;
                          return (
                            <div
                              key={region.bundesland}
                              style={{
                                display: 'flex', alignItems: 'center', gap: 10,
                                padding: '6px 10px', borderRadius: 8,
                                background: isActive ? 'rgba(192, 57, 43, 0.08)' : 'var(--bg-secondary)',
                                border: `1px solid ${isActive ? 'rgba(192, 57, 43, 0.3)' : 'var(--border-color)'}`,
                                transition: 'all 0.3s ease',
                                opacity: isActive ? 1 : 0.5,
                              }}
                            >
                              <span style={{
                                width: 22, height: 22, borderRadius: '50%',
                                background: isActive ? '#c0392b' : 'var(--border-color)',
                                color: isActive ? 'white' : 'var(--text-muted)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: 11, fontWeight: 700, flexShrink: 0,
                              }}>
                                {region.wave_rank}
                              </span>
                              <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                                  {region.bundesland}
                                </div>
                                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                                  KW {region.wave_week?.split('_')[1]} — Peak: {region.peak_incidence?.toFixed(1)}/100k
                                </div>
                              </div>
                            </div>
                          );
                        })}
                        {(waveData.regions || []).filter((r: any) => !r.wave_rank).length > 0 && (
                          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                            {(waveData.regions || []).filter((r: any) => !r.wave_rank).length} Regionen ohne Welle in dieser Saison
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Color legend */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, fontSize: 10, color: 'var(--text-muted)' }}>
                    <span>Niedrig</span>
                    <div style={{
                      width: 120, height: 10, borderRadius: 5,
                      background: 'linear-gradient(to right, var(--bg-secondary), #f4d03f, #e67e22, #c0392b)',
                    }} />
                    <span>Hoch</span>
                    <span style={{ marginLeft: 16 }}>Inzidenz pro 100.000 Einwohner</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Ausbruchs-Radar ── */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
              Ausbruchs-Radar — Live-Alerts
            </h2>
            <button
              onClick={fetchAlerts}
              disabled={alertLoading}
              style={{ ...btnSecondary, fontSize: 11, padding: '4px 12px', opacity: alertLoading ? 0.6 : 1 }}
            >
              {alertLoading ? 'Scannt\u2026' : 'Aktualisieren'}
            </button>
          </div>

          {alertData && (
            <div>
              {/* National forecast bar */}
              {alertData.national_forecast && Object.keys(alertData.national_forecast).length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Nationaler Trend (letzte 3 vs. vorherige 3 Wochen)
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {Object.entries(alertData.national_forecast).map(([disease, data]: [string, any]) => {
                      const color = data.direction === 'rising' ? '#c0392b' : data.direction === 'falling' ? '#27ae60' : 'var(--text-muted)';
                      const arrow = data.direction === 'rising' ? '\u2191' : data.direction === 'falling' ? '\u2193' : '\u2192';
                      return (
                        <div key={disease} style={{
                          padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                          background: data.direction === 'rising' ? 'rgba(192,57,43,0.08)' : data.direction === 'falling' ? 'rgba(39,174,96,0.08)' : 'var(--bg-secondary)',
                          color, border: `1px solid ${color}22`,
                        }}>
                          {arrow} {disease} {data.change_pct > 0 ? '+' : ''}{data.change_pct}%
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Map + Alerts side by side */}
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                {/* Alert Map */}
                <div style={{ position: 'relative', width: 380, height: 420, flexShrink: 0 }}>
                  <svg viewBox="0 0 420 460" style={{ width: '100%', height: '100%' }}>
                    {mapShapes.map((shape) => {
                      const blName = shape.name;
                      const region = alertData.region_summary?.[blName];
                      const severity = region?.max_severity || 0;
                      const highCount = region?.high_urgency_count || 0;

                      // Color by severity: gray → yellow → orange → red
                      let fill = 'var(--bg-secondary)';
                      if (severity > 3) fill = 'rgba(192, 57, 43, 0.7)';
                      else if (severity > 2) fill = 'rgba(230, 126, 34, 0.6)';
                      else if (severity > 1) fill = 'rgba(241, 196, 15, 0.5)';
                      else if (severity > 0.3) fill = 'rgba(241, 196, 15, 0.2)';

                      return (
                        <g key={shape.code || blName}>
                          <path
                            d={shape.d}
                            fill={fill}
                            stroke="var(--border-color)"
                            strokeWidth={highCount > 0 ? 2 : 0.8}
                            style={{ transition: 'fill 0.3s ease' }}
                          />
                          {region?.top_disease && severity > 0.5 && (
                            <text
                              x={shape.cx}
                              y={shape.cy}
                              textAnchor="middle"
                              fontSize={8}
                              fontWeight={600}
                              fill="var(--text-primary)"
                              style={{ pointerEvents: 'none' }}
                            >
                              {region.top_disease}
                            </text>
                          )}
                          {highCount > 0 && (
                            <circle
                              cx={shape.cx}
                              cy={shape.cy - 12}
                              r={6}
                              fill="#c0392b"
                              stroke="white"
                              strokeWidth={1.5}
                            />
                          )}
                          {highCount > 0 && (
                            <text
                              x={shape.cx}
                              y={shape.cy - 9}
                              textAnchor="middle"
                              fontSize={8}
                              fontWeight={700}
                              fill="white"
                              style={{ pointerEvents: 'none' }}
                            >
                              {highCount}
                            </text>
                          )}
                        </g>
                      );
                    })}
                  </svg>
                </div>

                {/* Alert list */}
                <div style={{ flex: 1, minWidth: 300, maxHeight: 420, overflowY: 'auto' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
                    {alertData.total_alerts} Signale erkannt — {alertData.high_urgency} dringend — Stand: {alertData.scan_date}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {(alertData.alerts || []).slice(0, 25).map((alert: any, idx: number) => {
                      const urgencyColor = alert.urgency === 'high' ? '#c0392b' : alert.urgency === 'medium' ? '#e67e22' : alert.urgency === 'info' ? '#27ae60' : 'var(--text-muted)';
                      const urgencyBg = alert.urgency === 'high' ? 'rgba(192,57,43,0.06)' : alert.urgency === 'medium' ? 'rgba(230,126,34,0.06)' : 'transparent';
                      const momentumArrow = alert.momentum_pct > 20 ? '\u2191\u2191' : alert.momentum_pct > 0 ? '\u2191' : alert.momentum_pct < -20 ? '\u2193\u2193' : '\u2193';
                      const leadLabel = alert.lead_lag_weeks > 0 ? `+${alert.lead_lag_weeks}W voraus` : alert.lead_lag_weeks < 0 ? `${alert.lead_lag_weeks}W hinterher` : 'synchron';

                      return (
                        <div
                          key={`${alert.bundesland}-${alert.disease}-${idx}`}
                          style={{
                            padding: '8px 12px', borderRadius: 8,
                            background: urgencyBg,
                            border: `1px solid ${urgencyColor}33`,
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 3 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                              {alert.disease} — {alert.bundesland}
                            </div>
                            <span style={{
                              fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                              background: urgencyColor, color: 'white', textTransform: 'uppercase',
                            }}>
                              {alert.urgency}
                            </span>
                          </div>
                          <div style={{ display: 'flex', gap: 12, fontSize: 10, color: 'var(--text-muted)' }}>
                            <span style={{ color: alert.momentum_pct > 0 ? '#c0392b' : '#27ae60' }}>
                              {momentumArrow} {alert.momentum_pct > 0 ? '+' : ''}{alert.momentum_pct}%
                            </span>
                            <span>{leadLabel}</span>
                            <span>National: {alert.national_direction === 'rising' ? '\u2191' : alert.national_direction === 'falling' ? '\u2193' : '\u2192'}</span>
                          </div>
                          <div style={{ fontSize: 11, color: urgencyColor, fontWeight: 600, marginTop: 3 }}>
                            {alert.action}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}

          {!alertData && !alertLoading && (
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              Scannt automatisch alle Krankheiten in allen Bundesländern...
            </p>
          )}
        </div>

        {/* ── Backtest History ── */}
        {btRuns.length > 0 && (
          <div style={cardStyle}>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>
              Backtest-Verlauf
            </h2>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                    {['Zeit', 'Mode', 'Target', 'Virus', 'R²', 'Korrelation'].map((h) => (
                      <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase' as const }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {btRuns.map((run: any, idx: number) => (
                    <tr key={run.id || idx} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>
                        {run.created_at ? format(parseISO(run.created_at), 'dd.MM.yy HH:mm') : '–'}
                      </td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-primary)' }}>
                        {run.mode === 'MARKET_CHECK' ? 'Markt' : 'Kunde'}
                      </td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-primary)' }}>{run.target_label || run.target_source || '–'}</td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-primary)' }}>{run.virus_typ || '–'}</td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-primary)', fontWeight: 600 }}>{run.r2_score?.toFixed(3) ?? '–'}</td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-primary)', fontWeight: 600 }}>{run.correlation_pct ? `${run.correlation_pct.toFixed(1)}%` : '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </>
    );
  };

  /* ─────────────────────────────────────────────────────────────────────────
   *  MAIN RENDER
   * ───────────────────────────────────────────────────────────────────────── */
  return (
    <div className="space-y-6">
      {view === 'lagebild' && renderLagebild()}
      {view === 'empfehlungen' && renderEmpfehlungen()}
      {view === 'backtest' && renderBacktest()}
      {renderSlideOver()}
    </div>
  );
};

export default MediaCockpit;
