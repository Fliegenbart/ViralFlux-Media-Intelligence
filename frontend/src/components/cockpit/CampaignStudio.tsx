import React from 'react';

import { UI_COPY, additionalSuggestionsText } from '../../lib/copy';
import { MediaCampaignsResponse, RecommendationCard } from '../../types/media';
import { CAMPAIGN_LANES } from './types';
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

interface Props {
  campaignsView: MediaCampaignsResponse | null;
  virus: string;
  brand: string;
  budget: number;
  goal: string;
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
  const grouped = CAMPAIGN_LANES.map((lane) => ({
    ...lane,
    cards: cards.filter((card) => recommendationLane(card) === lane.id),
    total: laneStateCount(lane.id, stateCounts),
  }));
  const reviewCount = laneStateCount('review', stateCounts);
  const approveCount = laneStateCount('approve', stateCounts);
  const syncCount = laneStateCount('sync', stateCounts);
  const liveCount = laneStateCount('live', stateCounts);
  const prepareCount = laneStateCount('prepare', stateCounts);
  const aiTouchedCount = cards.filter((card) => {
    const aiStatus = String(card.ai_generation_status || card.campaign_preview?.ai_generation_status || '').trim();
    return aiStatus.length > 0;
  }).length;
  const focusCard = cards.find((card) => ['approve', 'sync', 'review'].includes(recommendationLane(card))) || cards[0] || null;
  const focusTitle = focusCard
    ? (focusCard.display_title || focusCard.campaign_name || focusCard.recommended_product || focusCard.product)
    : 'Noch kein Kampagnenvorschlag im Fokus';
  const focusContext = focusCard
    ? `${focusCard.region_codes_display?.join(', ') || focusCard.region || 'National'} · ${flightWindowLabel(focusCard)}`
    : 'Die KI kann aus Regionen und Wochenentscheidung neue Kampagnenvorschläge erzeugen.';
  const focusCopy = focusCard
    ? readableCampaignSummary(focusCard)
    : 'Sobald Vorschläge vorliegen, rutschen die wichtigsten Fälle automatisch in Prüfung, Freigabe und Übergabe.';
  const hiddenBacklog = campaignsView?.summary?.hidden_backlog_cards ?? 0;
  const visibleCards = campaignsView?.summary?.visible_cards ?? cards.length;
  const reviewHeadline = focusCard ? 'Jetzt zuerst prüfen' : 'Noch kein prüfbarer Vorschlag im Fokus';
  const reviewContext = focusCard
    ? 'Die wichtigste offene Kampagne steht oben. Alles andere folgt darunter in den Status-Spalten.'
    : 'Sobald Vorschläge vorliegen, landet der stärkste Fall automatisch hier oben.';

  return (
    <div className="page-stack">
      <section className="card subsection-card" style={{ padding: 28 }}>
        <div className="section-heading" style={{ gap: 10 }}>
          <span className="section-kicker">Kampagnen</span>
          <h1 className="section-title">Kampagnen mit klarer nächster Aktion.</h1>
          <p className="section-copy">
            Zuerst zeigen wir die Fälle für Prüfung und Freigabe. Neue Vorschläge bleiben möglich, stehen aber bewusst nicht im Vordergrund.
          </p>
        </div>

        <div className="campaign-focus-panel" style={{ marginTop: 0 }}>
          <div className="campaign-focus-label">{reviewHeadline}</div>
          <div className="campaign-focus-title">{focusTitle}</div>
          <div className="campaign-focus-context">{focusContext}</div>
          <p className="campaign-focus-copy">{focusCopy}</p>
          <p className="campaign-focus-copy" style={{ marginTop: 8 }}>{reviewContext}</p>
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
              {focusCard ? 'Jetzt zuerst prüfen' : (generationLoading ? 'KI erstellt Vorschläge...' : 'Erste Vorschläge erstellen')}
            </button>
          </div>
        </div>

        <div className="metric-strip">
          <div className="metric-box">
            <span>Zu prüfen</span>
            <strong>{reviewCount}</strong>
          </div>
          <div className="metric-box">
            <span>Zur Freigabe</span>
            <strong>{approveCount}</strong>
          </div>
          <div className="metric-box">
            <span>Zur Übergabe</span>
            <strong>{syncCount}</strong>
          </div>
          <div className="metric-box">
            <span>Aktiv oder startklar</span>
            <strong>{campaignsView?.summary?.publishable_cards ?? 0}</strong>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="card campaign-empty-board" style={{ color: 'var(--text-muted)' }}>
          Lade Kampagnenvorschläge...
        </div>
      ) : cards.length === 0 ? (
        <section className="card campaign-empty-board">
          <div className="campaign-empty-eyebrow">Kampagnenübersicht</div>
          <h2 className="campaign-empty-title">Noch keine Kampagnenvorschläge in der Übersicht.</h2>
          <p className="campaign-empty-copy">
            Starte aus der Wochenentscheidung oder einer Region einen neuen Vorschlag. Danach landet er direkt in einer klaren Prüfstrecke statt in einer losen Liste.
          </p>
          <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
            {generationLoading ? 'KI erstellt Vorschläge...' : 'Jetzt erste Vorschläge erstellen'}
          </button>
        </section>
      ) : (
        <section className="campaign-board campaign-board-scroll">
          {grouped.map((lane, index) => (
            <div key={lane.id} className="lane-column campaign-lane-column">
              <div className="campaign-lane-shell">
                <div className="lane-header campaign-lane-header">
                  <div>
                    <div className="campaign-lane-index">0{index + 1}</div>
                    <div className="subsection-title" style={{ fontSize: 18, marginTop: 8 }}>{lane.label}</div>
                    <div className="subsection-copy" style={{ marginTop: 6 }}>{lane.description}</div>
                  </div>
                  <span className="step-chip">
                    {lane.cards.length}{lane.total > lane.cards.length ? ` / ${lane.total}` : ''}
                  </span>
                </div>

                <div className="campaign-lane-stack">
                  {lane.cards.length > 0 ? lane.cards.map((card) => {
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

                        <p className="campaign-work-item-copy">
                          {readableCampaignSummary(card)}
                        </p>

                        {(card.learning_state || card.outcome_signal_score != null) && (
                          <div className="review-chip-row" style={{ marginTop: 10 }}>
                            <span className="step-chip">
                              Learning {learningStateLabel(card.learning_state)}
                            </span>
                            <span className="step-chip">
                              Outcome {formatPercent(card.outcome_signal_score)}
                            </span>
                          </div>
                        )}

                        {Boolean(card.publish_blockers?.length) && (
                          <div className="review-chip-row" style={{ marginTop: 10 }}>
                            {card.publish_blockers!.slice(0, 2).map((blocker) => (
                              <span key={blocker} className="step-chip">{blocker}</span>
                            ))}
                          </div>
                        )}

                        <div className="campaign-work-item-metrics">
                          <div className="campaign-inline-stat">
                            <span>Produkt</span>
                            <strong>{card.recommended_product || card.product}</strong>
                          </div>
                          <div className="campaign-inline-stat">
                            <span>{metricContractLabel(card.field_contracts, 'signal_score', 'Signal-Score')}</span>
                            <strong>{formatPercent(primarySignalScore(card))}</strong>
                          </div>
                          <div className="campaign-inline-stat">
                            <span>{metricContractLabel(card.field_contracts, 'priority_score', 'Priority-Score')}</span>
                            <strong>{formatPercent(card.priority_score || card.urgency_score || 0)}</strong>
                          </div>
                          <div className="campaign-inline-stat">
                            <span>Budget</span>
                            <strong>{formatCurrency(card.campaign_preview?.budget?.weekly_budget_eur)}</strong>
                          </div>
                        </div>

                        <div className="campaign-work-item-footer">
                          <span>{flightWindowLabel(card)} · {card.evidence_strength || 'Evidenz offen'}</span>
                          <span>Details prüfen</span>
                        </div>
                      </button>
                    );
                  }) : (
                    <div className="campaign-empty-lane">
                      {lane.total > 0
                        ? additionalSuggestionsText(lane.total, 'Vorschläge in dieser Phase')
                        : 'Keine Vorschläge in dieser Phase.'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="campaign-support-grid">
        <section className="card campaign-setup-card campaign-compact-card">
          <div className="campaign-setup-head">
            <div>
              <div className="section-kicker">Generation</div>
              <h2 className="subsection-title">Neue Vorschläge erstellen</h2>
            </div>
            <span className="step-chip">{UI_COPY.ai}</span>
          </div>

          <div className="campaign-form-grid">
            <label className="campaign-field">
              <span>Brand</span>
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
              Die KI erstellt zuerst den Entwurf. Prüfung, Freigabe und Übergabe bleiben bewusst getrennt.
            </div>
            <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
              {generationLoading ? 'KI erstellt Vorschläge...' : 'Vorschläge erstellen'}
            </button>
          </div>
        </section>

        <section className="card campaign-guidance-card campaign-compact-card">
          <div className="section-heading" style={{ gap: 6 }}>
            <h2 className="subsection-title">Systemstand</h2>
            <p className="subsection-copy">
              Ein kurzer Überblick, damit du den Arbeitsstapel schnell einschätzen kannst.
            </p>
          </div>
          <div className="campaign-guidance-row">
            <span>Prüffokus</span>
            <strong>{reviewCount + approveCount}</strong>
          </div>
          <div className="campaign-guidance-row">
            <span>Übergabefokus</span>
            <strong>{syncCount}</strong>
          </div>
          <div className="campaign-guidance-row">
            <span>Priorisiert</span>
            <strong>{campaignsView?.summary?.deduped_cards ?? cards.length}</strong>
          </div>
          <div className="campaign-guidance-row">
            <span>{UI_COPY.additionalSuggestions}</span>
            <strong>{hiddenBacklog}</strong>
          </div>
          <div className="campaign-guidance-row">
            <span>Entwürfe</span>
            <strong>{prepareCount}</strong>
          </div>
          <div className="campaign-guidance-row">
            <span>Learning-State</span>
            <strong>{learningStateLabel(campaignsView?.summary?.learning_state)}</strong>
          </div>
          <div className="campaign-guidance-copy">
            {visibleCards} sichtbar · {campaignsView?.summary?.deduped_cards ?? cards.length} priorisiert für {virus} · {liveCount} aktiv · {aiTouchedCount} mit {UI_COPY.ai}-Plan
          </div>
        </section>
      </section>
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

  if (start === '-' && end === '-') return 'Flight offen';
  if (end === '-' || start === end) return `Start ${start}`;
  return `${start} – ${end}`;
}

function readableCampaignSummary(card: RecommendationCard): string {
  const blockers = card.publish_blockers || [];
  if (blockers.length > 0) {
    return blockers[0];
  }

  const summary = String(card.decision_brief?.summary_sentence || card.reason || '').trim();

  if (!summary) return 'Regionale Aktivierung entlang des aktuellen Signals.';
  if (/^[A-Z0-9_]+$/.test(summary)) {
    return `${humanizeTrigger(summary)} als Trigger erkannt.`;
  }

  return summary;
}

function humanizeTrigger(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map((segment) => segment.charAt(0) + segment.slice(1).toLowerCase())
    .join(' ');
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
