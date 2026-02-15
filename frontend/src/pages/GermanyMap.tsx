import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

// Bundesland SVG paths (simplified D3/topojson outlines)
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
  'Influenza B': '#8b5cf6',
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
    if (selectedRegion) {
      fetchRegionTimeseries(selectedRegion);
    }
  }, [selectedRegion, fetchRegionTimeseries]);

  const baseColor = VIRUS_COLORS[selectedVirus] || '#3b82f6';

  return (
    <div className="min-h-screen" style={{ background: '#0f172a' }}>
      {/* Header */}
      <header style={{ background: '#1e293b', borderBottom: '1px solid #334155' }}>
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/dashboard')} className="text-slate-400 hover:text-white transition">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-white tracking-tight">Deutschlandkarte</h1>
                <p className="text-xs text-slate-400">Regionale Viruslast-Verteilung + Transfer-Empfehlungen</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {Object.entries(VIRUS_COLORS).map(([virus, color]) => (
              <button
                key={virus}
                onClick={() => { setSelectedVirus(virus); setSelectedRegion(null); }}
                className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all"
                style={{
                  background: selectedVirus === virus ? color : 'transparent',
                  color: selectedVirus === virus ? 'white' : '#94a3b8',
                  border: `1px solid ${selectedVirus === virus ? color : '#334155'}`,
                }}
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
                <h2 className="text-lg font-bold text-white">{selectedVirus} - Viruslast nach Bundesland</h2>
                <p className="text-xs text-slate-500 mt-1">
                  {dataDate ? `Stand: ${format(new Date(dataDate), 'dd. MMMM yyyy', { locale: de })}` : 'Lade Daten...'}
                  {maxViruslast > 0 ? ` | Max: ${fmt(maxViruslast)} Genkopien/L` : ''}
                </p>
              </div>
              {/* Legend */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">Niedrig</span>
                <div className="flex">
                  {[0.1, 0.3, 0.5, 0.7, 0.9].map((v) => (
                    <div key={v} className="w-5 h-3" style={{ background: intensityToColor(v, baseColor) }} />
                  ))}
                </div>
                <span className="text-xs text-slate-500">Hoch</span>
              </div>
            </div>

            {!hasData ? (
              <div className="flex items-center justify-center py-32 text-center">
                <div>
                  <div className="text-4xl mb-4">🗺</div>
                  <p className="text-slate-400 mb-2">Keine regionalen Daten vorhanden</p>
                  <p className="text-sm text-slate-500 max-w-md">
                    Importiere zuerst die AMELAG Einzelstandort-Daten über
                    <code className="px-1.5 py-0.5 mx-1 rounded text-xs" style={{ background: '#334155', color: '#94a3b8' }}>
                      POST /api/v1/ingest/amelag
                    </code>
                  </p>
                </div>
              </div>
            ) : (
              <svg viewBox="0 0 420 460" className="w-full max-h-[500px]" style={{ filter: 'drop-shadow(0 4px 12px rgba(0,0,0,0.3))' }}>
                {Object.entries(BUNDESLAND_PATHS).map(([code, path]) => {
                  const region = regionData[code];
                  const intensity = region?.intensity || 0;
                  const isSelected = selectedRegion === code;
                  const fillColor = region ? intensityToColor(intensity, baseColor) : 'rgba(51,65,85,0.3)';

                  return (
                    <g key={code} className="cursor-pointer" onClick={() => setSelectedRegion(code === selectedRegion ? null : code)}>
                      <path
                        d={path.d}
                        fill={fillColor}
                        stroke={isSelected ? '#f1f5f9' : '#475569'}
                        strokeWidth={isSelected ? 2.5 : 1}
                        style={{ transition: 'all 0.3s ease' }}
                      />
                      <text
                        x={path.cx}
                        y={path.cy - 6}
                        textAnchor="middle"
                        fill={intensity > 0.5 ? '#fff' : '#94a3b8'}
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
                          fill={intensity > 0.5 ? '#ddd' : '#64748b'}
                          fontSize="7"
                        >
                          {fmt(region.avg_viruslast)}
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
              </svg>
            )}
          </div>

          {/* Sidebar: Region Details + Transfers */}
          <div className="space-y-6">

            {/* Selected Region Detail */}
            {selectedRegion && regionData[selectedRegion] && (
              <div className="card p-6 fade-in">
                <h3 className="text-lg font-bold text-white mb-1">{regionData[selectedRegion].name}</h3>
                <p className="text-xs text-slate-500 mb-4">{selectedRegion} | {regionData[selectedRegion].n_standorte} Messstellen</p>

                <div className="grid grid-cols-2 gap-4 mb-4">
                  <div className="p-3 rounded-lg" style={{ background: '#0f172a' }}>
                    <div className="text-xl font-bold text-white">{fmt(regionData[selectedRegion].avg_viruslast)}</div>
                    <div className="text-xs text-slate-500">Genkopien/L</div>
                  </div>
                  <div className="p-3 rounded-lg" style={{ background: '#0f172a' }}>
                    <div className="text-xl font-bold" style={{ color: regionData[selectedRegion].trend === 'steigend' ? '#ef4444' : regionData[selectedRegion].trend === 'fallend' ? '#10b981' : '#94a3b8' }}>
                      {regionData[selectedRegion].change_pct > 0 ? '+' : ''}{regionData[selectedRegion].change_pct}%
                    </div>
                    <div className="text-xs text-slate-500">Woche-zu-Woche</div>
                  </div>
                </div>

                {regionTimeseries.length > 0 && (
                  <div>
                    <p className="text-xs text-slate-500 mb-2">Verlauf (letzte 90 Tage)</p>
                    <ResponsiveContainer width="100%" height={120}>
                      <LineChart data={regionTimeseries.map(d => ({ ...d, date: format(new Date(d.date), 'dd.MM', { locale: de }) }))}>
                        <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} interval="preserveStartEnd" />
                        <YAxis tick={{ fill: '#64748b', fontSize: 9 }} tickFormatter={(v: number) => fmt(v)} width={45} />
                        <Tooltip
                          contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }}
                          labelStyle={{ color: '#f1f5f9' }}
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
              <h3 className="text-sm font-bold text-white mb-4">Top Regionen nach Viruslast</h3>
              <div className="space-y-2">
                {Object.entries(regionData)
                  .sort(([, a], [, b]) => b.avg_viruslast - a.avg_viruslast)
                  .slice(0, 8)
                  .map(([code, region], i) => (
                    <div
                      key={code}
                      className="flex items-center justify-between p-2 rounded-lg cursor-pointer transition-all hover:bg-slate-800/50"
                      style={{ background: selectedRegion === code ? 'rgba(59,130,246,0.1)' : 'transparent' }}
                      onClick={() => setSelectedRegion(code)}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-bold w-5" style={{ color: i < 3 ? '#ef4444' : '#64748b' }}>{i + 1}</span>
                        <div>
                          <div className="text-sm text-slate-300">{region.name}</div>
                          <div className="text-xs text-slate-600">{region.n_standorte} Messstellen</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-bold text-white">{fmt(region.avg_viruslast)}</div>
                        <div className="text-xs" style={{ color: region.trend === 'steigend' ? '#ef4444' : region.trend === 'fallend' ? '#10b981' : '#64748b' }}>
                          {region.trend === 'steigend' ? '\u2197' : region.trend === 'fallend' ? '\u2198' : '\u2192'} {region.change_pct > 0 ? '+' : ''}{region.change_pct}%
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            {/* Transfer Suggestions */}
            <div className="card p-6">
              <h3 className="text-sm font-bold text-white mb-1">Transfer-Empfehlungen</h3>
              <p className="text-xs text-slate-500 mb-4">Testkits zwischen Standorten verschieben</p>
              {transfers.length > 0 ? (
                <div className="space-y-3">
                  {transfers.map((t, i) => (
                    <div key={i} className="p-3 rounded-lg" style={{ background: '#0f172a', border: '1px solid #334155' }}>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`badge badge-${t.priority}`}>{t.priority}</span>
                        <span className="text-xs text-slate-500">{t.test_typ}</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-slate-400">{t.from_name}</span>
                        <span className="text-blue-400">&#8594;</span>
                        <span className="text-white font-medium">{t.to_name}</span>
                      </div>
                      <p className="text-xs text-slate-500 mt-1">{t.reason}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500 text-center py-4">Keine Transfers empfohlen</p>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default GermanyMap;
