import React, { useMemo } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';

import { RegionalBacktestTimelinePoint } from '../../types/media/regional';

/* ── ForecastChart ── */

interface ForecastChartProps {
  timeline: RegionalBacktestTimelinePoint[];
  regionName: string;
  className?: string;
}

function formatDayMonth(dateStr: string): string {
  const d = new Date(dateStr);
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  return `${day}.${month}`;
}

const ForecastChart: React.FC<ForecastChartProps> = ({ timeline, regionName, className }) => {
  const data = useMemo(() => {
    if (!timeline || timeline.length === 0) return [];

    return timeline.map((point) => ({
      date: point.as_of_date,
      dateLabel: formatDayMonth(point.as_of_date),
      actual: point.current_known_incidence,
      forecast: point.expected_target_incidence,
      lower: point.prediction_interval_lower ?? undefined,
      upper: point.prediction_interval_upper ?? undefined,
    }));
  }, [timeline]);

  const todayStr = useMemo(() => {
    const now = new Date();
    return now.toISOString().slice(0, 10);
  }, []);

  const todayLabel = useMemo(() => formatDayMonth(todayStr), [todayStr]);

  // Split data into historical (up to today) and forecast (from today onward)
  const { historicalData, forecastData } = useMemo(() => {
    const historical: typeof data = [];
    const forecast: typeof data = [];

    for (const point of data) {
      if (point.date <= todayStr) {
        historical.push(point);
      } else {
        forecast.push(point);
      }
    }

    // Add the last historical point to forecast for continuity
    if (historical.length > 0 && forecast.length > 0) {
      forecast.unshift(historical[historical.length - 1]);
    }

    return { historicalData: historical, forecastData: forecast };
  }, [data, todayStr]);

  // Merge into a single dataset for the chart
  const chartData = useMemo(() => {
    return data.map((point) => ({
      ...point,
      historicalLine: point.date <= todayStr ? point.actual : undefined,
      forecastLine: point.date >= todayStr ? point.forecast : undefined,
      bandLower: point.date >= todayStr ? point.lower : undefined,
      bandUpper: point.date >= todayStr ? point.upper : undefined,
    }));
  }, [data, todayStr]);

  if (!timeline || timeline.length === 0) {
    return (
      <div className={`forecast-chart-empty ${className || ''}`}>
        Keine Daten
      </div>
    );
  }

  return (
    <div className={className || ''} style={{ width: '100%', flex: 1 }}>
      <ResponsiveContainer width="100%" height="100%" minHeight={280}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--border-light, rgba(148,163,184,0.18))"
            vertical={false}
          />
          <XAxis
            dataKey="dateLabel"
            tick={{ fontSize: 11, fill: 'var(--text-muted, #94a3b8)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--border-light, rgba(148,163,184,0.18))' }}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11, fill: 'var(--text-muted, #94a3b8)' }}
            tickLine={false}
            axisLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--surface-primary, #fff)',
              border: '1px solid var(--border-light, #e2e8f0)',
              borderRadius: 8,
              fontSize: 12,
              boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
            }}
            labelFormatter={(label) => `${regionName} - ${label}`}
            formatter={(value: number, name: string) => {
              const nameMap: Record<string, string> = {
                historicalLine: 'Ist-Inzidenz',
                forecastLine: 'Prognose',
                bandUpper: 'Obergrenze',
                bandLower: 'Untergrenze',
              };
              return [typeof value === 'number' ? value.toFixed(1) : value, nameMap[name] || name];
            }}
          />

          {/* Confidence band */}
          <Area
            dataKey="bandUpper"
            stroke="none"
            fill="var(--color-primary, #6366f1)"
            fillOpacity={0.08}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Area
            dataKey="bandLower"
            stroke="none"
            fill="var(--surface-primary, #fff)"
            fillOpacity={1}
            isAnimationActive={false}
            connectNulls={false}
          />

          {/* Historical line (solid) */}
          <Line
            dataKey="historicalLine"
            type="monotone"
            stroke="var(--color-primary, #6366f1)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />

          {/* Forecast line (dashed) */}
          <Line
            dataKey="forecastLine"
            type="monotone"
            stroke="var(--color-primary, #6366f1)"
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={false}
            isAnimationActive={false}
            connectNulls
          />

          {/* Today reference line */}
          <ReferenceLine
            x={todayLabel}
            stroke="var(--text-muted, #94a3b8)"
            strokeDasharray="4 4"
            strokeWidth={1}
            label={{
              value: 'Heute',
              position: 'top',
              fill: 'var(--text-muted, #94a3b8)',
              fontSize: 11,
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

/* ── PredictionSummary ── */

interface PredictionSummaryProps {
  probability: number;
  regionName: string;
  horizonDays: number;
  confidence: number;
  changePct: number;
}

const PredictionSummary: React.FC<PredictionSummaryProps> = ({
  probability,
  regionName,
  horizonDays,
  confidence,
  changePct,
}) => {
  const probabilityPct = Math.round((probability <= 1 ? probability : probability / 100) * 100);
  const confidencePct = Math.round((confidence <= 1 ? confidence : confidence / 100) * 100);
  const sign = changePct >= 0 ? '+' : '';

  return (
    <div className="prediction-hero-summary">
      <span className="prediction-hero-summary__probability">{probabilityPct}%</span>
      <span className="prediction-hero-summary__text">
        Wellenwahrscheinlichkeit &middot; {regionName} &middot; n&auml;chste {horizonDays} Tage
      </span>
      <span className="prediction-hero-summary__confidence">
        Konfidenz: {confidencePct}% stabil &middot; Trend: {sign}{changePct.toFixed(1)}% WoW
      </span>
    </div>
  );
};

export { ForecastChart, PredictionSummary };
export type { ForecastChartProps, PredictionSummaryProps };
