import React, { useMemo } from 'react';
import { isBefore, parseISO } from 'date-fns';
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

import {
  BacktestChartPoint,
  BacktestResponse,
  RegionalBacktestResponse,
  RegionalForecastPrediction,
} from '../../types/media';
import {
  VIRUS_OPTIONS,
  formatDateShort,
  formatDateTime,
  formatPercent,
} from './cockpitUtils';
import { sanitizeEvidenceCopy } from './evidence/evidenceUtils';

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

interface WaveMarkers {
  lastObservedIndex: number;
  startIndex: number;
  peakIndex: number;
  cooldownIndex: number;
  lastValuedIndex: number;
  hasProjectedDataAfterObservation: boolean;
  narrative: string;
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

export function buildValidationRows(result: BacktestResponse | null, maxPoints = 84): ValidationRow[] {
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

function parseDate(value?: string | null): Date | null {
  if (!value) return null;
  try {
    return parseISO(value);
  } catch {
    return null;
  }
}

export function detectWaveMarkers(rows: ValidationRow[]): WaveMarkers {
  if (!rows.length) {
    return {
      lastObservedIndex: -1,
      startIndex: -1,
      peakIndex: -1,
      cooldownIndex: -1,
      lastValuedIndex: -1,
      hasProjectedDataAfterObservation: false,
      narrative: 'Noch keine Kurve verfügbar.',
    };
  }

  const historicalValues = rows
    .map((row) => row.actual)
    .filter(isNumber);
  const baseline = median(historicalValues);
  const rawLastObservedIndex = rows.reduce((latest, row, index) => (isNumber(row.actual) ? index : latest), -1);
  const valuedRows = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => isNumber(waveValue(row)));
  const lastValuedIndex = valuedRows.length ? valuedRows[valuedRows.length - 1].index : Math.max(0, rawLastObservedIndex);
  const lastObservedIndex = rawLastObservedIndex >= 0 ? rawLastObservedIndex : lastValuedIndex;
  const anchorIndex = Math.max(0, valuedRows.length ? lastObservedIndex : 0);

  const futureRange = valuedRows.filter(({ index }) => index >= anchorIndex);
  const peakEntry = futureRange.reduce<{ index: number; value: number } | null>((best, entry) => {
    const value = waveValue(entry.row);
    if (!isNumber(value)) return best;
    if (!best || value > best.value) return { index: entry.index, value };
    return best;
  }, null);
  const peakIndex = peakEntry?.index ?? anchorIndex;
  const peakValue = peakEntry?.value ?? baseline;

  let startIndex = Math.max(0, lastObservedIndex - 4);
  for (let index = Math.max(1, peakIndex - 12); index <= Math.min(lastObservedIndex, peakIndex - 2); index += 1) {
    const current = waveValue(rows[index]);
    const next = waveValue(rows[index + 1]);
    const nextTwo = waveValue(rows[index + 2]);
    if (!isNumber(current) || !isNumber(next) || !isNumber(nextTwo)) continue;
    if (nextTwo > current * 1.12 && next >= current * 0.98 && current >= baseline * 0.8) {
      startIndex = index;
      break;
    }
  }

  let cooldownIndex = lastValuedIndex;
  for (let index = peakIndex + 1; index <= lastValuedIndex; index += 1) {
    const value = waveValue(rows[index]);
    if (isNumber(value) && peakValue > 0 && value <= peakValue * 0.82) {
      cooldownIndex = index;
      break;
    }
  }

  const startDate = rows[startIndex]?.dateLabel || '-';
  const observedDate = rows[lastObservedIndex]?.dateLabel || '-';
  const peakDate = rows[peakIndex]?.dateLabel || '-';
  const cooldownDate = rows[cooldownIndex]?.dateLabel || '-';

  const observedValue = waveValue(rows[lastObservedIndex]) ?? 0;
  const hasProjectedDataAfterObservation = peakIndex > lastObservedIndex || lastValuedIndex > lastObservedIndex;

  let narrative = `Die sichtbare Kurve reicht bis zum letzten beobachteten Stand vom ${observedDate}.`;
  if (hasProjectedDataAfterObservation && peakValue > observedValue * 1.08) {
    narrative = `Die Welle ist seit ${startDate} sichtbar. Der letzte beobachtete Stand stammt vom ${observedDate}; im Modell peakt sie voraussichtlich um ${peakDate}.`;
  } else if (hasProjectedDataAfterObservation) {
    narrative = `Die Welle ist seit ${startDate} sichtbar. Der letzte beobachtete Stand stammt vom ${observedDate}; danach stabilisiert sich die modellierte Kurve rund um ${peakDate}.`;
  }
  if (!hasProjectedDataAfterObservation) {
    narrative = `${narrative} Danach liegen in diesem Run keine weiteren befüllten Punkte vor.`;
  } else if (cooldownIndex > peakIndex) {
    narrative = `${narrative} Danach erwarten wir eine Abschwächung Richtung ${cooldownDate}.`;
  }

  return {
    lastObservedIndex,
    startIndex,
    peakIndex,
    cooldownIndex,
    lastValuedIndex,
    hasProjectedDataAfterObservation,
    narrative,
  };
}

export function getWaveFreshnessHint(
  rows: ValidationRow[],
  markers: WaveMarkers,
  now: Date = new Date(),
): string | null {
  if (markers.lastObservedIndex < 0 || !rows.length) return null;
  const observedRow = rows[markers.lastObservedIndex];
  const observedDate = parseDate(observedRow?.date);
  const lastRowDate = parseDate(rows[rows.length - 1]?.date);
  const hasTrailingEmptySlots = markers.lastValuedIndex >= 0 && markers.lastValuedIndex < rows.length - 1;

  if (!observedDate) {
    return hasTrailingEmptySlots
      ? 'Nach dem letzten beobachteten Wert folgen in diesem Run noch unbelegte Datums-Slots.'
      : null;
  }

  if (hasTrailingEmptySlots || isBefore(observedDate, now) || (lastRowDate && isBefore(observedDate, lastRowDate))) {
    return `Letzte Beobachtung: ${observedRow.dateLabel}. Danach liegen in diesem Run noch keine Ist-Werte vor.`;
  }
  return null;
}

interface WaveOutlookPanelProps {
  virus: string;
  onVirusChange: (value: string) => void;
  result: BacktestResponse | null;
  loading: boolean;
  showVirusSelector?: boolean;
  title?: string;
  subtitle?: string;
}

interface FocusRegionChartRow {
  date: string;
  dateLabel: string;
  actual?: number | null;
  validated?: number | null;
  forecast?: number | null;
  bandBase?: number | null;
  bandRange?: number | null;
}

interface FocusRegionOutlookPanelProps {
  prediction: RegionalForecastPrediction | null;
  backtest: RegionalBacktestResponse | null;
  loading: boolean;
  horizonDays: number;
}

function formatVirusLevel(value?: number | null, digits = 1): string {
  if (!isNumber(value)) return '-';
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function normalizeIsoDate(value?: string | null): string | null {
  if (!value) return null;
  try {
    return parseISO(value).toISOString().slice(0, 10);
  } catch {
    return null;
  }
}

function addRegionPoint(
  store: Map<string, FocusRegionChartRow>,
  date: string,
  patch: Partial<FocusRegionChartRow>,
) {
  const existing = store.get(date) || {
    date,
    dateLabel: formatDateShort(date),
  };
  store.set(date, {
    ...existing,
    ...patch,
  });
}

function buildFocusRegionChartRows(
  prediction: RegionalForecastPrediction | null,
  backtest: RegionalBacktestResponse | null,
): FocusRegionChartRow[] {
  const rows = new Map<string, FocusRegionChartRow>();
  const timeline = [...(backtest?.timeline || [])].sort((left, right) => (
    String(left.as_of_date).localeCompare(String(right.as_of_date))
  ));

  timeline.slice(-12).forEach((entry) => {
    const actualDate = normalizeIsoDate(entry.as_of_date);
    if (actualDate) {
      addRegionPoint(rows, actualDate, {
        actual: entry.current_known_incidence,
      });
    }

    const targetDate = normalizeIsoDate(entry.target_date);
    if (targetDate) {
      addRegionPoint(rows, targetDate, {
        validated: entry.expected_target_incidence,
      });
    }
  });

  const currentDate = normalizeIsoDate(prediction?.last_data_date || prediction?.as_of_date);
  const targetDate = normalizeIsoDate(prediction?.target_date);
  const currentValue = prediction?.current_known_incidence;
  const forecastValue = prediction?.expected_target_incidence;
  const intervalLower = prediction?.prediction_interval?.lower;
  const intervalUpper = prediction?.prediction_interval?.upper;

  if (currentDate && isNumber(currentValue)) {
    addRegionPoint(rows, currentDate, {
      actual: currentValue,
      forecast: currentValue,
      bandBase: currentValue,
      bandRange: 0,
    });
  }

  if (targetDate && isNumber(forecastValue)) {
    addRegionPoint(rows, targetDate, {
      forecast: forecastValue,
      bandBase: isNumber(intervalLower) ? intervalLower : forecastValue,
      bandRange: isNumber(intervalLower) && isNumber(intervalUpper)
        ? Math.max(intervalUpper - intervalLower, 0)
        : 0,
    });
  }

  return Array.from(rows.values())
    .sort((left, right) => String(left.date).localeCompare(String(right.date)))
    .slice(-14);
}

function describeForecastDelta(prediction: RegionalForecastPrediction | null): string {
  if (!prediction || !isNumber(prediction.current_known_incidence) || !isNumber(prediction.expected_target_incidence)) {
    return 'nahe am letzten bestätigten Stand';
  }
  const current = Math.max(prediction.current_known_incidence, 0.0001);
  const changePct = ((prediction.expected_target_incidence - prediction.current_known_incidence) / current) * 100;
  const intensity = Math.abs(changePct) >= 25 ? 'deutlich' : Math.abs(changePct) >= 8 ? 'leicht' : 'nahe';

  if (Math.abs(changePct) < 5) {
    return 'nahe am letzten bestätigten Stand';
  }
  if (changePct > 0) {
    return `${intensity} über dem letzten bestätigten Stand`;
  }
  return `${intensity} unter dem letzten bestätigten Stand`;
}

function buildUncertaintyText(prediction: RegionalForecastPrediction | null): string {
  if (!prediction) {
    return 'Die Richtung bleibt erkennbar, die genaue Höhe können wir gerade noch nicht sauber einordnen.';
  }
  const lower = prediction.prediction_interval?.lower;
  const upper = prediction.prediction_interval?.upper;
  const mid = prediction.expected_target_incidence;
  const gatePassed = Boolean((prediction.quality_gate as { overall_passed?: boolean } | undefined)?.overall_passed);

  if (isNumber(lower) && isNumber(upper) && isNumber(mid) && mid > 0) {
    const widthRatio = Math.max(upper - lower, 0) / mid;
    if (gatePassed || widthRatio <= 0.35) {
      return 'Die Richtung ist belastbar, die genaue Höhe bleibt ein Forecast.';
    }
    if (widthRatio <= 0.7) {
      return 'Die Richtung ist erkennbar, die genaue Höhe bleibt ein Forecast.';
    }
  }
  return 'Die Richtung ist sichtbar, die genaue Höhe bleibt noch unsicher.';
}

export const FocusRegionOutlookPanel: React.FC<FocusRegionOutlookPanelProps> = ({
  prediction,
  backtest,
  loading,
  horizonDays,
}) => {
  const rows = useMemo(() => buildFocusRegionChartRows(prediction, backtest), [prediction, backtest]);
  const regionName = prediction?.bundesland_name || backtest?.bundesland_name || 'deine Fokusregion';
  const currentDate = formatDateShort(prediction?.last_data_date || prediction?.as_of_date);
  const targetDate = formatDateShort(prediction?.target_date);
  const deltaText = describeForecastDelta(prediction);
  const uncertaintyText = buildUncertaintyText(prediction);
  const hasHistorical = rows.some((row) => isNumber(row.actual));
  const hasForecast = rows.some((row) => isNumber(row.forecast));
  const chartReady = rows.length >= 2 && (hasHistorical || hasForecast);

  if (loading) {
    return (
      <div className="card" style={{ padding: 20, color: 'var(--text-muted)' }}>
        Fokusregion-Ausblick wird geladen...
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>Fokusregion in {horizonDays} Tagen</h2>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
            Hier sieht der Kunde die wichtigste Region zuerst. Der Satz oben sagt sofort, wo der Viruslage-Wert in {horizonDays} Tagen ungefähr stehen soll.
          </p>
        </div>
        <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-muted)' }}>
          {regionName}
        </div>
      </div>

      <div className="soft-panel" style={{ padding: 18, marginBottom: 16 }}>
        <p style={{ margin: 0, fontSize: 18, lineHeight: 1.5, color: 'var(--text-primary)', fontWeight: 800 }}>
          {prediction
            ? `In ${horizonDays} Tagen erwarten wir für ${regionName} einen Viruslage-Wert von ca. ${formatVirusLevel(prediction.expected_target_incidence)}, also ${deltaText}.`
            : `Für ${regionName} können wir gerade noch keine klare ${horizonDays}-Tage-Aussage formulieren.`}
        </p>
        <p style={{ margin: '10px 0 0', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          {prediction
            ? `Letzter bestätigter Ist-Wert vom ${currentDate}. Forecast-Ziel für ${targetDate}.`
            : 'Sobald ein frischer Forecast vorliegt, zeigen wir hier den Zieltag und den letzten bestätigten Stand.'}
        </p>
        <p style={{ margin: '8px 0 0', fontSize: 13, lineHeight: 1.6, color: 'var(--text-muted)' }}>
          {uncertaintyText}
        </p>
      </div>

      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', marginBottom: 16 }}>
        <div className="soft-panel" style={{ padding: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Fokusregion
          </div>
          <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
            {regionName}
          </div>
        </div>
        <div className="soft-panel" style={{ padding: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Letzter bestätigter Wert
          </div>
          <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: '#0a84ff' }}>
            {formatVirusLevel(prediction?.current_known_incidence)}
          </div>
        </div>
        <div className="soft-panel" style={{ padding: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Ziel in {horizonDays} Tagen
          </div>
          <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: '#5e5ce6' }}>
            {formatVirusLevel(prediction?.expected_target_incidence)}
          </div>
        </div>
        <div className="soft-panel" style={{ padding: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Bandbreite
          </div>
          <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
            {isNumber(prediction?.prediction_interval?.lower) && isNumber(prediction?.prediction_interval?.upper)
              ? `${formatVirusLevel(prediction?.prediction_interval?.lower)} bis ${formatVirusLevel(prediction?.prediction_interval?.upper)}`
              : '-'}
          </div>
        </div>
      </div>

      {chartReady ? (
        <div style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.22)" />
              <XAxis dataKey="dateLabel" tick={{ fill: '#64748b', fontSize: 11 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
              <Tooltip />
              <Legend />

              <ReferenceArea
                x1={formatDateShort(prediction?.last_data_date || prediction?.as_of_date)}
                x2={formatDateShort(prediction?.target_date)}
                fill="rgba(94, 92, 230, 0.05)"
              />
              <ReferenceLine
                x={formatDateShort(prediction?.last_data_date || prediction?.as_of_date)}
                stroke="#0a84ff"
                strokeDasharray="4 4"
                label={{ value: 'Bestätigt bis hier', position: 'top', fill: '#0a84ff', fontSize: 10 }}
              />
              <ReferenceLine
                x={formatDateShort(prediction?.target_date)}
                stroke="#5e5ce6"
                strokeDasharray="4 4"
                label={{ value: `+${horizonDays} Tage`, position: 'top', fill: '#5e5ce6', fontSize: 10 }}
              />

              <Area type="monotone" dataKey="bandBase" stackId="forecastBand" stroke="none" fill="transparent" activeDot={false} legendType="none" />
              <Area type="monotone" dataKey="bandRange" stackId="forecastBand" stroke="none" fill="rgba(94,92,230,0.16)" activeDot={false} name="Bandbreite" />

              <Line type="monotone" dataKey="actual" name="Ist-Wert" stroke="#0a84ff" strokeWidth={2.6} dot={false} />
              <Line type="monotone" dataKey="validated" name={`Validierter ${horizonDays}-Tage-Blick`} stroke="#475569" strokeWidth={1.7} dot={false} strokeDasharray="5 4" />
              <Line type="monotone" dataKey="forecast" name={`${horizonDays}-Tage-Ausblick`} stroke="#5e5ce6" strokeWidth={3} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="soft-panel" style={{ padding: 20, color: 'var(--text-muted)' }}>
          {`Für die Fokusregion fehlen gerade ausreichende Verlaufsdaten. Die ${horizonDays}-Tage-Aussage oben bleibt trotzdem sichtbar.`}
        </div>
      )}

      <div className="workspace-note-list" style={{ marginTop: 16 }}>
        <div className="workspace-note-card">
          {`Bestätigte Daten links, aktueller Forecast rechts: So sieht der Kunde sofort, was schon beobachtet ist und was unser ${horizonDays}-Tage-Ausblick ist.`}
        </div>
        {!backtest?.timeline?.length ? (
          <div className="workspace-note-card">
            Für den sauberen regionalen Rückblick fehlen gerade ausreichend historische Punkte. Deshalb zeigen wir den Fokus hier stärker über den aktuellen Forecast.
          </div>
        ) : null}
      </div>
    </div>
  );
};

export const WaveOutlookPanel: React.FC<WaveOutlookPanelProps> = ({
  virus,
  onVirusChange,
  result,
  loading,
  showVirusSelector = true,
  title = 'Letzte validierte Marktansicht',
  subtitle,
}) => {
  const rows = useMemo(() => buildValidationRows(result, 36), [result]);
  const markers = useMemo(() => detectWaveMarkers(rows), [rows]);
  const freshnessHint = useMemo(() => getWaveFreshnessHint(rows, markers), [rows, markers]);
  const targetLabel = result?.target_label || result?.target_source || 'Market Check';
  const selectedVirus = result?.virus_typ || virus;
  const effectiveSubtitle = subtitle || `Hier siehst du den zuletzt validierten Verlauf für ${selectedVirus}. Die Karte ist ein ehrlicher Rückblick bis zum letzten bestätigten Ist-Wert und kein Live-Ticker von heute.`;

  if (loading) {
    return (
      <div className="card" style={{ padding: 20, color: 'var(--text-muted)' }}>
        Validierte Marktansicht wird geladen...
      </div>
    );
  }

  if (rows.length < 4) {
    return (
      <div className="card" style={{ padding: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>{title}</h2>
        <div className="soft-panel" style={{ padding: 20, marginTop: 14, color: 'var(--text-muted)' }}>
          Noch keine ausreichend detaillierten Validierungsdaten für diese Rückblick-Kurve verfügbar.
        </div>
      </div>
    );
  }

  const startDate = rows[markers.startIndex]?.dateLabel || '-';
  const observedDate = rows[markers.lastObservedIndex]?.dateLabel || '-';
  const peakDate = rows[markers.peakIndex]?.dateLabel || '-';
  const cooldownDate = rows[markers.cooldownIndex]?.dateLabel || '-';

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>{title}</h2>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
            {effectiveSubtitle}
          </p>
        </div>
        <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-muted)' }}>
          {targetLabel}
        </div>
      </div>

      {showVirusSelector ? (
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
      ) : null}

      <div className="soft-panel" style={{ padding: 16, marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
        Die markierten Punkte helfen dir, den Start, den letzten bestätigten Stand und den im validierten Lauf sichtbar gewordenen Höhepunkt schnell zu erkennen.
      </div>

      {freshnessHint && (
        <div className="soft-panel" style={{ padding: 16, marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
          {freshnessHint}
        </div>
      )}

      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', marginBottom: 16 }}>
        {[
          { label: 'Welle beginnt', value: startDate, tone: '#2aa198' },
          { label: 'Letzter Ist-Wert', value: observedDate, tone: '#0a84ff' },
          { label: 'Erwarteter Peak', value: peakDate, tone: '#ff453a' },
          { label: 'Rückgang', value: cooldownDate, tone: '#ff9f0a' },
        ].map((item) => (
          <div key={item.label} className="soft-panel" style={{ padding: 16 }}>
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
              x1={rows[markers.lastObservedIndex]?.dateLabel}
              x2={rows[markers.lastValuedIndex]?.dateLabel || rows[markers.lastObservedIndex]?.dateLabel}
              fill="rgba(10, 132, 255, 0.06)"
            />
            <ReferenceLine x={rows[markers.startIndex]?.dateLabel} stroke="#2aa198" strokeDasharray="4 4" label={{ value: 'Beginn', position: 'top', fill: '#2aa198', fontSize: 10 }} />
            <ReferenceLine x={rows[markers.lastObservedIndex]?.dateLabel} stroke="#0a84ff" strokeDasharray="4 4" label={{ value: 'Ist-Wert', position: 'top', fill: '#0a84ff', fontSize: 10 }} />
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
        Diese Kurve bleibt bewusst rückblick-orientiert. Für den aktuellen Arbeitsstand solltest du immer zusätzlich auf den frischen Planungsausblick schauen.
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
            <span>Trefferquote</span>
            <strong>{formatPercent(decisionMetrics.hit_rate_pct || 0)}</strong>
          </div>
        ) : (
          <div className="metric-box">
            <span>Abweichung (sMAPE)</span>
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
              <Line yAxisId="left" type="monotone" dataKey="persistence" name="Persistenz-Basis" stroke="#64748b" strokeWidth={1.4} dot={false} strokeDasharray="3 3" />
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
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Einordnung</div>
          <div style={{ marginTop: 6, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            {sanitizeEvidenceCopy(result?.proof_text || result?.llm_insight)}
          </div>
        </div>
      )}
    </div>
  );
};
