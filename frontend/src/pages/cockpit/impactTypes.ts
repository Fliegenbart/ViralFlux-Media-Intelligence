/**
 * Shape of the /api/v1/media/cockpit/impact response.
 * Mirrors backend impact_builder.build_impact_payload.
 */
export interface ImpactLiveRankingItem {
  code: string;
  name: string;
  pRising: number | null;
  delta7d: number | null;
  decisionLabel: 'Watch' | 'Prepare' | 'Activate' | null;
}

export interface ImpactTruthRegion {
  code: string;
  name: string;
  incidence: number;
  weekLabel: string;
}

export interface ImpactTruthWeek {
  weekStart: string;
  weekLabel: string;
  regions: ImpactTruthRegion[];
  top3: string[];
}

export interface ImpactOutcomePipeline {
  connected: boolean;
  mediaOutcomeRecords: number;
  importBatches: number;
  outcomeObservations: number;
  holdoutGroupsDefined: number;
  lastImportBatchAt: string | null;
  lastRecordUpdatedAt: string | null;
  note: string;
}

export interface ImpactPayload {
  virusTyp: string;
  horizonDays: number;
  generatedAt: string;
  liveRanking: ImpactLiveRankingItem[];
  truthHistory: {
    source: string;
    weeksBack: number;
    timeline: ImpactTruthWeek[];
  };
  outcomePipeline: ImpactOutcomePipeline;
  notes: string[];
}
