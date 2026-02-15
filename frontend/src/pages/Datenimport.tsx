import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

// ─── Types ──────────────────────────────────────────────────────────────────
interface PreviewData {
  filename: string;
  total_rows: number;
  columns: string[];
  columns_valid: boolean;
  missing_columns: string[];
  extra_columns: string[];
  preview: Record<string, string>[];
}

interface UploadResult {
  success: boolean;
  upload_id: number;
  filename: string;
  file_format: string;
  row_count: number;
  date_range: { start: string | null; end: string | null };
  import_result: Record<string, number>;
}

interface UploadHistoryEntry {
  id: number;
  filename: string;
  upload_type: string;
  file_format: string;
  row_count: number;
  date_range_start: string | null;
  date_range_end: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
}

type UploadType = 'orders' | 'lab_results';

interface ZoneState {
  file: File | null;
  isDragging: boolean;
  preview: PreviewData | null;
  isLoadingPreview: boolean;
  isUploading: boolean;
  result: UploadResult | null;
  error: string | null;
}

const INITIAL_ZONE: ZoneState = {
  file: null,
  isDragging: false,
  preview: null,
  isLoadingPreview: false,
  isUploading: false,
  result: null,
  error: null,
};

// ─── Config ─────────────────────────────────────────────────────────────────
const ZONE_CONFIG: Record<UploadType, {
  title: string;
  subtitle: string;
  color: string;
  colorDim: string;
  colorBg: string;
  endpoint: string;
  required: string[];
  optional: string[];
}> = {
  orders: {
    title: 'Historische Bestelldaten',
    subtitle: 'ERP-Export mit Bestellhistorie',
    color: '#3b82f6',
    colorDim: '#3b82f640',
    colorBg: '#3b82f608',
    endpoint: '/api/v1/data-import/upload/orders',
    required: ['order_date', 'article_id', 'quantity'],
    optional: ['customer_id'],
  },
  lab_results: {
    title: 'Anonymisierte Laborergebnisse',
    subtitle: 'Teststatistiken ohne Patientendaten',
    color: '#10b981',
    colorDim: '#10b98140',
    colorBg: '#10b98108',
    endpoint: '/api/v1/data-import/upload/lab-results',
    required: ['datum', 'test_type', 'total_tests', 'positive_tests'],
    optional: ['region'],
  },
};

const STATUS_STYLES: Record<string, { label: string; bg: string; color: string }> = {
  success: { label: 'Erfolgreich', bg: '#10b98118', color: '#10b981' },
  error: { label: 'Fehler', bg: '#ef444418', color: '#ef4444' },
  partial: { label: 'Teilweise', bg: '#f59e0b18', color: '#f59e0b' },
};

const MAX_FILE_SIZE = 10 * 1024 * 1024;

// ─── Component ──────────────────────────────────────────────────────────────
const Datenimport: React.FC = () => {
  const navigate = useNavigate();
  const [zones, setZones] = useState<Record<UploadType, ZoneState>>({
    orders: { ...INITIAL_ZONE },
    lab_results: { ...INITIAL_ZONE },
  });
  const [history, setHistory] = useState<UploadHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  const fileInputRefs = {
    orders: useRef<HTMLInputElement>(null),
    lab_results: useRef<HTMLInputElement>(null),
  };

  // ─── Zone State Helper ──────────────────────────────────────────────
  const updateZone = useCallback((type: UploadType, patch: Partial<ZoneState>) => {
    setZones(prev => ({ ...prev, [type]: { ...prev[type], ...patch } }));
  }, []);

  // ─── Fetch History ──────────────────────────────────────────────────
  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/data-import/history?limit=15');
      if (res.ok) {
        const data = await res.json();
        setHistory(data);
      }
    } catch (e) {
      console.error('Fetch history error:', e);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  // ─── File Validation ────────────────────────────────────────────────
  const validateFile = (file: File): string | null => {
    const ext = file.name.toLowerCase();
    if (!ext.endsWith('.csv') && !ext.endsWith('.xlsx')) {
      return 'Nur CSV oder Excel (.xlsx) Dateien erlaubt';
    }
    if (file.size > MAX_FILE_SIZE) {
      return `Datei zu groß (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum: 10 MB`;
    }
    return null;
  };

  // ─── Preview ────────────────────────────────────────────────────────
  const loadPreview = useCallback(async (type: UploadType, file: File) => {
    updateZone(type, { file, isLoadingPreview: true, error: null, result: null, preview: null });

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`/api/v1/data-import/preview?upload_type=${type}`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Vorschau fehlgeschlagen' }));
        throw new Error(err.detail || 'Vorschau fehlgeschlagen');
      }
      const preview = await res.json();
      updateZone(type, { preview, isLoadingPreview: false });
    } catch (e: any) {
      updateZone(type, { error: e.message, isLoadingPreview: false, file: null });
    }
  }, [updateZone]);

  // ─── Upload ─────────────────────────────────────────────────────────
  const doUpload = useCallback(async (type: UploadType) => {
    const { file } = zones[type];
    if (!file) return;

    updateZone(type, { isUploading: true, error: null });

    const formData = new FormData();
    formData.append('file', file);

    try {
      const cfg = ZONE_CONFIG[type];
      const res = await fetch(cfg.endpoint, { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Upload fehlgeschlagen' }));
        throw new Error(err.detail || 'Upload fehlgeschlagen');
      }
      const result = await res.json();
      updateZone(type, { result, isUploading: false, preview: null });
      fetchHistory();
    } catch (e: any) {
      updateZone(type, { error: e.message, isUploading: false });
    }
  }, [zones, updateZone, fetchHistory]);

  // ─── Reset Zone ─────────────────────────────────────────────────────
  const resetZone = useCallback((type: UploadType) => {
    updateZone(type, { ...INITIAL_ZONE });
    if (fileInputRefs[type].current) {
      fileInputRefs[type].current!.value = '';
    }
  }, [updateZone]);

  // ─── Drag & Drop Handlers ──────────────────────────────────────────
  const handleDragOver = (type: UploadType) => (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    updateZone(type, { isDragging: true });
  };

  const handleDragLeave = (type: UploadType) => (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    updateZone(type, { isDragging: false });
  };

  const handleDrop = (type: UploadType) => (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    updateZone(type, { isDragging: false });

    const file = e.dataTransfer.files[0];
    if (!file) return;

    const err = validateFile(file);
    if (err) {
      updateZone(type, { error: err });
      return;
    }
    loadPreview(type, file);
  };

  const handleFileSelect = (type: UploadType) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const err = validateFile(file);
    if (err) {
      updateZone(type, { error: err });
      e.target.value = '';
      return;
    }
    loadPreview(type, file);
    e.target.value = '';
  };

  // ─── Format Helpers ─────────────────────────────────────────────────
  const fmtDate = (iso: string | null) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch { return iso; }
  };

  const fmtDateTime = (iso: string | null) => {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }) +
        ' ' + d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
  };

  // ─── Render Upload Zone ─────────────────────────────────────────────
  const renderZone = (type: UploadType) => {
    const cfg = ZONE_CONFIG[type];
    const zone = zones[type];

    return (
      <div
        className="rounded-xl overflow-hidden"
        style={{
          background: '#1e293b',
          border: `1px solid ${zone.isDragging ? cfg.color : '#334155'}`,
          transition: 'border-color 0.2s, box-shadow 0.2s',
          boxShadow: zone.isDragging ? `0 0 24px ${cfg.colorDim}` : 'none',
          animation: 'fadeSlideUp 0.5s ease-out both',
          animationDelay: type === 'orders' ? '0.1s' : '0.2s',
        }}
      >
        {/* Zone Header */}
        <div
          className="px-5 py-4 flex items-center justify-between"
          style={{ borderBottom: `1px solid #33415580`, background: cfg.colorBg }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{
                background: cfg.color,
                boxShadow: `0 0 8px ${cfg.colorDim}`,
              }}
            />
            <div>
              <div className="text-sm font-semibold text-slate-200">{cfg.title}</div>
              <div className="text-[11px] text-slate-500 mt-0.5">{cfg.subtitle}</div>
            </div>
          </div>
          <a
            href={`/api/v1/data-import/template/${type}`}
            className="text-[11px] px-2.5 py-1 rounded-md transition-colors hover:opacity-80"
            style={{ color: cfg.color, background: cfg.colorDim, textDecoration: 'none' }}
          >
            Vorlage CSV
          </a>
        </div>

        {/* Zone Body */}
        <div className="p-5">
          {/* Required columns info */}
          <div className="mb-4 flex flex-wrap gap-1.5">
            {cfg.required.map(col => (
              <span
                key={col}
                className="text-[10px] font-mono px-2 py-0.5 rounded"
                style={{ background: '#0f172a', color: cfg.color, border: `1px solid ${cfg.colorDim}` }}
              >
                {col}
              </span>
            ))}
            {cfg.optional.map(col => (
              <span
                key={col}
                className="text-[10px] font-mono px-2 py-0.5 rounded"
                style={{ background: '#0f172a', color: '#64748b', border: '1px solid #334155' }}
              >
                {col}?
              </span>
            ))}
          </div>

          {/* STATE: Idle — Drop Zone */}
          {!zone.file && !zone.result && (
            <div
              className="relative rounded-lg cursor-pointer group"
              style={{
                border: `2px dashed ${zone.isDragging ? cfg.color : '#475569'}`,
                background: zone.isDragging ? cfg.colorBg : '#0f172a40',
                transition: 'all 0.2s',
                minHeight: 140,
              }}
              onDragOver={handleDragOver(type)}
              onDragLeave={handleDragLeave(type)}
              onDrop={handleDrop(type)}
              onClick={() => fileInputRefs[type].current?.click()}
            >
              <input
                ref={fileInputRefs[type]}
                type="file"
                accept=".csv,.xlsx"
                className="hidden"
                onChange={handleFileSelect(type)}
              />
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-4">
                {/* Upload Icon */}
                <svg
                  width="36" height="36" viewBox="0 0 24 24" fill="none"
                  stroke={zone.isDragging ? cfg.color : '#64748b'}
                  strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                  className="transition-colors"
                  style={{ opacity: zone.isDragging ? 1 : 0.7 }}
                >
                  <path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <div className="text-center">
                  <div className="text-xs text-slate-400 group-hover:text-slate-300 transition-colors">
                    {zone.isDragging ? (
                      <span style={{ color: cfg.color }}>Datei hier ablegen</span>
                    ) : (
                      <>Datei hierher ziehen oder <span style={{ color: cfg.color }}>durchsuchen</span></>
                    )}
                  </div>
                  <div className="text-[10px] text-slate-600 mt-1.5">CSV oder Excel — max. 10 MB</div>
                </div>
              </div>
            </div>
          )}

          {/* STATE: Loading Preview */}
          {zone.isLoadingPreview && (
            <div
              className="rounded-lg flex items-center justify-center gap-3 py-12"
              style={{ background: '#0f172a40', border: `1px solid ${cfg.colorDim}` }}
            >
              <div
                className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
                style={{ borderColor: `${cfg.color} transparent ${cfg.colorDim} ${cfg.colorDim}` }}
              />
              <span className="text-xs text-slate-400">Datei wird analysiert...</span>
            </div>
          )}

          {/* STATE: Preview */}
          {zone.preview && !zone.isUploading && !zone.result && (
            <div>
              {/* Validation Status */}
              <div
                className="rounded-lg px-4 py-3 mb-3 flex items-center gap-2"
                style={{
                  background: zone.preview.columns_valid ? '#10b98110' : '#ef444410',
                  border: `1px solid ${zone.preview.columns_valid ? '#10b98130' : '#ef444430'}`,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                  stroke={zone.preview.columns_valid ? '#10b981' : '#ef4444'}
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  {zone.preview.columns_valid ? (
                    <path d="M22 11.08V12a10 10 0 11-5.93-9.14M22 4L12 14.01l-3-3" />
                  ) : (
                    <><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></>
                  )}
                </svg>
                <div>
                  <div className="text-xs font-medium" style={{ color: zone.preview.columns_valid ? '#10b981' : '#ef4444' }}>
                    {zone.preview.columns_valid
                      ? `${zone.preview.filename} — ${zone.preview.total_rows} Zeilen erkannt`
                      : `Fehlende Spalten: ${zone.preview.missing_columns.join(', ')}`
                    }
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    Spalten: {zone.preview.columns.join(', ')}
                  </div>
                </div>
              </div>

              {/* Preview Table */}
              {zone.preview.preview.length > 0 && (
                <div className="rounded-lg overflow-hidden mb-3" style={{ border: '1px solid #334155' }}>
                  <div className="overflow-x-auto">
                    <table className="w-full text-[11px]">
                      <thead>
                        <tr style={{ background: '#0f172a' }}>
                          {zone.preview.columns.map(col => (
                            <th
                              key={col}
                              className="px-3 py-2 text-left font-mono font-medium"
                              style={{
                                color: cfg.required.includes(col) ? cfg.color
                                  : zone.preview!.missing_columns.includes(col) ? '#ef4444' : '#64748b',
                              }}
                            >
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {zone.preview.preview.map((row, i) => (
                          <tr
                            key={i}
                            style={{
                              background: i % 2 === 0 ? '#1e293b' : '#1a2536',
                              borderTop: '1px solid #33415540',
                            }}
                          >
                            {zone.preview!.columns.map(col => (
                              <td key={col} className="px-3 py-1.5 text-slate-400 font-mono whitespace-nowrap">
                                {row[col] || '—'}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2">
                {zone.preview.columns_valid && (
                  <button
                    onClick={() => doUpload(type)}
                    className="flex-1 py-2 rounded-lg text-xs font-medium text-white transition-opacity hover:opacity-90"
                    style={{ background: cfg.color }}
                  >
                    {zone.preview.total_rows} Zeilen importieren
                  </button>
                )}
                <button
                  onClick={() => resetZone(type)}
                  className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 transition-colors hover:text-slate-200"
                  style={{ background: '#0f172a', border: '1px solid #334155' }}
                >
                  Abbrechen
                </button>
              </div>
            </div>
          )}

          {/* STATE: Uploading */}
          {zone.isUploading && (
            <div
              className="rounded-lg flex flex-col items-center justify-center gap-3 py-10"
              style={{ background: '#0f172a40', border: `1px solid ${cfg.colorDim}` }}
            >
              <div className="relative w-10 h-10">
                <div
                  className="absolute inset-0 rounded-full border-2 border-t-transparent animate-spin"
                  style={{ borderColor: `${cfg.color} transparent ${cfg.colorDim} ${cfg.colorDim}` }}
                />
              </div>
              <span className="text-xs text-slate-400">Daten werden importiert...</span>
            </div>
          )}

          {/* STATE: Result */}
          {zone.result && (
            <div>
              <div
                className="rounded-lg px-4 py-4 mb-3"
                style={{
                  background: zone.result.success ? '#10b98108' : '#ef444408',
                  border: `1px solid ${zone.result.success ? '#10b98130' : '#ef444430'}`,
                }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke={zone.result.success ? '#10b981' : '#ef4444'}
                    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    {zone.result.success ? (
                      <path d="M22 11.08V12a10 10 0 11-5.93-9.14M22 4L12 14.01l-3-3" />
                    ) : (
                      <><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /></>
                    )}
                  </svg>
                  <span className="text-sm font-medium" style={{ color: zone.result.success ? '#10b981' : '#ef4444' }}>
                    {zone.result.success ? 'Import erfolgreich' : 'Import fehlgeschlagen'}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px] ml-6">
                  <div className="text-slate-500">Datei</div>
                  <div className="text-slate-300 font-mono">{zone.result.filename}</div>
                  <div className="text-slate-500">Format</div>
                  <div className="text-slate-300 font-mono uppercase">{zone.result.file_format}</div>
                  <div className="text-slate-500">Zeilen</div>
                  <div className="text-slate-300 font-mono">{zone.result.row_count.toLocaleString('de-DE')}</div>
                  {zone.result.date_range.start && (
                    <>
                      <div className="text-slate-500">Zeitraum</div>
                      <div className="text-slate-300 font-mono">
                        {fmtDate(zone.result.date_range.start)} — {fmtDate(zone.result.date_range.end)}
                      </div>
                    </>
                  )}
                  {Object.entries(zone.result.import_result).map(([k, v]) => (
                    <React.Fragment key={k}>
                      <div className="text-slate-500 capitalize">{k.replace(/_/g, ' ')}</div>
                      <div className="font-mono" style={{ color: cfg.color }}>{v}</div>
                    </React.Fragment>
                  ))}
                </div>
              </div>
              <button
                onClick={() => resetZone(type)}
                className="w-full py-2 rounded-lg text-xs font-medium text-slate-400 transition-colors hover:text-slate-200"
                style={{ background: '#0f172a', border: '1px solid #334155' }}
              >
                Weitere Datei hochladen
              </button>
            </div>
          )}

          {/* Error Display */}
          {zone.error && !zone.isLoadingPreview && !zone.isUploading && (
            <div
              className="mt-3 rounded-lg px-4 py-2.5 flex items-center gap-2"
              style={{ background: '#ef444410', border: '1px solid #ef444425' }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span className="text-[11px] text-red-400">{zone.error}</span>
            </div>
          )}
        </div>
      </div>
    );
  };

  // ─── Render ─────────────────────────────────────────────────────────
  return (
    <div style={{ background: '#0f172a', minHeight: '100vh' }}>
      <style>{`
        @keyframes fadeSlideUp {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes scanline {
          0% { background-position: 0 0; }
          100% { background-position: 0 4px; }
        }
      `}</style>

      {/* ─── Header ──────────────────────────────────────────────── */}
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
                Datenimport
              </h1>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Historische Daten hochladen — fließt in Confidence Score ein
              </p>
            </div>
          </div>

          {/* Data flow indicator */}
          <div className="hidden sm:flex items-center gap-2 text-[10px] text-slate-600">
            <span className="px-2 py-0.5 rounded" style={{ background: '#0f172a', border: '1px solid #334155' }}>
              Upload
            </span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#475569" strokeWidth="2">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
            <span className="px-2 py-0.5 rounded" style={{ background: '#0f172a', border: '1px solid #334155' }}>
              Fusion Engine
            </span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#475569" strokeWidth="2">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
            <span className="px-2 py-0.5 rounded" style={{ background: '#10b98115', border: '1px solid #10b98130', color: '#10b981' }}>
              Confidence Score
            </span>
          </div>
        </div>
      </header>

      {/* ─── Main Content ────────────────────────────────────────── */}
      <main className="max-w-[1400px] mx-auto px-6 py-8">

        {/* Upload Zones */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
          {renderZone('orders')}
          {renderZone('lab_results')}
        </div>

        {/* ─── Upload History ──────────────────────────────────── */}
        <div
          className="rounded-xl overflow-hidden"
          style={{
            background: '#1e293b',
            border: '1px solid #334155',
            animation: 'fadeSlideUp 0.5s ease-out 0.35s both',
          }}
        >
          <div
            className="px-5 py-3.5 flex items-center justify-between"
            style={{ borderBottom: '1px solid #33415580' }}
          >
            <div className="flex items-center gap-2.5">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-sm font-medium text-slate-300">Upload-Verlauf</span>
              <span className="text-[10px] text-slate-600 font-mono">({history.length})</span>
            </div>
            <button
              onClick={fetchHistory}
              className="text-[10px] text-slate-600 hover:text-slate-400 transition-colors"
            >
              Aktualisieren
            </button>
          </div>

          {historyLoading ? (
            <div className="py-12 flex justify-center">
              <div className="w-5 h-5 rounded-full border-2 border-slate-600 border-t-slate-400 animate-spin" />
            </div>
          ) : history.length === 0 ? (
            <div className="py-12 text-center">
              <div className="text-xs text-slate-600">Noch keine Uploads vorhanden</div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr style={{ background: '#0f172a' }}>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-500">Datum</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-500">Dateiname</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-500">Typ</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-500">Format</th>
                    <th className="px-4 py-2.5 text-right font-medium text-slate-500">Zeilen</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-500">Zeitraum</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-500">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((entry, i) => {
                    const status = STATUS_STYLES[entry.status] || STATUS_STYLES.error;
                    const typeCfg = ZONE_CONFIG[entry.upload_type as UploadType];
                    return (
                      <tr
                        key={entry.id}
                        style={{
                          background: i % 2 === 0 ? '#1e293b' : '#1a2536',
                          borderTop: '1px solid #33415530',
                        }}
                      >
                        <td className="px-4 py-2 text-slate-400 font-mono whitespace-nowrap">
                          {fmtDateTime(entry.created_at)}
                        </td>
                        <td className="px-4 py-2 text-slate-300 font-mono max-w-[200px] truncate">
                          {entry.filename}
                        </td>
                        <td className="px-4 py-2">
                          <span
                            className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                            style={{
                              color: typeCfg?.color || '#94a3b8',
                              background: (typeCfg?.colorDim || '#94a3b840'),
                            }}
                          >
                            {entry.upload_type === 'orders' ? 'Bestellungen' : 'Laborergebnisse'}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-slate-500 font-mono uppercase">{entry.file_format}</td>
                        <td className="px-4 py-2 text-slate-300 font-mono text-right">
                          {entry.row_count?.toLocaleString('de-DE') || '—'}
                        </td>
                        <td className="px-4 py-2 text-slate-500 font-mono whitespace-nowrap">
                          {entry.date_range_start
                            ? `${fmtDate(entry.date_range_start)} — ${fmtDate(entry.date_range_end)}`
                            : '—'
                          }
                        </td>
                        <td className="px-4 py-2">
                          <span
                            className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                            style={{ color: status.color, background: status.bg }}
                            title={entry.error_message || undefined}
                          >
                            {status.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer info */}
        <div className="mt-6 text-center text-[10px] text-slate-600">
          Hochgeladene Daten fließen beim nächsten Score-Update automatisch in die Fusion Engine ein.
          Bestelldaten erhöhen den Confidence Score, Laborergebnisse verbessern die Baseline-Korrektur.
        </div>
      </main>
    </div>
  );
};

export default Datenimport;
