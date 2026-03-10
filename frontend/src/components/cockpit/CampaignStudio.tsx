import React from 'react';

import { UI_COPY, additionalSuggestionsText } from '../../lib/copy';
import { MediaCampaignsResponse, RecommendationCard } from '../../types/media';
import { CAMPAIGN_LANES } from './types';
import {
  workflowLabel,
  formatCurrency,
  formatDateShort,
  formatPercent,
  recommendationLane,
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
    : 'Die KI kann aus Regionen und Wochenentscheidung neue Kampagnenvorschlaege erzeugen.';
  const focusCopy = focusCard
    ? readableCampaignSummary(focusCard)
    : 'Sobald Vorschlaege vorliegen, rutschen die wichtigsten Faelle automatisch in Pruefung, Freigabe und Uebergabe.';
  const hiddenBacklog = campaignsView?.summary?.hidden_backlog_cards ?? 0;
  const visibleCards = campaignsView?.summary?.visible_cards ?? cards.length;

  return (
    <div className="page-stack">
      <section className="campaign-command-grid">
        <article className="card campaign-command-card">
          <div className="campaign-command-top">
            <div className="section-heading" style={{ gap: 14 }}>
              <span className="section-kicker">Campaign Studio</span>
              <h1 className="campaign-command-title">Kampagnenvorschlaege mit klarer naechster Aktion.</h1>
              <p className="section-copy">
                Die KI erstellt Vorschlaege. Das Team prueft Inhalt, Budget und Uebergabe, bevor etwas live geht.
              </p>
            </div>
            <span className="step-chip">{visibleCards} sichtbar · {campaignsView?.summary?.deduped_cards ?? cards.length} priorisiert fuer {virus}</span>
          </div>

          <div className="campaign-focus-panel">
            <div className="campaign-focus-label">Jetzt zuerst ansehen</div>
            <div className="campaign-focus-title">{focusTitle}</div>
            <div className="campaign-focus-context">{focusContext}</div>
            <p className="campaign-focus-copy">{focusCopy}</p>
            {hiddenBacklog > 0 && (
              <div className="campaign-focus-context" style={{ marginTop: 10 }}>
                {additionalSuggestionsText(hiddenBacklog)}
              </div>
            )}
          </div>

          <div className="campaign-metric-grid">
            <div className="campaign-metric-card">
              <span>Zu pruefen</span>
              <strong>{reviewCount}</strong>
              <small>Vorschlaege mit offener Pruefung</small>
            </div>
            <div className="campaign-metric-card">
              <span>Zur Freigabe</span>
              <strong>{approveCount}</strong>
              <small>Bereit fuer die Entscheidung</small>
            </div>
            <div className="campaign-metric-card">
              <span>Zur Uebergabe</span>
              <strong>{syncCount}</strong>
              <small>Fuer Mediatools vorbereitet</small>
            </div>
            <div className="campaign-metric-card">
              <span>Aktiv oder startklar</span>
              <strong>{campaignsView?.summary?.publishable_cards ?? 0}</strong>
              <small>{liveCount} aktiv · {aiTouchedCount} mit {UI_COPY.ai}-Plan</small>
            </div>
          </div>
        </article>

        <aside className="campaign-side-stack">
          <section className="card campaign-setup-card">
            <div className="campaign-setup-head">
              <div>
                <div className="section-kicker">Generation</div>
                <h2 className="subsection-title">Neue Vorschlaege erstellen</h2>
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
                Die KI erstellt zuerst den Vorschlag. Freigabe und spaetere Uebergabe bleiben getrennt.
              </div>
              <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
                {generationLoading ? 'KI erstellt Vorschlaege...' : 'Vorschlaege erstellen'}
              </button>
            </div>
          </section>

          <section className="card campaign-guidance-card">
            <div className="campaign-guidance-row">
              <span>Prueffokus</span>
              <strong>{reviewCount + approveCount}</strong>
            </div>
            <div className="campaign-guidance-row">
              <span>Uebergabefokus</span>
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
              <span>Entwuerfe</span>
              <strong>{prepareCount}</strong>
            </div>
            <div className="campaign-guidance-copy">
              Wenige starke Vorschlaege, klare Zustaende und ein direkter Weg zur Freigabe sorgen fuer Orientierung.
            </div>
          </section>
        </aside>
      </section>

      {loading ? (
        <div className="card campaign-empty-board" style={{ color: 'var(--text-muted)' }}>
          Lade Kampagnenvorschlaege...
        </div>
      ) : cards.length === 0 ? (
        <section className="card campaign-empty-board">
          <div className="campaign-empty-eyebrow">Kampagnenuebersicht</div>
          <h2 className="campaign-empty-title">Noch keine Kampagnenvorschlaege in der Uebersicht.</h2>
          <p className="campaign-empty-copy">
            Starte aus der Wochenentscheidung oder einer Region einen neuen Vorschlag. Danach landet er direkt in einer klaren Pruefstrecke statt in einer losen Liste.
          </p>
          <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
            {generationLoading ? 'KI erstellt Vorschlaege...' : 'Jetzt erste Vorschlaege erstellen'}
          </button>
        </section>
      ) : (
        <section className="campaign-board">
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
                            {confidenceLabel(card.confidence)}
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
                            <span>Shift</span>
                            <strong>{formatPercent(card.budget_shift_pct || 0)}</strong>
                          </div>
                          <div className="campaign-inline-stat">
                            <span>Flight</span>
                            <strong>{flightWindowLabel(card)}</strong>
                          </div>
                          <div className="campaign-inline-stat">
                            <span>Budget</span>
                            <strong>{formatCurrency(card.campaign_preview?.budget?.weekly_budget_eur)}</strong>
                          </div>
                        </div>

                        <div className="campaign-work-item-footer">
                          <span>{flightWindowLabel(card)} · {card.evidence_strength || 'Evidenz offen'}</span>
                          <span>Details pruefen</span>
                        </div>
                      </button>
                    );
                  }) : (
                    <div className="campaign-empty-lane">
                      {lane.total > 0
                        ? additionalSuggestionsText(lane.total, 'Vorschlaege in dieser Phase')
                        : 'Keine Vorschlaege in dieser Phase.'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
};

export default CampaignStudio;

function confidenceLabel(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return 'Confidence offen';
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(normalized)}% Confidence`;
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
