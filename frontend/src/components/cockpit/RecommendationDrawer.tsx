import React, { useEffect, useMemo, useState } from 'react';

import {
  ConnectorCatalogItem,
  PreparedSyncPayload,
  RecommendationDetail,
} from '../../types/media';
import {
  STATUS_ACTION_LABELS,
  formatCurrency,
  formatDateShort,
  formatPercent,
  nextWorkflowStatus,
  statusTone,
} from './cockpitUtils';

interface Props {
  detail: RecommendationDetail | null;
  loading: boolean;
  connectorCatalog: ConnectorCatalogItem[];
  syncPreview: PreparedSyncPayload | null;
  syncLoading: boolean;
  statusUpdating: boolean;
  regenerating: boolean;
  onClose: () => void;
  onAdvanceStatus: (id: string, nextStatus: string) => void;
  onRegenerateAI: (id: string) => void;
  onPrepareSync: (id: string, connectorKey: string) => void;
}

const RecommendationDrawer: React.FC<Props> = ({
  detail,
  loading,
  connectorCatalog,
  syncPreview,
  syncLoading,
  statusUpdating,
  regenerating,
  onClose,
  onAdvanceStatus,
  onRegenerateAI,
  onPrepareSync,
}) => {
  const [connectorKey, setConnectorKey] = useState<string>('meta_ads');
  const nextStatus = nextWorkflowStatus(detail?.status);
  const tone = statusTone(detail?.status);

  useEffect(() => {
    if (syncPreview?.connector_key) {
      setConnectorKey(syncPreview.connector_key);
      return;
    }
    if (connectorCatalog[0]?.key) {
      setConnectorKey(connectorCatalog[0].key);
    }
  }, [connectorCatalog, syncPreview?.connector_key]);

  const channelRows = detail?.campaign_pack?.channel_plan || [];
  const creativeAngles = detail?.campaign_pack?.ai_plan?.creative_angles || [];
  const keywordClusters = detail?.campaign_pack?.ai_plan?.keyword_clusters || [];
  const nextSteps = detail?.campaign_pack?.ai_plan?.next_steps || detail?.campaign_pack?.execution_checklist || [];
  const supportPoints = detail?.campaign_pack?.message_framework?.support_points || [];

  const syncPayloadText = useMemo(
    () => (syncPreview ? JSON.stringify(syncPreview.connector_payload, null, 2) : ''),
    [syncPreview],
  );

  if (!detail && !loading) return null;

  return (
    <div className="drawer-overlay" role="dialog" aria-modal="true">
      <div className="drawer-panel">
        <div className="drawer-header">
          <div>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
              <span style={{ borderRadius: 999, padding: '6px 10px', fontSize: 11, fontWeight: 700, ...tone }}>
                {detail?.status_label || detail?.status || 'Lädt'}
              </span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {detail?.region_codes_display?.join(', ') || detail?.region || 'National'}
              </span>
            </div>
            <h2 style={{ margin: '10px 0 0', fontSize: 28, lineHeight: 1.1, color: 'var(--text-primary)' }}>
              {detail?.campaign_name || detail?.display_title || 'Kampagnenpaket'}
            </h2>
          </div>
          <button className="media-button secondary" type="button" onClick={onClose}>Schließen</button>
        </div>

        {loading ? (
          <div style={{ padding: 24, color: 'var(--text-muted)' }}>Lade Kampagnenpaket...</div>
        ) : detail ? (
          <div style={{ display: 'grid', gap: 18 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
              {nextStatus && (
                <button
                  className="media-button"
                  type="button"
                  onClick={() => onAdvanceStatus(detail.id, nextStatus)}
                  disabled={statusUpdating}
                >
                  {statusUpdating ? 'Aktualisiere...' : (STATUS_ACTION_LABELS[nextStatus] || nextStatus)}
                </button>
              )}
              <button
                className="media-button secondary"
                type="button"
                onClick={() => onRegenerateAI(detail.id)}
                disabled={regenerating}
              >
                {regenerating ? 'Qwen arbeitet...' : 'Mit Qwen neu erzeugen'}
              </button>
            </div>

            <section className="drawer-grid">
              <div className="card" style={{ padding: 18 }}>
                <h3 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)' }}>Paket-Überblick</h3>
                <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', marginTop: 14 }}>
                  <div className="metric-box">
                    <span>Produkt</span>
                    <strong style={{ fontSize: 18 }}>{detail.recommended_product || detail.product}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Budget-Shift</span>
                    <strong>{formatPercent(detail.budget_shift_pct || 0)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Budget</span>
                    <strong style={{ fontSize: 18 }}>{formatCurrency(detail.campaign_pack?.budget_plan?.weekly_budget_eur)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Flight Start</span>
                    <strong style={{ fontSize: 18 }}>{formatDateShort(detail.activation_window?.start)}</strong>
                  </div>
                </div>
                <div className="soft-panel" style={{ padding: 16, marginTop: 14 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Warum jetzt?</div>
                  <div style={{ marginTop: 6, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                    {detail.decision_brief?.summary_sentence || detail.reason || 'Trigger- und Playbook-basierte Aktivierung.'}
                  </div>
                </div>
              </div>

              <div className="card" style={{ padding: 18 }}>
                <h3 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)' }}>Creative Package</h3>
                <div style={{ marginTop: 14, display: 'grid', gap: 14 }}>
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Hero Message</div>
                    <div style={{ marginTop: 6, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                      {detail.campaign_pack?.message_framework?.hero_message || 'Noch keine Hero Message'}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Support Points</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                      {supportPoints.length > 0 ? supportPoints.map((point) => (
                        <span key={point} className="step-chip">{point}</span>
                      )) : <span style={{ color: 'var(--text-muted)' }}>Keine Support Points hinterlegt.</span>}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Creative Angles</div>
                    <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                      {creativeAngles.length > 0 ? creativeAngles.map((angle) => (
                        <div key={angle} className="soft-panel" style={{ padding: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
                          {angle}
                        </div>
                      )) : <span style={{ color: 'var(--text-muted)' }}>Keine AI-Angles vorhanden.</span>}
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section className="drawer-grid">
              <div className="card" style={{ padding: 18 }}>
                <h3 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)' }}>Channel Plan</h3>
                <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
                  {channelRows.length > 0 ? channelRows.map((row) => (
                    <div key={`${row.channel}-${row.share_pct}`} className="evidence-row">
                      <span>{row.channel}</span>
                      <strong>{formatPercent(row.share_pct || 0)}</strong>
                    </div>
                  )) : (
                    <div style={{ color: 'var(--text-muted)' }}>Noch kein Channel-Plan vorhanden.</div>
                  )}
                </div>

                <div style={{ marginTop: 18 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Keyword Cluster</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                    {keywordClusters.length > 0 ? keywordClusters.map((keyword) => (
                      <span key={keyword} className="step-chip">{keyword}</span>
                    )) : <span style={{ color: 'var(--text-muted)' }}>Keine Keywords hinterlegt.</span>}
                  </div>
                </div>
              </div>

              <div className="card" style={{ padding: 18 }}>
                <h3 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)' }}>Next Steps und Guardrails</h3>
                <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
                  {nextSteps.length > 0 ? nextSteps.map((step, index) => (
                    <div key={index} className="soft-panel" style={{ padding: 12 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {String((step as { task?: string }).task || 'Nächster Schritt')}
                      </div>
                      <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                        {String((step as { owner?: string }).owner || 'Team')} · {String((step as { eta?: string }).eta || '-')}
                      </div>
                    </div>
                  )) : <div style={{ color: 'var(--text-muted)' }}>Keine operativen Schritte hinterlegt.</div>}
                </div>

                <div className="soft-panel" style={{ padding: 16, marginTop: 16 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Guardrail Notes</div>
                  <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                    {(detail.guardrail_notes || detail.campaign_pack?.guardrail_report?.applied_fixes || []).length > 0 ? (
                      (detail.guardrail_notes || detail.campaign_pack?.guardrail_report?.applied_fixes || []).map((note) => (
                        <div key={note} style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{note}</div>
                      ))
                    ) : (
                      <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Keine zusätzlichen Guardrail-Hinweise.</div>
                    )}
                  </div>
                </div>
              </div>
            </section>

            <section className="card" style={{ padding: 18 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)' }}>Media-Tool Sync Preview</h3>
                  <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
                    Connector-ready Paket für spätere Meta-, Google- oder DV360-Anbindung.
                  </p>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                  <select className="media-input" value={connectorKey} onChange={(event) => setConnectorKey(event.target.value)} style={{ minWidth: 160 }}>
                    {connectorCatalog.map((connector) => (
                      <option key={connector.key} value={connector.key}>
                        {connector.label}
                      </option>
                    ))}
                  </select>
                  <button
                    className="media-button"
                    type="button"
                    onClick={() => onPrepareSync(detail.id, connectorKey)}
                    disabled={syncLoading}
                  >
                    {syncLoading ? 'Bereite Sync vor...' : 'Sync vorbereiten'}
                  </button>
                </div>
              </div>

              {syncPreview ? (
                <div style={{ display: 'grid', gap: 16, marginTop: 16 }}>
                  <div className="drawer-grid">
                    <div className="soft-panel" style={{ padding: 16 }}>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Readiness</div>
                      <div style={{ marginTop: 6, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {syncPreview.readiness.can_sync_now ? 'Sync-ready' : syncPreview.readiness.state}
                      </div>
                      <div style={{ display: 'grid', gap: 6, marginTop: 12 }}>
                        {syncPreview.readiness.blockers.map((blocker) => (
                          <div key={blocker} style={{ fontSize: 13, color: '#b45309' }}>{blocker}</div>
                        ))}
                        {syncPreview.readiness.warnings.map((warning) => (
                          <div key={warning} style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{warning}</div>
                        ))}
                      </div>
                    </div>
                    <div className="soft-panel" style={{ padding: 16 }}>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Connector</div>
                      <div style={{ marginTop: 6, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {syncPreview.connector_label}
                      </div>
                      <div style={{ marginTop: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                        Preview erzeugt am {formatDateShort(syncPreview.generated_at)}
                      </div>
                    </div>
                  </div>

                  <pre className="sync-preview-block">{syncPayloadText}</pre>
                </div>
              ) : (
                <div style={{ marginTop: 14, color: 'var(--text-muted)' }}>
                  Noch kein Connector-Preview geladen.
                </div>
              )}
            </section>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default RecommendationDrawer;
