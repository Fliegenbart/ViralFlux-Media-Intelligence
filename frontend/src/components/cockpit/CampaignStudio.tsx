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

  return (
    <div style={{ display: 'grid', gap: 20 }}>
      <section className="context-filter-rail">
        <div>
          <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
            Campaign Studio
          </span>
          <h1 style={{ margin: '6px 0 0', fontSize: 28, color: 'var(--text-primary)' }}>
            Publishable Pakete statt loser Empfehlungen
          </h1>
        </div>
        <span className="step-chip">{cards.length} Kampagnenpakete für {virus}</span>
      </section>

      <section className="card" style={{ padding: 20 }}>
        <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
          <label style={{ display: 'grid', gap: 8 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Brand</span>
            <input className="media-input" value={brand} onChange={(event) => onBrandChange(event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 8 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Wochenbudget</span>
            <input
              className="media-input"
              type="number"
              value={budget}
              onChange={(event) => onBudgetChange(Number(event.target.value || 0))}
            />
          </label>
          <label style={{ display: 'grid', gap: 8 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Ziel</span>
            <input className="media-input" value={goal} onChange={(event) => onGoalChange(event.target.value)} />
          </label>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
              {generationLoading ? 'Qwen erzeugt Pakete...' : 'Kampagnen generieren'}
            </button>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Lade Kampagnenpakete...
        </div>
      ) : (
        <section className="campaign-board">
          {grouped.map((lane) => (
            <div key={lane.id} className="lane-column">
              <div className="lane-header">
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{lane.label}</div>
                  <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>{lane.description}</div>
                </div>
                <span className="step-chip">{lane.cards.length}</span>
              </div>

              <div style={{ display: 'grid', gap: 12 }}>
                {lane.cards.length > 0 ? lane.cards.map((card) => {
                  const tone = statusTone(card.status);
                  return (
                    <button
                      type="button"
                      key={card.id}
                      onClick={() => onOpenRecommendation(card.id)}
                      className="lane-card"
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                        <div style={{ textAlign: 'left' }}>
                          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>
                            {card.campaign_name || card.display_title || card.product}
                          </div>
                          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                            {card.region_codes_display?.join(', ') || card.region || 'National'}
                          </div>
                        </div>
                        <span style={{ borderRadius: 999, padding: '6px 10px', fontSize: 11, fontWeight: 700, ...tone }}>
                          {card.status_label || card.status}
                        </span>
                      </div>

                      <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', marginTop: 14 }}>
                        <div>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Produkt</div>
                          <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>
                            {card.recommended_product || card.product}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Budget-Shift</div>
                          <div style={{ marginTop: 4, fontSize: 13, color: 'var(--accent-violet)', fontWeight: 700 }}>
                            {formatPercent(card.budget_shift_pct || 0)}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Flight Start</div>
                          <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>
                            {formatDateShort(card.activation_window?.start)}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Budget</div>
                          <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>
                            {formatCurrency(card.campaign_preview?.budget?.weekly_budget_eur)}
                          </div>
                        </div>
                      </div>

                      <div style={{ marginTop: 14, fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)', textAlign: 'left' }}>
                        {card.reason || card.decision_brief?.summary_sentence || 'Regionale Aktivierung entlang des aktuellen Signals.'}
                      </div>
                    </button>
                  );
                }) : (
                  <div className="soft-panel" style={{ padding: 16, color: 'var(--text-muted)', fontSize: 13 }}>
                    Keine Pakete in dieser Phase.
                  </div>
                )}
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
};

export default CampaignStudio;
