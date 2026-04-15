import { addDays, differenceInCalendarDays, format, parseISO } from 'date-fns';

import type {
  RegionalBacktestResponse,
  RegionalForecastPrediction,
} from '../../types/media';

export interface DecisionForecastChartRow {
  date: string;
  axisLabel: string;
  actual?: number | null;
  forecast?: number | null;
  bandLower?: number | null;
  bandUpper?: number | null;
  bandBase?: number | null;
  bandRange?: number | null;
  inForecastZone: boolean;
}

export interface DecisionForecastChartModel {
  rows: DecisionForecastChartRow[];
  hasHistory: boolean;
  hasForecast: boolean;
  currentDate: string | null;
  targetDate: string | null;
  currentLabel: string | null;
  targetLabel: string | null;
}

interface BuildDecisionForecastChartModelArgs {
  horizonDays: number;
  prediction: RegionalForecastPrediction | null;
  backtest: RegionalBacktestResponse | null;
}

function normalizeIsoDate(value?: string | null): string | null {
  if (!value) return null;
  const isoDate = String(value).slice(0, 10);

  try {
    parseISO(isoDate);
    return isoDate;
  } catch {
    return null;
  }
}

function formatAxisLabel(value: string): string {
  try {
    return format(parseISO(value), 'dd.MM.');
  } catch {
    return value;
  }
}

function formatFullDate(value: string | null): string | null {
  if (!value) return null;

  try {
    return format(parseISO(value), 'dd.MM.yyyy');
  } catch {
    return value;
  }
}

function lerp(start: number, end: number, progress: number): number {
  return Number((start + ((end - start) * progress)).toFixed(2));
}

function hasFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function buildDecisionForecastChartModel({
  horizonDays,
  prediction,
  backtest,
}: BuildDecisionForecastChartModelArgs): DecisionForecastChartModel {
  const rows = new Map<string, DecisionForecastChartRow>();

  const currentDate = normalizeIsoDate(prediction?.last_data_date || prediction?.as_of_date);
  const targetDate = normalizeIsoDate(prediction?.target_date)
    || (currentDate ? addDays(parseISO(`${currentDate}T00:00:00Z`), Math.max(horizonDays, 1)).toISOString().slice(0, 10) : null);
  const currentValue = prediction?.current_known_incidence;
  const forecastValue = prediction?.expected_target_incidence;
  const intervalLower = prediction?.prediction_interval?.lower;
  const intervalUpper = prediction?.prediction_interval?.upper;

  const historyEntries = [...(backtest?.timeline || [])]
    .filter((entry) => hasFiniteNumber(entry.current_known_incidence))
    .sort((left, right) => String(left.as_of_date).localeCompare(String(right.as_of_date)))
    .filter((entry) => {
      const isoDate = normalizeIsoDate(entry.as_of_date);
      if (!isoDate) return false;
      return !currentDate || isoDate <= currentDate;
    })
    .slice(-10);

  historyEntries.forEach((entry) => {
    const isoDate = normalizeIsoDate(entry.as_of_date);
    if (!isoDate) return;

    rows.set(isoDate, {
      date: isoDate,
      axisLabel: formatAxisLabel(isoDate),
      actual: entry.current_known_incidence,
      inForecastZone: false,
    });
  });

  if (currentDate && hasFiniteNumber(currentValue) && targetDate && hasFiniteNumber(forecastValue)) {
    const totalSteps = Math.max(differenceInCalendarDays(parseISO(targetDate), parseISO(currentDate)), horizonDays, 1);

    for (let offset = 0; offset <= totalSteps; offset += 1) {
      const date = addDays(parseISO(`${currentDate}T00:00:00Z`), offset).toISOString().slice(0, 10);
      const progress = totalSteps === 0 ? 1 : offset / totalSteps;
      const lowerValue = hasFiniteNumber(intervalLower) ? lerp(currentValue, intervalLower, progress) : lerp(currentValue, forecastValue, progress);
      const upperValue = hasFiniteNumber(intervalUpper) ? lerp(currentValue, intervalUpper, progress) : lerp(currentValue, forecastValue, progress);
      const entry = rows.get(date);

      rows.set(date, {
        date,
        axisLabel: formatAxisLabel(date),
        actual: entry?.actual,
        forecast: lerp(currentValue, forecastValue, progress),
        bandLower: lowerValue,
        bandUpper: upperValue,
        bandBase: lowerValue,
        bandRange: Number((upperValue - lowerValue).toFixed(2)),
        inForecastZone: true,
      });
    }
  }

  const orderedRows = Array.from(rows.values()).sort((left, right) => left.date.localeCompare(right.date));

  return {
    rows: orderedRows,
    hasHistory: orderedRows.some((row) => hasFiniteNumber(row.actual)),
    hasForecast: orderedRows.some((row) => hasFiniteNumber(row.forecast)),
    currentDate,
    targetDate,
    currentLabel: formatFullDate(currentDate),
    targetLabel: formatFullDate(targetDate),
  };
}
