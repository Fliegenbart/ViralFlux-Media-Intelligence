import {
  BacktestResponse,
  ConnectorCatalogItem,
  MediaCampaignsResponse,
  MediaDecisionResponse,
  MediaEvidenceResponse,
  PilotReportingResponse,
  PilotReadoutResponse,
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalBacktestResponse,
  RegionalForecastResponse,
  RegionalBenchmarkResponse,
  RegionalPortfolioResponse,
  MediaRegionsResponse,
  PreparedSyncPayload,
  RecommendationCard,
  RecommendationDetail,
  TruthImportBatchDetailResponse,
  TruthImportResponse,
} from '../../types/media';

export interface GenerateRecommendationsPayload {
  brand: string;
  product: string;
  campaign_goal: string;
  weekly_budget: number;
  channel_pool: string[];
  strategy_mode: string;
  max_cards: number;
  virus_typ: string;
}

export interface OpenRegionCampaignPayload {
  region_code: string;
  brand: string;
  product: string;
  campaign_goal: string;
  weekly_budget: number;
  virus_typ: string;
}

export interface TruthImportPayload {
  brand: string;
  source_label: string;
  replace_existing: boolean;
  validate_only: boolean;
  file_name: string;
  csv_payload: string;
}

export interface PilotReportingPayload {
  brand?: string;
  lookbackWeeks?: number;
  windowStart?: string;
  windowEnd?: string;
  regionCode?: string;
  product?: string;
  includeDraft?: boolean;
}

export interface PilotReadoutPayload {
  brand?: string;
  virus?: string;
  horizonDays?: number;
  weeklyBudgetEur?: number;
  topN?: number;
}

const DEFAULT_FETCH_TIMEOUT_MS = 20000;
const HEAVY_FETCH_TIMEOUT_MS = 45000;

export async function fetchJson<T>(
  url: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_FETCH_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(
        (data as { detail?: string; error?: string }).detail
        || (data as { error?: string }).error
        || `HTTP ${response.status}`,
      );
    }
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('timeout');
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export function sortRecommendations(cards: RecommendationCard[]): RecommendationCard[] {
  return [...cards].sort((a, b) => {
    const publishableDelta = Number(Boolean(b.is_publishable)) - Number(Boolean(a.is_publishable));
    if (publishableDelta !== 0) return publishableDelta;

    const priorityDelta = Number(b.priority_score || 0) - Number(a.priority_score || 0);
    if (priorityDelta !== 0) return priorityDelta;

    const signalDelta = Number(b.signal_score || 0) - Number(a.signal_score || 0);
    if (signalDelta !== 0) return signalDelta;

    const urgencyDelta = Number(b.urgency_score || 0) - Number(a.urgency_score || 0);
    if (urgencyDelta !== 0) return urgencyDelta;

    return Number(b.confidence || 0) - Number(a.confidence || 0);
  });
}

export const mediaApi = {
  async getDecision(virus: string, brand: string): Promise<MediaDecisionResponse> {
    const qs = new URLSearchParams({ virus_typ: virus, brand });
    return fetchJson<MediaDecisionResponse>(`/api/v1/media/decision?${qs.toString()}`, undefined, DEFAULT_FETCH_TIMEOUT_MS);
  },

  async getRegions(virus: string, brand: string): Promise<MediaRegionsResponse> {
    const qs = new URLSearchParams({ virus_typ: virus, brand });
    return fetchJson<MediaRegionsResponse>(`/api/v1/media/regions?${qs.toString()}`);
  },

  async getCampaigns(brand: string): Promise<MediaCampaignsResponse> {
    const qs = new URLSearchParams({ brand, limit: '120' });
    const data = await fetchJson<MediaCampaignsResponse>(`/api/v1/media/campaigns?${qs.toString()}`);
    return {
      ...data,
      cards: sortRecommendations(data.cards || []),
    };
  },

  async getEvidence(virus: string, brand: string): Promise<MediaEvidenceResponse> {
    const qs = new URLSearchParams({ virus_typ: virus, brand });
    return fetchJson<MediaEvidenceResponse>(`/api/v1/media/evidence?${qs.toString()}`, undefined, DEFAULT_FETCH_TIMEOUT_MS);
  },

  async getPilotReporting(payload: PilotReportingPayload = {}): Promise<PilotReportingResponse> {
    const qs = new URLSearchParams();
    if (payload.brand) qs.set('brand', payload.brand);
    if (payload.lookbackWeeks != null) qs.set('lookback_weeks', String(payload.lookbackWeeks));
    if (payload.windowStart) qs.set('window_start', payload.windowStart);
    if (payload.windowEnd) qs.set('window_end', payload.windowEnd);
    if (payload.regionCode) qs.set('region_code', payload.regionCode);
    if (payload.product) qs.set('product', payload.product);
    if (payload.includeDraft != null) qs.set('include_draft', String(payload.includeDraft));
    const suffix = qs.toString();
    return fetchJson<PilotReportingResponse>(
      `/api/v1/media/pilot-reporting${suffix ? `?${suffix}` : ''}`,
      undefined,
      20000,
    );
  },

  async getPilotReadout(payload: PilotReadoutPayload = {}): Promise<PilotReadoutResponse> {
    const qs = new URLSearchParams();
    if (payload.brand) qs.set('brand', payload.brand);
    if (payload.virus) qs.set('virus_typ', payload.virus);
    if (payload.horizonDays != null) qs.set('horizon_days', String(payload.horizonDays));
    if (payload.weeklyBudgetEur != null) qs.set('weekly_budget_eur', String(payload.weeklyBudgetEur));
    if (payload.topN != null) qs.set('top_n', String(payload.topN));
    const suffix = qs.toString();
    return fetchJson<PilotReadoutResponse>(
      `/api/v1/media/pilot-readout${suffix ? `?${suffix}` : ''}`,
      undefined,
      20000,
    );
  },

  async getBacktestRun(runId: string): Promise<BacktestResponse> {
    return fetchJson<BacktestResponse>(`/api/v1/backtest/runs/${encodeURIComponent(runId)}`);
  },

  async getRegionalBenchmark(referenceVirus = 'Influenza A'): Promise<RegionalBenchmarkResponse> {
    const qs = new URLSearchParams({ reference_virus: referenceVirus });
    return fetchJson<RegionalBenchmarkResponse>(`/api/v1/forecast/regional/benchmark?${qs.toString()}`);
  },

  async getRegionalPortfolio(referenceVirus = 'Influenza A', topN = 12): Promise<RegionalPortfolioResponse> {
    const qs = new URLSearchParams({ reference_virus: referenceVirus, top_n: String(topN) });
    return fetchJson<RegionalPortfolioResponse>(`/api/v1/forecast/regional/portfolio?${qs.toString()}`, undefined, 20000);
  },

  async getRegionalForecast(
    virus: string,
    horizonDays: number,
  ): Promise<RegionalForecastResponse> {
    const qs = new URLSearchParams({
      virus_typ: virus,
      horizon_days: String(horizonDays),
    });
    return fetchJson<RegionalForecastResponse>(`/api/v1/forecast/regional/decisions?${qs.toString()}`, undefined, HEAVY_FETCH_TIMEOUT_MS);
  },

  async getRegionalBacktest(
    virus: string,
    regionCode: string,
    horizonDays: number,
  ): Promise<RegionalBacktestResponse> {
    const qs = new URLSearchParams({
      virus_typ: virus,
      horizon_days: String(horizonDays),
    });
    return fetchJson<RegionalBacktestResponse>(
      `/api/v1/forecast/regional/backtest/${encodeURIComponent(regionCode)}?${qs.toString()}`,
      undefined,
      HEAVY_FETCH_TIMEOUT_MS,
    );
  },

  async getRegionalAllocation(
    virus: string,
    weeklyBudgetEur: number,
    horizonDays: number,
  ): Promise<RegionalAllocationResponse> {
    const qs = new URLSearchParams({
      virus_typ: virus,
      weekly_budget_eur: String(weeklyBudgetEur),
      horizon_days: String(horizonDays),
    });
    return fetchJson<RegionalAllocationResponse>(`/api/v1/forecast/regional/media-allocation?${qs.toString()}`, undefined, HEAVY_FETCH_TIMEOUT_MS);
  },

  async getRegionalCampaignRecommendations(
    virus: string,
    weeklyBudgetEur: number,
    horizonDays: number,
    topN = 12,
  ): Promise<RegionalCampaignRecommendationsResponse> {
    const qs = new URLSearchParams({
      virus_typ: virus,
      weekly_budget_eur: String(weeklyBudgetEur),
      horizon_days: String(horizonDays),
      top_n: String(topN),
    });
    return fetchJson<RegionalCampaignRecommendationsResponse>(`/api/v1/forecast/regional/campaign-recommendations?${qs.toString()}`, undefined, HEAVY_FETCH_TIMEOUT_MS);
  },

  async getRecommendationDetail(id: string): Promise<RecommendationDetail> {
    return fetchJson<RecommendationDetail>(`/api/v1/media/recommendations/${encodeURIComponent(id)}`);
  },

  async getConnectors(): Promise<ConnectorCatalogItem[]> {
    const data = await fetchJson<{ connectors?: ConnectorCatalogItem[] }>('/api/v1/media/connectors/catalog', undefined, 8000);
    return data.connectors || [];
  },

  async generateRecommendations(payload: GenerateRecommendationsPayload): Promise<{ cards?: RecommendationCard[] }> {
    return fetchJson<{ cards?: RecommendationCard[] }>(
      '/api/v1/media/recommendations/generate',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      30000,
    );
  },

  async openRegionCampaign(payload: OpenRegionCampaignPayload): Promise<{ action?: string; card_id?: string }> {
    return fetchJson<{ action?: string; card_id?: string }>(
      '/api/v1/media/recommendations/open-region',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      30000,
    );
  },

  async updateRecommendationStatus(id: string, status: string): Promise<{ new_status?: string }> {
    return fetchJson<{ new_status?: string }>(
      `/api/v1/media/recommendations/${encodeURIComponent(id)}/status`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      },
    );
  },

  async regenerateRecommendationAI(id: string): Promise<RecommendationDetail> {
    return fetchJson<RecommendationDetail>(
      `/api/v1/media/recommendations/${encodeURIComponent(id)}/regenerate-ai`,
      { method: 'POST' },
      30000,
    );
  },

  async prepareSync(id: string, connectorKey: string): Promise<PreparedSyncPayload> {
    return fetchJson<PreparedSyncPayload>(
      `/api/v1/media/recommendations/${encodeURIComponent(id)}/prepare-sync`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connector_key: connectorKey }),
      },
    );
  },

  async importTruthCsv(payload: TruthImportPayload): Promise<TruthImportResponse> {
    return fetchJson<TruthImportResponse>(
      '/api/v1/media/outcomes/import',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      30000,
    );
  },

  async getTruthImportBatchDetail(batchId: string): Promise<TruthImportBatchDetailResponse> {
    return fetchJson<TruthImportBatchDetailResponse>(
      `/api/v1/media/outcomes/import-batches/${encodeURIComponent(batchId)}`,
    );
  },
};
