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
  metricContractBadge,
  metricContractDisplayLabel,
  metricContractNote,
  primarySignalScore,
  recommendationLane,
  signalConfidencePercent,
  statusTone,
} from './cockpitUtils';
import WorkspaceStatusPanel from './WorkspaceStatusPanel';
import {
  OperatorPanel,
  OperatorSection,
  OperatorStat,
} from './operator/OperatorPrimitives';

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
  const focusSignalLabel = metricContractDisplayLabel(focusCard?.field_contracts, 'signal_score', 'Signal-Score');
  const focusSignalBadge = metricContractBadge(focusCard?.field_contracts, 'signal_score', 'Ranking-Signal');
  const focusSignalNote = metricContractNote(
    focusCard?.field_contracts,
    'signal_score',
    'Hilft beim Vergleichen und Priorisieren, ist aber keine Eintrittswahrscheinlichkeit.',
  );
  const hiddenBacklog = campaignsView?.summary?.hidden_backlog_cards ?? 0;
  const visibleCards = campaignsView?.summary?.visible_cards ?? cards.length;
  const aiTouchedCount = cards.filter((card) => {
    const aiStatus = String(card.ai_generation_status || card.campaign_preview?.ai_generation_status || '').trim();
    return aiStatus.length > 0;
  }).length;
  const focusNotes = [
    focusCard ? `${focusSignalLabel}: ${focusSignalBadge}. ${focusSignalNote}` : null,
    hiddenBacklog > 0 ? additionalSuggestionsText(hiddenBacklog) : null,
    focusCard?.recommended_product ? `Produktfokus: ${focusCard.recommended_product}` : null,
  ].filter(Boolean) as string[];
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
      <OperatorSection
        kicker="Kampagnen"
        title="Jetzt zuerst prüfen"
        description="Hier steht immer zuerst der Fall, um den du dich jetzt kümmern solltest."
        tone="accent"
        className="campaign-hero-shell"
      >
        <div className="campaign-command-grid">
          <div className="campaign-focus-panel" style={{ marginTop: 0 }}>
            <div className="review-chip-row">
              <span className="step-chip">Fokusfall</span>
              <span className="step-chip">{focusContext}</span>
              <span className="step-chip">{focusCard ? workflowLabel(focusCard.lifecycle_state || focusCard.status) : 'noch offen'}</span>
            </div>
            <div className="campaign-focus-title">{focusTitle}</div>
            <div className="campaign-focus-context">{focusContext}</div>
            <p className="campaign-focus-copy">{focusCopy}</p>

            <div className="operator-stat-grid">
              <OperatorStat
                label="Phase"
                value={focusCard ? workflowLabel(focusCard.lifecycle_state || focusCard.status) : 'Offen'}
                meta="aktueller Arbeitsstand"
                tone="accent"
              />
              <OperatorStat
                label={focusSignalLabel}
                value={focusCard ? formatPercent(primarySignalScore(focusCard)) : '-'}
                meta="hilft beim Priorisieren"
              />
              <OperatorStat
                label="Budget"
                value={formatCurrency(focusCard?.campaign_preview?.budget?.weekly_budget_eur)}
                meta="aktueller Vorschlag"
              />
              <OperatorStat
                label="Region"
                value={focusCard?.region_codes_display?.join(', ') || focusCard?.region || 'National'}
                meta="für den nächsten Schritt"
              />
            </div>

            <div className="workspace-note-list">
              {focusNotes.map((item) => (
                <div key={item} className="workspace-note-card">
                  {item}
                </div>
              ))}
            </div>

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

          <OperatorPanel
            eyebrow="Pipeline"
            title="Wie die Arbeit gerade verteilt ist"
            description="Hier siehst du zuerst, wie viele Fälle vorbereitet, freigegeben oder schon aktiv sind."
            tone="muted"
            className="campaign-command-rail"
          >
            <div className="operator-stat-grid">
              <OperatorStat label="Vorbereitung" value={prepareCount} meta="offene Fälle" />
              <OperatorStat label="Freigabe" value={approvalCount} meta="entscheidungsreif" tone="accent" />
              <OperatorStat label="Aktiv" value={activeCount} meta="laufende Fälle" />
              <OperatorStat label="Sichtbar" value={visibleCards} meta="in der Übersicht" />
            </div>

            <div className="workspace-note-list">
              <div className="workspace-note-card">{campaignsView?.summary?.deduped_cards ?? cards.length} priorisierte Fälle</div>
              <div className="workspace-note-card">{aiTouchedCount} automatisch erstellt oder ergänzt</div>
              <div className="workspace-note-card">
                {focusCard
                  ? `Als Nächstes geht es zuerst in ${phaseTitle(phaseForCard(focusCard))}.`
                  : 'Sobald ein Fall vorliegt, landet er hier automatisch im passenden Schritt.'}
              </div>
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>

      <WorkspaceStatusPanel
        status={workspaceStatus}
        title="Was vor der Freigabe noch geklärt sein sollte"
        intro="Hier siehst du, ob du einen Fall direkt freigeben kannst oder erst noch etwas prüfen musst."
      />

      {loading ? (
        <OperatorSection
          kicker="Kampagnenübersicht"
          title="Lade Kampagnenvorschläge..."
          description="Einen Moment, wir holen die aktuelle Phase und den Fokusfall."
          tone="muted"
        >
          <div className="workspace-note-card">Die Übersicht wird gerade aufgebaut.</div>
        </OperatorSection>
      ) : cards.length === 0 ? (
        <OperatorSection
          kicker="Kampagnenübersicht"
          title="Noch keine Kampagnenvorschläge in der Übersicht."
          description="Sobald ein Vorschlag erstellt wurde, erscheint er hier direkt in der passenden Arbeitsphase."
          tone="muted"
        >
          <div className="action-row">
            <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
              {generationLoading ? 'Vorschläge werden erstellt...' : 'Jetzt erste Vorschläge erstellen'}
            </button>
          </div>
        </OperatorSection>
      ) : (
        <OperatorSection
          kicker="Arbeitsphasen"
          title="So ist die Pipeline gerade sortiert"
          description="Der wichtigste Fall steht oben. Darunter siehst du, welche Vorschläge noch in Vorbereitung, Freigabe oder bereits aktiv sind."
          tone="muted"
        >
          <section className="workspace-phase-grid">
            {phaseGroups.map((group) => (
              <OperatorPanel
                key={group.id}
                eyebrow="Arbeitsphase"
                title={phaseTitle(group.id)}
                description={group.description}
                actions={<span className="step-chip">{group.total} Fälle</span>}
                className="campaign-lane-column"
              >
                <div className="campaign-lane-stack">
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
                              metricContractDisplayLabel(card.field_contracts, 'signal_confidence_pct', 'Signal-Sicherheit'),
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
                            <span>{metricContractDisplayLabel(card.field_contracts, 'signal_score', 'Signal-Score')}</span>
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
              </OperatorPanel>
            ))}
          </section>
        </OperatorSection>
      )}

      <CollapsibleSection
        title="Weitere Vorschläge erstellen"
        subtitle="Wenn der wichtigste Fall geklärt ist, kannst du hier weitere Vorschläge anlegen."
      >
        <div className="workspace-two-column">
          <OperatorPanel
            title="Erstellung"
            description="Hier legst du neue Vorschläge mit wenigen Angaben an."
          >
            <div className="campaign-form-grid">
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
                Neue Vorschläge starten als Entwurf und können danach geprüft werden.
              </div>
              <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
                {generationLoading ? 'Vorschläge werden erstellt...' : 'Vorschläge erstellen'}
              </button>
            </div>
          </OperatorPanel>

          <OperatorPanel
            title="Arbeitskontext"
            description="Diese Angaben helfen dir, neue Vorschläge schneller einzuordnen."
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">
                Virus: {virus}
              </div>
              <div className="workspace-note-card">
                Lernstand: {learningStateLabel(campaignsView?.summary?.learning_state)}
              </div>
              <div className="workspace-note-card">
                Zusätzliche Vorschläge: {hiddenBacklog}
              </div>
              <div className="workspace-note-card">
                Aktiv: {activeCount}
              </div>
            </div>
          </OperatorPanel>
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

function phaseTitle(id: 'prepare' | 'approval' | 'active'): string {
  if (id === 'prepare') return 'Entwürfe';
  if (id === 'approval') return 'Freigaben';
  return 'Aktive Fälle';
}

function phaseForCard(card: RecommendationCard): 'prepare' | 'approval' | 'active' {
  const lane = recommendationLane(card);
  if (lane === 'prepare' || lane === 'review') return 'prepare';
  if (lane === 'approve' || lane === 'sync') return 'approval';
  return 'active';
}
