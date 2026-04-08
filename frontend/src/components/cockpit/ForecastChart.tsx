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
  ReferenceDot,
} from 'recharts';

import { RegionalBacktestTimelinePoint } from '../../types/media/regional';
import { ForecastChartTooltip } from './ForecastChartTooltip';

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

function formatForecastAxisTickLabel(value: string | number | undefined, tone: 'x' | 'y'): string {
  if (tone === 'x') return String(value ?? '');
  return String(value ?? '');
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

type AxisTickProps = {
  x?: number;
  y?: number;
  payload?: {
    value?: string | number;
  };
  tone: 'x' | 'y';
};

function ForecastAxisTick({ x = 0, y = 0, payload, tone }: AxisTickProps): React.JSX.Element {
  const value = payload?.value;
  const label = formatForecastAxisTickLabel(value, tone);

  return (
    <text
      x={x}
      y={y}
      dy={tone === 'x' ? 18 : 4}
      textAnchor={tone === 'x' ? 'middle' : 'end'}
      className={`forecast-chart-axis-tick forecast-chart-axis-tick--${tone}`}
    >
      {label}
    </text>
  );
}

type ActiveDotProps = {
  cx?: number;
  cy?: number;
};

function ForecastActiveDot({ cx, cy, color }: ActiveDotProps & { color: string }): React.JSX.Element | null {
  if (typeof cx !== 'number' || typeof cy !== 'number') return null;

  return (
    <g>
      <circle cx={cx} cy={cy} r={14} fill={color} fillOpacity={0.14} />
      <circle cx={cx} cy={cy} r={6.5} fill="#ffffff" stroke={color} strokeWidth={3} />
      <circle cx={cx} cy={cy} r={2.75} fill={color} />
    </g>
  );
}

type ReferenceLabelProps = {
  viewBox?: {
    x?: number;
  };
  value?: string | number;
  color: string;
  kind: 'today' | 'peak';
};

function ForecastReferenceLabel({
  viewBox,
  value,
  color,
  kind,
}: ReferenceLabelProps): React.JSX.Element | null {
  if (!viewBox || typeof viewBox.x !== 'number' || !value) return null;

  return (
    <text
      x={viewBox.x + 8}
      y={24}
      className={`forecast-chart-reference-label forecast-chart-reference-label--${kind}`}
      fill={color}
    >
      {value}
    </text>
  );
}

type ReferenceLabelCallbackProps = {
  viewBox?: {
    x?: number;
  };
};

type ActiveDotCallbackProps = {
  cx?: number;
  cy?: number;
};

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

  const peakPoint = useMemo(() => {
    const futurePoints = chartData.filter(
      (point) =>
        typeof point.forecastLine === 'number' &&
        point.date >= todayStr,
    );

    return futurePoints.reduce<typeof futurePoints[number] | null>((best, point) => {
      if (!best) return point;
      return (point.forecastLine ?? Number.NEGATIVE_INFINITY) >
        (best.forecastLine ?? Number.NEGATIVE_INFINITY)
        ? point
        : best;
    }, null);
  }, [chartData, todayStr]);

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
        <ComposedChart data={chartData} margin={{ top: 20, right: 18, bottom: 10, left: 2 }}>
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
          <XAxis
            dataKey="dateLabel"
            tick={<ForecastAxisTick tone="x" />}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
            minTickGap={26}
            tickMargin={10}
          />
          <YAxis
            tick={<ForecastAxisTick tone="y" />}
            tickLine={false}
            axisLine={false}
            width={42}
            tickMargin={10}
          />
          <Tooltip
            cursor={{ stroke: theme.reference, strokeWidth: 1.35, strokeDasharray: '3 3', strokeOpacity: 0.72 }}
            content={(props) => (
              <ForecastChartTooltip
                active={props.active}
                label={props.label}
                payload={props.payload as Array<{ name?: string; value?: number | string | null }> | undefined}
                regionName={regionName}
              />
            )}
          />

          {/* Confidence band */}
          <Area dataKey="bandUpper" stroke="none" fill={theme.forecastBand} fillOpacity={variant === 'default' ? 0.1 : 0.14} isAnimationActive={false} connectNulls={false} legendType="none" />
          <Area dataKey="bandLower" stroke="none" fill="#fff" fillOpacity={1} isAnimationActive={false} connectNulls={false} legendType="none" />

          {/* Historical gradient fill */}
          <Area dataKey="historicalLine" type="monotone" stroke="none" fill="url(#fcHistGrad)" isAnimationActive={false} connectNulls legendType="none" />

          {/* Historical line */}
          <Line
            dataKey="historicalLine"
            type="monotone"
            stroke={theme.actual}
            strokeWidth={variant === 'default' ? 2.6 : 3}
            dot={false}
            activeDot={(props: ActiveDotCallbackProps) => (
              <ForecastActiveDot cx={props.cx} cy={props.cy} color={theme.actual} />
            )}
            isAnimationActive={false}
            connectNulls
            name="Ist-Wert"
          />

          {/* Forecast line — DRAMATIC, with glow */}
          <Line
            dataKey="forecastLine"
            type="monotone"
            stroke={theme.forecast}
            strokeWidth={variant === 'default' ? 3.5 : 3}
            strokeDasharray={variant === 'default' ? undefined : '6 4'}
            dot={false}
            activeDot={(props: ActiveDotCallbackProps) => (
              <ForecastActiveDot cx={props.cx} cy={props.cy} color={theme.forecast} />
            )}
            isAnimationActive={false}
            connectNulls
            filter="url(#fcGlow)"
            name="Forecast"
          />

          {peakPoint && peakPoint.dateLabel !== todayLabel && typeof peakPoint.forecastLine === 'number' ? (
            <>
              <ReferenceLine
                x={peakPoint.dateLabel}
                stroke={theme.forecast}
                strokeDasharray="3 3"
                strokeOpacity={0.5}
                ifOverflow="extendDomain"
                label={(props: ReferenceLabelCallbackProps) => (
                  <ForecastReferenceLabel
                    {...props}
                    color={theme.forecast}
                    kind="peak"
                    value={`Peak · ${peakPoint.dateLabel}`}
                  />
                )}
              />
              <ReferenceDot
                x={peakPoint.dateLabel}
                y={peakPoint.forecastLine}
                r={5.5}
                fill={theme.forecast}
                stroke="#ffffff"
                strokeWidth={3}
                ifOverflow="extendDomain"
              />
            </>
          ) : null}

          {/* Today — solid cliff edge */}
          <ReferenceLine
            x={todayLabel}
            stroke={theme.reference}
            strokeWidth={variant === 'default' ? 1.6 : 1.2}
            strokeDasharray="2 3"
            strokeOpacity={0.7}
            label={(props: ReferenceLabelCallbackProps) => (
              <ForecastReferenceLabel
                {...props}
                color={theme.reference}
                kind="today"
                value="Heute"
              />
            )}
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

export { ForecastChart, PredictionSummary, formatForecastAxisTickLabel };
export type { ForecastChartProps, PredictionSummaryProps };
