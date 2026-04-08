export interface LatestForecastPoint {
  date: string;
  predicted_value: number;
  lower_bound?: number | null;
  upper_bound?: number | null;
  confidence?: number | null;
  model_version?: string | null;
  trend_momentum_7d?: number | null;
  outbreak_risk_score?: number | null;
}

export interface LatestForecastResponse {
  virus_typ: string;
  forecast: LatestForecastPoint[];
  created_at?: string | null;
  model_version?: string | null;
  message?: string;
}
