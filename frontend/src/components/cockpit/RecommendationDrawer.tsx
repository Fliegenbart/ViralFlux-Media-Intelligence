import React, { useEffect, useMemo, useState } from 'react';

import {
  ConnectorCatalogItem,
  PreparedSyncPayload,
  RecommendationDetail,
} from '../../types/media';
import {
  STATUS_ACTION_LABELS,
  aiModelLabel,
  formatCurrency,
  formatDateShort,
  formatDateTime,
  formatPercent,
  kpiLabel,
  nextWorkflowStatus,
  readinessStateLabel,
  statusTone,
  workflowLabel,
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
  const tone = statusTone(detail?.lifecycle_state || detail?.status);

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
  const nextSteps = (detail?.campaign_pack?.ai_plan?.next_steps || detail?.campaign_pack?.execution_checklist || []) as Array<{
    task?: string;
    owner?: string;
    eta?: string;
  }>;
  const supportPoints = detail?.campaign_pack?.message_framework?.support_points || [];
  const audienceSegments = detail?.campaign_pack?.targeting?.audience_segments || detail?.target_audience || [];
  const guardrailNotes = detail?.guardrail_notes || detail?.campaign_pack?.guardrail_report?.applied_fixes || [];
  const workflowSteps = [
    { key: 'PREPARE', label: 'Vorbereiten', copy: 'Signal-Kontext und Paketstruktur schärfen' },
    { key: 'REVIEW', label: 'Review', copy: 'Guardrails, Mapping und Timing prüfen' },
    { key: 'APPROVE', label: 'Freigabe', copy: 'Paket ist entscheidungsreif' },
    { key: 'SYNC_READY', label: 'Sync', copy: 'Connector-Preview oder operative Übergabe' },
    { key: 'LIVE', label: 'Live', copy: 'Aktiv oder bereits ausgespielt' },
  ];
  const normalizedStatus = String(detail?.lifecycle_state || detail?.status || '').toUpperCase();
  const currentWorkflowIndex = Math.max(workflowSteps.findIndex((step) => step.key === normalizedStatus), 0);
  const confidenceValue = detail?.confidence == null
    ? null
    : Math.round((detail.confidence <= 1 ? detail.confidence * 100 : detail.confidence));
  const heroSummary = detail?.decision_brief?.summary_sentence || detail?.reason || 'Signal- und Playbook-basiertes Kampagnenpaket für Review und Freigabe.';
  const syncStateTone = syncPreview?.readiness.can_sync_now
    ? {
        background: 'rgba(16, 185, 129, 0.10)',
        color: '#047857',
        border: '1px solid rgba(16, 185, 129, 0.24)',
      }
    : {
        background: 'rgba(245, 158, 11, 0.12)',
        color: '#b45309',
        border: '1px solid rgba(245, 158, 11, 0.24)',
      };

  const syncPayloadText = useMemo(
    () => (syncPreview ? JSON.stringify(syncPreview.connector_payload, null, 2) : ''),
    [syncPreview],
  );

  if (!detail && !loading) return null;

  return (
    <div className="drawer-overlay" role="dialog" aria-modal="true">
      <div className="drawer-panel review-sheet">
        <div className="drawer-header review-sheet-header">
          <div className="review-sheet-topline">
            <span className="campaign-status-badge" style={tone}>
              {detail?.status_label || workflowLabel(detail?.status) || 'Lädt'}
            </span>
            <span className="campaign-confidence-chip">
              {detail?.region_codes_display?.join(', ') || detail?.region || 'National'}
            </span>
            {detail?.updated_at && (
              <span className="campaign-confidence-chip">
                Aktualisiert {formatDateTime(detail.updated_at)}
              </span>
            )}
          </div>
          <button className="media-button secondary" type="button" onClick={onClose}>Schließen</button>
        </div>

        {loading ? (
          <div className="campaign-empty-board" style={{ color: 'var(--text-muted)' }}>Lade Kampagnenpaket...</div>
        ) : detail ? (
          <div className="review-sheet-stack">
            <section className="review-sheet-hero">
              <div className="review-sheet-main">
                <span className="section-kicker">Campaign Review</span>
                <h2 className="review-sheet-title">
                  {detail.display_title || detail.campaign_name || 'Kampagnenpaket'}
                </h2>
                <p className="review-sheet-copy">{heroSummary}</p>

                <div className="review-chip-row">
                  <span className="campaign-confidence-chip">
                    {confidenceValue != null ? `${confidenceValue}% Confidence` : 'Confidence offen'}
                  </span>
                  <span className="campaign-confidence-chip">
                    {workflowLabel(detail.lifecycle_state || detail.status)}
                  </span>
                  <span className="campaign-confidence-chip">
                    KPI {kpiLabel(detail.primary_kpi || detail.campaign_pack?.measurement_plan?.primary_kpi)}
                  </span>
                  <span className="campaign-confidence-chip">
                    {aiModelLabel(detail.campaign_pack?.ai_meta?.provider, detail.campaign_pack?.ai_meta?.model)}
                  </span>
                </div>

                <div className="review-action-row">
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
              </div>

              <aside className="review-sheet-aside">
                <div className="campaign-focus-label">Review Snapshot</div>
                <div className="campaign-focus-title">{detail.recommended_product || detail.product}</div>
                <div className="campaign-focus-context">
                  {detail.region_codes_display?.join(', ') || detail.region || 'National'}
                </div>

                <div className="campaign-metric-grid review-metric-grid">
                  <div className="campaign-metric-card">
                    <span>Shift</span>
                    <strong>{formatPercent(detail.budget_shift_pct || 0)}</strong>
                    <small>Budgetverschiebung</small>
                  </div>
                  <div className="campaign-metric-card">
                    <span>Budget</span>
                    <strong>{formatCurrency(detail.campaign_pack?.budget_plan?.weekly_budget_eur)}</strong>
                    <small>Wochenbudget</small>
                  </div>
                  <div className="campaign-metric-card">
                    <span>Flight</span>
                    <strong>{formatDateShort(detail.activation_window?.start)}</strong>
                    <small>Geplanter Start</small>
                  </div>
                  <div className="campaign-metric-card">
                    <span>Sync</span>
                    <strong>{readinessStateLabel(syncPreview?.readiness.state, syncPreview?.readiness.can_sync_now)}</strong>
                    <small>{syncPreview?.connector_label || 'noch kein Connector-Preview'}</small>
                  </div>
                </div>
              </aside>
            </section>

            <section className="workflow-rail">
              {workflowSteps.map((step, index) => {
                const isCurrent = index === currentWorkflowIndex;
                const isComplete = index < currentWorkflowIndex;
                return (
                  <div
                    key={step.key}
                    className={`workflow-step${isCurrent ? ' is-current' : ''}${isComplete ? ' is-complete' : ''}`}
                  >
                    <div className="workflow-step-index">0{index + 1}</div>
                    <div className="workflow-step-copy">
                      <strong>{step.label}</strong>
                      <span>{step.copy}</span>
                    </div>
                  </div>
                );
              })}
            </section>

            <section className="drawer-grid">
              <div className="card review-card">
                <h3 className="subsection-title">Paket-Überblick</h3>
                <div className="review-stat-grid">
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
                    <span>Flight</span>
                    <strong style={{ fontSize: 18 }}>{formatDateShort(detail.activation_window?.start)}</strong>
                  </div>
                </div>

                <div className="soft-panel review-panel-soft">
                  <div className="campaign-focus-label">Warum jetzt?</div>
                  <div className="review-body-copy">{heroSummary}</div>
                </div>

                <div className="review-detail-group">
                  <div className="campaign-focus-label">Audience</div>
                  <div className="review-chip-row">
                    {audienceSegments.length > 0 ? audienceSegments.map((segment) => (
                      <span key={segment} className="step-chip">{segment}</span>
                    )) : <span className="review-muted-copy">Keine Audience-Segmente hinterlegt.</span>}
                  </div>
                </div>
              </div>

              <div className="card review-card">
                <h3 className="subsection-title">Creative Package</h3>
                <div className="review-detail-group">
                  <div className="campaign-focus-label">Hero Message</div>
                  <div className="review-hero-message">
                    {detail.campaign_pack?.message_framework?.hero_message || 'Noch keine Hero Message'}
                  </div>
                </div>
                <div className="review-detail-group">
                  <div className="campaign-focus-label">Support Points</div>
                  <div className="review-chip-row">
                    {supportPoints.length > 0 ? supportPoints.map((point) => (
                      <span key={point} className="step-chip">{point}</span>
                    )) : <span className="review-muted-copy">Keine Support Points hinterlegt.</span>}
                  </div>
                </div>
                <div className="review-detail-group">
                  <div className="campaign-focus-label">Creative Angles</div>
                  <div className="review-stack">
                    {creativeAngles.length > 0 ? creativeAngles.map((angle) => (
                      <div key={angle} className="soft-panel review-soft-line">
                        {angle}
                      </div>
                    )) : <span className="review-muted-copy">Keine AI-Angles vorhanden.</span>}
                  </div>
                </div>
                {(detail.campaign_pack?.message_framework?.compliance_note || detail.campaign_pack?.ai_plan?.compliance_hinweis) && (
                  <div className="soft-panel review-panel-soft">
                    <div className="campaign-focus-label">Compliance</div>
                    <div className="review-body-copy">
                      {detail.campaign_pack?.message_framework?.compliance_note || detail.campaign_pack?.ai_plan?.compliance_hinweis}
                    </div>
                  </div>
                )}
              </div>
            </section>

            <section className="drawer-grid">
              <div className="card review-card">
                <h3 className="subsection-title">Channel Plan</h3>
                <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
                  {channelRows.length > 0 ? channelRows.map((row) => (
                    <div key={`${row.channel}-${row.share_pct}`} className="evidence-row">
                      <span>{row.channel}</span>
                      <strong>{formatPercent(row.share_pct || 0)}</strong>
                    </div>
                  )) : (
                    <div className="review-muted-copy">Noch kein Channel-Plan vorhanden.</div>
                  )}
                </div>

                <div className="review-detail-group">
                  <div className="campaign-focus-label">Keyword Cluster</div>
                  <div className="review-chip-row">
                    {keywordClusters.length > 0 ? keywordClusters.map((keyword) => (
                      <span key={keyword} className="step-chip">{keyword}</span>
                    )) : <span className="review-muted-copy">Keine Keywords hinterlegt.</span>}
                  </div>
                </div>
              </div>

              <div className="card review-card">
                <h3 className="subsection-title">Next Steps und Guardrails</h3>
                <div className="review-stack" style={{ marginTop: 14 }}>
                  {nextSteps.length > 0 ? nextSteps.map((step, index) => (
                    <div key={index} className="soft-panel review-soft-line">
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {String(step.task || 'Nächster Schritt')}
                      </div>
                      <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                        {String(step.owner || 'Team')} · {String(step.eta || '-')}
                      </div>
                    </div>
                  )) : <div className="review-muted-copy">Keine operativen Schritte hinterlegt.</div>}
                </div>

                <div className="soft-panel review-panel-soft">
                  <div className="campaign-focus-label">Guardrail Notes</div>
                  <div className="review-stack">
                    {guardrailNotes.length > 0 ? (
                      guardrailNotes.map((note) => (
                        <div key={note} className="review-body-copy">{note}</div>
                      ))
                    ) : (
                      <div className="review-muted-copy">Keine zusätzlichen Guardrail-Hinweise.</div>
                    )}
                  </div>
                </div>

                <div className="soft-panel review-panel-soft">
                  <div className="campaign-focus-label">Publish-Blocker</div>
                  <div className="review-stack">
                    {detail.publish_blockers && detail.publish_blockers.length > 0 ? (
                      detail.publish_blockers.map((note) => (
                        <div key={note} className="review-body-copy">{note}</div>
                      ))
                    ) : (
                      <div className="review-muted-copy">{publishabilityHint(detail)}</div>
                    )}
                  </div>
                </div>
              </div>
            </section>

            <section className="card review-card">
              <div className="review-sync-header">
                <div>
                  <h3 className="subsection-title">Media-Tool Sync Preview</h3>
                  <p className="subsection-copy" style={{ marginTop: 6 }}>
                    Connector-ready Paket für spätere Meta-, Google- oder DV360-Anbindung.
                  </p>
                </div>
                <div className="review-sync-actions">
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
                <div className="review-sync-stack">
                  <div className="drawer-grid">
                    <div className="soft-panel review-panel-soft">
                      <div className="campaign-focus-label">Readiness</div>
                      <div className="review-sync-state" style={syncStateTone}>
                        {readinessStateLabel(syncPreview.readiness.state, syncPreview.readiness.can_sync_now)}
                      </div>
                      <div className="review-stack" style={{ marginTop: 12 }}>
                        {syncPreview.readiness.blockers.map((blocker) => (
                          <div key={blocker} style={{ fontSize: 13, color: '#b45309' }}>{blocker}</div>
                        ))}
                        {syncPreview.readiness.warnings.map((warning) => (
                          <div key={warning} style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{warning}</div>
                        ))}
                      </div>
                    </div>
                    <div className="soft-panel review-panel-soft">
                      <div className="campaign-focus-label">Connector</div>
                      <div className="review-hero-message" style={{ fontSize: 18 }}>
                        {syncPreview.connector_label}
                      </div>
                      <div className="review-body-copy" style={{ marginTop: 8 }}>
                        Preview erzeugt am {formatDateShort(syncPreview.generated_at)}
                      </div>
                    </div>
                  </div>

                  <pre className="sync-preview-block">{syncPayloadText}</pre>
                </div>
              ) : (
                <div className="review-muted-copy" style={{ marginTop: 14 }}>
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

function publishabilityHint(detail: RecommendationDetail): string {
  const lifecycle = String(detail.lifecycle_state || detail.status || '').toUpperCase();
  if (detail.is_publishable) {
    return 'Keine offenen Blocker. Paket ist direkt nutzbar.';
  }
  if (lifecycle === 'SYNC_READY') {
    return 'Keine Inhaltsblocker. Paket kann jetzt in den Connector- oder Live-Schritt gehen.';
  }
  if (lifecycle === 'APPROVE') {
    return 'Keine Inhaltsblocker. Paket ist freigabefähig und wartet auf die Entscheidung.';
  }
  if (lifecycle === 'REVIEW') {
    return 'Keine Inhaltsblocker. Paket wartet auf Review und den nächsten Workflow-Schritt.';
  }
  return 'Keine Inhaltsblocker. Paket braucht noch den nächsten Workflow-Schritt.';
}
