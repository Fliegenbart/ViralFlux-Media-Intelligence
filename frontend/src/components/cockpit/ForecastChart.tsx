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
  variant?: 'default' | 'hero-alert' | 'hero-calm';
}

function formatDayMonth(dateStr: string): string {
  const d = new Date(dateStr);
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  return `${day}.${month}`;
}

const CHART_THEME = {
  default: {
    actual: '#4f46e5',
    forecast: '#4f46e5',
    forecastBand: '#4f46e5',
    tick: '#94a3b8',
    grid: 'rgba(148,163,184,0.12)',
    reference: '#4f46e5',
  },
  'hero-alert': {
    actual: '#0f1c1a',
    forecast: '#e8523a',
    forecastBand: '#e8523a',
    tick: '#8a9794',
    grid: 'rgba(138,151,148,0.18)',
    reference: '#8a9794',
  },
  'hero-calm': {
    actual: '#0f1c1a',
    forecast: '#1f7a66',
    forecastBand: '#1f7a66',
    tick: '#8a9794',
    grid: 'rgba(138,151,148,0.18)',
    reference: '#8a9794',
  },
} as const;

const ForecastChart: React.FC<ForecastChartProps> = ({
  timeline,
  regionName,
  className,
  variant = 'default',
}) => {
  const theme = CHART_THEME[variant];
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
      <ResponsiveContainer width="100%" height="100%" minHeight={300}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <defs>
            <linearGradient id="fcHistGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={theme.actual} stopOpacity={variant === 'default' ? 0.12 : 0.08} />
              <stop offset="100%" stopColor={theme.actual} stopOpacity={0.01} />
            </linearGradient>
            <filter id="fcGlow">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} vertical={false} />
          <XAxis dataKey="dateLabel" tick={{ fontSize: 11, fill: theme.tick }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 11, fill: theme.tick }} tickLine={false} axisLine={false} width={40} />
          <Tooltip
            contentStyle={{ background: '#fff', border: 'none', borderRadius: 8, fontSize: 12, boxShadow: '0 4px 16px rgba(0,0,0,0.12)' }}
            labelFormatter={(label) => `${regionName} · ${label}`}
            formatter={(value: number, name: string) => {
              const nameMap: Record<string, string> = { historicalLine: 'Ist-Inzidenz', forecastLine: 'Prognose', bandUpper: 'Obergrenze', bandLower: 'Untergrenze' };
              return [typeof value === 'number' ? value.toFixed(1) : value, nameMap[name] || name];
            }}
          />

          {/* Confidence band */}
          <Area dataKey="bandUpper" stroke="none" fill={theme.forecastBand} fillOpacity={variant === 'default' ? 0.1 : 0.14} isAnimationActive={false} connectNulls={false} legendType="none" />
          <Area dataKey="bandLower" stroke="none" fill="#fff" fillOpacity={1} isAnimationActive={false} connectNulls={false} legendType="none" />

          {/* Historical gradient fill */}
          <Area dataKey="historicalLine" type="monotone" stroke="none" fill="url(#fcHistGrad)" isAnimationActive={false} connectNulls legendType="none" />

          {/* Historical line */}
          <Line dataKey="historicalLine" type="monotone" stroke={theme.actual} strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls name="Ist-Wert" />

          {/* Forecast line — DRAMATIC, with glow */}
          <Line dataKey="forecastLine" type="monotone" stroke={theme.forecast} strokeWidth={variant === 'default' ? 3.5 : 3} dot={false} isAnimationActive={false} connectNulls filter="url(#fcGlow)" name="Forecast" />

          {/* Today — solid cliff edge */}
          <ReferenceLine x={todayLabel} stroke={theme.reference} strokeWidth={variant === 'default' ? 2 : 1.5} label={{ value: 'Heute', position: 'insideTopRight', fill: theme.reference, fontSize: 11, fontWeight: 600 }} />
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
