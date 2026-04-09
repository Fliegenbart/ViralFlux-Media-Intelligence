import { differenceInCalendarDays, isBefore, parseISO } from 'date-fns';

import {
  BacktestChartPoint,
  BacktestResponse,
  RegionalBacktestResponse,
  RegionalForecastPrediction,
  WaveRadarResponse,
} from '../../types/media';
import {
  formatDateShort,
  formatPercent,
} from './cockpitUtils';

export interface ValidationRow extends BacktestChartPoint {
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

export interface WaveMarkers {
  lastObservedIndex: number;
  startIndex: number;
  peakIndex: number;
  cooldownIndex: number;
  lastValuedIndex: number;
  hasProjectedDataAfterObservation: boolean;
  narrative: string;
}

export interface FocusRegionChartRow {
  date: string;
  dateLabel: string;
  actual?: number | null;
  validated?: number | null;
  forecast?: number | null;
  bandBase?: number | null;
  bandRange?: number | null;
}

export interface WaveSpreadRow {
  rank: number;
  bundesland: string;
  dateLabel: string;
  offsetDays: number;
}

export function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

export function readBooleanFlag(record: Record<string, unknown> | null | undefined, keys: string[]): boolean | null {
  if (!record) return null;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'boolean') return value;
  }
  return null;
}

export function readNumberValue(record: Record<string, unknown> | null | undefined, keys: string[]): number | null {
  if (!record) return null;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

export function passStateLabel(passed: boolean | null): string {
  if (passed == null) return '-';
  return passed ? 'erfüllt' : 'beobachten';
}

export function formatSampleCoverage(value: number | null): string {
  if (!isNumber(value)) return '-';
  const normalized = value <= 1 ? value * 100 : value;
  return formatPercent(normalized, 0);
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

export function formatVirusLevel(value?: number | null, digits = 1): string {
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

export function buildFocusRegionChartRows(
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

export function buildWaveSpreadRows(result: WaveRadarResponse | null, limit = 6): WaveSpreadRow[] {
  const firstOnsetDate = parseDate(result?.summary?.first_onset?.date);

  return [...(result?.regions || [])]
    .filter((region) => region?.wave_start && region?.wave_rank != null)
    .sort((left, right) => Number(left.wave_rank ?? Number.MAX_SAFE_INTEGER) - Number(right.wave_rank ?? Number.MAX_SAFE_INTEGER))
    .slice(0, limit)
    .map((region) => {
      const waveDate = parseDate(region.wave_start);
      return {
        rank: Number(region.wave_rank ?? 0),
        bundesland: String(region.bundesland || '-'),
        dateLabel: formatDateShort(region.wave_start),
        offsetDays: waveDate && firstOnsetDate
          ? Math.max(differenceInCalendarDays(waveDate, firstOnsetDate), 0)
          : 0,
      };
    });
}

export function describeForecastDelta(prediction: RegionalForecastPrediction | null): string {
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

export function buildUncertaintyText(prediction: RegionalForecastPrediction | null): string {
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
