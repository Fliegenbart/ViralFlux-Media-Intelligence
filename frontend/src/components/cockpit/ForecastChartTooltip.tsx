import React from 'react';

type TooltipRow = {
  name?: string;
  value?: number | string | null;
  color?: string;
};

interface ForecastChartTooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: TooltipRow[];
  regionName?: string;
}

const SERIES_LABELS: Record<string, string> = {
  historicalLine: 'Ist-Inzidenz',
  forecastLine: 'Prognose',
  actual: 'Ist-Wert',
  forecast: 'Forecast',
};

function formatTooltipValue(value?: number | string | null): string {
  if (value == null || value === '') return '—';
  if (typeof value === 'number') return value.toFixed(1);
  return String(value);
}

const ForecastChartTooltip: React.FC<ForecastChartTooltipProps> = ({
  active,
  label,
  payload,
  regionName,
}) => {
  if (!active || !payload || payload.length === 0) return null;

  const visibleRows = payload.filter((entry) => {
    const key = String(entry.name || '');
    return key !== 'bandUpper' && key !== 'bandLower' && entry.value != null;
  });

  if (visibleRows.length === 0) return null;

  const title = regionName && label ? `${regionName} · ${label}` : String(label || regionName || 'Kurvenpunkt');

  return (
    <div className="forecast-chart-tooltip">
      <div className="forecast-chart-tooltip__title">{title}</div>
      <div className="forecast-chart-tooltip__list">
        {visibleRows.map((entry) => {
          const key = String(entry.name || 'row');
          return (
            <div key={`${key}-${String(entry.value)}`} className="forecast-chart-tooltip__row">
              <span className="forecast-chart-tooltip__label">{SERIES_LABELS[key] || key}</span>
              <strong className="forecast-chart-tooltip__value">{formatTooltipValue(entry.value)}</strong>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export { ForecastChartTooltip };
export type { ForecastChartTooltipProps };
