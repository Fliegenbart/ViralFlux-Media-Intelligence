import React from 'react';

import { RecommendationCard } from '../../types/media';
import { CAMPAIGN_LANES } from './types';
import {
  formatCurrency,
  formatDateShort,
  formatPercent,
  recommendationLane,
  statusTone,
} from './cockpitUtils';

interface Props {
  cards: RecommendationCard[];
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
  cards,
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
  const grouped = CAMPAIGN_LANES.map((lane) => ({
    ...lane,
    cards: cards.filter((card) => recommendationLane(card) === lane.id),
  }));
  const confidenceValues = cards
    .map((card) => card.confidence)
    .filter((value): value is number => value != null && !Number.isNaN(value))
    .map((value) => (value <= 1 ? value * 100 : value));
  const averageConfidence = confidenceValues.length > 0
    ? Math.round(confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length)
    : null;
  const reviewCount = grouped.find((lane) => lane.id === 'review')?.cards.length || 0;
  const approveCount = grouped.find((lane) => lane.id === 'approve')?.cards.length || 0;
  const syncCount = grouped.find((lane) => lane.id === 'sync')?.cards.length || 0;
  const liveCount = grouped.find((lane) => lane.id === 'live')?.cards.length || 0;
  const aiTouchedCount = cards.filter((card) => {
    const aiStatus = String(card.ai_generation_status || card.campaign_preview?.ai_generation_status || '').trim();
    return aiStatus.length > 0;
  }).length;
  const focusCard = cards.find((card) => ['approve', 'sync', 'review'].includes(recommendationLane(card))) || cards[0] || null;
  const focusTitle = focusCard
    ? (focusCard.campaign_name || focusCard.display_title || focusCard.recommended_product || focusCard.product)
    : 'Noch keine Pakete im Review';
  const focusContext = focusCard
    ? `${focusCard.region_codes_display?.join(', ') || focusCard.region || 'National'} · ${flightWindowLabel(focusCard)}`
    : 'Qwen kann aus Regionen und Wochenentscheidung neue reviewbare Pakete erzeugen.';
  const focusCopy = focusCard
    ? (focusCard.reason || focusCard.decision_brief?.summary_sentence || 'Nächster sinnvoller Kandidat für Review, Freigabe oder Connector-Vorbereitung.')
    : 'Sobald Pakete vorliegen, verschiebt sich der Fokus automatisch auf Review, Freigabe und Sync-Readiness.';

  return (
    <div className="page-stack">
      <section className="campaign-command-grid">
        <article className="card campaign-command-card">
          <div className="campaign-command-top">
            <div className="section-heading" style={{ gap: 14 }}>
              <span className="section-kicker">Campaign Studio</span>
              <h1 className="campaign-command-title">Kampagnen wie ein Review-System, nicht wie eine Liste.</h1>
              <p className="section-copy">
                Qwen erzeugt strukturierte Pakete, das Team prüft Guardrails, Budget und Connector-Readiness in einem sauberen Freigabefluss.
              </p>
            </div>
            <span className="step-chip">{cards.length} Pakete für {virus}</span>
          </div>

          <div className="campaign-focus-panel">
            <div className="campaign-focus-label">Nächster Review-Fokus</div>
            <div className="campaign-focus-title">{focusTitle}</div>
            <div className="campaign-focus-context">{focusContext}</div>
            <p className="campaign-focus-copy">{focusCopy}</p>
          </div>

          <div className="campaign-metric-grid">
            <div className="campaign-metric-card">
              <span>In Review</span>
              <strong>{reviewCount}</strong>
              <small>Pakete mit offener Prüfung</small>
            </div>
            <div className="campaign-metric-card">
              <span>Freigabefähig</span>
              <strong>{approveCount}</strong>
              <small>Bereit für Entscheidung</small>
            </div>
            <div className="campaign-metric-card">
              <span>Sync-ready</span>
              <strong>{syncCount}</strong>
              <small>Connector-Vorbereitung möglich</small>
            </div>
            <div className="campaign-metric-card">
              <span>Confidence</span>
              <strong>{averageConfidence != null ? `${averageConfidence}%` : '-'}</strong>
              <small>{liveCount} live · {aiTouchedCount} mit AI-Plan</small>
            </div>
          </div>
        </article>

        <aside className="campaign-side-stack">
          <section className="card campaign-setup-card">
            <div className="campaign-setup-head">
              <div>
                <div className="section-kicker">Generation</div>
                <h2 className="subsection-title">Neue Pakete aufsetzen</h2>
              </div>
              <span className="step-chip">Qwen</span>
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
                AI erzeugt zuerst strukturierte Pakete. Freigabe und späterer Tool-Sync bleiben getrennt.
              </div>
              <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
                {generationLoading ? 'Qwen erzeugt Pakete...' : 'Kampagnen generieren'}
              </button>
            </div>
          </section>

          <section className="card campaign-guidance-card">
            <div className="campaign-guidance-row">
              <span>Review-Fokus</span>
              <strong>{reviewCount + approveCount}</strong>
            </div>
            <div className="campaign-guidance-row">
              <span>Connector-Fokus</span>
              <strong>{syncCount}</strong>
            </div>
            <div className="campaign-guidance-copy">
              Gute UX hier heißt: wenige starke Pakete, klare Zustände, ein sauberer Schritt zur Freigabe.
            </div>
          </section>
        </aside>
      </section>

      {loading ? (
        <div className="card campaign-empty-board" style={{ color: 'var(--text-muted)' }}>
          Lade Kampagnenpakete...
        </div>
      ) : cards.length === 0 ? (
        <section className="card campaign-empty-board">
          <div className="campaign-empty-eyebrow">Campaign Queue</div>
          <h2 className="campaign-empty-title">Noch keine reviewbaren Pakete im Board.</h2>
          <p className="campaign-empty-copy">
            Starte aus der Wochenentscheidung oder einer Region ein neues Paket. Danach landen Qwen-Entwürfe direkt in einem klaren Review-State statt in einer losen Empfehlungsliste.
          </p>
          <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
            {generationLoading ? 'Qwen erzeugt Pakete...' : 'Jetzt erste Pakete erzeugen'}
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
                  <span className="step-chip">{lane.cards.length}</span>
                </div>

                <div className="campaign-lane-stack">
                  {lane.cards.length > 0 ? lane.cards.map((card) => {
                    const tone = statusTone(card.status);
                    return (
                      <button
                        type="button"
                        key={card.id}
                        onClick={() => onOpenRecommendation(card.id)}
                        className="lane-card campaign-work-item"
                      >
                        <div className="campaign-work-item-top">
                          <span className="campaign-status-badge" style={tone}>
                            {card.status_label || card.status}
                          </span>
                          <span className="campaign-confidence-chip">
                            {confidenceLabel(card.confidence)}
                          </span>
                        </div>

                        <div className="campaign-work-item-head">
                          <div className="campaign-work-item-title">
                            {card.campaign_name || card.display_title || card.product}
                          </div>
                          <div className="campaign-work-item-subtitle">
                            {card.region_codes_display?.join(', ') || card.region || 'National'}
                          </div>
                        </div>

                        <p className="campaign-work-item-copy">
                          {card.reason || card.decision_brief?.summary_sentence || 'Regionale Aktivierung entlang des aktuellen Signals.'}
                        </p>

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
                            <strong>{formatDateShort(card.activation_window?.start)}</strong>
                          </div>
                          <div className="campaign-inline-stat">
                            <span>Budget</span>
                            <strong>{formatCurrency(card.campaign_preview?.budget?.weekly_budget_eur)}</strong>
                          </div>
                        </div>

                        <div className="campaign-work-item-footer">
                          <span>{flightWindowLabel(card)}</span>
                          <span>Review öffnen</span>
                        </div>
                      </button>
                    );
                  }) : (
                    <div className="campaign-empty-lane">
                      Keine Pakete in dieser Phase.
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
