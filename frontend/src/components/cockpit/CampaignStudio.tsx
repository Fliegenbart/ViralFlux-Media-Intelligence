import React from 'react';

import { OPERATOR_LABELS } from '../../constants/operatorLabels';
import { additionalSuggestionsText, evidenceStatusHelper, evidenceStatusLabel } from '../../lib/copy';
import { normalizeGermanText } from '../../lib/plainLanguage';
import { MediaCampaignsResponse, RecommendationCard, WorkspaceStatusSummary } from '../../types/media';
import CollapsibleSection from '../CollapsibleSection';
import {
  formatCurrency,
  formatDateShort,
  learningStateLabel,
  recommendationLane,
  signalConfidencePercent,
  statusTone,
  workflowLabel,
} from './cockpitUtils';
import {
  OperatorPanel,
  OperatorSection,
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

type ApprovalTone = 'success' | 'warning' | 'neutral';

interface ApprovalStatusItem {
  label: string;
  value: string;
  detail: string;
  tone: ApprovalTone;
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
  const blockedCards = cards.filter((card) => hasPublishBlockers(card));
  const readyCards = cards.filter((card) => isApprovalReady(card));
  const prepareCount = laneStateCount('prepare', stateCounts) + laneStateCount('review', stateCounts);
  const approvalCount = laneStateCount('approve', stateCounts) + laneStateCount('sync', stateCounts);
  const activeCount = laneStateCount('live', stateCounts);
  const focusCard = cards.find((card) => ['review', 'approve', 'sync'].includes(recommendationLane(card))) || prepareCards[0] || cards[0] || null;
  const focusTitle = focusCard
    ? buildCampaignFocusTitle(focusCard)
    : 'Noch kein Fall im Fokus';
  const focusContext = focusCard
    ? `${focusCard.region_codes_display?.join(', ') || focusCard.region || 'National'} · ${focusCard.recommended_product || focusCard.product || 'Produkt offen'}`
    : 'Sobald Vorschläge vorliegen, steht der wichtigste Fall hier direkt im Fokus.';
  const focusCopy = focusCard
    ? buildCampaignDecisionCopy(focusCard)
    : 'Die Seite zeigt danach direkt, welcher Fall zuerst geprüft, freigegeben oder weiter vorbereitet werden sollte.';
  const focusReadiness = focusCard ? approvalReadiness(focusCard) : null;
  const focusBudgetDirection = focusCard ? budgetDirectionLabel(focusCard) : 'Budgetrichtung offen';
  const focusChannelDirection = focusCard ? channelDirectionLabel(focusCard) : 'Kanalmix wird nach dem ersten Vorschlag sichtbar';
  const focusActionLabel = focusCard ? recommendationActionLabel(focusCard) : 'Erste Vorschläge erstellen';
  const hiddenBacklog = campaignsView?.summary?.hidden_backlog_cards ?? 0;
  const queueCards = buildSecondaryApprovalQueue(cards, focusCard?.id || null);
  const trustItems = buildCampaignTrustItems(focusCard, workspaceStatus);
  const statusSummary = [
    {
      label: 'Prüfbar',
      value: String(readyCards.length),
      detail: 'Fälle ohne offene Blocker vor dem nächsten operativen Schritt.',
    },
    {
      label: 'Blockiert',
      value: String(blockedCards.length),
      detail: blockedCards.length > 0 ? 'Mindestens ein Fall braucht vor dem nächsten operativen Schritt noch Klärung.' : 'Aktuell gibt es keine offenen Blocker.',
    },
    {
      label: 'Aktiv',
      value: String(activeCount),
      detail: prepareCount > 0 ? `${prepareCount} weitere Fälle befinden sich noch in Vorbereitung.` : 'Keine weiteren frühen Fälle offen.',
    },
  ];
  const phaseGroups = [
    {
      id: 'prepare',
      label: 'Vorbereitung',
      description: 'Frühe oder noch nicht freigabereife Fälle.',
      cards: prepareCards,
      total: prepareCount,
    },
    {
      id: 'approval',
      label: 'Prüfen & Freigeben',
      description: 'Fälle, die als Nächstes geprüft, freigegeben oder übergeben werden können.',
      cards: approvalCards,
      total: approvalCount,
    },
    {
      id: 'active',
      label: 'Aktiv',
      description: 'Bereits laufende oder operativ übergebene Fälle.',
      cards: activeCards,
      total: activeCount,
    },
  ] as const;

  return (
    <div className="page-stack">
      <OperatorSection
        title="Welcher Fall als Nächstes geprüft werden sollte"
        tone="accent"
        className="campaign-hero-shell"
      >
        {loading ? (
          <div className="campaign-approval-skeleton" aria-label="Kampagnenansicht wird geladen">
            <div className="workspace-note-card campaign-approval-skeleton__hero" />
            <div className="campaign-approval-skeleton__grid">
              <div className="workspace-note-card campaign-approval-skeleton__block" />
              <div className="workspace-note-card campaign-approval-skeleton__block" />
              <div className="workspace-note-card campaign-approval-skeleton__block" />
            </div>
            <div className="workspace-note-card campaign-approval-skeleton__trust" />
          </div>
        ) : cards.length === 0 ? (
          <div className="campaign-empty-board campaign-empty-board--approval">
            <span className="campaign-empty-eyebrow">Maßnahmen</span>
            <h3 className="campaign-empty-title">Noch kein prüfbarer Fall sichtbar</h3>
            <p className="campaign-empty-copy">
              Sobald der erste Vorschlag vorliegt, erscheint hier genau der Fall, der als Nächstes geprüft oder freigegeben werden sollte.
            </p>
            <div className="action-row">
              <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
                {generationLoading ? 'Vorschläge werden erstellt...' : 'Erste Vorschläge erstellen'}
              </button>
            </div>
          </div>
        ) : (
          <div className="campaign-approval-stack">
            <div className="campaign-command-grid campaign-command-grid--approval">
              <OperatorPanel tone="accent" className="workspace-zone workspace-zone--hero campaign-focus-panel campaign-approval-hero">
                <div className="campaign-approval-hero__header">
                  <div>
                    <span className="campaign-focus-label">Empfohlene Aktion</span>
                    <h3 className="campaign-focus-title">{focusTitle}</h3>
                    <div className="campaign-focus-context">{focusContext}</div>
                  </div>
                  <div className="campaign-approval-hero__pills">
                    {focusCard ? (
                      <span className="campaign-status-badge" style={statusTone(focusCard.lifecycle_state || focusCard.status)}>
                        {workflowLabel(focusCard.lifecycle_state || focusCard.status)}
                      </span>
                    ) : null}
                    {focusReadiness ? (
                      <span className={`campaign-confidence-chip campaign-confidence-chip--${focusReadiness.tone}`}>
                        {focusReadiness.label}
                      </span>
                    ) : null}
                  </div>
                </div>

                <p className="campaign-focus-copy">{focusCopy}</p>

                <div className="campaign-hero-facts-inline">
                  <span><strong>{focusCard?.region || '—'}</strong> · {focusCard?.product || '—'}</span>
                  <span className="campaign-hero-facts-sep">·</span>
                  <span>{focusChannelDirection || 'Offen'}</span>
                  <span className="campaign-hero-facts-sep">·</span>
                  <span>{focusActionLabel}</span>
                </div>

                {focusReadiness?.tone === 'warning' ? (
                  <div className="workspace-note-card campaign-approval-hero__callout">
                    <strong>{focusReadiness.label}</strong>
                    <p>{focusReadiness.detail}</p>
                  </div>
                ) : null}

                <div className="action-row">
                  <button
                    className="media-button"
                    type="button"
                    onClick={() => (focusCard ? onOpenRecommendation(focusCard.id) : onGenerate())}
                    disabled={generationLoading && !focusCard}
                  >
                    {focusCard ? focusActionLabel : (generationLoading ? 'Vorschläge werden erstellt...' : 'Erste Vorschläge erstellen')}
                  </button>
                </div>
              </OperatorPanel>

              <OperatorPanel
                eyebrow="Nächster Schritt"
                title="Warum dieser Fall jetzt vorne liegt"
                description="Hier wird sichtbar, ob gerade eher Prüfung, Freigabe, Klärung oder Übergabe im Vordergrund steht."
                tone="muted"
                className="workspace-zone workspace-zone--support campaign-command-rail campaign-approval-summary"
              >
                <div className="campaign-approval-summary__grid">
                  {statusSummary.map((item) => (
                    <div key={item.label} className="workspace-note-card campaign-approval-summary__line">
                      <div className="campaign-approval-summary__line-head">
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </div>
                      <p>{item.detail}</p>
                    </div>
                  ))}
                </div>
                <div className="workspace-note-list">
                  {hiddenBacklog > 0 ? (
                    <div className="workspace-note-card">
                      {additionalSuggestionsText(hiddenBacklog)}
                    </div>
                  ) : null}
                </div>
              </OperatorPanel>
            </div>

            <OperatorPanel
              eyebrow="Belastbarkeit"
              title="Was diesen Fokusfall trägt"
              tone="muted"
              className="workspace-zone workspace-zone--trust campaign-trust-panel"
            >
              <div className="workspace-status-grid campaign-trust-grid">
                {trustItems.map((item) => (
                  <article
                    key={item.label}
                    className={`workspace-status-card workspace-status-card--${item.tone}`}
                  >
                    <span className="workspace-status-card__question">{item.label}</span>
                    <strong>{item.value}</strong>
                    <p>{item.detail}</p>
                  </article>
                ))}
              </div>
            </OperatorPanel>

            <OperatorPanel
              eyebrow="Danach"
              title="Welche Fälle als Nächstes folgen"
              tone="muted"
              className="workspace-zone workspace-zone--secondary campaign-approval-queue"
            >
              <div className="campaign-approval-queue__list">
                {queueCards.length > 0 ? queueCards.map((card) => {
                  const readiness = approvalReadiness(card);
                  return (
                    <button
                      type="button"
                      key={card.id}
                      onClick={() => onOpenRecommendation(card.id)}
                    className="campaign-list-card campaign-approval-next-card"
                  >
                      <div className="campaign-work-item-top">
                        <span className={`campaign-confidence-chip campaign-confidence-chip--${readiness.tone}`}>
                          {readiness.label}
                        </span>
                      </div>
                      <div className="campaign-work-item-head">
                        <div className="campaign-work-item-title">
                          {card.display_title || card.campaign_name || card.product}
                        </div>
                        <div className="campaign-work-item-subtitle">
                          {(card.region_codes_display?.join(', ') || card.region || 'National')} · {card.recommended_product || card.product}
                        </div>
                      </div>
                      <p className="campaign-work-item-copy">{readableCampaignSummary(card)}</p>
                      <div className="campaign-work-item-footer">
                        <span>{recommendationActionLabel(card)} · {budgetDirectionLabel(card)}</span>
                      </div>
                    </button>
                  );
                }) : (
                  <div className="workspace-note-card">
                    Aktuell gibt es neben dem Fokusfall keine weiteren belastbar priorisierten Fälle.
                  </div>
                )}
              </div>
            </OperatorPanel>
          </div>
        )}
      </OperatorSection>

      {!loading && cards.length > 0 ? (
        <CollapsibleSection title="Arbeitsphasen" subtitle="Vorbereitung, Prüfung und aktive Fälle">
          <section className="workspace-phase-grid">
            {phaseGroups.map((group) => (
              <OperatorPanel
                key={group.id}
                eyebrow="Phase"
                title={phaseTitle(group.id)}
                description={group.description}
                actions={<span className="step-chip">{group.total} Fälle</span>}
                className="campaign-lane-column"
              >
                <div className="campaign-lane-stack">
                  {group.cards.length > 0 ? group.cards.map((card) => {
                    const tone = statusTone(card.lifecycle_state || card.status);
                    const readiness = approvalReadiness(card);
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
                          <span className={`campaign-confidence-chip campaign-confidence-chip--${readiness.tone}`}>
                            {readiness.label}
                          </span>
                        </div>

                        <div className="campaign-work-item-head">
                          <div className="campaign-work-item-title">
                            {card.display_title || card.campaign_name || card.product}
                          </div>
                          <div className="campaign-work-item-subtitle">
                            {(card.region_codes_display?.join(', ') || card.region || 'National')} · {card.recommended_product || card.product}
                          </div>
                        </div>

                        <p className="campaign-work-item-copy">{readableCampaignSummary(card)}</p>

                        <div className="campaign-work-item-metrics">
                          <div className="campaign-inline-stat">
                            <span>Richtung</span>
                            <strong>{channelDirectionLabel(card)} · {budgetDirectionLabel(card)}</strong>
                          </div>
                          <div className="campaign-inline-stat">
                            <span>Evidenz</span>
                            <strong>{evidenceStatusLabel(card.evidence_class) || 'Noch offen'}</strong>
                          </div>
                          <div className="campaign-inline-stat">
                            <span>Empfohlene Aktion</span>
                            <strong>{recommendationActionLabel(card)}</strong>
                          </div>
                        </div>

                        <div className="campaign-work-item-footer">
                          <span>{flightWindowLabel(card)} · {readiness.detail}</span>
                        </div>
                      </button>
                    );
                  }) : (
                    <div className="campaign-empty-lane">
                      {group.total > 0
                        ? additionalSuggestionsText(group.total, 'Vorschläge in dieser Phase')
                        : 'In dieser Phase liegen aktuell keine Fälle.'}
                    </div>
                  )}
                </div>
              </OperatorPanel>
            ))}
          </section>
        </CollapsibleSection>
      ) : null}

      <CollapsibleSection
        className="workspace-zone workspace-zone--detail"
        title="Weitere Vorschläge erstellen"
        subtitle="Nur dann relevant, wenn nach dem Fokusfall weitere Maßnahmen vorbereitet werden sollen."
      >
        <div className="workspace-two-column">
          <OperatorPanel
            title="Neue Vorschläge"
            description="Hier werden neue Vorschläge angelegt. Bereits priorisierte oder freizugebende Fälle bleiben davon unberührt."
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
                Neue Vorschläge starten als Entwurf und wandern danach in Prüfung, Freigabe oder operative Übergabe.
              </div>
              <button className="media-button" type="button" onClick={onGenerate} disabled={generationLoading}>
                {generationLoading ? 'Vorschläge werden erstellt...' : 'Vorschläge erstellen'}
              </button>
            </div>
          </OperatorPanel>

          <OperatorPanel
            title="Kontext"
            description="Diese Werte helfen bei der Einordnung, bleiben aber bewusst in der zweiten Ebene."
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

function hasPublishBlockers(card?: RecommendationCard | null): boolean {
  return Boolean(card?.publish_blockers && card.publish_blockers.length > 0);
}

function isApprovalReady(card?: RecommendationCard | null): boolean {
  if (!card || hasPublishBlockers(card)) return false;
  const lane = recommendationLane(card);
  return lane === 'review' || lane === 'approve' || lane === 'sync';
}

function confidenceLabel(
  signalConfidencePct?: number | null,
  confidence?: number | null,
  label = OPERATOR_LABELS.signal_confidence,
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

function buildCampaignFocusTitle(card: RecommendationCard): string {
  const rawTitle = normalizeGermanText(
    String(card.display_title || card.campaign_name || '').trim(),
  );
  const product = normalizeGermanText(String(card.recommended_product || card.product || '').trim());
  const region = normalizeGermanText(String(card.region_codes_display?.join(', ') || card.region || '').trim());

  const cleanedTitle = rawTitle
    .replace(/\s+/g, ' ')
    .replace(new RegExp(`^(?:${escapeRegExp(product)}[:\\s-]*){2,}`, 'i'), `${product}: `)
    .replace(new RegExp(`^(?:${escapeRegExp(product)}[:\\s-]*)+`, 'i'), '')
    .trim();

  if (cleanedTitle && cleanedTitle !== product) {
    if (region && !cleanedTitle.toLowerCase().includes(region.toLowerCase())) {
      return `${product}: ${cleanedTitle} in ${region}`;
    }
    return `${product}: ${cleanedTitle}`;
  }

  if (product && region) return `${product} in ${region}`;
  if (product) return product;
  if (region) return `Kampagnenfall in ${region}`;
  return 'Kampagnenfall prüfen';
}

function buildCampaignDecisionCopy(card: RecommendationCard): string {
  const summary = readableCampaignSummary(card);
  const cleaned = summary.replace(/\s+/g, ' ').trim();
  if (cleaned.length <= 140) return cleaned;
  const firstSentence = cleaned.match(/^.*?[.!?](\s|$)/)?.[0]?.trim();
  if (firstSentence) return firstSentence;
  return `${cleaned.slice(0, 137).trimEnd()}...`;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
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
  if (laneId === 'prepare') return Number(states.PREPARE || states.prepare || 0);
  if (laneId === 'review') return Number(states.REVIEW || states.review || 0);
  if (laneId === 'approve') return Number(states.APPROVE || states.approve || 0);
  if (laneId === 'sync') return Number(states.SYNC_READY || states.sync || 0);
  if (laneId === 'live') return Number(states.LIVE || states.live || 0);
  return 0;
}

function phaseTitle(id: 'prepare' | 'approval' | 'active'): string {
  if (id === 'prepare') return 'In Vorbereitung';
  if (id === 'approval') return 'Prüfen & Freigeben';
  return 'Aktive Fälle';
}

function recommendationActionLabel(card: RecommendationCard): string {
  const lane = recommendationLane(card);
  if (hasPublishBlockers(card)) return 'Blocker prüfen';
  if (lane === 'sync') return 'Übergabe vorbereiten';
  if (lane === 'approve') return 'Zur Freigabe öffnen';
  if (lane === 'live') return 'Aktiven Fall öffnen';
  return 'Empfehlung prüfen';
}

function budgetDirectionLabel(card: RecommendationCard): string {
  const shift = Number(card.budget_shift_pct || 0);
  if (!Number.isFinite(shift)) return 'Budgetrichtung offen';
  if (shift > 0) return 'Budget eher erhöhen';
  if (shift < 0) return 'Budget eher senken';
  return 'Budget eher halten';
}

function budgetSupportCopy(card?: RecommendationCard | null): string {
  if (!card) return 'Der Wochenrahmen wird sichtbar, sobald ein konkreter Vorschlag vorliegt.';
  const weeklyBudget = card.campaign_preview?.budget?.weekly_budget_eur;
  if (typeof weeklyBudget === 'number' && Number.isFinite(weeklyBudget)) {
    return `Wochenrahmen ${formatCurrency(weeklyBudget)}.`;
  }
  return 'Zuerst sichtbar wird die Richtung, nicht bloß eine einzelne Zahl.';
}

function channelDirectionLabel(card: RecommendationCard): string {
  const entries = Object.entries(card.channel_mix || {})
    .filter(([, value]) => typeof value === 'number' && value > 0)
    .sort((left, right) => Number(right[1]) - Number(left[1]))
    .slice(0, 2);

  if (entries.length === 0) return 'Kanalmix im Detail prüfen';

  const topChannels = entries.map(([key]) => humanizeChannel(key));
  if (topChannels.length === 1) return `${topChannels[0]} im Fokus`;
  return `${topChannels[0]} + ${topChannels[1]} im Fokus`;
}

function humanizeChannel(value: string): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'ctv') return 'CTV';
  if (normalized === 'search') return 'Search';
  if (normalized === 'social') return 'Social';
  if (normalized === 'programmatic') return 'Programmatic';
  return normalizeGermanText(value);
}

function approvalReadiness(card: RecommendationCard): { label: string; detail: string; tone: ApprovalTone } {
  const blockers = card.publish_blockers || [];
  const lane = recommendationLane(card);

  if (blockers.length > 0) {
    return {
      label: 'Blockiert',
      detail: normalizeGermanText(blockers[0]),
      tone: 'warning',
    };
  }

  if (lane === 'sync') {
    return {
      label: 'Bereit zur Übergabe',
      detail: 'Der Vorschlag ist freigegeben und kann für die operative Übergabe vorbereitet werden.',
      tone: 'success',
    };
  }

  if (lane === 'approve') {
    return {
      label: 'Bereit für Freigabe',
      detail: 'Die Empfehlung ist entscheidungsreif und wartet auf den nächsten Freigabeschritt.',
      tone: 'success',
    };
  }

  if (lane === 'review') {
    return {
      label: 'Bereit zur Prüfung',
      detail: 'Die Empfehlung sollte jetzt fachlich geprüft und priorisiert werden.',
      tone: 'neutral',
    };
  }

  if (lane === 'live') {
    return {
      label: 'Aktiv',
      detail: 'Der Fall läuft bereits oder befindet sich operativ in Umsetzung.',
      tone: 'neutral',
    };
  }

  return {
    label: 'In Vorbereitung',
    detail: 'Der Fall braucht noch Nachschärfung, bevor er prüf- oder freigabefähig wird.',
    tone: 'neutral',
  };
}

function buildSecondaryApprovalQueue(cards: RecommendationCard[], focusId: string | null): RecommendationCard[] {
  const fallback = cards.filter((card) => card.id !== focusId);
  const priorityBuckets = [
    fallback.find((card) => recommendationLane(card) === 'approve' && !hasPublishBlockers(card)),
    fallback.find((card) => recommendationLane(card) === 'review' && !hasPublishBlockers(card)),
    fallback.find((card) => hasPublishBlockers(card)),
    fallback.find((card) => recommendationLane(card) === 'sync'),
    fallback.find((card) => recommendationLane(card) === 'live'),
    fallback.find((card) => recommendationLane(card) === 'prepare'),
  ].filter(Boolean) as RecommendationCard[];

  const unique = priorityBuckets.filter((card, index, all) => (
    all.findIndex((item) => item.id === card.id) === index
  ));

  if (unique.length >= 3) return unique.slice(0, 3);

  for (const card of fallback) {
    if (!unique.find((item) => item.id === card.id)) unique.push(card);
    if (unique.length === 3) break;
  }

  return unique;
}

function buildCampaignTrustItems(
  focusCard: RecommendationCard | null,
  workspaceStatus: WorkspaceStatusSummary | null,
): ApprovalStatusItem[] {
  const forecastItem = workspaceStatus?.items.find((item) => item.key === 'forecast_status');
  const freshnessItem = workspaceStatus?.items.find((item) => item.key === 'data_freshness');
  const blockersItem = workspaceStatus?.items.find((item) => item.key === 'open_blockers');
  const focusReadiness = focusCard ? approvalReadiness(focusCard) : null;

  return [
    {
      label: 'Belastbarkeit',
      value: focusCard?.evidence_class ? evidenceStatusLabel(focusCard.evidence_class) : (forecastItem?.value || 'Manuell prüfen'),
      detail: focusCard?.evidence_class
        ? (evidenceStatusHelper(focusCard.evidence_class) || confidenceLabel(focusCard.signal_confidence_pct, focusCard.confidence))
        : (forecastItem?.detail || 'Der Fall stützt sich aktuell auf Vorhersage-, Evidenz- und Marktsignale.'),
      tone: focusCard?.evidence_class === 'truth_backed' ? 'success' : 'neutral',
    },
    {
      label: 'Datenlage',
      value: freshnessItem?.value || 'Noch offen',
      detail: freshnessItem?.detail || 'Die Datenlage wird sichtbar, sobald Evidenz und Kundendaten vollständig vorliegen.',
      tone: freshnessItem?.tone === 'warning' ? 'warning' : freshnessItem?.tone === 'success' ? 'success' : 'neutral',
    },
    {
      label: 'Einsatzreife & Übergabe',
      value: focusReadiness?.label || (blockersItem?.value || 'Noch offen'),
      detail: focusReadiness?.detail || blockersItem?.detail || 'Der nächste operative Schritt ist noch nicht belastbar genug markiert.',
      tone: focusReadiness?.tone || (blockersItem?.tone === 'warning' ? 'warning' : 'neutral'),
    },
  ];
}
