import React, { useMemo } from 'react';
import {
  CartesianGrid,
  Line,
  ResponsiveContainer,
  ReferenceArea,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
  LineChart,
} from 'recharts';

import {
  VIRUS_RADAR_HERO_COLORS,
  VirusRadarHeroChartRow,
} from '../../features/media/virusRadarHeroForecast';

interface MultiVirusForecastChartProps {
  data: VirusRadarHeroChartRow[];
  selectedVirus: string;
  className?: string;
  loading?: boolean;
}

type TooltipEntry = {
  name?: string;
  value?: number | string | null;
  color?: string;
};

function HeroForecastTooltip({
  active,
  label,
  payload,
  selectedVirus,
}: {
  active?: boolean;
  label?: string;
  payload?: TooltipEntry[];
  selectedVirus: string;
}): React.JSX.Element | null {
  if (!active || !payload?.length) return null;

  const visibleItems = payload.filter((entry) => typeof entry.value === 'number' && Number.isFinite(entry.value));
  if (!visibleItems.length) return null;

  return (
    <div className="virus-radar-multi-chart-tooltip">
      <div className="virus-radar-multi-chart-tooltip__title">{selectedVirus} · {label}</div>
      <div className="virus-radar-multi-chart-tooltip__rows">
        {visibleItems.map((entry) => (
          <div key={String(entry.name)} className="virus-radar-multi-chart-tooltip__row">
            <span style={{ color: entry.color || '#4b5b58' }}>{entry.name}</span>
            <div className="virus-radar-multi-chart-tooltip__value">
              <strong>{Number(entry.value).toFixed(0)}</strong>
              <small>Index</small>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function axisDomain(values: Array<number | null | undefined>): [number, number] {
  const numericValues = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (!numericValues.length) return [80, 140];
  const min = Math.min(...numericValues);
  const max = Math.max(...numericValues);
  return [Math.max(40, Math.floor(min / 10) * 10 - 10), Math.ceil(max / 10) * 10 + 10];
}

const MultiVirusForecastChart: React.FC<MultiVirusForecastChartProps> = ({
  data,
  selectedVirus,
  className,
  loading = false,
}) => {
  const chartData = useMemo(() => data.map((row) => ({
    date: row.date,
    dateLabel: row.dateLabel,
    actual: row.actualSeries[selectedVirus],
    forecast: row.forecastSeries[selectedVirus],
  })), [data, selectedVirus]);

  const virusColor = VIRUS_RADAR_HERO_COLORS[selectedVirus] || '#1f7a66';

  const yDomain = useMemo(() => axisDomain(
    chartData.flatMap((row) => [row.actual, row.forecast]),
  ), [chartData]);

  const todayLabel = useMemo(() => {
    const latestActual = [...chartData].reverse().find((row) => typeof row.actual === 'number' && Number.isFinite(row.actual));
    return latestActual?.dateLabel || null;
  }, [chartData]);
  const forecastEndLabel = chartData[chartData.length - 1]?.dateLabel || null;

  if (loading && !data.length) {
    return <div className={`forecast-chart-empty ${className || ''}`}>Der Virus-Verlauf wird gerade aufgebaut.</div>;
  }

  if (!data.length) {
    return <div className={`forecast-chart-empty ${className || ''}`}>Noch kein belastbarer Virus-Verlauf verfügbar.</div>;
  }

  return (
    <div className={className || ''} style={{ width: '100%', flex: 1 }}>
      <ResponsiveContainer width="100%" height="100%" minHeight={340}>
        <LineChart data={chartData} margin={{ top: 18, right: 12, bottom: 12, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,151,148,0.18)" vertical={false} />
          <XAxis
            dataKey="dateLabel"
            tickLine={false}
            axisLine={false}
            tick={{ fill: '#8a9794', fontSize: 12, fontWeight: 600 }}
            tickMargin={12}
            minTickGap={24}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fill: '#8a9794', fontSize: 12, fontWeight: 600 }}
            tickMargin={10}
            width={44}
            domain={yDomain}
          />
          <Tooltip
            cursor={{ stroke: '#8a9794', strokeWidth: 1.2, strokeDasharray: '3 3', strokeOpacity: 0.72 }}
            content={(props) => (
              <HeroForecastTooltip
                active={props.active}
                label={String(props.label || '')}
                payload={props.payload as TooltipEntry[] | undefined}
                selectedVirus={selectedVirus}
              />
            )}
          />

          {todayLabel && forecastEndLabel && todayLabel !== forecastEndLabel ? (
            <ReferenceArea
              x1={todayLabel}
              x2={forecastEndLabel}
              fill={virusColor}
              fillOpacity={0.05}
              ifOverflow="extendDomain"
            />
          ) : null}

          {todayLabel ? (
            <ReferenceLine
              x={todayLabel}
              stroke="#8a9794"
              strokeWidth={1.2}
              strokeDasharray="2 3"
              strokeOpacity={0.72}
              label={{
                value: 'Heute',
                position: 'insideTopLeft',
                fill: '#8a9794',
                fontSize: 11,
                fontWeight: 700,
              }}
            />
          ) : null}
          <Line
            type="monotone"
            dataKey="actual"
            stroke="#0f1c1a"
            strokeWidth={2.9}
            dot={false}
            connectNulls
            isAnimationActive={false}
            name="Letzte Wochen"
          />
          <Line
            type="monotone"
            dataKey="forecast"
            stroke={virusColor}
            strokeWidth={2.9}
            strokeDasharray="6 4"
            dot={false}
            connectNulls
            activeDot={{ r: 5, stroke: '#ffffff', strokeWidth: 2 }}
            isAnimationActive={false}
            name="Nächste 7 Tage"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export { MultiVirusForecastChart };
export type { MultiVirusForecastChartProps };
