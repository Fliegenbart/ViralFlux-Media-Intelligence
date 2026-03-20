import React from 'react';

import { additionalSuggestionsText } from '../../lib/copy';
import { normalizeGermanText } from '../../lib/plainLanguage';
import { MediaCampaignsResponse, RecommendationCard, WorkspaceStatusSummary } from '../../types/media';
import CollapsibleSection from '../CollapsibleSection';
import {
  workflowLabel,
  formatCurrency,
  formatDateShort,
  formatPercent,
  learningStateLabel,
  metricContractLabel,
  primarySignalScore,
  recommendationLane,
  signalConfidencePercent,
  statusTone,
} from './cockpitUtils';
import WorkspaceStatusPanel from './WorkspaceStatusPanel';

interface Props {
  campaignsView: MediaCampaignsResponse | null;
  virus: string;
  brand: string;
  budget: number;
  goal: string;
  workspaceStatus: WorkspaceStatusSummary | null;
  loading: boolean;
  generationLoading: boolean;
  onBrandChange: (value: string) => void;
  onBudgetChange: (value: number) => void;
  onGoalChange: (value: string) => void;
  onGenerate: () => void;
  onOpenRecommendation: (id: string) => void;
}

const CampaignStudio: React.FC<Props> = ({
  campaignsView,
  virus,
  brand,
  budget,
  goal,
  workspaceStatus,
  loading,
  generationLoading,
  onBrandChange,
  onBudgetChange,
  onGoalChange,
  onGenerate,
  onOpenRecommendation,
}) => {
  const cards = campaignsView?.cards || [];
  const stateCounts = campaignsView?.summary?.states || {};
  const prepareCards = cards.filter((card) => ['prepare', 'review'].includes(recommendationLane(card)));
  const approvalCards = cards.filter((card) => ['approve', 'sync'].includes(recommendationLane(card)));
  const activeCards = cards.filter((card) => recommendationLane(card) === 'live');
  const prepareCount = laneStateCount('prepare', stateCounts) + laneStateCount('review', stateCounts);
  const approvalCount = laneStateCount('approve', stateCounts) + laneStateCount('sync', stateCounts);
  const activeCount = laneStateCount('live', stateCounts);
  const focusCard = cards.find((card) => ['review', 'approve', 'sync'].includes(recommendationLane(card))) || prepareCards[0] || cards[0] || null;
  const focusTitle = focusCard
    ? normalizeGermanText(focusCard.display_title || focusCard.campaign_name || focusCard.recommended_product || focusCard.product)
    : 'Noch kein Kampagnenvorschlag im Fokus';
  const focusContext = focusCard
    ? normalizeGermanText(`${focusCard.region_codes_display?.join(', ') || focusCard.region || 'National'} · ${flightWindowLabel(focusCard)}`)
    : 'Neue Vorschläge lassen sich weiterhin erzeugen, stehen aber bewusst nicht mehr vor der eigentlichen Arbeit.';
  const focusCopy = focusCard
    ? readableCampaignSummary(focusCard)
    : 'Sobald Vorschläge vorliegen, landet der wichtigste Fall automatisch ganz oben und nicht in einer unübersichtlichen Liste.';
  const hiddenBacklog = campaignsView?.summary?.hidden_backlog_cards ?? 0;
  const visibleCards = campaignsView?.summary?.visible_cards ?? cards.length;
  const aiTouchedCount = cards.filter((card) => {
    const aiStatus = String(card.ai_generation_status || card.campaign_preview?.ai_generation_status || '').trim();
    return aiStatus.length > 0;
  }).length;
  const phaseGroups = [
    {
      id: 'prepare',
      label: 'Vorbereitung',
      description: 'Entwürfe und offene Prüfungen.',
      cards: prepareCards,
      total: prepareCount,
    },
    {
      id: 'approval',
      label: 'Freigabe',
      description: 'Entscheidungsreife Fälle und Übergaben.',
      cards: approvalCards,
      total: approvalCount,
    },
    {
      id: 'active',
      label: 'Aktiv',
      description: 'Laufende oder startklare Kampagnen.',
      cards: activeCards,
      total: activeCount,
    },
  ] as const;

  return (
    <div className="page-stack">
      <section className="card subsection-card workspace-priority-card" style={{ padding: 28 }}>
        <div className="workspace-priority-grid">
          <div>
            <div className="section-heading" style={{ gap: 8 }}>
              <span className="section-kicker">Kampagnen</span>
              <h1 className="section-title workspace-priority-card__title">Jetzt zuerst prüfen</h1>
              <p className="section-copy">
                Oben steht immer nur der wichtigste Fall. Er leitet sich aus der aktuellen Vorhersage und der Region mit dem frühesten Signal ab.
              </p>
            </div>

            <div className="campaign-focus-panel" style={{ marginTop: 0 }}>
              <div className="campaign-focus-title">{focusTitle}</div>
              <div className="campaign-focus-context">{focusContext}</div>
              <p className="campaign-focus-copy">{focusCopy}</p>
              {hiddenBacklog > 0 && (
                <div className="campaign-focus-context" style={{ marginTop: 10 }}>
                  {additionalSuggestionsText(hiddenBacklog)}
                </div>
              )}
              <div className="action-row" style={{ marginTop: 16 }}>
                <button
                  className="media-button"
                  type="button"
                  onClick={() => (focusCard ? onOpenRecommendation(focusCard.id) : onGenerate())}
                  disabled={generationLoading && !focusCard}
                >
                  {focusCard ? 'Diesen Fall öffnen' : (generationLoading ? 'Vorschläge werden erstellt...' : 'Erste Vorschläge erstellen')}
                </button>
              </div>
            </div>
          </div>

          <aside className="soft-panel workspace-priority-card__aside">
            <div>
              <div className="section-kicker">Überblick</div>
              <div className="workspace-note-list" style={{ marginTop: 12 }}>
                <div className="workspace-note-card">{prepareCount} Fälle in Vorbereitung</div>
                <div className="workspace-note-card">{approvalCount} Fälle in Freigabe</div>
                <div className="workspace-note-card">{activeCount} aktive oder startklare Kampagnen</div>
              </div>
            </div>

            <div style={{ display: 'grid', gap: 10 }}>
              <div className="evidence-row">
                <span>Sichtbar</span>
                <strong>{visibleCards}</strong>
              </div>
              <div className="evidence-row">
                <span>Priorisiert</span>
                <strong>{campaignsView?.summary?.deduped_cards ?? cards.length}</strong>
              </div>
              <div className="evidence-row">
                <span>Aktiv</span>
                <strong>{activeCards.length}</strong>
              </div>
              <div className="evidence-row">
                <span>Automatisch angereichert</span>
                <strong>{aiTouchedCount}</strong>
              </div>
            </div>
          </aside>
        </div>
      </section>

      <WorkspaceStatusPanel
        status={workspaceStatus}
        title="Bevor wir freigeben"
        intro="Der Kampagnenstapel bleibt bewusst eng an Vorhersage, Datenfrische, Kundendaten und offene Blocker gekoppelt."
      />

      {loading ? (
        <div className="card campaign-empty-board" style={{ color: 'var(--text-muted)' }}>
          Lade Kampagnenvorschläge...
        </div>
      ) : cards.length === 0 ? (
        <section className="card campaign-empty-board">
          <div className="campaign-empty-eyebrow">Kampagnenübersicht</div>
          <h2 className="campaign-empty-title">Noch keine Kampagnenvorschläge in der Übersicht.</h2>
          <p className="campaign-empty-copy">
            Starte aus der Wochenentscheidung oder einer Region einen neuen Vorschlag. Danach landet er direkt in einer klaren Arbeitsphase.
          </p>
          <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
            {generationLoading ? 'Vorschläge werden erstellt...' : 'Jetzt erste Vorschläge erstellen'}
          </button>
        </section>
      ) : (
        <section className="workspace-phase-grid">
          {phaseGroups.map((group) => (
            <section key={group.id} className="card subsection-card workspace-phase-column" style={{ padding: 20 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <span className="section-kicker">{group.label}</span>
                <h2 className="subsection-title">{group.total}</h2>
                <p className="subsection-copy">{group.description}</p>
              </div>

              <div className="campaign-lane-stack" style={{ marginTop: 14 }}>
                {group.cards.length > 0 ? group.cards.map((card) => {
                  const tone = statusTone(card.lifecycle_state || card.status);
                  return (
                    <button
                      type="button"
                      key={card.id}
                      onClick={() => onOpenRecommendation(card.id)}
                      className="lane-card campaign-work-item"
                    >
                      <div className="campaign-work-item-top">
                        <span className="campaign-status-badge" style={tone}>
                          {workflowLabel(card.lifecycle_state || card.status)}
                        </span>
                        <span className="campaign-confidence-chip">
                          {confidenceLabel(
                            card.signal_confidence_pct,
                            card.confidence,
                            metricContractLabel(card.field_contracts, 'signal_confidence_pct', 'Signal-Konfidenz'),
                          )}
                        </span>
                      </div>

                      <div className="campaign-work-item-head">
                        <div className="campaign-work-item-title">
                          {card.display_title || card.campaign_name || card.product}
                        </div>
                        <div className="campaign-work-item-subtitle">
                          {card.region_codes_display?.join(', ') || card.region || 'National'}
                        </div>
                      </div>

                      <p className="campaign-work-item-copy">{readableCampaignSummary(card)}</p>

                      <div className="campaign-work-item-metrics">
                        <div className="campaign-inline-stat">
                          <span>Produkt</span>
                          <strong>{card.recommended_product || card.product}</strong>
                        </div>
                        <div className="campaign-inline-stat">
                          <span>Signal</span>
                          <strong>{formatPercent(primarySignalScore(card))}</strong>
                        </div>
                        <div className="campaign-inline-stat">
                          <span>Budget</span>
                          <strong>{formatCurrency(card.campaign_preview?.budget?.weekly_budget_eur)}</strong>
                        </div>
                      </div>

                      <div className="campaign-work-item-footer">
                        <span>{flightWindowLabel(card)} · {normalizeGermanText(card.evidence_strength || 'Prüfstatus offen')}</span>
                        <span>Details prüfen</span>
                      </div>
                    </button>
                  );
                }) : (
                  <div className="campaign-empty-lane">
                    {group.total > 0
                      ? additionalSuggestionsText(group.total, 'Vorschläge in dieser Phase')
                      : 'Keine Vorschläge in dieser Phase.'}
                  </div>
                )}
              </div>
            </section>
          ))}
        </section>
      )}

      <CollapsibleSection
        title="Weitere Vorschläge erstellen"
        subtitle="Dieser Bereich bleibt bewusst nachgeordnet. Erst prüfen wir den wichtigsten Fall, dann erzeugen wir neue Entwürfe."
      >
        <div className="workspace-two-column">
          <section className="soft-panel workspace-detail-panel">
            <div className="section-kicker">Erstellung</div>
            <div className="campaign-form-grid" style={{ marginTop: 16 }}>
              <label className="campaign-field">
                <span>Marke</span>
                <input className="media-input" value={brand} onChange={(event) => onBrandChange(event.target.value)} />
              </label>
              <label className="campaign-field">
                <span>Wochenbudget</span>
                <input
                  className="media-input"
                  type="number"
                  value={budget}
                  onChange={(event) => onBudgetChange(Number(event.target.value || 0))}
                />
              </label>
              <label className="campaign-field campaign-field-wide">
                <span>Ziel</span>
                <input className="media-input" value={goal} onChange={(event) => onGoalChange(event.target.value)} />
              </label>
            </div>
            <div className="campaign-setup-footer">
              <div className="campaign-setup-note">
                Das System erstellt zuerst einen Entwurf. Prüfung und Freigabe bleiben bewusst davor.
              </div>
              <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
                {generationLoading ? 'Vorschläge werden erstellt...' : 'Vorschläge erstellen'}
              </button>
            </div>
          </section>

          <section className="soft-panel workspace-detail-panel">
            <div className="section-kicker">Arbeitskontext</div>
            <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
              <div className="evidence-row">
                <span>Virus</span>
                <strong>{virus}</strong>
              </div>
              <div className="evidence-row">
                <span>Lernstand</span>
                <strong>{learningStateLabel(campaignsView?.summary?.learning_state)}</strong>
              </div>
              <div className="evidence-row">
                <span>Zusätzliche Vorschläge</span>
                <strong>{hiddenBacklog}</strong>
              </div>
              <div className="evidence-row">
                <span>Aktiv</span>
                <strong>{activeCount}</strong>
              </div>
            </div>
          </section>
        </div>
      </CollapsibleSection>
    </div>
  );
};

export default CampaignStudio;

function confidenceLabel(
  signalConfidencePct?: number | null,
  confidence?: number | null,
  label = 'Signal-Konfidenz',
): string {
  const normalized = signalConfidencePercent(signalConfidencePct, confidence);
  if (normalized == null) return `${label} offen`;
  return `${normalized}% ${label}`;
}

function flightWindowLabel(card: RecommendationCard): string {
  const start = formatDateShort(card.activation_window?.start);
  const end = formatDateShort(card.activation_window?.end);

  if (start === '-' && end === '-') return 'Startfenster offen';
  if (end === '-' || start === end) return `Start ${start}`;
  return `${start} – ${end}`;
}

function readableCampaignSummary(card: RecommendationCard): string {
  const blockers = card.publish_blockers || [];
  if (blockers.length > 0) {
    return normalizeGermanText(blockers[0]);
  }

  const summary = normalizeGermanText(String(card.decision_brief?.summary_sentence || card.reason || '').trim());

  if (!summary) return 'Kampagnenvorschlag aus aktueller Vorhersage und Fokusregion.';
  if (/^[A-Z0-9_]+$/.test(summary)) {
    return `Auslöser: ${humanizeTrigger(summary)}.`;
  }

  return summary;
}

function humanizeTrigger(value: string): string {
  return normalizeGermanText(value
    .split('_')
    .filter(Boolean)
    .map((segment) => segment.charAt(0) + segment.slice(1).toLowerCase())
    .join(' '));
}

function laneStateCount(
  laneId: 'prepare' | 'review' | 'approve' | 'sync' | 'live',
  states: Record<string, number>,
): number {
  if (laneId === 'prepare') return Number(states.PREPARE || 0);
  if (laneId === 'review') return Number(states.REVIEW || 0);
  if (laneId === 'approve') return Number(states.APPROVE || 0);
  if (laneId === 'sync') return Number(states.SYNC_READY || 0);
  if (laneId === 'live') return Number(states.LIVE || 0);
  return 0;
}
