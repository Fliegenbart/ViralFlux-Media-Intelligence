import React, { useState, useEffect } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, 
  Tooltip, Legend, ResponsiveContainer, Area, AreaChart
} from 'recharts';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

interface DashboardData {
  current_viral_loads: Record<string, {
    value: number;
    date: string;
    trend: string;
  }>;
  top_trends: Array<{keyword: string; score: number}>;
  are_inzidenz: {value: number; date: string};
  forecast_summary: Record<string, any>;
  weather: {avg_temperature: number; avg_humidity: number};
}

const Dashboard: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [selectedVirus, setSelectedVirus] = useState('Influenza A');
  const [timeseriesData, setTimeseriesData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
    fetchTimeseriesData();
  }, [selectedVirus]);

  const fetchDashboardData = async () => {
    try {
      const response = await fetch('/api/v1/dashboard/overview');
      const result = await response.json();
      setData(result);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchTimeseriesData = async () => {
    try {
      const response = await fetch(`/api/v1/dashboard/timeseries/${selectedVirus}`);
      const result = await response.json();
      setTimeseriesData(result);
    } catch (error) {
      console.error('Error fetching timeseries:', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-2xl text-gray-600">Lade Dashboard...</div>
      </div>
    );
  }

  const getTrendColor = (trend: string) => {
    switch (trend) {
      case 'steigend': return 'text-red-600';
      case 'fallend': return 'text-green-600';
      default: return 'text-gray-600';
    }
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'steigend': return '↗';
      case 'fallend': return '↘';
      default: return '→';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                🦠 VirusRadar Pro
              </h1>
              <p className="text-sm text-gray-600 mt-1">
                Intelligentes Frühwarnsystem für Labordiagnostik
              </p>
            </div>
            <div className="text-right">
              <div className="text-sm text-gray-600">
                Letztes Update: {new Date().toLocaleString('de-DE')}
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {/* Aktuelle Viruslast - Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {data && Object.entries(data.current_viral_loads).map(([virus, info]) => (
            <div
              key={virus}
              className={`bg-white rounded-lg shadow p-6 cursor-pointer transition-all hover:shadow-lg ${
                selectedVirus === virus ? 'ring-2 ring-blue-500' : ''
              }`}
              onClick={() => setSelectedVirus(virus)}
            >
              <div className="text-sm font-medium text-gray-600 mb-2">{virus}</div>
              <div className="flex items-baseline justify-between">
                <div className="text-3xl font-bold text-gray-900">
                  {info.value.toFixed(0)}
                </div>
                <div className={`text-xl font-semibold ${getTrendColor(info.trend)}`}>
                  {getTrendIcon(info.trend)}
                </div>
              </div>
              <div className="text-xs text-gray-500 mt-2">
                Genkopien/L
              </div>
              <div className={`text-sm font-medium mt-2 ${getTrendColor(info.trend)}`}>
                {info.trend}
              </div>
            </div>
          ))}
        </div>

        {/* Hauptchart - Zeitreihe mit Prognose */}
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            {selectedVirus} - Viruslast & 14-Tage-Prognose
          </h2>
          {timeseriesData && (
            <ResponsiveContainer width="100%" height={400}>
              <AreaChart
                data={[
                  ...timeseriesData.historical.map((d: any) => ({
                    date: format(new Date(d.date), 'dd.MM', { locale: de }),
                    historical: d.viral_load,
                    upper: d.upper_bound,
                    lower: d.lower_bound,
                  })),
                  ...timeseriesData.forecast.map((d: any) => ({
                    date: format(new Date(d.date), 'dd.MM', { locale: de }),
                    forecast: d.predicted_value,
                    upper: d.upper_bound,
                    lower: d.lower_bound,
                  }))
                ]}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis label={{ value: 'Genkopien/L', angle: -90, position: 'insideLeft' }} />
                <Tooltip />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="lower"
                  stackId="1"
                  stroke="none"
                  fill="#e0e0e0"
                  fillOpacity={0.3}
                />
                <Area
                  type="monotone"
                  dataKey="upper"
                  stackId="1"
                  stroke="none"
                  fill="#e0e0e0"
                  fillOpacity={0.3}
                />
                <Line
                  type="monotone"
                  dataKey="historical"
                  stroke="#2563eb"
                  strokeWidth={2}
                  name="Gemessen"
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  stroke="#dc2626"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  name="Prognose"
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Bottom Row - Trends & Wetter */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Google Trends */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">
              📊 Google Trends Top Keywords
            </h2>
            {data && (
              <div className="space-y-4">
                {data.top_trends.map((trend, idx) => (
                  <div key={idx} className="flex items-center justify-between">
                    <span className="text-gray-700">{trend.keyword}</span>
                    <div className="flex items-center space-x-3">
                      <div className="w-32 bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-blue-600 h-2 rounded-full"
                          style={{ width: `${trend.score}%` }}
                        />
                      </div>
                      <span className="text-sm font-semibold text-gray-600 w-12 text-right">
                        {trend.score}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Wetter & ARE */}
          <div className="space-y-6">
            {/* Wetter */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-bold text-gray-900 mb-4">
                🌡️ Wetter (Ø Deutschland)
              </h2>
              {data && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-sm text-gray-600">Temperatur</div>
                    <div className="text-2xl font-bold text-gray-900">
                      {data.weather.avg_temperature.toFixed(1)}°C
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">Luftfeuchtigkeit</div>
                    <div className="text-2xl font-bold text-gray-900">
                      {data.weather.avg_humidity.toFixed(0)}%
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* ARE Inzidenz */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-bold text-gray-900 mb-4">
                🏥 ARE Inzidenz (GrippeWeb)
              </h2>
              {data && data.are_inzidenz.value && (
                <div>
                  <div className="text-3xl font-bold text-gray-900">
                    {data.are_inzidenz.value.toFixed(0)}
                  </div>
                  <div className="text-sm text-gray-600 mt-1">
                    pro 100.000 Einwohner
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
