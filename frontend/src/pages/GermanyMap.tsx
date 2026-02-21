import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import { RegionTooltipData } from '../types/media';

// TODO(legacy-map): Legacy-Karte mit vereinfachten Pfaden. MediaCockpit nutzt jetzt die echte GeoJSON-Bundeslandkarte.
const BUNDESLAND_PATHS: Record<string, { d: string; cx: number; cy: number }> = {
  'SH': { d: 'M195,10 L230,5 L250,25 L260,60 L240,80 L215,90 L190,80 L180,55 L185,30Z', cx: 220, cy: 48 },
  'HH': { d: 'M220,90 L240,88 L245,100 L235,108 L218,105Z', cx: 232, cy: 98 },
  'MV': { d: 'M260,20 L340,10 L370,30 L365,55 L340,70 L300,75 L270,65 L255,50Z', cx: 315, cy: 42 },
  'HB': { d: 'M190,105 L210,100 L215,115 L200,120 L188,115Z', cx: 202, cy: 110 },
  'NI': { d: 'M140,80 L190,75 L220,90 L225,115 L250,130 L260,165 L230,190 L200,195 L160,185 L130,160 L110,130 L120,100Z', cx: 185, cy: 140 },
  'BB': { d: 'M310,80 L370,85 L385,110 L380,160 L355,185 L310,190 L290,170 L285,130 L295,100Z', cx: 335, cy: 135 },
  'BE': { d: 'M325,120 L345,118 L348,135 L340,142 L322,138Z', cx: 335, cy: 130 },
  'ST': { d: 'M260,130 L290,125 L310,140 L305,185 L280,200 L255,195 L240,175 L245,150Z', cx: 275, cy: 162 },
  'NW': { d: 'M80,170 L140,160 L170,180 L175,215 L160,250 L130,265 L90,255 L65,230 L60,200Z', cx: 118, cy: 215 },
  'HE': { d: 'M150,220 L190,210 L210,230 L205,275 L190,300 L160,305 L140,285 L135,250Z', cx: 172, cy: 260 },
  'TH': { d: 'M220,200 L280,195 L300,215 L295,250 L270,265 L235,260 L215,240Z', cx: 258, cy: 228 },
  'SN': { d: 'M300,200 L365,195 L380,220 L370,255 L340,270 L305,260 L295,235Z', cx: 338, cy: 230 },
  'RP': { d: 'M60,265 L100,255 L125,275 L130,310 L120,340 L90,355 L60,340 L45,310 L48,280Z', cx: 88, cy: 305 },
  'SL': { d: 'M55,345 L80,338 L90,360 L78,375 L55,370Z', cx: 72, cy: 358 },
  'BW': { d: 'M95,340 L145,310 L185,320 L200,355 L190,400 L160,430 L120,435 L85,415 L70,385 L80,360Z', cx: 140, cy: 380 },
  'BY': { d: 'M185,270 L240,260 L290,275 L320,310 L330,360 L310,410 L270,440 L230,445 L195,430 L175,400 L170,350 L175,310Z', cx: 250, cy: 360 },
};

const VIRUS_COLORS: Record<string, string> = {
  'Influenza A': '#3b82f6',
  'Influenza B': '#4338ca',
  'SARS-CoV-2': '#ef4444',
  'RSV A': '#10b981',
};

interface RegionData {
  name: string;
  avg_viruslast: number;
  avg_normalisiert: number | null;
  n_standorte: number;
  einwohner: number | null;
  intensity: number;
  trend: string;
  change_pct: number;
  tooltip?: RegionTooltipData | null;
}

interface StandortData {
  standort: string;
  bundesland: string;
  latitude: number;
  longitude: number;
  viruslast: number;
  viruslast_normalisiert: number | null;
  vorhersage: number | null;
  einwohner: number | null;
  unter_bg: boolean;
  intensity: number;
  trend: string;
  change_pct: number;
}

interface TransferSuggestion {
  from_region: string;
  from_name: string;
  to_region: string;
  to_name: string;
  reason: string;
  priority: string;
  test_typ: string;
}

// Affine transformation: lat/lon → SVG viewbox (0 0 420 460)
// Calibrated with 3 reference points: Berlin (52.52,13.41)→(335,130), Hamburg (53.55,9.99)→(232,98), Stuttgart area (48.66,9.35)→(140,380)
const latLonToSvg = (lat: number, lon: number): { x: number; y: number } => ({
  x: 14.27 * lat + 34.42 * lon - 876.1,
  y: -56.7 * lat - 7.71 * lon + 3211.3,
});

const standortRadius = (einwohner: number | null): number => {
  if (!einwohner || einwohner <= 0) return 2.5;
  // log-scale: 5K→2, 50K→3, 500K→4.5, 1.5M→5.5
  return Math.min(6, Math.max(2, 1 + Math.log10(einwohner) * 0.8));
};

const fmt = (n: number) => {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return n.toFixed(0);
};

const intensityToColor = (intensity: number, baseColor: string): string => {
  // intensity 0-1 maps to dark-to-bright color
  const alpha = 0.15 + intensity * 0.85;
  // Convert hex to rgb
  const r = parseInt(baseColor.slice(1, 3), 16);
  const g = parseInt(baseColor.slice(3, 5), 16);
  const b = parseInt(baseColor.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
};

const GermanyMap: React.FC = () => {
  const navigate = useNavigate();
  const [selectedVirus, setSelectedVirus] = useState('Influenza A');
  const [regionData, setRegionData] = useState<Record<string, RegionData>>({});
  const [transfers, setTransfers] = useState<TransferSuggestion[]>([]);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const [horizonDays, setHorizonDays] = useState(0);
  const [showTechDetails, setShowTechDetails] = useState(false);
  const [showStandorte, setShowStandorte] = useState(false);
  const [standorteData, setStandorteData] = useState<StandortData[]>([]);
  const [hoveredStandort, setHoveredStandort] = useState<string | null>(null);
  const [standortTooltipPos, setStandortTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [regionTimeseries, setRegionTimeseries] = useState<Array<{ date: string; viruslast: number }>>([]);
  const [hasData, setHasData] = useState(false);
  const [maxViruslast, setMaxViruslast] = useState(0);
  const [dataDate, setDataDate] = useState('');

  const fetchMapData = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/map/regional/${encodeURIComponent(selectedVirus)}`);
      if (!res.ok) return;
      const data = await res.json();
      setRegionData(data.regions || {});
      setHasData(data.has_data);
      setMaxViruslast(data.max_viruslast || 0);
      setDataDate(data.date || '');
    } catch (e) {
      console.error('Map data fetch error:', e);
    }
  }, [selectedVirus]);

  const fetchTransfers = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/map/transfer-suggestions/${encodeURIComponent(selectedVirus)}`);
      if (!res.ok) return;
      const data = await res.json();
      setTransfers(data.suggestions || []);
    } catch (e) {
      console.error('Transfer suggestions error:', e);
    }
  }, [selectedVirus]);

  const fetchRegionTimeseries = useCallback(async (bl: string) => {
    try {
      const res = await fetch(`/api/v1/map/regional-timeseries/${encodeURIComponent(selectedVirus)}/${bl}`);
      if (!res.ok) return;
      const data = await res.json();
      setRegionTimeseries(data.timeseries || []);
    } catch (e) {
      console.error('Region timeseries error:', e);
    }
  }, [selectedVirus]);

  useEffect(() => {
    fetchMapData();
    fetchTransfers();
  }, [fetchMapData, fetchTransfers]);

  useEffect(() => {
    if (!showStandorte) return;
    fetch(`/api/v1/map/standorte/${encodeURIComponent(selectedVirus)}`)
      .then((r) => r.json())
      .then((d) => setStandorteData(d.standorte || []))
      .catch(() => setStandorteData([]));
  }, [showStandorte, selectedVirus]);

  useEffect(() => {
    if (selectedRegion) {
      fetchRegionTimeseries(selectedRegion);
    }
  }, [selectedRegion, fetchRegionTimeseries]);

  const baseColor = VIRUS_COLORS[selectedVirus] || '#3b82f6';
  const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
  const projectedIntensity = (region?: RegionData | null) => {
    if (!region) return 0;
    const base = Number(region.intensity || 0);
    const change = Number(region.change_pct || 0) / 100;
    const factor = 1 + change * (horizonDays / 14) * 0.9;
    return clamp01(base * factor);
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="text-slate-400 hover:text-slate-700 transition border border-slate-200 rounded-lg p-1.5"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-blue-500 to-indigo-600">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-900 tracking-tight" style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}>Deutschlandkarte</h1>
                <p className="text-xs text-slate-500">Radar-Map mit +14 Tage Forecast-Slider (Business-first)</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {Object.entries(VIRUS_COLORS).map(([virus, color]) => (
              <button
                key={virus}
                onClick={() => { setSelectedVirus(virus); setSelectedRegion(null); }}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  selectedVirus === virus
                    ? 'text-white shadow-sm'
                    : 'text-slate-500 bg-transparent border border-slate-200 hover:border-slate-300'
                }`}
                style={selectedVirus === virus ? { background: color, border: `1px solid ${color}` } : undefined}
              >
                {virus}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6">
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

          {/* Map */}
          <div className="xl:col-span-2 card p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900" style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}>
                  Deutschland Radar: {selectedVirus}{' '}
                  <span className="text-slate-500 font-normal">
                    {horizonDays === 0 ? '(Heute)' : `( +${horizonDays} Tage )`}
                  </span>
                </h2>
                <p className="text-xs text-slate-500 mt-1">
                  {dataDate ? `Stand: ${format(new Date(dataDate), 'dd. MMMM yyyy', { locale: de })}` : 'Lade Daten...'}
                  {showTechDetails && maxViruslast > 0 ? ` | Max: ${fmt(maxViruslast)} Genkopien/L` : ''}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowStandorte((s) => !s)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition border ${
                    showStandorte
                      ? 'border-indigo-300 bg-indigo-50 text-indigo-600'
                      : 'border-slate-200 text-slate-500 hover:bg-slate-50 hover:border-slate-300'
                  }`}
                >
                  {showStandorte ? 'Messstellen ausblenden' : 'Messstellen anzeigen'}
                </button>
                <button
                  onClick={() => setShowTechDetails((s) => !s)}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg transition border border-slate-200 text-slate-500 hover:bg-slate-50 hover:border-slate-300"
                >
                  {showTechDetails ? 'Tech Details ausblenden' : 'Tech Details anzeigen'}
                </button>
                <div className="hidden sm:flex items-center gap-2">
                  <span className="text-[11px] text-slate-400">0</span>
                  <input
                    type="range"
                    min={0}
                    max={14}
                    value={horizonDays}
                    onChange={(e) => setHorizonDays(Number(e.target.value))}
                    className="w-40 accent-indigo-500"
                    title="Visualisierte 14-Tage-Entwicklung (heuristisch aus Trend/Change%)."
                  />
                  <span className="text-[11px] text-slate-400">14</span>
                </div>
              </div>
            </div>

            {!hasData ? (
              <div className="flex items-center justify-center py-32 text-center">
                <div>
                  <div className="text-4xl mb-4">🗺</div>
                  <p className="text-slate-500 mb-2">Keine regionalen Daten vorhanden</p>
                  <p className="text-sm text-slate-400 max-w-md">
                    Importiere zuerst die AMELAG Einzelstandort-Daten über
                    <code className="px-1.5 py-0.5 mx-1 rounded text-xs bg-slate-100 text-slate-600 border border-slate-200">
                      POST /api/v1/ingest/amelag
                    </code>
                  </p>
                </div>
              </div>
            ) : (
              <div ref={mapContainerRef} style={{ position: 'relative' }}>
              <svg
                viewBox="0 0 420 460"
                className="w-full max-h-[500px]"
                style={{ filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.08))' }}
              >
                {Object.entries(BUNDESLAND_PATHS).map(([code, path]) => {
                  const region = regionData[code];
                  const intensity = projectedIntensity(region);
                  const isSelected = selectedRegion === code;
                  const fillColor = region ? intensityToColor(intensity, baseColor) : 'rgba(226,232,240,0.5)';
                  const band = !region ? '' : intensity >= 0.7 ? 'Hoch' : intensity >= 0.4 ? 'Mittel' : 'Niedrig';

                  return (
                    <g
                      key={code}
                      className="cursor-pointer"
                      onClick={() => setSelectedRegion(code === selectedRegion ? null : code)}
                      onMouseEnter={(e) => {
                        if (!region) return;
                        setHoveredRegion(code);
                        const rect = mapContainerRef.current?.getBoundingClientRect();
                        if (rect) setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
                      }}
                      onMouseMove={(e) => {
                        if (!region) return;
                        const rect = mapContainerRef.current?.getBoundingClientRect();
                        if (rect) setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
                      }}
                      onMouseLeave={() => setHoveredRegion(null)}
                    >
                      <path
                        d={path.d}
                        fill={fillColor}
                        stroke={isSelected ? '#4338ca' : '#cbd5e1'}
                        strokeWidth={isSelected ? 2.5 : 1}
                        style={{ transition: 'all 0.3s ease' }}
                      />
                      <text
                        x={path.cx}
                        y={path.cy - 6}
                        textAnchor="middle"
                        fill={intensity > 0.5 ? '#fff' : '#334155'}
                        fontSize="9"
                        fontWeight="700"
                      >
                        {code}
                      </text>
                      {region && (
                        <text
                          x={path.cx}
                          y={path.cy + 6}
                          textAnchor="middle"
                          fill={intensity > 0.5 ? '#e2e8f0' : '#64748b'}
                          fontSize="7"
                        >
                          {band}
                        </text>
                      )}
                      {region && (
                        <text
                          x={path.cx}
                          y={path.cy + 15}
                          textAnchor="middle"
                          fill={region.trend === 'steigend' ? '#ef4444' : region.trend === 'fallend' ? '#10b981' : '#64748b'}
                          fontSize="8"
                        >
                          {region.trend === 'steigend' ? '\u2197' : region.trend === 'fallend' ? '\u2198' : '\u2192'}
                        </text>
                      )}
                    </g>
                  );
                })}

                {/* Kläranlagen-Standorte Overlay */}
                {showStandorte && standorteData.map((s) => {
                  const pos = latLonToSvg(s.latitude, s.longitude);
                  if (pos.x < -10 || pos.x > 430 || pos.y < -10 || pos.y > 470) return null;
                  const r = standortRadius(s.einwohner);
                  const isHovered = hoveredStandort === s.standort;
                  const dotColor = intensityToColor(Math.min(1, s.intensity * 1.3), baseColor);

                  return (
                    <circle
                      key={s.standort}
                      cx={pos.x}
                      cy={pos.y}
                      r={isHovered ? r + 2 : r}
                      fill={dotColor}
                      stroke={isHovered ? '#0f172a' : '#ffffff'}
                      strokeWidth={isHovered ? 1.5 : 0.8}
                      style={{
                        transition: 'r 0.15s ease, stroke 0.15s ease',
                        cursor: 'pointer',
                        filter: isHovered ? 'drop-shadow(0 1px 3px rgba(0,0,0,0.3))' : 'none',
                      }}
                      onMouseEnter={(e) => {
                        setHoveredStandort(s.standort);
                        const rect = mapContainerRef.current?.getBoundingClientRect();
                        if (rect) setStandortTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
                      }}
                      onMouseMove={(e) => {
                        const rect = mapContainerRef.current?.getBoundingClientRect();
                        if (rect) setStandortTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
                      }}
                      onMouseLeave={() => setHoveredStandort(null)}
                    />
                  );
                })}
              </svg>

              {/* Hover-Tooltip */}
              {hoveredRegion && regionData[hoveredRegion]?.tooltip && (() => {
                const tip = regionData[hoveredRegion].tooltip!;
                const containerW = mapContainerRef.current?.offsetWidth || 600;
                const containerH = mapContainerRef.current?.offsetHeight || 500;
                const flipX = tooltipPos.x > containerW - 380;
                const flipY = tooltipPos.y > containerH - 200;
                const bandColors: Record<string, { bg: string; border: string; text: string }> = {
                  critical: { bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.3)', text: '#dc2626' },
                  high: { bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.3)', text: '#d97706' },
                  elevated: { bg: 'rgba(250,204,21,0.08)', border: 'rgba(250,204,21,0.3)', text: '#ca8a04' },
                  low: { bg: 'rgba(34,197,94,0.08)', border: 'rgba(34,197,94,0.3)', text: '#16a34a' },
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
                        boxShadow: '0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)',
                        padding: '14px 16px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>{tip.region_name}</div>
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
                          Score: <span style={{ fontWeight: 600, color: '#334155' }}>{tip.peix_score?.toFixed(1)}</span>
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>
                          Impact: <span style={{ fontWeight: 600, color: '#334155' }}>{tip.impact_probability?.toFixed(0)}%</span>
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>
                          Trend:{' '}
                          <span style={{ fontWeight: 600, color: tip.trend === 'steigend' ? '#dc2626' : tip.trend === 'fallend' ? '#16a34a' : '#64748b' }}>
                            {tip.trend === 'steigend' ? '\u2197' : tip.trend === 'fallend' ? '\u2198' : '\u2192'}{' '}
                            {tip.change_pct > 0 ? '+' : ''}{tip.change_pct}%
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

                      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 600,
                            padding: '3px 8px',
                            borderRadius: 999,
                            background: 'linear-gradient(135deg, rgba(34,197,94,0.1), rgba(16,185,129,0.08))',
                            color: '#16a34a',
                            border: '1px solid rgba(34,197,94,0.2)',
                          }}
                        >
                          {tip.recommended_product}
                        </span>
                        <span style={{ fontSize: 10, color: '#94a3b8' }}>Klick für Details</span>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Standort Hover-Tooltip */}
              {hoveredStandort && (() => {
                const s = standorteData.find((d) => d.standort === hoveredStandort);
                if (!s) return null;
                const containerW = mapContainerRef.current?.offsetWidth || 600;
                const flipX = standortTooltipPos.x > containerW - 240;
                const trendColor = s.trend === 'steigend' ? '#dc2626' : s.trend === 'fallend' ? '#16a34a' : '#64748b';
                const trendArrow = s.trend === 'steigend' ? '\u2197' : s.trend === 'fallend' ? '\u2198' : '\u2192';

                return (
                  <div
                    style={{
                      position: 'absolute',
                      left: flipX ? standortTooltipPos.x - 220 : standortTooltipPos.x + 14,
                      top: standortTooltipPos.y - 8,
                      zIndex: 60,
                      pointerEvents: 'none',
                    }}
                  >
                    <div
                      style={{
                        background: '#ffffff',
                        border: '1px solid #e2e8f0',
                        borderRadius: 10,
                        boxShadow: '0 6px 24px rgba(0,0,0,0.12)',
                        padding: '10px 14px',
                        minWidth: 180,
                        maxWidth: 220,
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>
                        {s.standort}
                      </div>
                      <div style={{ display: 'flex', gap: 8, fontSize: 11, color: '#64748b', marginBottom: 4 }}>
                        <span>{s.bundesland}</span>
                        {s.einwohner && <span>{fmt(s.einwohner)} EW</span>}
                      </div>
                      <div style={{ display: 'flex', gap: 12, fontSize: 11, marginBottom: 2 }}>
                        <span style={{ color: '#64748b' }}>
                          Viruslast: <span style={{ fontWeight: 600, color: '#334155' }}>{fmt(s.viruslast)}</span>
                        </span>
                        <span style={{ fontWeight: 600, color: trendColor }}>
                          {trendArrow} {s.change_pct > 0 ? '+' : ''}{s.change_pct}%
                        </span>
                      </div>
                      {s.unter_bg && (
                        <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>Unter Bestimmungsgrenze</div>
                      )}
                    </div>
                  </div>
                );
              })()}
              </div>
            )}
          </div>

          {/* Sidebar: Region Details + Transfers */}
          <div className="space-y-6">

            {/* Selected Region Detail */}
            {selectedRegion && regionData[selectedRegion] && (
              <div className="card p-6 fade-in">
                <h3 className="text-lg font-bold text-slate-900 mb-1">{regionData[selectedRegion].name}</h3>
                <p className="text-xs text-slate-500 mb-4">{selectedRegion} | {regionData[selectedRegion].n_standorte} Messstellen</p>

                <div className="grid grid-cols-2 gap-4 mb-4">
                  <div className="bg-slate-50 rounded-xl p-3">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Radar Level</div>
                    <div className="text-xl font-bold text-slate-900">
                      {(() => {
                        const i = projectedIntensity(regionData[selectedRegion]);
                        return i >= 0.7 ? 'Hoch' : i >= 0.4 ? 'Mittel' : 'Niedrig';
                      })()}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1">Qualitativ (Default)</div>
                  </div>
                  <div className="bg-slate-50 rounded-xl p-3">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Trend</div>
                    <div className="text-xl font-bold" style={{ color: regionData[selectedRegion].trend === 'steigend' ? '#ef4444' : regionData[selectedRegion].trend === 'fallend' ? '#10b981' : '#94a3b8' }}>
                      {regionData[selectedRegion].trend === 'steigend' ? '\u2197' : regionData[selectedRegion].trend === 'fallend' ? '\u2198' : '\u2192'}{' '}
                      {regionData[selectedRegion].change_pct > 0 ? '+' : ''}{regionData[selectedRegion].change_pct}%
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1">14-Tage Radar nutzt Trend</div>
                  </div>
                </div>

                {showTechDetails && (
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <div className="bg-slate-50 rounded-xl p-3">
                      <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Rohwert</div>
                      <div className="text-xl font-bold text-slate-900">{fmt(regionData[selectedRegion].avg_viruslast)}</div>
                      <div className="text-xs text-slate-500">Genkopien/L</div>
                    </div>
                    <div className="bg-slate-50 rounded-xl p-3">
                      <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">Messstellen</div>
                      <div className="text-xl font-bold text-slate-900">{regionData[selectedRegion].n_standorte}</div>
                      <div className="text-xs text-slate-500">n</div>
                    </div>
                  </div>
                )}

                {showTechDetails && regionTimeseries.length > 0 && (
                  <div>
                    <p className="text-xs text-slate-500 mb-2">Verlauf (letzte 90 Tage)</p>
                    <ResponsiveContainer width="100%" height={120}>
                      <LineChart data={regionTimeseries.map(d => ({ ...d, date: format(new Date(d.date), 'dd.MM', { locale: de }) }))}>
                        <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
                        <YAxis tick={{ fill: '#64748b', fontSize: 9 }} tickFormatter={(v: number) => fmt(v)} width={45} />
                        <Tooltip
                          contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 11, boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}
                          labelStyle={{ color: '#0f172a' }}
                        />
                        <Line type="monotone" dataKey="viruslast" stroke={baseColor} strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            )}

            {/* Top Regions Ranking */}
            <div className="card p-6">
              <h3 className="text-sm font-bold text-slate-900 mb-4">Top Regionen nach Viruslast</h3>
              <div className="space-y-2">
                {Object.entries(regionData)
                  .sort(([, a], [, b]) => b.avg_viruslast - a.avg_viruslast)
                  .slice(0, 8)
                  .map(([code, region], i) => (
                    <div
                      key={code}
                      className={`flex items-center justify-between p-2 rounded-lg cursor-pointer transition-all hover:bg-slate-50 ${
                        selectedRegion === code ? 'bg-blue-50 border border-blue-100' : 'bg-transparent'
                      }`}
                      onClick={() => setSelectedRegion(code)}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-bold w-5" style={{ color: i < 3 ? '#ef4444' : '#64748b' }}>{i + 1}</span>
                        <div>
                          <div className="text-sm text-slate-700">{region.name}</div>
                          <div className="text-xs text-slate-400">{region.n_standorte} Messstellen</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-bold text-slate-900">
                          {(() => {
                            const ii = projectedIntensity(region);
                            return ii >= 0.7 ? 'Hoch' : ii >= 0.4 ? 'Mittel' : 'Niedrig';
                          })()}
                        </div>
                        <div className="text-xs" style={{ color: region.trend === 'steigend' ? '#ef4444' : region.trend === 'fallend' ? '#10b981' : '#64748b' }}>
                          {region.trend === 'steigend' ? '\u2197' : region.trend === 'fallend' ? '\u2198' : '\u2192'} {region.change_pct > 0 ? '+' : ''}{region.change_pct}%
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            {/* Budget Shift Suggestions (Legacy endpoint; UI is media-first) */}
            <div className="card p-6">
              <h3 className="text-sm font-bold text-slate-900 mb-1">Budget-Shifts (Pilot)</h3>
              <p className="text-xs text-slate-500 mb-4">Heuristische Vorschlaege, um Budget in Regionen mit hohem Timing-Fit zu schieben</p>
              {transfers.length > 0 ? (
                <div className="space-y-3">
                  {transfers.map((t, i) => (
                    <div key={i} className="p-3 rounded-lg bg-white border border-slate-200 shadow-sm">
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`badge badge-${t.priority}`}>{t.priority}</span>
                        <span className="text-xs text-slate-400">Signal: {t.test_typ}</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-slate-500">{t.from_name}</span>
                        <span className="text-indigo-500">&#8594;</span>
                        <span className="text-slate-900 font-medium">{t.to_name}</span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">{t.reason}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 text-center py-4">Keine Transfers empfohlen</p>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default GermanyMap;
