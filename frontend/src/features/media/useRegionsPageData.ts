import { useCallback, useEffect, useRef, useState } from 'react';

import {
  MediaRegionsResponse,
  WorkspaceStatusSummary,
} from '../../types/media';
import { mediaApi } from './api';
import {
  buildWorkspaceStatus,
  noop,
  ToastLike,
} from './useMediaData.shared';

export function useRegionsPageData(
  virus: string,
  brand: string,
  dataVersion: number,
  toast: ToastLike = noop,
) {
  const [regionsView, setRegionsView] = useState<MediaRegionsResponse | null>(null);
  const [regionsLoading, setRegionsLoading] = useState(false);
  const [workspaceStatus, setWorkspaceStatus] = useState<WorkspaceStatusSummary | null>(null);
  const loadVersionRef = useRef(0);

  const loadRegions = useCallback(async () => {
    const loadVersion = ++loadVersionRef.current;
    setRegionsLoading(true);
    const [regionsResult, evidenceResult] = await Promise.allSettled([
      mediaApi.getRegions(virus, brand),
      mediaApi.getEvidence(virus, brand),
    ]);

    if (loadVersionRef.current !== loadVersion) {
      return;
    }

    if (regionsResult.status === 'fulfilled') {
      setRegionsView(regionsResult.value);
    } else {
      console.error('Regions fetch failed', regionsResult.reason);
      setRegionsView(null);
      toast('Regionen konnten nicht geladen werden.', 'error');
    }

    if (evidenceResult.status === 'fulfilled') {
      setWorkspaceStatus(buildWorkspaceStatus(null, evidenceResult.value));
    } else {
      console.error('Regions evidence fetch failed', evidenceResult.reason);
      setWorkspaceStatus(null);
      toast('Der Qualitätsstatus für Regionen konnte nicht geladen werden.', 'error');
    }

    setRegionsLoading(false);
  }, [brand, toast, virus]);

  useEffect(() => {
    loadRegions();
    return () => {
      loadVersionRef.current += 1;
    };
  }, [dataVersion, loadRegions]);

  return {
    regionsView,
    regionsLoading,
    loadRegions,
    workspaceStatus,
  };
}
