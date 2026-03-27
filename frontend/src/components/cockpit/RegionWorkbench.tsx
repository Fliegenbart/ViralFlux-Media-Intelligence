import React, { useMemo, useRef, useState } from 'react';

import { MediaRegionsResponse, WorkspaceStatusSummary, WorkspaceStatusTone } from '../../types/media';
import { explainInPlainGerman, normalizeGermanText } from '../../lib/plainLanguage';
import CollapsibleSection from '../CollapsibleSection';
import { UI_COPY } from '../../lib/copy';
import GermanyMap from './GermanyMap';
import {
  formatDateShort,
  formatPercent,
  metricContractDisplayLabel,
  metricContractNote,
  primarySignalScore,
  VIRUS_OPTIONS,
} from './cockpitUtils';
import {
  OperatorChipRail,
  OperatorPanel,
  OperatorSection,
} from './operator/OperatorPrimitives';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  regionsView: MediaRegionsResponse | null;
  workspaceStatus: WorkspaceStatusSummary | null;
  loading: boolean;
  selectedRegion: string | null;
  onSelectRegion: (code: string) => void;
  onOpenRecommendation: (id: string) => void;
  onGenerateRegionCampaign: (code: string) => void;
  regionActionLoading: boolean;
}

type RegionListFilter = 'all' | 'prioritized' | 'low_evidence';
type RegionalDirection = 'increase' | 'hold' | 'observe' | 'restrained';

interface RegionalTrustItem {
  key: 'reliability' | 'evidence' | 'readiness';
  label: string;
  value: string;
  detail: string;
  tone: WorkspaceStatusTone;
}

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value <= 1 ? value * 100 : value;
  return formatPercent(pct, digits);
}

function hasInsufficientEvidence(region?: {
  source_trace?: string[];
  signal_drivers?: Array<{ label: string; strength_pct: number }>;
  signal_score?: number;
  peix_score?: number;
  impact_probability?: number;
} | null): boolean {
  if (!region) return true;
  const sourceCount = region.source_trace?.length || 0;
  const driverCount = region.signal_drivers?.length || 0;
  const signal = primarySignalScore(region);
  return signal <= 0 || (sourceCount < 2 && driverCount === 0);
}

function evidenceLabel(region?: {
  source_trace?: string[];
  signal_drivers?: Array<{ label: string; strength_pct: number }>;
  signal_score?: number;
  peix_score?: number;
  impact_probability?: number;
} | null): string {
  if (!region || hasInsufficientEvidence(region)) return 'Zu wenig Evidenz';
  const sourceCount = region.source_trace?.length || 0;
  if (sourceCount >= 2) return 'Mehrere Quellen';
  return 'Erste Evidenz';
}

function normalizeRegionText(value?: string | null): string {
  return normalizeGermanText(String(value || '').trim()).toLowerCase();
}

function deriveRegionalDirection(
  region?: {
    forecast_direction?: string;
    decision_mode?: string;
    decision_mode_label?: string;
    source_trace?: string[];
    signal_drivers?: Array<{ label: string; strength_pct: number }>;
    signal_score?: number;
    peix_score?: number;
    impact_probability?: number;
  } | null,
  suggestion?: {
    priority?: string;
  } | null,
): RegionalDirection {
  if (hasInsufficientEvidence(region)) return 'restrained';

  const priority = normalizeRegionText(
    suggestion?.priority
      || region?.decision_mode_label
      || region?.decision_mode,
  );

  if (
    priority.includes('hoch')
    || priority.includes('high')
    || priority.includes('activate')
    || priority.includes('aktiv')
  ) {
    return 'increase';
  }

  if (
    priority.includes('mittel')
    || priority.includes('medium')
    || priority.includes('prepare')
    || priority.includes('halt')
  ) {
    return 'hold';
  }

  if (
    priority.includes('niedrig')
    || priority.includes('watch')
    || priority.includes('beobacht')
  ) {
    return 'observe';
  }

  const forecastDirection = normalizeRegionText(region?.forecast_direction);
  if (forecastDirection.includes('auf')) return 'hold';
  if (forecastDirection.includes('ab')) return 'restrained';

  return 'observe';
}

function regionalDirectionLabel(direction: RegionalDirection): string {
  if (direction === 'increase') return 'Fokus erhöhen';
  if (direction === 'hold') return 'Fokus halten';
  if (direction === 'observe') return 'Beobachten';
  return 'Zurückhaltend bleiben';
}

function regionalDirectionTone(direction: RegionalDirection): WorkspaceStatusTone {
  if (direction === 'increase') return 'success';
  if (direction === 'hold') return 'neutral';
  return 'warning';
}

function regionalActionHeadline(direction: RegionalDirection, regionName?: string | null): string {
  const cleanedRegionName = String(regionName || 'dieses Bundesland').trim();
  if (direction === 'increase') return `Fokus erhöhen in ${cleanedRegionName}`;
  if (direction === 'hold') return `Fokus halten in ${cleanedRegionName}`;
  if (direction === 'observe') return `${cleanedRegionName} weiter beobachten`;
  return `In ${cleanedRegionName} vorerst zurückhaltend bleiben`;
}

function budgetDirectionLabel(
  budgetShiftPct: number | null | undefined,
  direction: RegionalDirection,
): string {
  if (typeof budgetShiftPct === 'number' && Number.isFinite(budgetShiftPct)) {
    if (budgetShiftPct > 0) return 'Budget eher erhöhen';
    if (budgetShiftPct < 0) return 'Budget eher zurückhaltend steuern';
    return 'Budget eher halten';
  }

  if (direction === 'increase') return 'Budget eher erhöhen';
  if (direction === 'hold') return 'Budget eher halten';
  return 'Budget eher zurückhaltend steuern';
}

function nextStepLabel(hasRecommendation: boolean, direction: RegionalDirection): string {
  if (hasRecommendation) return 'Vorschlag bereit';
  if (direction === 'increase' || direction === 'hold') return 'Maßnahme prüfbar';
  return 'Noch zurückhaltend';
}

const RegionWorkbench: React.FC<Props> = ({
  virus,
  onVirusChange,
  regionsView,
  workspaceStatus,
  loading,
  selectedRegion,
  onSelectRegion,
  onOpenRecommendation,
  onGenerateRegionCampaign,
  regionActionLoading,
}) => {
  const [listFilter, setListFilter] = useState<RegionListFilter>('all');
  const comparisonRef = useRef<HTMLDivElement>(null);
  const detailsRef = useRef<HTMLDivElement>(null);
  const activeMap = regionsView?.map;
  const topRegions = (activeMap?.top_regions || []).slice(0, 5);
  const fallbackRegionCode = selectedRegion || topRegions[0]?.code || null;
  const region = fallbackRegionCode ? activeMap?.regions?.[fallbackRegionCode] || null : null;
  const suggestion = activeMap?.activation_suggestions?.find((item) => item.region === fallbackRegionCode) || null;
  const primaryRegion = region || topRegions[0] || null;
  const signalLabel = metricContractDisplayLabel(primaryRegion?.field_contracts, 'signal_score', UI_COPY.signalScore);
  const signalNote = metricContractNote(
    primaryRegion?.field_contracts,
    'signal_score',
    'Hilft beim Vergleichen und Priorisieren, ist aber keine punktgenaue Vorhersage.',
  );

  const regionRows = useMemo(() => {
    const suggestionByRegion = new Map((activeMap?.activation_suggestions || []).map((item) => [item.region, item]));
    return Object.entries(activeMap?.regions || {})
      .map(([code, item]) => ({
        code,
        region: item,
        suggestion: suggestionByRegion.get(code),
      }))
      .sort((left, right) => {
        const leftRank = Number(left.region.priority_rank ?? Number.MAX_SAFE_INTEGER);
        const rightRank = Number(right.region.priority_rank ?? Number.MAX_SAFE_INTEGER);
        if (leftRank !== rightRank) return leftRank - rightRank;
        return primarySignalScore(right.region) - primarySignalScore(left.region);
      });
  }, [activeMap]);

  const filteredRegionRows = regionRows.filter(({ region: regionItem }) => {
    if (listFilter === 'prioritized') return !hasInsufficientEvidence(regionItem);
    if (listFilter === 'low_evidence') return hasInsufficientEvidence(regionItem);
    return true;
  });

  const regionListTitle = listFilter === 'prioritized'
    ? 'Prüfbare Bundesländer'
    : listFilter === 'low_evidence'
      ? 'Bundesländer mit zu wenig Evidenz'
      : 'Bundesländer im Vergleich';

  const selectedEvidence = evidenceLabel(region || primaryRegion);
  const selectedDirection = deriveRegionalDirection(region || primaryRegion, suggestion);
  const selectedDirectionLabel = regionalDirectionLabel(selectedDirection);
  const hasRecommendation = Boolean((region || primaryRegion)?.recommendation_ref?.card_id);
  const budgetDirection = budgetDirectionLabel(suggestion?.budget_shift_pct, selectedDirection);
  const primaryReason = explainInPlainGerman(
    region?.priority_explanation
      || suggestion?.reason
      || region?.tooltip?.recommendation_text
      || 'Diese Region zeigt aktuell die staerkste Dynamik aus Vorhersage, Versorgung und Nachfrage.',
  );
  const comparisonReason = (regionItem?: {
    priority_explanation?: string;
    tooltip?: { recommendation_text?: string | null } | null;
  } | null, suggestionReason?: string | null) => explainInPlainGerman(
    regionItem?.priority_explanation
      || suggestionReason
      || regionItem?.tooltip?.recommendation_text
      || 'Für dieses Bundesland liegt aktuell noch keine kurze Einordnung vor.',
  );
  const actionDisabledReason = !fallbackRegionCode
    ? 'Wähle zuerst ein Bundesland aus.'
    : (!hasRecommendation && (selectedDirection === 'observe' || selectedDirection === 'restrained'))
      ? 'Für dieses Bundesland reicht die aktuelle Evidenz noch nicht für einen neuen regionalen Vorschlag.'
      : (!hasRecommendation && workspaceStatus?.blocker_count)
        ? workspaceStatus.blockers[0] || 'Vor dem nächsten Schritt müssen offene Punkte geklärt werden.'
        : null;
  const primaryActionLabel = hasRecommendation ? 'Regionalen Vorschlag öffnen' : 'Regionale Maßnahme prüfen';
  const primaryAction = () => {
    if (!fallbackRegionCode) return;
    const recommendationId = region?.recommendation_ref?.card_id || primaryRegion?.recommendation_ref?.card_id;
    if (recommendationId) {
      onOpenRecommendation(recommendationId);
      return;
    }
    onGenerateRegionCampaign(fallbackRegionCode);
  };
  const secondaryRegions = regionRows
    .filter(({ code }) => code !== fallbackRegionCode)
    .slice(0, 3)
    .map(({ code, region: row, suggestion: rowSuggestion }) => ({
      code,
      name: row.name,
      direction: deriveRegionalDirection(row, rowSuggestion),
      directionLabel: regionalDirectionLabel(deriveRegionalDirection(row, rowSuggestion)),
      evidence: evidenceLabel(row),
      reason: comparisonReason(row, rowSuggestion?.reason),
      nextStep: nextStepLabel(Boolean(row.recommendation_ref?.card_id), deriveRegionalDirection(row, rowSuggestion)),
    }));

  const forecastStatusItem = workspaceStatus?.items.find((item) => item.key === 'forecast_status');
  const dataFreshnessItem = workspaceStatus?.items.find((item) => item.key === 'data_freshness');
  const blockerItem = workspaceStatus?.items.find((item) => item.key === 'open_blockers');
  const trustSummary = actionDisabledReason
    || workspaceStatus?.summary
    || 'Die regionale Empfehlung stützt sich auf Forecast, Datenlage und Einsatzreife.';
  const trustItems: RegionalTrustItem[] = [
    {
      key: 'reliability',
      label: 'Belastbarkeit',
      value: forecastStatusItem?.value || (selectedDirection === 'increase' ? 'Prüfbar' : 'Beobachten'),
      detail: forecastStatusItem?.detail || 'Das Forecast-Signal bleibt Unterstützung für die Regionsentscheidung.',
      tone: forecastStatusItem?.tone || regionalDirectionTone(selectedDirection),
    },
    {
      key: 'evidence',
      label: 'Datenlage',
      value: selectedEvidence,
      detail: selectedEvidence === 'Zu wenig Evidenz'
        ? 'Für dieses Bundesland fehlen mehrere stützende Quellen oder Signaltreiber.'
        : dataFreshnessItem?.detail || 'Die Datenlage ist für dieses Bundesland ausreichend sichtbar.',
      tone: selectedEvidence === 'Zu wenig Evidenz'
        ? 'warning'
        : dataFreshnessItem?.tone || 'neutral',
    },
    {
      key: 'readiness',
      label: 'Einsatzreife',
      value: workspaceStatus?.blocker_count
        ? 'Blockiert'
        : hasRecommendation
          ? 'Bereit zur Prüfung'
          : actionDisabledReason
            ? 'Noch nicht belastbar'
            : 'Bereit zur Prüfung',
      detail: workspaceStatus?.blocker_count
        ? workspaceStatus.blockers[0] || blockerItem?.detail || 'Vor dem nächsten Schritt gibt es offene Punkte.'
        : hasRecommendation
          ? 'Für dieses Bundesland liegt bereits ein regionaler Vorschlag vor.'
          : actionDisabledReason || 'Der nächste regionale Schritt kann direkt aus dieser Seite vorbereitet werden.',
      tone: workspaceStatus?.blocker_count || actionDisabledReason
        ? 'warning'
        : hasRecommendation
          ? 'success'
          : 'neutral',
    },
  ];

  const scrollToRef = (ref: React.RefObject<HTMLDivElement>) => {
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (loading && !regionsView) {
    return (
      <OperatorSection
        kicker="Regionen"
        title="Regionen werden aufgebaut"
        description="Die Hauptregion, die Begründung und die Folgepfade werden gerade neu zusammengestellt."
        tone="muted"
      >
        <div className="regions-loading-skeleton" aria-label="Regionale Arbeitsfläche wird geladen">
          <div className="regions-loading-skeleton__hero">
            <div className="workspace-note-card regions-loading-skeleton__block regions-loading-skeleton__block--hero" />
            <div className="workspace-note-card regions-loading-skeleton__block regions-loading-skeleton__block--note" />
          </div>
          <div className="regions-loading-skeleton__grid">
            <div className="workspace-note-card regions-loading-skeleton__block" />
            <div className="workspace-note-card regions-loading-skeleton__block" />
          </div>
          <div className="workspace-note-card regions-loading-skeleton__block regions-loading-skeleton__block--list" />
        </div>
      </OperatorSection>
    );
  }

  if (!activeMap?.has_data) {
    return (
      <OperatorSection
        kicker="Regionen"
        title="Noch keine regionale Sicht verfügbar"
        description="Für diese Auswahl liegt aktuell kein Bundesland-Scope vor."
        tone="muted"
      >
        <div className="regions-empty-stage">
          <div className="workspace-note-card regions-empty-stage__panel">
            <span className="now-weekly-plan-card__label">Was fehlt</span>
            <strong>Es gibt noch keinen belastbaren Bundesland-Scope für diese Auswahl.</strong>
            <p>Die Seite bleibt ruhig und zeigt erst dann eine Priorisierung, wenn wirklich eine regionale Richtung trägt.</p>
          </div>
          <div className="workspace-note-card regions-empty-stage__panel">
            <span className="now-weekly-plan-card__label">Nächster Schritt</span>
            <strong>Zur Wochenentscheidung zurück oder Evidenz prüfen</strong>
            <p>Solange keine regionale Lage steht, sollte zuerst die Datenlage oder der Wochenfokus geklärt werden.</p>
          </div>
        </div>
      </OperatorSection>
    );
  }

  if (regionRows.length === 0) {
    return (
      <OperatorSection
        kicker="Regionen"
        title="Noch keine belastbare Priorisierung"
        description="Es gibt erste Bundesland-Daten, aber noch keine starke Reihenfolge für den nächsten Schritt."
        tone="muted"
      >
        <div className="regions-empty-stage">
          <div className="workspace-note-card regions-empty-stage__panel">
            <span className="now-weekly-plan-card__label">Was sichtbar bleibt</span>
            <strong>Die Regionen sind da, aber noch ohne klare Rangordnung.</strong>
            <p>Das ist kein Fehlerzustand, sondern eine bewusst zurückhaltende Darstellung.</p>
          </div>
          <div className="workspace-note-card regions-empty-stage__panel">
            <span className="now-weekly-plan-card__label">Nächster Schritt</span>
            <strong>Evidenzlage oder Wochenfokus schärfen</strong>
            <p>Erst wenn Datenlage und Freigabe stärker tragen, lohnt sich eine harte regionale Priorisierung.</p>
          </div>
        </div>
      </OperatorSection>
    );
  }

  return (
    <div className="page-stack regions-template-page">
      <OperatorSection
        kicker="Regionen"
        title="Regionen"
        description="Eine Hauptregion. Zwei Folgepfade. Eine klare nächste Bewegung."
        tone="accent"
        className="operator-toolbar-shell"
      >
        <div className="now-toolbar">
          <div className="now-toolbar__intro">
            <span className="now-toolbar__eyebrow">Signalfilter</span>
            <div className="now-toolbar__heading">
              <strong>Diese Woche</strong>
              <span>Eine Region vorne, zwei sichtbar dahinter.</span>
            </div>
          </div>
          <OperatorChipRail className="review-chip-row">
            {VIRUS_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onVirusChange(option)}
                className={`tab-chip ${option === virus ? 'active' : ''}`}
              >
                {option}
              </button>
            ))}
          </OperatorChipRail>

          <div className="workspace-note-card regions-toolbar-note">
            <strong>Datenstand {formatDateShort(activeMap.date)}</strong>
            <span>
              {workspaceStatus?.data_freshness === 'Beobachten' ? 'Ein Teil der Daten ist nicht ganz frisch.' : 'Bundesland-Level, bewusst ohne City-Präzision.'}
            </span>
          </div>
        </div>

        <div className="regions-briefing-stack">
          <OperatorPanel
            tone="accent"
            className={`regions-action-hero regions-action-hero--${selectedDirection}`}
          >
            <div className="regions-action-hero__header">
              <div>
                <span className="now-weekly-plan-card__label">Aktuelle Entscheidung</span>
                <h3 className="regions-action-hero__title">
                  {regionalActionHeadline(selectedDirection, primaryRegion?.name)}
                </h3>
              </div>
              <div className="regions-action-hero__pills">
                <span className={`regions-direction-pill regions-direction-pill--${selectedDirection}`}>
                  {selectedDirectionLabel}
                </span>
              </div>
            </div>

            <p className="regions-action-hero__copy">{primaryReason}</p>

            <div className="regions-action-hero__facts">
              <article className="workspace-note-card regions-action-fact">
                <span className="now-weekly-plan-card__label">Bundesland</span>
                <strong>{primaryRegion?.name || 'Noch offen'}</strong>
                <p>Bewusst ohne City-Präzision.</p>
              </article>
              <article className="workspace-note-card regions-action-fact">
                <span className="now-weekly-plan-card__label">Richtungsbild</span>
                <strong>{budgetDirection}</strong>
                <p>{region?.forecast_direction || 'Seitwärts'} · {selectedEvidence}</p>
              </article>
              <article className="workspace-note-card regions-action-fact">
                <span className="now-weekly-plan-card__label">Nächster Schritt</span>
                <strong>{hasRecommendation ? 'Bestehenden Vorschlag prüfen' : 'Regionale Maßnahme vorbereiten'}</strong>
                <p>{hasRecommendation ? 'Der Vorschlag kann direkt geöffnet werden.' : 'Nur wenn die Datenlage dafür reicht.'}</p>
              </article>
            </div>

            {actionDisabledReason ? (
              <div className="workspace-note-card regions-action-callout">
                <strong>{selectedDirectionLabel}</strong>
                <p>{actionDisabledReason}</p>
              </div>
            ) : null}

            <div className="action-row">
              <button
                className="media-button"
                type="button"
                onClick={primaryAction}
                disabled={!fallbackRegionCode || regionActionLoading || Boolean(actionDisabledReason)}
              >
                {regionActionLoading ? 'Wird vorbereitet...' : primaryActionLabel}
              </button>
              <button
                className="media-button secondary"
                type="button"
                onClick={() => scrollToRef(comparisonRef)}
              >
                Bundesländer vergleichen
              </button>
              <button
                className="media-button secondary"
                type="button"
                onClick={() => scrollToRef(detailsRef)}
              >
                Begründung prüfen
              </button>
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Woran sie trägt"
            title="Warum die Region vorne liegt"
            description={trustSummary}
            tone="muted"
            className="regions-trust-shell"
          >
            <div className="regions-trust-grid">
              {trustItems.map((item) => (
                <article
                  key={item.key}
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
            title="Zwei nächste Regionen"
            description="Hier bleiben die nächsten Bundesländer sichtbar, ohne die Hauptentscheidung zu verwischen."
            tone="muted"
            className="regions-secondary-shell"
          >
            <div className="regions-secondary-grid">
              {secondaryRegions.length > 0 ? secondaryRegions.map((item) => (
                <button
                  type="button"
                  key={item.code}
                  onClick={() => onSelectRegion(item.code)}
                  className="campaign-list-card regions-secondary-card"
                >
                  <div className="regions-secondary-card__top">
                    <div>
                      <div className="regions-secondary-card__title">{item.name}</div>
                      <div className="regions-secondary-card__meta">{item.nextStep} · {item.evidence}</div>
                    </div>
                    <span className={`regions-direction-pill regions-direction-pill--${item.direction}`}>
                      {item.directionLabel}
                    </span>
                  </div>
                  <p>{item.reason}</p>
                </button>
              )) : (
                <div className="workspace-note-card">
                  Aktuell gibt es keine weiteren belastbaren Bundesländer mit klarer Richtung.
                </div>
              )}
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>

      <div ref={comparisonRef}>
        <OperatorSection
          kicker="Arbeitsmodus"
          title="Details bei Bedarf"
          description="Die Liste bleibt das Arbeitswerkzeug für Richtung, Begründung und nächsten Schritt."
          tone="muted"
        >
          <div className="regions-workbench-grid">
            <OperatorPanel
              title={regionListTitle}
              description="Nutze die Liste für die eigentliche Priorisierung, nicht die Karte allein."
              className="regions-list-panel"
            >
              <div className="regions-list-panel__header">
                <OperatorChipRail>
                  <button
                    type="button"
                    onClick={() => setListFilter('all')}
                    className={`tab-chip ${listFilter === 'all' ? 'active' : ''}`}
                  >
                    Alle
                  </button>
                  <button
                    type="button"
                    onClick={() => setListFilter('prioritized')}
                    className={`tab-chip ${listFilter === 'prioritized' ? 'active' : ''}`}
                  >
                    Prüfbar
                  </button>
                  <button
                    type="button"
                    onClick={() => setListFilter('low_evidence')}
                    className={`tab-chip ${listFilter === 'low_evidence' ? 'active' : ''}`}
                  >
                    Zu wenig Evidenz
                  </button>
                </OperatorChipRail>
              </div>

              <div className="regions-compare-list" aria-label="Regionenvergleich">
                {filteredRegionRows.length > 0 ? filteredRegionRows.map(({ code, region: row, suggestion: rowSuggestion }) => {
                  const selected = fallbackRegionCode === code;
                  const rowDirection = deriveRegionalDirection(row, rowSuggestion);
                  const rowDirectionLabel = regionalDirectionLabel(rowDirection);
                  const rowEvidence = evidenceLabel(row);
                  const rowReason = comparisonReason(row, rowSuggestion?.reason);
                  const rowNextStep = nextStepLabel(Boolean(row.recommendation_ref?.card_id), rowDirection);
                  return (
                    <button
                      key={code}
                      type="button"
                      onClick={() => onSelectRegion(code)}
                      className={`campaign-list-card ${selected ? 'card-selected' : ''}`}
                    >
                      <div className="regions-compare-list__row-head">
                        <div style={{ textAlign: 'left' }}>
                          <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>{row.name}</div>
                          <div className="regions-compare-list__row-meta">
                            Rang #{row.priority_rank ?? '-'} · {rowNextStep}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div className="ops-number-emphasis">{formatFractionPercent(primarySignalScore(row), 0)}</div>
                          <div className="ops-row-meta">{signalLabel}</div>
                        </div>
                      </div>

                      <p className="regions-compare-list__reason">{rowReason}</p>

                      <div className="regions-compare-list__meta">
                        <span className={`regions-direction-pill regions-direction-pill--${rowDirection}`}>
                          {rowDirectionLabel}
                        </span>
                        <span className={`regions-status-chip ${rowEvidence === 'Zu wenig Evidenz' ? 'regions-status-chip--warning' : ''}`}>
                          {rowEvidence}
                        </span>
                      </div>
                    </button>
                  );
                }) : (
                  <div className="workspace-note-card">
                    Für diesen Filter gibt es aktuell keine passenden Bundesländer.
                  </div>
                )}
              </div>
            </OperatorPanel>

            <OperatorPanel
              title="Orientierungskarte auf Bundesland-Level"
              description="Die Karte hilft bei Auswahl und räumlicher Einordnung. Die eigentliche Handlung leitest du aus Karte plus Liste ab, nicht aus der Fläche allein."
              tone="muted"
              className="regions-map-panel regions-map-shell"
            >
              <GermanyMap
                regions={activeMap.regions}
                selectedRegion={fallbackRegionCode}
                onSelectRegion={onSelectRegion}
              />

              <div className="workspace-note-list">
                <div className="workspace-note-card">
                  <strong>Orientierung statt Hauptentscheidung:</strong> Die Karte zeigt das regionale Signalbild auf Bundesland-Level und vermeidet bewusst City-Präzision.
                </div>
                <div className="workspace-note-card">
                  <strong>{signalLabel}:</strong> {signalNote}
                </div>
              </div>
            </OperatorPanel>
          </div>
        </OperatorSection>
      </div>

      <div ref={detailsRef}>
        <CollapsibleSection
          title={region ? `Tiefe bei Bedarf: ${region.name}` : 'Tiefe bei Bedarf'}
          subtitle="Treiber, Rohdetails und längere Begründung nur wenn du tiefer einsteigen möchtest."
        >
          <div className="workspace-two-column">
            <OperatorPanel
              title="Begründung"
              description="Die kurze Begründung bleibt zuerst sichtbar, alles Weitere kommt darunter."
            >
              <div className="workspace-note-list">
                <div className="workspace-note-card">{primaryReason}</div>
                <div className="workspace-note-card">
                  {region
                    ? 'Wenn das Bundesland passt, springst du von hier direkt in den regionalen Kampagnenpfad.'
                    : 'Sobald eine Region gewählt ist, steht hier genau ein klarer Arbeitsgrund.'}
                </div>
              </div>
            </OperatorPanel>

            <OperatorPanel
              title="Treiber und Rohdetails"
              description="Die signalgebenden Details bleiben gesammelt und gut lesbar, aber im zweiten Blick."
            >
              <div className="review-chip-row">
                {(region?.signal_drivers || []).map((driver) => (
                  <span key={driver.label} className="step-chip">
                    {normalizeGermanText(driver.label)} {formatPercent(driver.strength_pct || 0)}
                  </span>
                ))}
              </div>
              <div className="workspace-note-list">
                <div className="workspace-note-card">
                  Signalveränderung: {formatPercent(region?.change_pct || 0, 1)}
                </div>
                <div className="workspace-note-card">
                  Tendenz: {region?.forecast_direction || 'seitwärts'}
                </div>
                <div className="workspace-note-card">
                  Evidenzlage: {selectedEvidence}
                </div>
              </div>
            </OperatorPanel>
          </div>
        </CollapsibleSection>
      </div>
    </div>
  );
};

export default RegionWorkbench;
