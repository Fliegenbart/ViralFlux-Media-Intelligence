import React, { useId, useMemo } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type {
  RegionalBacktestResponse,
  RegionalForecastPrediction,
} from '../../types/media';
import {
  buildDecisionForecastChartModel,
  type DecisionForecastChartRow,
} from './decisionForecastChart.utils';

interface Props {
  prediction: RegionalForecastPrediction | null;
  backtest: RegionalBacktestResponse | null;
  horizonDays: number;
}

function DecisionForecastTooltip({
  active,
  label,
  payload,
}: {
  active?: boolean;
  label?: string;
  payload?: Array<{ dataKey?: string; value?: number | string | null }>;
}) {
  if (!active || !payload?.length) return null;

  const actual = payload.find((entry) => entry.dataKey === 'actual' && typeof entry.value === 'number');
  const forecast = payload.find((entry) => entry.dataKey === 'forecast' && typeof entry.value === 'number');
  const lower = payload.find((entry) => entry.dataKey === 'bandBase' && typeof entry.value === 'number');
  const range = payload.find((entry) => entry.dataKey === 'bandRange' && typeof entry.value === 'number');

  const upperValue = typeof lower?.value === 'number' && typeof range?.value === 'number'
    ? Number(lower.value) + Number(range.value)
    : null;

  return (
    <div className="decision-forecast-chart__tooltip">
      <div className="decision-forecast-chart__tooltip-title">{label}</div>
      {typeof actual?.value === 'number' ? (
        <div className="decision-forecast-chart__tooltip-row">
          <span>Historisch</span>
          <strong>{Number(actual.value).toFixed(1)}</strong>
        </div>
      ) : null}
      {typeof forecast?.value === 'number' ? (
        <div className="decision-forecast-chart__tooltip-row">
          <span>Fortfuehrung</span>
          <strong>{Number(forecast.value).toFixed(1)}</strong>
        </div>
      ) : null}
      {typeof lower?.value === 'number' && upperValue != null ? (
        <div className="decision-forecast-chart__tooltip-row">
          <span>Bandbreite</span>
          <strong>{Number(lower.value).toFixed(1)} bis {upperValue.toFixed(1)}</strong>
        </div>
      ) : null}
    </div>
  );
}

function numericExtent(rows: DecisionForecastChartRow[]): [number, number] {
  const values = rows.flatMap((row) => [
    row.actual,
    row.forecast,
    row.bandLower,
    row.bandUpper,
  ]).filter((value): value is number => typeof value === 'number' && Number.isFinite(value));

  if (!values.length) return [0, 100];

  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = Math.max((max - min) * 0.12, 4);

  return [
    Math.max(0, Number((min - padding).toFixed(1))),
    Number((max + padding).toFixed(1)),
  ];
}

const ACTUAL_COLOR = '#203743';
const FORECAST_COLOR = '#167c6b';
const FORECAST_FILL = 'rgba(22, 124, 107, 0.14)';
const FUTURE_ZONE_FILL = 'rgba(22, 124, 107, 0.06)';
const GRID_COLOR = 'rgba(148, 163, 184, 0.18)';
const AXIS_COLOR = '#6b7b8f';

export const DecisionForecastChart: React.FC<Props> = ({
  prediction,
  backtest,
  horizonDays,
}) => {
  const model = useMemo(() => buildDecisionForecastChartModel({
    horizonDays,
    prediction,
    backtest,
  }), [backtest, horizonDays, prediction]);
  const yDomain = useMemo(() => numericExtent(model.rows), [model.rows]);
  const chartId = useId().replace(/:/g, '');
  const actualGradientId = `${chartId}-decision-actual-gradient`;

  if (!model.hasHistory && !model.hasForecast) {
    return (
      <div className="decision-forecast-chart decision-forecast-chart--empty">
        Noch kein belastbarer Verlauf fuer diese Entscheidung verfuegbar.
      </div>
    );
  }

  return (
    <div className="decision-forecast-chart">
      <div className="decision-forecast-chart__topline">
        <div className="decision-forecast-chart__legend" aria-label="Legende">
          <span className="decision-forecast-chart__legend-item">
            <span className="decision-forecast-chart__swatch decision-forecast-chart__swatch--actual" aria-hidden="true" />
            Historisch
          </span>
          <span className="decision-forecast-chart__legend-item">
            <span className="decision-forecast-chart__swatch decision-forecast-chart__swatch--forecast" aria-hidden="true" />
            Modellierte 7-Tage-Fortfuehrung
          </span>
          <span className="decision-forecast-chart__legend-item">
            <span className="decision-forecast-chart__swatch decision-forecast-chart__swatch--band" aria-hidden="true" />
            Bandbreite
          </span>
        </div>

        <div className="decision-forecast-chart__anchors">
          {model.currentLabel ? <span>Stand {model.currentLabel}</span> : null}
          {model.targetLabel ? <span>Ziel {model.targetLabel}</span> : null}
        </div>
      </div>

      <div className="decision-forecast-chart__surface" aria-label="Entscheidungsgraph">
        <ResponsiveContainer width="100%" height="100%" minHeight={320}>
          <ComposedChart data={model.rows} margin={{ top: 10, right: 12, bottom: 10, left: 0 }}>
            <defs>
              <linearGradient id={actualGradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={ACTUAL_COLOR} stopOpacity={0.16} />
                <stop offset="100%" stopColor={ACTUAL_COLOR} stopOpacity={0.02} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(value) => {
                const row = model.rows.find((entry) => entry.date === value);
                return row?.axisLabel || '';
              }}
              tick={{ fill: AXIS_COLOR, fontSize: 12, fontWeight: 600 }}
              tickLine={false}
              axisLine={false}
              minTickGap={28}
              tickMargin={10}
            />
            <YAxis
              tick={{ fill: AXIS_COLOR, fontSize: 12, fontWeight: 600 }}
              tickFormatter={(value) => Number(value).toFixed(0)}
              tickLine={false}
              axisLine={false}
              width={42}
              tickMargin={10}
              domain={yDomain}
            />
            <Tooltip
              cursor={{ stroke: 'rgba(32, 55, 67, 0.24)', strokeWidth: 1, strokeDasharray: '3 3' }}
              content={(props) => (
                <DecisionForecastTooltip
                  active={props.active}
                  label={String(props.label || '')}
                  payload={props.payload as Array<{ dataKey?: string; value?: number | string | null }> | undefined}
                />
              )}
            />

            {model.currentDate && model.targetDate && model.currentDate !== model.targetDate ? (
              <ReferenceArea
                x1={model.currentDate}
                x2={model.targetDate}
                fill={FUTURE_ZONE_FILL}
                strokeOpacity={0}
                ifOverflow="extendDomain"
              />
            ) : null}

            {model.currentDate ? (
              <ReferenceLine
                x={model.currentDate}
                stroke={FORECAST_COLOR}
                strokeWidth={1.5}
                strokeOpacity={0.7}
                label={{
                  value: 'Heute',
                  position: 'insideTopRight',
                  fill: FORECAST_COLOR,
                  fontSize: 11,
                  fontWeight: 700,
                }}
              />
            ) : null}

            <Area
              type="monotone"
              dataKey="bandBase"
              stackId="decisionForecastBand"
              stroke="none"
              fill="transparent"
              activeDot={false}
              legendType="none"
              connectNulls
            />
            <Area
              type="monotone"
              dataKey="bandRange"
              stackId="decisionForecastBand"
              stroke="none"
              fill={FORECAST_FILL}
              activeDot={false}
              legendType="none"
              connectNulls
            />
            <Area
              type="monotone"
              dataKey="actual"
              stroke="none"
              fill={`url(#${actualGradientId})`}
              activeDot={false}
              legendType="none"
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="actual"
              stroke={ACTUAL_COLOR}
              strokeWidth={2.6}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="forecast"
              stroke={FORECAST_COLOR}
              strokeWidth={3}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="decision-forecast-chart__zones" aria-hidden="true">
        <span>Vergangenheit</span>
        <span>Naechste 7 Tage</span>
      </div>
    </div>
  );
};
