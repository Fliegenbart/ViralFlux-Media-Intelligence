import React, { useEffect, useMemo, useState } from 'react';

import { normalizeGermanText } from '../../lib/plainLanguage';
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
  learningStateLabel,
  metricContractLabel,
  nextWorkflowStatus,
  primarySignalScore,
  readinessStateLabel,
  signalConfidencePercent,
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
    { key: 'PREPARE', label: 'Entwurf', copy: 'Signal-Kontext und Aufbau schärfen' },
    { key: 'REVIEW', label: 'Prüfung', copy: 'Inhalt, Timing und Hinweise prüfen' },
    { key: 'APPROVE', label: 'Freigabe', copy: 'Vorschlag ist entscheidungsreif' },
    { key: 'SYNC_READY', label: 'Übergabe', copy: 'Für Plattformen oder operative Übergabe bereit' },
    { key: 'LIVE', label: 'Aktiv', copy: 'Freigegeben oder bereits ausgespielt' },
  ];
  const normalizedStatus = String(detail?.lifecycle_state || detail?.status || '').toUpperCase();
  const currentWorkflowIndex = Math.max(workflowSteps.findIndex((step) => step.key === normalizedStatus), 0);
  const confidenceValue = signalConfidencePercent(detail?.signal_confidence_pct, detail?.confidence);
  const heroSummary = normalizeGermanText(
    detail?.decision_brief?.summary_sentence
    || detail?.reason
    || 'Kampagnenvorschlag aus aktueller Vorhersage und Fokusregion zur Prüfung und Freigabe.',
  );
  const signalScoreLabel = normalizeGermanText(metricContractLabel(detail?.field_contracts, 'signal_score', 'Signalwert'));
  const priorityScoreLabel = normalizeGermanText(metricContractLabel(detail?.field_contracts, 'priority_score', 'Priorität'));
  const signalConfidenceLabel = normalizeGermanText(metricContractLabel(detail?.field_contracts, 'signal_confidence_pct', 'Signalsicherheit'));
  const outcomeConfidenceLabel = normalizeGermanText(metricContractLabel(detail?.field_contracts, 'outcome_confidence_pct', 'Sicherheit aus Kundendaten'));
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
          <div className="campaign-empty-board" style={{ color: 'var(--text-muted)' }}>Lade Kampagnenvorschlag…</div>
        ) : detail ? (
          <div className="review-sheet-stack">
            <section className="review-sheet-hero">
              <div className="review-sheet-main">
                <span className="section-kicker">Kampagnendetail</span>
                <h2 className="review-sheet-title">
                  {normalizeGermanText(detail.display_title || detail.campaign_name || 'Kampagnenvorschlag')}
                </h2>
                <p className="review-sheet-copy">{heroSummary}</p>

                <div className="review-chip-row">
                  <span className="campaign-confidence-chip">
                    {confidenceValue != null ? `${confidenceValue}% ${signalConfidenceLabel}` : `${signalConfidenceLabel} offen`}
                  </span>
                  <span className="campaign-confidence-chip">
                    {workflowLabel(detail.lifecycle_state || detail.status)}
                  </span>
                  <span className="campaign-confidence-chip">
                    {signalScoreLabel} {formatPercent(primarySignalScore(detail))}
                  </span>
                  <span className="campaign-confidence-chip">
                    {priorityScoreLabel} {formatPercent(detail.priority_score || detail.urgency_score || 0)}
                  </span>
                  <span className="campaign-confidence-chip">
                    Lernstand {learningStateLabel(detail.learning_state)}
                  </span>
                  <span className="campaign-confidence-chip">
                    Zielgröße {kpiLabel(detail.primary_kpi || detail.campaign_pack?.measurement_plan?.primary_kpi)}
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
                    {regenerating ? 'Wird neu erstellt...' : 'Neu erstellen'}
                  </button>
                </div>
              </div>

              <aside className="review-sheet-aside">
                <div className="campaign-focus-label">Aktueller Stand</div>
                <div className="campaign-focus-title">{normalizeGermanText(detail.recommended_product || detail.product)}</div>
                <div className="campaign-focus-context">
                  {normalizeGermanText(detail.region_codes_display?.join(', ') || detail.region || 'National')}
                </div>

                <div className="campaign-metric-grid review-metric-grid">
                  <div className="campaign-metric-card">
                    <span>Änderung</span>
                    <strong>{formatPercent(detail.budget_shift_pct || 0)}</strong>
                    <small>Budgetverschiebung</small>
                  </div>
                  <div className="campaign-metric-card">
                    <span>Budget</span>
                    <strong>{formatCurrency(detail.campaign_pack?.budget_plan?.weekly_budget_eur)}</strong>
                    <small>Wochenbudget</small>
                  </div>
                  <div className="campaign-metric-card">
                    <span>Startfenster</span>
                    <strong>{formatDateShort(detail.activation_window?.start)}</strong>
                    <small>Geplanter Start</small>
                  </div>
                  <div className="campaign-metric-card">
                    <span>Übergabe</span>
                    <strong>{readinessStateLabel(syncPreview?.readiness.state, syncPreview?.readiness.can_sync_now)}</strong>
                    <small>{syncPreview?.connector_label || 'noch keine Übergabevorschau'}</small>
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
                <h3 className="subsection-title">Überblick</h3>
                <div className="review-stat-grid">
                  <div className="metric-box">
                    <span>Produkt</span>
                    <strong style={{ fontSize: 18 }}>{normalizeGermanText(detail.recommended_product || detail.product)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Budgetänderung</span>
                    <strong>{formatPercent(detail.budget_shift_pct || 0)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Budget</span>
                    <strong style={{ fontSize: 18 }}>{formatCurrency(detail.campaign_pack?.budget_plan?.weekly_budget_eur)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Startfenster</span>
                    <strong style={{ fontSize: 18 }}>{formatDateShort(detail.activation_window?.start)}</strong>
                  </div>
                </div>

                <div className="soft-panel review-panel-soft">
                  <div className="campaign-focus-label">Warum jetzt?</div>
                  <div className="review-body-copy">{heroSummary}</div>
                </div>

                {(detail.outcome_signal_score != null || detail.outcome_learning_explanation) && (
                  <div className="soft-panel review-panel-soft">
                    <div className="campaign-focus-label">Wirkung aus Kundendaten</div>
                    <div className="review-body-copy" style={{ marginTop: 8 }}>
                      {normalizeGermanText(detail.outcome_learning_explanation) || 'Kundendaten sind für diesen Vorschlag noch nicht stark genug angeschlossen.'}
                    </div>
                    <div className="review-chip-row" style={{ marginTop: 10 }}>
                      <span className="step-chip">
                        Wirkungssignal {formatPercent(detail.outcome_signal_score)}
                      </span>
                      <span className="step-chip">
                        Lernstand {learningStateLabel(detail.learning_state)}
                      </span>
                      <span className="step-chip">
                        {outcomeConfidenceLabel} {detail.outcome_confidence_pct != null ? formatPercent(detail.outcome_confidence_pct) : '-'}
                      </span>
                    </div>
                  </div>
                )}

                <div className="review-detail-group">
                  <div className="campaign-focus-label">Zielgruppen</div>
                  <div className="review-chip-row">
                    {audienceSegments.length > 0 ? audienceSegments.map((segment) => (
                      <span key={segment} className="step-chip">{segment}</span>
                    )) : <span className="review-muted-copy">Keine Zielgruppen hinterlegt.</span>}
                  </div>
                </div>
              </div>

              <div className="card review-card">
                <h3 className="subsection-title">Botschaften</h3>
                <div className="review-detail-group">
                  <div className="campaign-focus-label">Leitbotschaft</div>
                  <div className="review-hero-message">
                    {detail.campaign_pack?.message_framework?.hero_message || 'Noch keine Leitbotschaft'}
                  </div>
                </div>
                <div className="review-detail-group">
                  <div className="campaign-focus-label">Argumente</div>
                  <div className="review-chip-row">
                    {supportPoints.length > 0 ? supportPoints.map((point) => (
                      <span key={point} className="step-chip">{normalizeGermanText(point)}</span>
                    )) : <span className="review-muted-copy">Keine Argumente hinterlegt.</span>}
                  </div>
                </div>
                <div className="review-detail-group">
                  <div className="campaign-focus-label">Textansätze</div>
                  <div className="review-stack">
                    {creativeAngles.length > 0 ? creativeAngles.map((angle) => (
                      <div key={angle} className="soft-panel review-soft-line">
                        {normalizeGermanText(angle)}
                      </div>
                    )) : <span className="review-muted-copy">Keine Textansätze vorhanden.</span>}
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
                <h3 className="subsection-title">Kanalmix</h3>
                <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
                  {channelRows.length > 0 ? channelRows.map((row) => (
                    <div key={`${row.channel}-${row.share_pct}`} className="evidence-row">
                      <span>{row.channel}</span>
                      <strong>{formatPercent(row.share_pct || 0)}</strong>
                    </div>
                  )) : (
                    <div className="review-muted-copy">Noch kein Kanalmix vorhanden.</div>
                  )}
                </div>

                <div className="review-detail-group">
                  <div className="campaign-focus-label">Suchthemen</div>
                  <div className="review-chip-row">
                    {keywordClusters.length > 0 ? keywordClusters.map((keyword) => (
                      <span key={keyword} className="step-chip">{normalizeGermanText(keyword)}</span>
                    )) : <span className="review-muted-copy">Keine Keywords hinterlegt.</span>}
                  </div>
                </div>
              </div>

              <div className="card review-card">
                <h3 className="subsection-title">Nächste Schritte und Leitplanken</h3>
                <div className="review-stack" style={{ marginTop: 14 }}>
                  {nextSteps.length > 0 ? nextSteps.map((step, index) => (
                    <div key={index} className="soft-panel review-soft-line">
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {normalizeGermanText(String(step.task || 'Nächster Schritt'))}
                      </div>
                      <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                        {normalizeGermanText(String(step.owner || 'Team'))} · {normalizeGermanText(String(step.eta || '-'))}
                      </div>
                    </div>
                  )) : <div className="review-muted-copy">Keine operativen Schritte hinterlegt.</div>}
                </div>

                <div className="soft-panel review-panel-soft">
                  <div className="campaign-focus-label">Leitplanken</div>
                  <div className="review-stack">
                    {guardrailNotes.length > 0 ? (
                      guardrailNotes.map((note) => (
                        <div key={note} className="review-body-copy">{normalizeGermanText(note)}</div>
                      ))
                    ) : (
                      <div className="review-muted-copy">Keine zusätzlichen Hinweise.</div>
                    )}
                  </div>
                </div>

                <div className="soft-panel review-panel-soft">
                  <div className="campaign-focus-label">Freigabe-Hinweise</div>
                  <div className="review-stack">
                    {detail.publish_blockers && detail.publish_blockers.length > 0 ? (
                      detail.publish_blockers.map((note) => (
                        <div key={note} className="review-body-copy">{normalizeGermanText(note)}</div>
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
                  <h3 className="subsection-title">Übergabevorschau für Plattformen</h3>
                  <p className="subsection-copy" style={{ marginTop: 6 }}>
                    Vorbereitete Übergabe für Meta, Google oder DV360.
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
                    {syncLoading ? 'Bereite Übergabe vor…' : 'Übergabe vorbereiten'}
                  </button>
                </div>
              </div>

              {syncPreview ? (
                <div className="review-sync-stack">
                  <div className="drawer-grid">
                    <div className="soft-panel review-panel-soft">
                      <div className="campaign-focus-label">Status</div>
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
                      <div className="campaign-focus-label">Zielsystem</div>
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
                  Noch keine Übergabevorschau geladen.
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
    return 'Keine offenen Blocker. Der Vorschlag ist direkt nutzbar.';
  }
  if (lifecycle === 'SYNC_READY') {
    return 'Keine Inhaltsblocker. Der Vorschlag kann jetzt an ein Mediatool übergeben oder aktiviert werden.';
  }
  if (lifecycle === 'APPROVE') {
    return 'Keine Inhaltsblocker. Der Vorschlag ist freigabefähig und wartet auf die Entscheidung.';
  }
  if (lifecycle === 'REVIEW') {
    return 'Keine Inhaltsblocker. Der Vorschlag wartet auf die Prüfung und den nächsten Schritt.';
  }
  return 'Keine Inhaltsblocker. Der Vorschlag braucht noch den nächsten Schritt.';
}
