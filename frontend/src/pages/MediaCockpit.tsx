import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTheme, useToast } from '../App';
import { geoMercator, geoPath } from 'd3-geo';
import { format, parseISO } from 'date-fns';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  CartesianGrid,
  Legend,
} from 'recharts';
import { de } from 'date-fns/locale';
import {
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
  backtest_summary: { latest_market: any; latest_customer: any; recent_runs: Array<any> };
  data_freshness: Record<string, string | null>;
}

/* ─── Utility helpers ─── */

const intensityColor = (intensity: number) => {
  const a = 0.25 + Math.min(1, Math.max(0, intensity)) * 0.65;
  return `rgba(27, 83, 155, ${a})`;
};

const trendIcon = (trend: string) =>
  trend === 'steigend' ? '\u2197' : trend === 'fallend' ? '\u2198' : '\u2192';

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
  const [btTargetSource, setBtTargetSource] = useState('RKI_ARE');
  const [btRunning, setBtRunning] = useState(false);
  const [btResult, setBtResult] = useState<any>(null);
  const [btCustomerResult, setBtCustomerResult] = useState<any>(null);
  const [btCustomerRunning, setBtCustomerRunning] = useState(false);
  const [btRuns, setBtRuns] = useState<any[]>([]);
  const btFileRef = useRef<HTMLInputElement>(null);

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

    return (
      <div className="space-y-6">
        {/* PeixEpiScore banner */}
        {peixSummary && (
          <div className="flex flex-wrap items-center gap-4 px-4 py-3 rounded-xl bg-indigo-50 border border-indigo-100">
            <span className="text-[10px] text-indigo-400 uppercase tracking-wider font-medium">
              PeixEpiScore
            </span>
            <span className="text-sm font-bold text-indigo-700">
              {peixSummary.national_score ?? '\u2014'}
              <span className="text-xs font-normal text-indigo-400"> / 100</span>
            </span>
            <span className="text-xs text-indigo-500">
              Band: <span className="font-semibold">{peixSummary.national_band ?? '\u2014'}</span>
            </span>
            <span className="text-xs text-indigo-500">
              Impact:{' '}
              <span className="font-semibold">
                {peixSummary.national_impact_probability ?? '\u2014'}%
              </span>
            </span>
          </div>
        )}

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
    { value: 'RKI_ARE', label: 'RKI ARE (Atemwegserkrankungen)' },
    { value: 'SURVSTAT', label: 'SURVSTAT Respiratory' },
    { value: 'MYCOPLASMA', label: 'SURVSTAT Mycoplasma' },
    { value: 'KEUCHHUSTEN', label: 'SURVSTAT Keuchhusten' },
    { value: 'PNEUMOKOKKEN', label: 'SURVSTAT Pneumokokken' },
  ];

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

  const runMarketBacktest = async () => {
    setBtRunning(true);
    setBtResult(null);
    try {
      const qs = new URLSearchParams({
        target_source: btTargetSource,
        virus_typ: virus,
      });
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
    try {
      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      const qs = new URLSearchParams({ virus_typ: virus });
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
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
                {[
                  { label: 'R²', value: btResult.metrics.r2_score?.toFixed(3) },
                  { label: 'Korrelation', value: `${btResult.metrics.correlation_pct?.toFixed(1)}%` },
                  { label: 'sMAPE', value: btResult.metrics.smape?.toFixed(1) },
                  { label: 'Lead/Lag', value: `${btResult.lead_lag?.best_lag_days ?? '?'} Tage` },
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

              {/* Chart */}
              {btResult.chart_data?.length > 0 && (
                <div style={{ width: '100%', height: 300, marginBottom: 16 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={btResult.chart_data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(d: string) => {
                          try { return format(parseISO(d), 'dd.MM.yy'); } catch { return d; }
                        }}
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                      />
                      <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                      <RechartsTooltip
                        contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 8, fontSize: 12 }}
                        labelFormatter={(d: string) => {
                          try { return format(parseISO(d), 'dd.MM.yyyy'); } catch { return d; }
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Line type="monotone" dataKey="real_qty" name="Proxy (Ist)" stroke="#c0392b" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="predicted_qty" name="ViralFlux" stroke="var(--accent-violet)" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="baseline_seasonal" name="Seasonal" stroke="#95a5a6" strokeWidth={1.5} dot={false} strokeDasharray="4 4" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {btResult.proof_text && (
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
                  {btResult.proof_text}
                </p>
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
              {btCustomerResult.proof_text && (
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
                  {btCustomerResult.proof_text}
                </p>
              )}
            </div>
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
