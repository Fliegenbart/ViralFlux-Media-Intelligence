import { useCallback, useEffect, useRef, useState } from 'react';

import {
  MediaCampaignsResponse,
  WorkspaceStatusSummary,
} from '../../types/media';
import { mediaApi } from './api';
import {
  buildWorkspaceStatus,
  noop,
  ToastLike,
} from './useMediaData.shared';

export function useCampaignsPageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [campaignsView, setCampaignsView] = useState<MediaCampaignsResponse | null>(null);
  const [campaignsLoading, setCampaignsLoading] = useState(false);
  const [workspaceStatus, setWorkspaceStatus] = useState<WorkspaceStatusSummary | null>(null);
  const loadVersionRef = useRef(0);

  const loadCampaigns = useCallback(async () => {
    const loadVersion = ++loadVersionRef.current;
    setCampaignsLoading(true);
    const [campaignsResult, evidenceResult] = await Promise.allSettled([
      mediaApi.getCampaigns(brand),
      mediaApi.getEvidence(virus, brand),
    ]);

    if (loadVersionRef.current !== loadVersion) {
      return;
    }

    if (campaignsResult.status === 'fulfilled') {
      setCampaignsView(campaignsResult.value);
    } else {
      console.error('Campaigns fetch failed', campaignsResult.reason);
      setCampaignsView(null);
      toast('Kampagnenvorschläge konnten nicht geladen werden.', 'error');
    }

    if (evidenceResult.status === 'fulfilled') {
      setWorkspaceStatus(buildWorkspaceStatus(null, evidenceResult.value));
    } else {
      console.error('Campaigns evidence fetch failed', evidenceResult.reason);
      setWorkspaceStatus(null);
      toast('Der Qualitätsstatus für Kampagnen konnte nicht geladen werden.', 'error');
    }

    setCampaignsLoading(false);
  }, [brand, toast, virus]);

  useEffect(() => {
    loadCampaigns();
    return () => {
      loadVersionRef.current += 1;
    };
  }, [dataVersion, loadCampaigns]);

  return {
    campaignsView,
    campaignsLoading,
    loadCampaigns,
    workspaceStatus,
  };
}
