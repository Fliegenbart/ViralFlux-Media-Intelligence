import React, { useEffect, useId, useMemo, useRef, useState } from 'react';

import CollapsibleSection from '../CollapsibleSection';
import { OPERATOR_LABELS } from '../../constants/operatorLabels';
import { UI_COPY, evidenceStatusHelper, evidenceStatusLabel } from '../../lib/copy';
import { explainInPlainGerman, normalizeGermanText } from '../../lib/plainLanguage';
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
  metricContractBadge,
  metricContractDisplayLabel,
  metricContractNote,
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

type DrawerTone = 'success' | 'warning' | 'neutral';

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
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const lastFocusedRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const summaryId = useId();
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

  useEffect(() => {
    if (!detail && !loading) return undefined;

    lastFocusedRef.current = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }

      if (event.key === 'Tab' && drawerRef.current) {
        const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      lastFocusedRef.current?.focus();
    };
  }, [detail, loading, onClose]);

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
  const detailEvidenceClass = detail?.evidence_class;
  const heroSummary = explainInPlainGerman(
    detail?.decision_brief?.summary_sentence
    || detail?.reason
    || 'Kampagnenvorschlag aus aktueller Vorhersage und Fokusregion zur Prüfung und Freigabe.',
  );
  const signalScoreLabel = normalizeGermanText(metricContractDisplayLabel(detail?.field_contracts, 'signal_score', UI_COPY.signalScore));
  const signalScoreBadge = metricContractBadge(detail?.field_contracts, 'signal_score', OPERATOR_LABELS.ranking_signal);
  const signalScoreNote = metricContractNote(
    detail?.field_contracts,
    'signal_score',
    'Hilft beim Vergleichen und Priorisieren, ist aber keine Eintrittswahrscheinlichkeit.',
  );
  const priorityScoreLabel = normalizeGermanText(metricContractDisplayLabel(detail?.field_contracts, 'priority_score', UI_COPY.decisionPriority));
  const priorityScoreBadge = metricContractBadge(detail?.field_contracts, 'priority_score', 'Aktivierungs-Priorität');
  const priorityScoreNote = metricContractNote(
    detail?.field_contracts,
    'priority_score',
    'Hilft bei der Reihenfolge der Aktivierung, nicht bei der Schätzung eines Eintritts.',
  );
  const signalConfidenceLabel = normalizeGermanText(metricContractDisplayLabel(detail?.field_contracts, 'signal_confidence_pct', OPERATOR_LABELS.signal_confidence));
  const signalConfidenceBadge = metricContractBadge(detail?.field_contracts, 'signal_confidence_pct', OPERATOR_LABELS.signal_confidence);
  const signalConfidenceNote = metricContractNote(
    detail?.field_contracts,
    'signal_confidence_pct',
    'Beschreibt Signalsicherheit oder Agreement, nicht die Modellwahrscheinlichkeit.',
  );
  const outcomeSignalLabel = normalizeGermanText(metricContractDisplayLabel(detail?.field_contracts, 'outcome_signal_score', 'Wirkungssignal aus Kundendaten'));
  const outcomeSignalBadge = metricContractBadge(detail?.field_contracts, 'outcome_signal_score', 'Outcome-Lernsignal');
  const outcomeSignalNote = metricContractNote(
    detail?.field_contracts,
    'outcome_signal_score',
    'Beschreibt ein beobachtetes Lernsignal aus Kundendaten, keine Forecast-Wahrscheinlichkeit.',
  );
  const outcomeConfidenceLabel = normalizeGermanText(metricContractDisplayLabel(detail?.field_contracts, 'outcome_confidence_pct', 'Lern-Sicherheit'));
  const outcomeConfidenceBadge = metricContractBadge(detail?.field_contracts, 'outcome_confidence_pct', 'Lern-Sicherheit');
  const outcomeConfidenceNote = metricContractNote(
    detail?.field_contracts,
    'outcome_confidence_pct',
    'Beschreibt die Sicherheit des Outcome-Lernsignals, nicht die Modellkalibrierung.',
  );
  const drawerReadiness = detail ? approvalMemoReadiness(detail, syncPreview) : null;
  const budgetDirection = detail ? budgetDirectionLabel(detail.budget_shift_pct) : 'Budgetrichtung offen';
  const channelDirection = detail ? drawerChannelDirection(detail, channelRows) : 'Kanalmix im Detail prüfen';
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
    <div className="drawer-overlay" role="presentation" onClick={onClose}>
      <div
        ref={drawerRef}
        className="drawer-panel review-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={summaryId}
        aria-busy={loading}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-header review-sheet-header">
          <button ref={closeButtonRef} className="media-button secondary" type="button" onClick={onClose} aria-label="Kampagnen-Detail schließen">Schließen</button>
        </div>

        {loading ? (
          <div className="campaign-empty-board" role="status" aria-live="polite" style={{ color: 'var(--text-muted)' }}>Lade Kampagnenvorschlag…</div>
        ) : detail ? (
          <div className="review-sheet-stack">
            <section className="review-sheet-hero">
              <div className="review-sheet-main">
                <div className="review-sheet-topline">
                  <span className="campaign-status-badge" style={tone}>
                    {detail?.status_label || workflowLabel(detail?.status) || 'Lädt'}
                  </span>
                  {drawerReadiness ? (
                    <span className={`campaign-confidence-chip campaign-confidence-chip--${drawerReadiness.tone}`}>
                      {drawerReadiness.label}
                    </span>
                  ) : null}
                </div>
                <span className="section-kicker">Freigabe-Memo</span>
                <h2 id={titleId} className="review-sheet-title">
                  {normalizeGermanText(detail.display_title || detail.campaign_name || 'Kampagnenvorschlag')}
                </h2>
                <div className="review-sheet-meta">
                  <span className="review-sheet-meta__item">
                    {(detail.region_codes_display?.join(', ') || detail.region || 'National')} · Bundesland-Level
                  </span>
                  {detail?.updated_at ? (
                    <span className="review-sheet-meta__item">
                      Stand {formatDateTime(detail.updated_at)}
                    </span>
                  ) : null}
                </div>
                <p id={summaryId} className="review-sheet-copy">{heroSummary}</p>

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
                <div className="campaign-focus-label">Freigabe auf einen Blick</div>
                <div className="campaign-focus-title">{normalizeGermanText(detail.recommended_product || detail.product)}</div>
                <div className="campaign-focus-context">
                  {normalizeGermanText(detail.region_codes_display?.join(', ') || detail.region || 'National')}
                </div>

                <div className="campaign-metric-grid review-metric-grid">
                  <div className="campaign-metric-card">
                    <span>Budgetrichtung</span>
                    <strong>{budgetDirection}</strong>
                    <small>{drawerBudgetSupport(detail)}</small>
                  </div>
                  <div className="campaign-metric-card">
                    <span>Kanalfokus</span>
                    <strong>{channelDirection}</strong>
                    <small>Die erste Ebene zeigt bewusst nur die Richtung.</small>
                  </div>
                </div>

                <div className="workspace-note-list review-sheet-aside-notes">
                  <div className="workspace-note-card">
                    <strong>Startfenster</strong>
                    <div>{flightWindowLabel(detail)}</div>
                  </div>
                  <div className="workspace-note-card">
                    <strong>Übergabe</strong>
                    <div>{readinessStateLabel(syncPreview?.readiness.state, syncPreview?.readiness.can_sync_now)} · {syncPreview?.connector_label || 'noch keine Übergabevorschau'}</div>
                  </div>
                </div>
              </aside>
            </section>

            <section className="workflow-rail" aria-label="Workflow-Fortschritt">
              {workflowSteps.map((step, index) => {
                const isCurrent = index === currentWorkflowIndex;
                const isComplete = index < currentWorkflowIndex;
                return (
                  <div
                    key={step.key}
                    className={`workflow-step${isCurrent ? ' is-current' : ''}${isComplete ? ' is-complete' : ''}`}
                    aria-current={isCurrent ? 'step' : undefined}
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

            <section className="drawer-grid review-sheet-grid review-sheet-grid--primary">
              <div className="card review-card">
                <h3 className="subsection-title">Freigabe auf einen Blick</h3>
                <div className="review-stat-grid">
                  <div className="metric-box">
                    <span>Budgetrichtung</span>
                    <strong style={{ fontSize: 18 }}>{budgetDirection}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Zielgröße</span>
                    <strong style={{ fontSize: 18 }}>{kpiLabel(detail.primary_kpi || detail.campaign_pack?.measurement_plan?.primary_kpi)}</strong>
                  </div>
                </div>

                <div className="soft-panel review-panel-soft">
                  <div className="campaign-focus-label">Warum jetzt?</div>
                  <div className="review-body-copy">{heroSummary}</div>
                </div>

                <div className="soft-panel review-panel-soft">
                  <div className="campaign-focus-label">Was diese Empfehlung trägt</div>
                  <div className="review-stack">
                    <div className="review-body-copy">
                      <strong>Belastbarkeit</strong>: {detailEvidenceClass ? evidenceStatusLabel(detailEvidenceClass) : 'Noch offen'}. {detailEvidenceClass ? evidenceStatusHelper(detailEvidenceClass) : 'Der Fall braucht noch eine genauere Einordnung.'}
                    </div>
                    <div className="review-body-copy">
                      <strong>{OPERATOR_LABELS.signal_confidence}</strong>: {confidenceValue != null ? `${confidenceValue}% ${signalConfidenceLabel}` : `${signalConfidenceLabel} offen`}.
                    </div>
                    <div className="review-body-copy">
                      <strong>{UI_COPY.stateLevelScope}</strong>: Bundesland-Level, kein City-Forecast.
                    </div>
                  </div>
                </div>

                <div className="soft-panel review-panel-soft">
                  <div className="campaign-focus-label">Blocker und Handoff</div>
                  <div className="review-stack">
                    {detail.publish_blockers && detail.publish_blockers.length > 0 ? (
                      detail.publish_blockers.map((note) => (
                        <div key={note} className="review-body-copy">{explainInPlainGerman(note)}</div>
                      ))
                    ) : (
                      <div className="review-body-copy">{publishabilityHint(detail)}</div>
                    )}
                    <div className="review-body-copy">
                      <strong>Übergabe</strong>: {readinessStateLabel(syncPreview?.readiness.state, syncPreview?.readiness.can_sync_now)}.
                    </div>
                  </div>
                </div>
              </div>

              <div className="card review-card">
                <h3 className="subsection-title">Operative Richtung</h3>

                <div className="review-detail-group">
                  <div className="campaign-focus-label">Leitbotschaft</div>
                  <div className="review-hero-message">
                    {detail.campaign_pack?.message_framework?.hero_message || 'Noch keine Leitbotschaft'}
                  </div>
                </div>

                <div className="review-detail-group">
                  <div className="campaign-focus-label">Kanalmix</div>
                  <div style={{ display: 'grid', gap: 10 }}>
                    {channelRows.length > 0 ? channelRows.map((row) => (
                      <div key={`${row.channel}-${row.share_pct}`} className="evidence-row">
                        <span>{normalizeGermanText(row.channel)}</span>
                        <strong>{formatPercent(row.share_pct || 0)}</strong>
                      </div>
                    )) : (
                      <div className="review-muted-copy">Noch kein Kanalmix vorhanden.</div>
                    )}
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
                  <div className="campaign-focus-label">Nächste Schritte</div>
                  <div className="review-stack">
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

            <section className="card review-card">
              <div className="review-sync-header">
                <div>
                  <h3 className="subsection-title">Übergabe vorbereiten</h3>
                  <p className="subsection-copy" style={{ marginTop: 6 }}>
                    Hier bereitest du die operative Übergabe für Meta, Google oder DV360 vor.
                  </p>
                </div>
                <div className="review-sync-actions">
                  <select aria-label="Zielsystem für Übergabe" className="media-input" value={connectorKey} onChange={(event) => setConnectorKey(event.target.value)} style={{ minWidth: 160 }}>
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
                  <div className="drawer-grid review-sheet-grid review-sheet-grid--sync">
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

                  <CollapsibleSection
                    title="Rohpayload anzeigen"
                    subtitle="Nur wenn du die technische Übergabestruktur im Detail sehen möchtest."
                  >
                    <pre className="sync-preview-block">{syncPayloadText}</pre>
                  </CollapsibleSection>
                </div>
              ) : (
                <div className="review-muted-copy" style={{ marginTop: 14 }}>
                  Noch keine Übergabevorschau geladen.
                </div>
              )}
            </section>

            <CollapsibleSection
              title="Zweiter Blick: Kennzahlen und Lernsignale"
              subtitle="Diese Details helfen beim tieferen Verständnis, gehören aber bewusst nicht in die erste Freigabeschicht."
            >
              <section className="drawer-grid review-sheet-grid review-sheet-grid--secondary">
                <div className="card review-card">
                  <h3 className="subsection-title">Kennzahlen einordnen</h3>
                  <div className="review-stack">
                    <div className="review-body-copy">
                      <strong>{signalScoreLabel}</strong>: {signalScoreBadge}. {signalScoreNote}
                    </div>
                    <div className="review-body-copy">
                      <strong>{priorityScoreLabel}</strong>: {priorityScoreBadge}. {priorityScoreNote}
                    </div>
                    <div className="review-body-copy">
                      <strong>{signalConfidenceLabel}</strong>: {signalConfidenceBadge}. {signalConfidenceNote}
                    </div>
                    <div className="review-body-copy">
                      <strong>KI-Modell</strong>: {aiModelLabel(detail.campaign_pack?.ai_meta?.provider, detail.campaign_pack?.ai_meta?.model)}
                    </div>
                    <div className="review-body-copy">
                      <strong>{signalScoreLabel}</strong> aktuell: {formatPercent(primarySignalScore(detail))}
                    </div>
                  </div>

                  {(detail.outcome_signal_score != null || detail.outcome_learning_explanation) && (
                    <div className="soft-panel review-panel-soft">
                      <div className="campaign-focus-label">Wirkung aus Kundendaten</div>
                      <div className="review-body-copy" style={{ marginTop: 8 }}>
                        {explainInPlainGerman(detail.outcome_learning_explanation) || 'Kundendaten sind für diesen Vorschlag noch nicht stark genug angeschlossen.'}
                      </div>
                      <div className="review-chip-row" style={{ marginTop: 10 }}>
                        <span className="step-chip">
                          {outcomeSignalLabel} {formatPercent(detail.outcome_signal_score)}
                        </span>
                        <span className="step-chip">
                          Lernstand {learningStateLabel(detail.learning_state)}
                        </span>
                        <span className="step-chip">
                          {outcomeConfidenceLabel} {detail.outcome_confidence_pct != null ? formatPercent(detail.outcome_confidence_pct) : '-'}
                        </span>
                      </div>
                      <div className="review-stack" style={{ marginTop: 12 }}>
                        <div className="review-body-copy">
                          <strong>{outcomeSignalLabel}</strong>: {outcomeSignalBadge}. {outcomeSignalNote}
                        </div>
                        <div className="review-body-copy">
                          <strong>{outcomeConfidenceLabel}</strong>: {outcomeConfidenceBadge}. {outcomeConfidenceNote}
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                <div className="card review-card">
                  <h3 className="subsection-title">Weitere Details</h3>

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

                  <div className="review-detail-group">
                    <div className="campaign-focus-label">Suchthemen</div>
                    <div className="review-chip-row">
                      {keywordClusters.length > 0 ? keywordClusters.map((keyword) => (
                        <span key={keyword} className="step-chip">{normalizeGermanText(keyword)}</span>
                      )) : <span className="review-muted-copy">Keine Keywords hinterlegt.</span>}
                    </div>
                  </div>

                  <div className="review-detail-group">
                    <div className="campaign-focus-label">Zielgruppen</div>
                    <div className="review-chip-row">
                      {audienceSegments.length > 0 ? audienceSegments.map((segment) => (
                        <span key={segment} className="step-chip">{segment}</span>
                      )) : <span className="review-muted-copy">Keine Zielgruppen hinterlegt.</span>}
                    </div>
                  </div>

                  <div className="soft-panel review-panel-soft">
                    <div className="campaign-focus-label">Leitplanken</div>
                    <div className="review-stack">
                      {guardrailNotes.length > 0 ? (
                        guardrailNotes.map((note) => (
                          <div key={note} className="review-body-copy">{explainInPlainGerman(note)}</div>
                        ))
                      ) : (
                        <div className="review-muted-copy">Keine zusätzlichen Hinweise.</div>
                      )}
                    </div>
                  </div>
                </div>
              </section>
            </CollapsibleSection>
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

function approvalMemoReadiness(
  detail: RecommendationDetail,
  syncPreview: PreparedSyncPayload | null,
): { label: string; detail: string; tone: DrawerTone } {
  if (detail.publish_blockers && detail.publish_blockers.length > 0) {
    return {
      label: 'Blockiert',
      detail: explainInPlainGerman(detail.publish_blockers[0]),
      tone: 'warning',
    };
  }

  const lifecycle = String(detail.lifecycle_state || detail.status || '').toUpperCase();
  if (syncPreview?.readiness.can_sync_now || lifecycle === 'SYNC_READY') {
    return {
      label: 'Bereit zur Übergabe',
      detail: 'Die Empfehlung kann jetzt für das Mediatool vorbereitet werden.',
      tone: 'success',
    };
  }
  if (lifecycle === 'APPROVE' || lifecycle === 'APPROVED') {
    return {
      label: 'Bereit für Freigabe',
      detail: 'Der Vorschlag ist entscheidungsreif und wartet auf den Freigabeschritt.',
      tone: 'success',
    };
  }
  if (lifecycle === 'REVIEW' || lifecycle === 'READY') {
    return {
      label: 'Bereit zur Prüfung',
      detail: 'Der Vorschlag sollte jetzt fachlich geprüft und priorisiert werden.',
      tone: 'neutral',
    };
  }
  if (lifecycle === 'LIVE' || lifecycle === 'ACTIVATED') {
    return {
      label: 'Aktiv',
      detail: 'Der Vorschlag ist bereits aktiv oder operativ in Bewegung.',
      tone: 'neutral',
    };
  }
  return {
    label: 'In Vorbereitung',
    detail: 'Der Vorschlag braucht noch Nachschärfung vor der Freigabe.',
    tone: 'neutral',
  };
}

function budgetDirectionLabel(budgetShiftPct?: number | null): string {
  const shift = Number(budgetShiftPct || 0);
  if (!Number.isFinite(shift)) return 'Budgetrichtung offen';
  if (shift > 0) return 'Budget eher erhöhen';
  if (shift < 0) return 'Budget eher senken';
  return 'Budget eher halten';
}

function drawerBudgetSupport(detail: RecommendationDetail): string {
  const weeklyBudget = detail.campaign_pack?.budget_plan?.weekly_budget_eur;
  if (typeof weeklyBudget === 'number' && Number.isFinite(weeklyBudget)) {
    return `Wochenrahmen ${formatCurrency(weeklyBudget)}.`;
  }
  return 'Die Freigabe startet bewusst mit der Richtung, nicht mit Scheingenauigkeit.';
}

function drawerChannelDirection(
  detail: RecommendationDetail,
  channelRows: RecommendationDetail['campaign_pack']['channel_plan'],
): string {
  const fromPlan = [...(channelRows || [])]
    .filter((row) => typeof row.share_pct === 'number' && row.share_pct > 0)
    .sort((left, right) => Number(right.share_pct) - Number(left.share_pct))
    .slice(0, 2)
    .map((row) => humanizeChannel(row.channel));

  if (fromPlan.length === 0) {
    const fromCard = Object.entries(detail.channel_mix || {})
      .filter(([, value]) => typeof value === 'number' && value > 0)
      .sort((left, right) => Number(right[1]) - Number(left[1]))
      .slice(0, 2)
      .map(([key]) => humanizeChannel(key));

    if (fromCard.length === 0) return 'Kanalmix im Detail prüfen';
    if (fromCard.length === 1) return `${fromCard[0]} im Fokus`;
    return `${fromCard[0]} + ${fromCard[1]} im Fokus`;
  }

  if (fromPlan.length === 1) return `${fromPlan[0]} im Fokus`;
  return `${fromPlan[0]} + ${fromPlan[1]} im Fokus`;
}

function humanizeChannel(value: string): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'ctv') return 'CTV';
  if (normalized === 'search') return 'Search';
  if (normalized === 'social') return 'Social';
  if (normalized === 'programmatic') return 'Programmatic';
  return normalizeGermanText(value);
}

function flightWindowLabel(detail: RecommendationDetail): string {
  const start = formatDateShort(detail.activation_window?.start);
  const end = formatDateShort(detail.activation_window?.end);

  if (start === '-' && end === '-') return 'Startfenster offen';
  if (end === '-' || start === end) return `Start ${start}`;
  return `${start} – ${end}`;
}
