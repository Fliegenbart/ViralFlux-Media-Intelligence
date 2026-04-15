import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import RecommendationDrawer from '../../components/cockpit/RecommendationDrawer';
import { ConnectorCatalogItem, PreparedSyncPayload, RecommendationDetail } from '../../types/media';
import { mediaApi } from './api';
import { useMediaWorkflow } from './workflowContext';
import { useToast } from '../../lib/appContext';

const RecommendationOverlay: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const {
    selectedRecommendationId,
    recommendationOverlayMode,
    closeRecommendation,
    invalidateData,
    dataVersion,
  } = useMediaWorkflow();

  const [detail, setDetail] = useState<RecommendationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [connectorCatalog, setConnectorCatalog] = useState<ConnectorCatalogItem[]>([]);
  const [syncPreview, setSyncPreview] = useState<PreparedSyncPayload | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const isRouteBound = recommendationOverlayMode === 'route';

  const loadDetail = useCallback(async (id: string) => {
    setDetailLoading(true);
    setSyncPreview(null);
    try {
      setDetail(await mediaApi.getRecommendationDetail(id));
    } catch (error) {
      console.error('Recommendation detail failed', error);
      toast('Kampagnendetail konnte nicht geladen werden.', 'error');
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (!selectedRecommendationId) {
      setDetail(null);
      setSyncPreview(null);
      return;
    }
    loadDetail(selectedRecommendationId);
  }, [dataVersion, loadDetail, selectedRecommendationId]);

  useEffect(() => {
    if (!selectedRecommendationId) {
      setConnectorCatalog([]);
      return;
    }
    mediaApi.getConnectors()
      .then(setConnectorCatalog)
      .catch((error) => console.error('Connector catalog failed', error));
  }, [selectedRecommendationId]);

  useEffect(() => {
    if (isRouteBound && !location.pathname.startsWith('/kampagnen')) {
      closeRecommendation();
    }
  }, [closeRecommendation, isRouteBound, location.pathname]);

  const handleClose = useCallback(() => {
    closeRecommendation();
    setSyncPreview(null);
    if (isRouteBound) {
      navigate('/kampagnen');
    }
  }, [closeRecommendation, isRouteBound, navigate]);

  const handleAdvanceStatus = useCallback(async (id: string, nextStatus: string) => {
    setStatusUpdating(true);
    try {
      const data = await mediaApi.updateRecommendationStatus(id, nextStatus);
      toast(`Status auf ${data.new_status || nextStatus} gesetzt.`, 'success');
      invalidateData();
      await loadDetail(id);
    } catch (error) {
      console.error('Status update failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Statuswechsel fehlgeschlagen: ${message}`, 'error');
    } finally {
      setStatusUpdating(false);
    }
  }, [invalidateData, loadDetail, toast]);

  const handleRegenerateAI = useCallback(async (id: string) => {
    setRegenerating(true);
    try {
      setDetail(await mediaApi.regenerateRecommendationAI(id));
      invalidateData();
      toast('KI-Plan aktualisiert.', 'success');
    } catch (error) {
      console.error('AI regeneration failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`KI-Neuberechnung fehlgeschlagen: ${message}`, 'error');
    } finally {
      setRegenerating(false);
    }
  }, [invalidateData, toast]);

  const handlePrepareSync = useCallback(async (id: string, connectorKey: string) => {
    setSyncLoading(true);
    try {
      const data = await mediaApi.prepareSync(id, connectorKey);
      setSyncPreview(data);
      setConnectorCatalog(data.available_connectors || connectorCatalog);
      toast('Übergabevorschau vorbereitet.', 'success');
    } catch (error) {
      console.error('Prepare sync failed', error);
      const message = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast(`Übergabevorschau fehlgeschlagen: ${message}`, 'error');
    } finally {
      setSyncLoading(false);
    }
  }, [connectorCatalog, toast]);

  const hasOverlay = useMemo(
    () => Boolean(selectedRecommendationId || detailLoading || detail),
    [detail, detailLoading, selectedRecommendationId],
  );

  if (!hasOverlay) return null;

  return (
    <RecommendationDrawer
      detail={detail}
      loading={detailLoading}
      connectorCatalog={connectorCatalog}
      syncPreview={syncPreview}
      syncLoading={syncLoading}
      statusUpdating={statusUpdating}
      regenerating={regenerating}
      onClose={handleClose}
      onAdvanceStatus={handleAdvanceStatus}
      onRegenerateAI={handleRegenerateAI}
      onPrepareSync={handlePrepareSync}
    />
  );
};

export default RecommendationOverlay;
