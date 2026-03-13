import React, { useMemo } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { BacktestChartPoint, BacktestResponse } from '../../types/media';
import {
  VIRUS_OPTIONS,
  formatDateShort,
  formatDateTime,
  formatPercent,
} from './cockpitUtils';

interface ValidationRow extends BacktestChartPoint {
  actual?: number | null;
  model?: number | null;
  forecast?: number | null;
  seasonal?: number | null;
  persistence?: number | null;
  dateLabel: string;
  ci80Base?: number | null;
  ci80Range?: number | null;
  ci95Base?: number | null;
  ci95Range?: number | null;
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

function buildValidationRows(result: BacktestResponse | null, maxPoints = 84): ValidationRow[] {
  const source = [...(result?.chart_data || [])]
    .filter((point) => point?.date)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));

  return source.slice(-maxPoints).map((point) => ({
    ...point,
    actual: point.real_qty ?? null,
    model: point.predicted_qty ?? null,
    forecast: point.forecast_qty ?? null,
    seasonal: point.baseline_seasonal ?? null,
    persistence: point.baseline_persistence ?? null,
    ci80Base: point.ci_80_lower ?? null,
    ci80Range: isNumber(point.ci_80_lower) && isNumber(point.ci_80_upper)
      ? point.ci_80_upper - point.ci_80_lower
      : null,
    ci95Base: point.ci_95_lower ?? null,
    ci95Range: isNumber(point.ci_95_lower) && isNumber(point.ci_95_upper)
      ? point.ci_95_upper - point.ci_95_lower
      : null,
    dateLabel: formatDateShort(point.date),
  }));
}

function waveValue(row: ValidationRow): number | null {
  if (isNumber(row.actual)) return row.actual;
  if (isNumber(row.forecast)) return row.forecast;
  if (isNumber(row.model)) return row.model;
  return null;
}

function detectWaveMarkers(rows: ValidationRow[]) {
  if (!rows.length) {
    return {
      currentIndex: -1,
      startIndex: -1,
      peakIndex: -1,
      cooldownIndex: -1,
      narrative: 'Noch keine Kurve verfügbar.',
    };
  }

  const historicalValues = rows
    .map((row) => row.actual)
    .filter(isNumber);
  const baseline = median(historicalValues);
  const currentIndex = Math.max(
    0,
    rows.reduce((latest, row, index) => (isNumber(row.actual) ? index : latest), -1),
  );

  const futureRange = rows
    .map((row, index) => ({ row, index }))
    .filter(({ index, row }) => index >= currentIndex && isNumber(waveValue(row)));
  const peakEntry = futureRange.reduce<{ index: number; value: number } | null>((best, entry) => {
    const value = waveValue(entry.row);
    if (!isNumber(value)) return best;
    if (!best || value > best.value) return { index: entry.index, value };
    return best;
  }, null);
  const peakIndex = peakEntry?.index ?? currentIndex;
  const peakValue = peakEntry?.value ?? baseline;

  let startIndex = Math.max(0, currentIndex - 4);
  for (let index = Math.max(1, peakIndex - 12); index <= Math.min(currentIndex, peakIndex - 2); index += 1) {
    const current = waveValue(rows[index]);
    const next = waveValue(rows[index + 1]);
    const nextTwo = waveValue(rows[index + 2]);
    if (!isNumber(current) || !isNumber(next) || !isNumber(nextTwo)) continue;
    if (nextTwo > current * 1.12 && next >= current * 0.98 && current >= baseline * 0.8) {
      startIndex = index;
      break;
    }
  }

  let cooldownIndex = rows.length - 1;
  for (let index = peakIndex + 1; index < rows.length; index += 1) {
    const value = waveValue(rows[index]);
    if (isNumber(value) && peakValue > 0 && value <= peakValue * 0.82) {
      cooldownIndex = index;
      break;
    }
  }

  const startDate = rows[startIndex]?.dateLabel || '-';
  const currentDate = rows[currentIndex]?.dateLabel || '-';
  const peakDate = rows[peakIndex]?.dateLabel || '-';
  const cooldownDate = rows[cooldownIndex]?.dateLabel || '-';

  const currentValue = waveValue(rows[currentIndex]) ?? 0;
  const direction = peakValue > currentValue * 1.08
    ? `Die Welle startet ab ${startDate}, baut sich über ${currentDate} weiter auf und peakt voraussichtlich um ${peakDate}.`
    : `Die Welle ist ab ${startDate} sichtbar, liegt um ${currentDate} im Fokus und stabilisiert sich rund um ${peakDate}.`;
  const tail = cooldownIndex > peakIndex
    ? ` Danach erwarten wir eine Abschwächung Richtung ${cooldownDate}.`
    : '';

  return {
    currentIndex,
    startIndex,
    peakIndex,
    cooldownIndex,
    narrative: `${direction}${tail}`,
  };
}

interface WaveOutlookPanelProps {
  virus: string;
  onVirusChange: (value: string) => void;
  result: BacktestResponse | null;
  loading: boolean;
}

export const WaveOutlookPanel: React.FC<WaveOutlookPanelProps> = ({
  virus,
  onVirusChange,
  result,
  loading,
}) => {
  const rows = useMemo(() => buildValidationRows(result, 36), [result]);
  const markers = useMemo(() => detectWaveMarkers(rows), [rows]);
  const targetLabel = result?.target_label || result?.target_source || 'Market Check';
  const selectedVirus = result?.virus_typ || virus;

  if (loading) {
    return (
      <div className="card" style={{ padding: 20, color: 'var(--text-muted)' }}>
        Wellenentwicklung wird geladen...
      </div>
    );
  }

  if (rows.length < 4) {
    return (
      <div className="card" style={{ padding: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>Wellenentwicklung</h2>
        <div className="soft-panel" style={{ padding: 20, marginTop: 14, color: 'var(--text-muted)' }}>
          Noch keine ausreichend detaillierten Forecast-Daten für die Wellenkurve verfügbar.
        </div>
      </div>
    );
  }

  const startDate = rows[markers.startIndex]?.dateLabel || '-';
  const currentDate = rows[markers.currentIndex]?.dateLabel || '-';
  const peakDate = rows[markers.peakIndex]?.dateLabel || '-';
  const cooldownDate = rows[markers.cooldownIndex]?.dateLabel || '-';

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>Wellenentwicklung</h2>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
            Gezeigt wird die epidemiologische Welle für {selectedVirus} im Signalraum {targetLabel}. Die Kurve beschreibt Virusaktivität und Forecast, nicht die Nachfrage eines einzelnen Produkts.
          </p>
        </div>
        <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-muted)' }}>
          {targetLabel}
        </div>
      </div>

      <div className="review-chip-row" style={{ marginBottom: 16 }}>
        {VIRUS_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onVirusChange(option)}
            className={`tab-chip ${option === selectedVirus ? 'active' : ''}`}
          >
            {option}
          </button>
        ))}
      </div>

      <div className="soft-panel" style={{ padding: 14, marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
        Die markierten Punkte zeigen den geschätzten Beginn, den aktuellen Stand und den erwarteten Peak der {selectedVirus}-Welle. Produktvorschläge entstehen erst im nächsten Schritt aus dieser Viruslage plus Region, Forecast und Versorgung.
      </div>

      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', marginBottom: 16 }}>
        {[
          { label: 'Welle beginnt', value: startDate, tone: '#2aa198' },
          { label: 'Wir stehen hier', value: currentDate, tone: '#0a84ff' },
          { label: 'Erwarteter Peak', value: peakDate, tone: '#ff453a' },
          { label: 'Rückgang', value: cooldownDate, tone: '#ff9f0a' },
        ].map((item) => (
          <div key={item.label} className="soft-panel" style={{ padding: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              {item.label}
            </div>
            <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: item.tone }}>
              {item.value}
            </div>
          </div>
        ))}
      </div>

      <div style={{ height: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.22)" />
            <XAxis dataKey="dateLabel" tick={{ fill: '#64748b', fontSize: 11 }} />
            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
            <Tooltip />
            <Legend />

            <ReferenceArea
              x1={rows[markers.currentIndex]?.dateLabel}
              x2={rows[rows.length - 1]?.dateLabel}
              fill="rgba(10, 132, 255, 0.06)"
            />
            <ReferenceLine x={rows[markers.startIndex]?.dateLabel} stroke="#2aa198" strokeDasharray="4 4" label={{ value: 'Beginn', position: 'top', fill: '#2aa198', fontSize: 10 }} />
            <ReferenceLine x={rows[markers.currentIndex]?.dateLabel} stroke="#0a84ff" strokeDasharray="4 4" label={{ value: 'Jetzt', position: 'top', fill: '#0a84ff', fontSize: 10 }} />
            <ReferenceLine x={rows[markers.peakIndex]?.dateLabel} stroke="#ff453a" strokeDasharray="4 4" label={{ value: 'Peak', position: 'top', fill: '#ff453a', fontSize: 10 }} />

            <Area type="monotone" dataKey="ci95Base" stackId="ci95" stroke="none" fill="transparent" activeDot={false} legendType="none" />
            <Area type="monotone" dataKey="ci95Range" stackId="ci95" stroke="none" fill="rgba(59,130,246,0.08)" activeDot={false} legendType="none" />
            <Area type="monotone" dataKey="ci80Base" stackId="ci80" stroke="none" fill="transparent" activeDot={false} legendType="none" />
            <Area type="monotone" dataKey="ci80Range" stackId="ci80" stroke="none" fill="rgba(59,130,246,0.18)" activeDot={false} legendType="none" />

            <Line type="monotone" dataKey="actual" name="Ist-Wert" stroke="#0a84ff" strokeWidth={2.5} dot={false} />
            <Line type="monotone" dataKey="model" name="Validierte Prognose" stroke="#475569" strokeWidth={1.8} dot={false} strokeDasharray="5 4" />
            <Line type="monotone" dataKey="forecast" name="Ausblick" stroke="#5e5ce6" strokeWidth={2.8} dot={false} />
            <Line type="monotone" dataKey="seasonal" name="Saison-Baseline" stroke="#ff9f0a" strokeWidth={1.6} dot={false} strokeDasharray="3 3" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p style={{ margin: '14px 0 0', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
        {markers.narrative}
      </p>
      <p style={{ margin: '8px 0 0', fontSize: 12, lineHeight: 1.6, color: 'var(--text-muted)' }}>
        Wenn du zwischen Viren wechselst, lädt diese Kurve die passende Welle neu. Eine Produktansicht wäre fachlich eine andere Kurve und ist hier aktuell noch nicht hinterlegt.
      </p>
    </div>
  );
};

interface ValidationSectionProps {
  title: string;
  subtitle: string;
  result: BacktestResponse | null;
  loading: boolean;
  emptyMessage: string;
}

export const ValidationSection: React.FC<ValidationSectionProps> = ({
  title,
  subtitle,
  result,
  loading,
  emptyMessage,
}) => {
  const rows = useMemo(() => buildValidationRows(result, 72), [result]);
  const hasBio = rows.some((row) => isNumber(row.bio));
  const chartReady = rows.some((row) => isNumber(row.actual) || isNumber(row.model));
  const decisionMetrics = result?.decision_metrics;
  const metrics = result?.metrics;

  return (
    <div className="card" style={{ padding: 20, display: 'grid', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>{title}</h2>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>{subtitle}</p>
        </div>
        <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-muted)' }}>
          {result?.created_at ? formatDateTime(result.created_at) : '-'}
        </div>
      </div>

      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
        <div className="metric-box">
          <span>R²</span>
          <strong>{metrics?.r2_score != null ? metrics.r2_score.toFixed(2) : '-'}</strong>
        </div>
        <div className="metric-box">
          <span>Korrelation</span>
          <strong>{formatPercent((metrics?.correlation_pct ?? ((metrics?.correlation ?? 0) * 100)) as number)}</strong>
        </div>
        <div className="metric-box">
          <span>Datenpunkte</span>
          <strong>{metrics?.data_points ?? rows.length}</strong>
        </div>
        {decisionMetrics ? (
          <div className="metric-box">
            <span>Hit-Rate</span>
            <strong>{formatPercent(decisionMetrics.hit_rate_pct || 0)}</strong>
          </div>
        ) : (
          <div className="metric-box">
            <span>sMAPE</span>
            <strong>{metrics?.smape != null ? `${metrics.smape.toFixed(1)}%` : '-'}</strong>
          </div>
        )}
      </div>

      {loading ? (
        <div className="soft-panel" style={{ padding: 24, color: 'var(--text-muted)' }}>
          Validierungsdaten werden geladen...
        </div>
      ) : chartReady ? (
        <div style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.22)" />
              <XAxis dataKey="dateLabel" tick={{ fill: '#64748b', fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fill: '#64748b', fontSize: 11 }} />
              {hasBio && <YAxis yAxisId="right" orientation="right" tick={{ fill: '#64748b', fontSize: 11 }} />}
              <Tooltip />
              <Legend />

              <Line yAxisId="left" type="monotone" dataKey="actual" name="Ist" stroke="#0a84ff" strokeWidth={2.5} dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="model" name="Modell" stroke="#5e5ce6" strokeWidth={2.2} dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="seasonal" name="Saison-Baseline" stroke="#ff9f0a" strokeWidth={1.6} dot={false} strokeDasharray="3 3" />
              <Line yAxisId="left" type="monotone" dataKey="persistence" name="Persistence" stroke="#64748b" strokeWidth={1.4} dot={false} strokeDasharray="3 3" />
              {hasBio && <Line yAxisId="right" type="monotone" dataKey="bio" name="Bio-Signal" stroke="#7c3aed" strokeWidth={1.8} dot={false} />}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="soft-panel" style={{ padding: 24, color: 'var(--text-muted)' }}>
          {emptyMessage}
        </div>
      )}

      {(result?.proof_text || result?.llm_insight) && (
        <div className="soft-panel" style={{ padding: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Interpretation</div>
          <div style={{ marginTop: 6, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            {result?.proof_text || result?.llm_insight}
          </div>
        </div>
      )}
    </div>
  );
};
