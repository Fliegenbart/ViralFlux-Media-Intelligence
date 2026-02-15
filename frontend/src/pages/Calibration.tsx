import React, { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ComposedChart,
} from 'recharts';
import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';

// ─── Types ──────────────────────────────────────────────────────────────────
type PageState = 'UPLOAD' | 'PREVIEW' | 'LOADING' | 'RESULTS';

type VirusType = 'Influenza A' | 'Influenza B' | 'SARS-CoV-2' | 'RSV A';

interface PreviewData {
  filename: string;
  total_rows: number;
  columns: string[];
  columns_valid: boolean;
  missing_columns: string[];
  preview: Record<string, string>[];
}

interface CalibrationResult {
  metrics: {
    r2_score: number;
    correlation: number;
    correlation_pct: number;
    mae: number;
    data_points: number;
    date_range: { start: string; end: string };
  };
  default_weights: Record<string, number>;
  optimized_weights: Record<string, number>;
  llm_insight: string;
  chart_data: Array<{
    date: string;
    real_qty: number;
    predicted_qty: number;
    bio: number;
    psycho: number;
    context: number;
  }>;
  error?: string;
}

// ─── Constants ──────────────────────────────────────────────────────────────
const ACCENT = '#f59e0b';
const ACCENT_DIM = '#f59e0b40';
const ACCENT_BG = '#f59e0b08';
const BLUE = '#3b82f6';
const REQUIRED_COLUMNS = ['datum', 'menge'];
const MAX_FILE_SIZE = 10 * 1024 * 1024;

const VIRUS_OPTIONS: VirusType[] = ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'];

const WEIGHT_LABELS: Record<string, string> = {
  bio: 'Biologisch',
  market: 'Marktdaten',
  psycho: 'Suchverhalten',
  context: 'Kontext',
};

const WEIGHT_KEYS = ['bio', 'market', 'psycho', 'context'];

// ─── Component ──────────────────────────────────────────────────────────────
const Calibration: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ─── State ──────────────────────────────────────────────────────────
  const [pageState, setPageState] = useState<PageState>('UPLOAD');
  const [selectedVirus, setSelectedVirus] = useState<VirusType>('Influenza A');
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [result, setResult] = useState<CalibrationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ─── File Validation ────────────────────────────────────────────────
  const validateFile = (f: File): string | null => {
    const name = f.name.toLowerCase();
    if (!name.endsWith('.csv') && !name.endsWith('.xlsx')) {
      return 'Nur CSV oder Excel (.xlsx) Dateien erlaubt';
    }
    if (f.size > MAX_FILE_SIZE) {
      return `Datei zu groß (${(f.size / 1024 / 1024).toFixed(1)} MB). Maximum: 10 MB`;
    }
    return null;
  };

  // ─── Load Preview ──────────────────────────────────────────────────
  const loadPreview = useCallback(async (f: File) => {
    setFile(f);
    setError(null);

    const formData = new FormData();
    formData.append('file', f);

    try {
      const res = await fetch('/api/v1/calibration/preview', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Vorschau fehlgeschlagen' }));
        throw new Error(err.detail || 'Vorschau fehlgeschlagen');
      }
      const data: PreviewData = await res.json();
      setPreview(data);
      setPageState('PREVIEW');
    } catch (e: any) {
      setError(e.message);
      setFile(null);
    }
  }, []);

  // ─── Run Calibration ──────────────────────────────────────────────
  const runCalibration = useCallback(async () => {
    if (!file) return;

    setPageState('LOADING');
    setError(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('virus_type', selectedVirus);

    try {
      const res = await fetch('/api/v1/calibration/run', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Kalibrierung fehlgeschlagen' }));
        throw new Error(err.detail || 'Kalibrierung fehlgeschlagen');
      }
      const data: CalibrationResult = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      setResult(data);
      setPageState('RESULTS');
    } catch (e: any) {
      setError(e.message);
      setPageState('PREVIEW');
    }
  }, [file, selectedVirus]);

  // ─── Reset ────────────────────────────────────────────────────────
  const resetAll = useCallback(() => {
    setPageState('UPLOAD');
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  // ─── Drag & Drop Handlers ────────────────────────────────────────
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const droppedFile = e.dataTransfer.files[0];
    if (!droppedFile) return;

    const err = validateFile(droppedFile);
    if (err) {
      setError(err);
      return;
    }
    loadPreview(droppedFile);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;

    const err = validateFile(selected);
    if (err) {
      setError(err);
      e.target.value = '';
      return;
    }
    loadPreview(selected);
    e.target.value = '';
  };

  // ─── Score Color Helper ───────────────────────────────────────────
  const scoreColor = (pct: number): string => {
    if (pct >= 70) return '#10b981';
    if (pct >= 50) return '#f59e0b';
    return '#ef4444';
  };

  // ─── Chart Data ───────────────────────────────────────────────────
  const chartData = result?.chart_data?.map((d) => ({
    ...d,
    dateLabel: (() => {
      try {
        return format(parseISO(d.date), 'MMM yy', { locale: de });
      } catch {
        return d.date;
      }
    })(),
  })) || [];

  // ─── Render: UPLOAD State ─────────────────────────────────────────
  const renderUpload = () => (
    <div
      className="max-w-2xl mx-auto"
      style={{ animation: 'fadeSlideUp 0.5s ease-out both' }}
    >
      {/* Virus Type Selector */}
      <div
        className="rounded-xl p-6 mb-6"
        style={{ background: '#1e293b', border: '1px solid #334155' }}
      >
        <div className="text-sm font-medium text-slate-300 mb-3">Virustyp auswählen</div>
        <div className="flex flex-wrap gap-2">
          {VIRUS_OPTIONS.map((virus) => (
            <button
              key={virus}
              onClick={() => setSelectedVirus(virus)}
              className="px-4 py-2 rounded-lg text-xs font-medium transition-all"
              style={{
                background: selectedVirus === virus ? ACCENT : '#0f172a',
                color: selectedVirus === virus ? '#0f172a' : '#94a3b8',
                border: `1px solid ${selectedVirus === virus ? ACCENT : '#334155'}`,
                fontWeight: selectedVirus === virus ? 700 : 500,
              }}
            >
              {virus}
            </button>
          ))}
        </div>
      </div>

      {/* Drop Zone */}
      <div
        className="rounded-xl overflow-hidden"
        style={{
          background: '#1e293b',
          border: `1px solid ${isDragging ? ACCENT : '#334155'}`,
          transition: 'border-color 0.2s, box-shadow 0.2s',
          boxShadow: isDragging ? `0 0 24px ${ACCENT_DIM}` : 'none',
        }}
      >
        {/* Zone Header */}
        <div
          className="px-5 py-4 flex items-center justify-between"
          style={{ borderBottom: '1px solid #33415580', background: ACCENT_BG }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: ACCENT, boxShadow: `0 0 8px ${ACCENT_DIM}` }}
            />
            <div>
              <div className="text-sm font-semibold text-slate-200">Historische Bestelldaten</div>
              <div className="text-[11px] text-slate-500 mt-0.5">CSV oder Excel mit Ihren echten Bestellmengen</div>
            </div>
          </div>
          <a
            href="/api/v1/calibration/template"
            className="text-[11px] px-2.5 py-1 rounded-md transition-colors hover:opacity-80"
            style={{ color: ACCENT, background: ACCENT_DIM, textDecoration: 'none' }}
          >
            Vorlage herunterladen
          </a>
        </div>

        {/* Zone Body */}
        <div className="p-5">
          {/* Required columns */}
          <div className="mb-4 flex flex-wrap gap-1.5">
            {REQUIRED_COLUMNS.map((col) => (
              <span
                key={col}
                className="text-[10px] font-mono px-2 py-0.5 rounded"
                style={{ background: '#0f172a', color: ACCENT, border: `1px solid ${ACCENT_DIM}` }}
              >
                {col}
              </span>
            ))}
          </div>

          {/* Drop Area */}
          <div
            className="relative rounded-lg cursor-pointer group"
            style={{
              border: `2px dashed ${isDragging ? ACCENT : '#475569'}`,
              background: isDragging ? ACCENT_BG : '#0f172a40',
              transition: 'all 0.2s',
              minHeight: 140,
            }}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={handleFileSelect}
            />
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-4">
              <svg
                width="36" height="36" viewBox="0 0 24 24" fill="none"
                stroke={isDragging ? ACCENT : '#64748b'}
                strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                className="transition-colors"
                style={{ opacity: isDragging ? 1 : 0.7 }}
              >
                <path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <div className="text-center">
                <div className="text-xs text-slate-400 group-hover:text-slate-300 transition-colors">
                  {isDragging ? (
                    <span style={{ color: ACCENT }}>Datei hier ablegen</span>
                  ) : (
                    <>Datei hierher ziehen oder <span style={{ color: ACCENT }}>durchsuchen</span></>
                  )}
                </div>
                <div className="text-[10px] text-slate-600 mt-1.5">CSV oder Excel — max. 10 MB</div>
              </div>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div
              className="mt-3 rounded-lg px-4 py-2.5 flex items-center gap-2"
              style={{ background: '#ef444410', border: '1px solid #ef444425' }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span className="text-[11px] text-red-400">{error}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  // ─── Render: PREVIEW State ────────────────────────────────────────
  const renderPreview = () => {
    if (!preview) return null;

    const hasDatum = preview.columns.includes('datum');
    const hasMenge = preview.columns.includes('menge');

    return (
      <div
        className="max-w-2xl mx-auto"
        style={{ animation: 'fadeSlideUp 0.4s ease-out both' }}
      >
        <div
          className="rounded-xl overflow-hidden"
          style={{ background: '#1e293b', border: '1px solid #334155' }}
        >
          {/* File Info */}
          <div
            className="px-5 py-4"
            style={{ borderBottom: '1px solid #33415580', background: ACCENT_BG }}
          >
            <div className="flex items-center gap-3">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={ACCENT} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                <polyline points="14,2 14,8 20,8" />
              </svg>
              <div>
                <div className="text-sm font-semibold text-slate-200">{preview.filename}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">{preview.total_rows} Zeilen erkannt</div>
              </div>
            </div>
          </div>

          <div className="p-5">
            {/* Column Validation */}
            <div className="mb-4 flex flex-wrap gap-2">
              {REQUIRED_COLUMNS.map((col) => {
                const found = col === 'datum' ? hasDatum : hasMenge;
                return (
                  <div
                    key={col}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono"
                    style={{
                      background: found ? '#10b98110' : '#ef444410',
                      border: `1px solid ${found ? '#10b98130' : '#ef444430'}`,
                      color: found ? '#10b981' : '#ef4444',
                    }}
                  >
                    {found ? (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20,6 9,17 4,12" />
                      </svg>
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    )}
                    {col}
                  </div>
                );
              })}
            </div>

            {/* Preview Table */}
            {preview.preview.length > 0 && (
              <div className="rounded-lg overflow-hidden mb-4" style={{ border: '1px solid #334155' }}>
                <div className="overflow-x-auto">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr style={{ background: '#0f172a' }}>
                        {preview.columns.map((col) => (
                          <th
                            key={col}
                            className="px-3 py-2 text-left font-mono font-medium"
                            style={{
                              color: REQUIRED_COLUMNS.includes(col) ? ACCENT : '#64748b',
                            }}
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.preview.slice(0, 5).map((row, i) => (
                        <tr
                          key={i}
                          style={{
                            background: i % 2 === 0 ? '#1e293b' : '#1a2536',
                            borderTop: '1px solid #33415540',
                          }}
                        >
                          {preview.columns.map((col) => (
                            <td key={col} className="px-3 py-1.5 text-slate-400 font-mono whitespace-nowrap">
                              {row[col] || '\u2014'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div
                className="mb-4 rounded-lg px-4 py-2.5 flex items-center gap-2"
                style={{ background: '#ef444410', border: '1px solid #ef444425' }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span className="text-[11px] text-red-400">{error}</span>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2">
              {preview.columns_valid && (
                <button
                  onClick={runCalibration}
                  className="flex-1 py-2.5 rounded-lg text-xs font-semibold text-white transition-opacity hover:opacity-90"
                  style={{ background: ACCENT, color: '#0f172a' }}
                >
                  Kalibrierung starten
                </button>
              )}
              <button
                onClick={resetAll}
                className="px-4 py-2.5 rounded-lg text-xs font-medium text-slate-400 transition-colors hover:text-slate-200"
                style={{ background: '#0f172a', border: '1px solid #334155' }}
              >
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // ─── Render: LOADING State ────────────────────────────────────────
  const renderLoading = () => (
    <div
      className="max-w-md mx-auto text-center py-20"
      style={{ animation: 'fadeSlideUp 0.4s ease-out both' }}
    >
      <div
        className="rounded-xl p-12"
        style={{ background: '#1e293b', border: '1px solid #334155' }}
      >
        {/* Spinner */}
        <div className="relative w-16 h-16 mx-auto mb-6">
          <div
            className="absolute inset-0 rounded-full border-4 border-t-transparent"
            style={{
              borderColor: `${ACCENT} transparent ${ACCENT_DIM} ${ACCENT_DIM}`,
              animation: 'spin 1s linear infinite',
            }}
          />
          <div
            className="absolute inset-2 rounded-full border-2 border-t-transparent"
            style={{
              borderColor: `transparent ${ACCENT_DIM} transparent ${ACCENT}`,
              animation: 'spin 1.5s linear infinite reverse',
            }}
          />
        </div>

        <div className="text-base font-semibold text-slate-200 mb-2">
          Simulation läuft...
        </div>
        <div className="text-xs text-slate-500 mb-6">
          Historische Daten werden analysiert
        </div>

        {/* Pulsing dots */}
        <div className="flex justify-center gap-2">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="w-2 h-2 rounded-full"
              style={{
                background: ACCENT,
                animation: `pulse 1.4s ease-in-out ${i * 0.2}s infinite`,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );

  // ─── Render: RESULTS State ────────────────────────────────────────
  const renderResults = () => {
    if (!result) return null;

    const pct = result.metrics.correlation_pct;
    const color = scoreColor(pct);
    const circumference = 2 * Math.PI * 54;
    const strokeDashoffset = circumference - (pct / 100) * circumference;

    return (
      <div style={{ animation: 'fadeSlideUp 0.5s ease-out both' }}>
        {/* ─── 3-Panel Grid ──────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">

          {/* Panel 1: Score */}
          <div
            className="flex flex-col items-center justify-center"
            style={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 12,
              padding: 24,
            }}
          >
            <div className="relative" style={{ width: 140, height: 140 }}>
              <svg viewBox="0 0 120 120" className="w-full h-full" style={{ transform: 'rotate(-90deg)' }}>
                {/* Background ring */}
                <circle
                  cx="60" cy="60" r="54"
                  fill="none"
                  stroke="#334155"
                  strokeWidth="8"
                />
                {/* Progress ring */}
                <circle
                  cx="60" cy="60" r="54"
                  fill="none"
                  stroke={color}
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={circumference}
                  strokeDashoffset={strokeDashoffset}
                  style={{ transition: 'stroke-dashoffset 1.5s ease-out' }}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-4xl font-black text-white">{pct.toFixed(0)}</span>
                <span className="text-[11px] text-slate-400 -mt-1">% Übereinstimmung</span>
              </div>
            </div>
            <div className="mt-4 text-center">
              <div className="text-xs text-slate-500">
                R² = {result.metrics.r2_score.toFixed(3)} | MAE = {result.metrics.mae.toFixed(1)}
              </div>
              <div className="text-[10px] text-slate-600 mt-1">
                {result.metrics.data_points} Datenpunkte | {result.metrics.date_range.start} — {result.metrics.date_range.end}
              </div>
            </div>
          </div>

          {/* Panel 2: Weights Before/After */}
          <div
            style={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 12,
              padding: 24,
            }}
          >
            <div className="text-sm font-semibold text-slate-200 mb-4">Gewichte</div>
            <div className="space-y-4">
              {WEIGHT_KEYS.map((key) => {
                const defVal = (result.default_weights[key] ?? 0) * 100;
                const optVal = (result.optimized_weights[key] ?? 0) * 100;
                return (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs text-slate-400">{WEIGHT_LABELS[key] || key}</span>
                      <div className="flex items-center gap-3 text-[10px]">
                        <span className="text-slate-500">{defVal.toFixed(0)}%</span>
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#475569" strokeWidth="2">
                          <path d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
                        <span style={{ color: ACCENT, fontWeight: 600 }}>{optVal.toFixed(0)}%</span>
                      </div>
                    </div>
                    {/* Bars */}
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[9px] text-slate-600 w-14 text-right">Standard</span>
                        <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: '#0f172a' }}>
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{ width: `${defVal}%`, background: '#475569' }}
                          />
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[9px] w-14 text-right" style={{ color: ACCENT }}>Optimiert</span>
                        <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: '#0f172a' }}>
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{ width: `${optVal}%`, background: ACCENT }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Panel 3: LLM Insight */}
          <div
            style={{
              background: '#1e293b',
              border: `1px solid ${ACCENT_DIM}`,
              borderRadius: 12,
              padding: 24,
              boxShadow: `0 0 20px ${ACCENT}10`,
            }}
          >
            <div className="flex items-center gap-2 mb-4">
              {/* AI / Sparkle icon as SVG */}
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={ACCENT} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2l2.09 6.26L20.18 10l-6.09 1.74L12 18l-2.09-6.26L3.82 10l6.09-1.74L12 2z" />
                <path d="M19 15l1.04 3.13L23.18 19l-3.14.87L19 23l-1.04-3.13L14.82 19l3.14-.87L19 15z" />
                <path d="M5 15l1.04 3.13L9.18 19l-3.14.87L5 23l-1.04-3.13L.82 19l3.14-.87L5 15z" />
              </svg>
              <span className="text-sm font-semibold text-slate-200">KI-Analyse</span>
            </div>
            <p
              className="text-sm text-slate-300 leading-relaxed"
              style={{ fontSize: '0.9rem', lineHeight: 1.7 }}
            >
              {result.llm_insight}
            </p>
          </div>
        </div>

        {/* ─── Chart (full width) ─────────────────────────────── */}
        <div
          className="mb-6"
          style={{
            background: '#1e293b',
            border: '1px solid #334155',
            borderRadius: 12,
            padding: 24,
          }}
        >
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-base font-bold text-white">Vergleich: Bestellungen vs. Vorhersage</h3>
              <p className="text-xs text-slate-500 mt-1">{selectedVirus} — historisches Backtesting</p>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="dateLabel"
                tick={{ fill: '#64748b', fontSize: 11 }}
                tickLine={{ stroke: '#334155' }}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: '#64748b', fontSize: 11 }}
                tickLine={{ stroke: '#334155' }}
                label={{
                  value: 'Bestellmenge',
                  angle: -90,
                  position: 'insideLeft',
                  style: { fill: '#64748b', fontSize: 10 },
                  offset: 0,
                }}
              />
              <Tooltip
                contentStyle={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: 8,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                }}
                labelStyle={{ color: '#f1f5f9' }}
                itemStyle={{ color: '#94a3b8' }}
                formatter={(value: number, name: string) => [
                  value?.toLocaleString('de-DE'),
                  name,
                ]}
              />
              <Legend
                wrapperStyle={{ paddingTop: 16 }}
                formatter={(value: string) => (
                  <span style={{ color: '#94a3b8', fontSize: 12 }}>{value}</span>
                )}
              />
              <Line
                type="monotone"
                dataKey="real_qty"
                name="Ihre Bestellungen"
                stroke={BLUE}
                strokeWidth={2}
                dot={false}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="predicted_qty"
                name="LabPulse Vorhersage"
                stroke={ACCENT}
                strokeWidth={2}
                strokeDasharray="6 3"
                dot={false}
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* ─── New Analysis Button ────────────────────────────── */}
        <div className="text-center">
          <button
            onClick={resetAll}
            className="px-8 py-3 rounded-lg text-sm font-semibold transition-all hover:opacity-90"
            style={{
              background: ACCENT,
              color: '#0f172a',
            }}
          >
            Neue Analyse
          </button>
        </div>
      </div>
    );
  };

  // ─── Main Render ──────────────────────────────────────────────────
  return (
    <div style={{ background: '#0f172a', minHeight: '100vh' }}>
      <style>{`
        @keyframes fadeSlideUp {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes pulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1.2); }
        }
      `}</style>

      {/* ─── Header ──────────────────────────────────────────── */}
      <header
        style={{
          background: '#1e293b',
          borderBottom: '1px solid #334155',
          position: 'sticky',
          top: 0,
          zIndex: 40,
        }}
      >
        <div className="max-w-[1400px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="p-1.5 rounded-lg transition-colors hover:bg-slate-700"
              style={{ color: '#94a3b8' }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h1 className="text-lg font-bold text-slate-100 tracking-tight">
                Modell-Kalibrierung
              </h1>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Backtesting auf Ihren historischen Bestelldaten
              </p>
            </div>
          </div>

          {/* State indicator */}
          <div className="hidden sm:flex items-center gap-2 text-[10px] text-slate-600">
            {(['UPLOAD', 'PREVIEW', 'LOADING', 'RESULTS'] as PageState[]).map((state, i) => (
              <React.Fragment key={state}>
                {i > 0 && (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#475569" strokeWidth="2">
                    <path d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                )}
                <span
                  className="px-2 py-0.5 rounded"
                  style={{
                    background: pageState === state ? ACCENT_BG : '#0f172a',
                    border: `1px solid ${pageState === state ? ACCENT_DIM : '#334155'}`,
                    color: pageState === state ? ACCENT : '#475569',
                    fontWeight: pageState === state ? 600 : 400,
                  }}
                >
                  {state === 'UPLOAD' ? 'Upload' : state === 'PREVIEW' ? 'Vorschau' : state === 'LOADING' ? 'Analyse' : 'Ergebnis'}
                </span>
              </React.Fragment>
            ))}
          </div>
        </div>
      </header>

      {/* ─── Main Content ─────────────────────────────────────── */}
      <main className="max-w-[1400px] mx-auto px-6 py-8">
        {pageState === 'UPLOAD' && renderUpload()}
        {pageState === 'PREVIEW' && renderPreview()}
        {pageState === 'LOADING' && renderLoading()}
        {pageState === 'RESULTS' && renderResults()}
      </main>

      {/* ─── Footer ──────────────────────────────────────────── */}
      <div className="mt-6 pb-8 text-center text-[10px] text-slate-600">
        Kalibrierungsdaten werden nicht gespeichert und nur für die aktuelle Analyse verwendet.
      </div>
    </div>
  );
};

export default Calibration;
