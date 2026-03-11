import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

import { UI_COPY } from '../../lib/copy';

type RecommendationOverlayMode = 'overlay' | 'route' | null;

interface MediaWorkflowContextValue {
  virus: string;
  setVirus: (value: string) => void;
  brand: string;
  setBrand: (value: string) => void;
  weeklyBudget: number;
  setWeeklyBudget: (value: number) => void;
  campaignGoal: string;
  setCampaignGoal: (value: string) => void;
  dataVersion: number;
  invalidateData: () => void;
  selectedRecommendationId: string | null;
  recommendationOverlayMode: RecommendationOverlayMode;
  openRecommendation: (id: string, mode?: Exclude<RecommendationOverlayMode, null>) => void;
  closeRecommendation: () => void;
}

const MediaWorkflowContext = createContext<MediaWorkflowContextValue | null>(null);

export const MediaWorkflowProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [virus, setVirus] = useState('Influenza A');
  const [brand, setBrand] = useState('gelo');
  const [weeklyBudget, setWeeklyBudget] = useState(120000);
  const [campaignGoal, setCampaignGoal] = useState<string>(UI_COPY.defaultCampaignGoal);
  const [dataVersion, setDataVersion] = useState(0);
  const [selectedRecommendationId, setSelectedRecommendationId] = useState<string | null>(null);
  const [recommendationOverlayMode, setRecommendationOverlayMode] = useState<RecommendationOverlayMode>(null);

  const invalidateData = useCallback(() => {
    setDataVersion((current) => current + 1);
  }, []);

  const openRecommendation = useCallback((id: string, mode: Exclude<RecommendationOverlayMode, null> = 'overlay') => {
    if (!id) return;
    setSelectedRecommendationId(id);
    setRecommendationOverlayMode(mode);
  }, []);

  const closeRecommendation = useCallback(() => {
    setSelectedRecommendationId(null);
    setRecommendationOverlayMode(null);
  }, []);

  const value = useMemo<MediaWorkflowContextValue>(() => ({
    virus,
    setVirus,
    brand,
    setBrand,
    weeklyBudget,
    setWeeklyBudget,
    campaignGoal,
    setCampaignGoal,
    dataVersion,
    invalidateData,
    selectedRecommendationId,
    recommendationOverlayMode,
    openRecommendation,
    closeRecommendation,
  }), [
    brand,
    campaignGoal,
    closeRecommendation,
    dataVersion,
    invalidateData,
    openRecommendation,
    recommendationOverlayMode,
    selectedRecommendationId,
    virus,
    weeklyBudget,
  ]);

  return (
    <MediaWorkflowContext.Provider value={value}>
      {children}
    </MediaWorkflowContext.Provider>
  );
};

export function useMediaWorkflow(): MediaWorkflowContextValue {
  const context = useContext(MediaWorkflowContext);
  if (!context) {
    throw new Error('useMediaWorkflow must be used inside MediaWorkflowProvider');
  }
  return context;
}
