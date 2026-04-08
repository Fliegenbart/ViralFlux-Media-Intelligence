import React, { useMemo } from 'react';
import {
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  LineChart,
} from 'recharts';

import {
  VIRUS_RADAR_HERO_COLORS,
  VIRUS_RADAR_HERO_VIRUSES,
  VirusRadarHeroChartRow,
} from '../../features/media/virusRadarHeroForecast';

interface MultiVirusForecastChartProps {
  data: VirusRadarHeroChartRow[];
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
}: {
  active?: boolean;
  label?: string;
  payload?: TooltipEntry[];
}): React.JSX.Element | null {
  if (!active || !payload?.length) return null;

  const visibleItems = payload.filter((entry) => typeof entry.value === 'number' && Number.isFinite(entry.value));
  if (!visibleItems.length) return null;

  return (
    <div className="virus-radar-multi-chart-tooltip">
      <div className="virus-radar-multi-chart-tooltip__title">{label}</div>
      <div className="virus-radar-multi-chart-tooltip__rows">
        {visibleItems.map((entry) => (
          <div key={String(entry.name)} className="virus-radar-multi-chart-tooltip__row">
            <span style={{ color: entry.color || '#4b5b58' }}>{entry.name}</span>
            <strong>{Number(entry.value).toFixed(0)}</strong>
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
  className,
  loading = false,
}) => {
  const chartData = useMemo(() => data.map((row, index) => {
    const nextIsForecast = data[index + 1]?.isForecast ?? false;
    const nextRow = { dateLabel: row.dateLabel };

    VIRUS_RADAR_HERO_VIRUSES.forEach((virus) => {
      const value = row.series[virus];
      (nextRow as Record<string, number | string | null>)[`${virus}Actual`] = row.isForecast ? null : value;
      (nextRow as Record<string, number | string | null>)[`${virus}Forecast`] = row.isForecast || nextIsForecast ? value : null;
    });

    return nextRow;
  }), [data]);

  const yDomain = useMemo(() => axisDomain(
    data.flatMap((row) => VIRUS_RADAR_HERO_VIRUSES.map((virus) => row.series[virus])),
  ), [data]);

  if (loading && !data.length) {
    return <div className={`forecast-chart-empty ${className || ''}`}>Die 4-Virus-Prognose wird gerade aufgebaut.</div>;
  }

  if (!data.length) {
    return <div className={`forecast-chart-empty ${className || ''}`}>Noch keine gemeinsame Prognose verfügbar.</div>;
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
              />
            )}
          />

          {VIRUS_RADAR_HERO_VIRUSES.map((virus) => (
            <Line
              key={`${virus}-actual`}
              type="monotone"
              dataKey={`${virus}Actual`}
              stroke={VIRUS_RADAR_HERO_COLORS[virus]}
              strokeWidth={2.6}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          ))}
          {VIRUS_RADAR_HERO_VIRUSES.map((virus) => (
            <Line
              key={`${virus}-forecast`}
              type="monotone"
              dataKey={`${virus}Forecast`}
              stroke={VIRUS_RADAR_HERO_COLORS[virus]}
              strokeWidth={2.6}
              strokeDasharray="6 4"
              dot={false}
              connectNulls
              activeDot={{ r: 5, stroke: '#ffffff', strokeWidth: 2 }}
              isAnimationActive={false}
              name={virus}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export { MultiVirusForecastChart };
export type { MultiVirusForecastChartProps };
