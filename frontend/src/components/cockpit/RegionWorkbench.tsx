import React, { useMemo, useState } from 'react';

import { MediaRegionsResponse, WorkspaceStatusSummary } from '../../types/media';
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
  OperatorStat,
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
  const activeMap = regionsView?.map;
  const topRegions = (activeMap?.top_regions || []).slice(0, 5);
  const fallbackRegionCode = selectedRegion || topRegions[0]?.code || null;
  const region = fallbackRegionCode ? activeMap?.regions?.[fallbackRegionCode] || null : null;
  const suggestion = activeMap?.activation_suggestions?.find((item) => item.region === fallbackRegionCode);
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
    ? 'Regionen mit belastbarerem Signal'
    : listFilter === 'low_evidence'
      ? 'Regionen mit zu wenig Evidenz'
      : 'Regionenvergleich auf Bundesland-Level';

  if (loading && !regionsView) {
    return (
      <OperatorSection
        kicker="Regionen"
        title="Hier sehen wir den wahrscheinlichen frühen Start"
        description="Wir holen gerade die Kartendaten. Gleich siehst du wieder, welche Region zuerst relevant wird."
        tone="muted"
      >
        <div className="workspace-note-card">Lade Regionen...</div>
      </OperatorSection>
    );
  }

  if (!activeMap?.has_data) {
    return (
      <OperatorSection
        kicker="Regionen"
        title="Hier sehen wir den wahrscheinlichen frühen Start"
        description="Für diese Auswahl liegen gerade keine Kartendaten vor."
        tone="muted"
      >
        <div className="workspace-note-card">Keine Kartendaten vorhanden.</div>
      </OperatorSection>
    );
  }

  const primaryReason = explainInPlainGerman(
    region?.priority_explanation
      || suggestion?.reason
      || region?.tooltip?.recommendation_text
      || 'Diese Region zeigt aktuell die stärkste Dynamik aus Vorhersage, Versorgung und Nachfrage.',
  );
  const primaryActionLabel = region?.recommendation_ref?.card_id
    ? 'Kampagnenvorschlag öffnen'
    : 'Vorschlag für Region erstellen';
  const selectedEvidence = evidenceLabel(region || primaryRegion);
  const primaryAction = () => {
    if (!fallbackRegionCode) return;
    if (region?.recommendation_ref?.card_id) {
      onOpenRecommendation(region.recommendation_ref.card_id);
      return;
    }
    onGenerateRegionCampaign(fallbackRegionCode);
  };

  return (
    <div className="page-stack">
      <OperatorSection
        kicker="Regionen"
        title="Bundesländer vergleichen"
        description="Die Karte gibt Orientierung auf Bundesland-Level. Für Entscheidungen nutzen wir zusätzlich die Liste, damit keine scheinbare City-Präzision entsteht."
        tone="muted"
        className="operator-toolbar-shell"
      >
        <div className="now-toolbar">
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

          <OperatorChipRail className="review-chip-row">
            <span className="step-chip">Datenstand {formatDateShort(activeMap.date)}</span>
            <span className="step-chip">Bundesland-Level</span>
            <span className="step-chip">Kein City-Forecast</span>
          </OperatorChipRail>
        </div>
      </OperatorSection>

      <OperatorSection
        kicker="Ausgewähltes Bundesland"
        title={region?.name ? `${region.name} liegt im aktuellen Bundesland-Ranking vorne` : 'Wähle ein Bundesland aus Karte oder Liste'}
        description="Hier siehst du das führende Bundesland ehrlich auf Scope-Ebene: Signal, Arbeitsstufe und Evidenz bleiben getrennt und verständlich."
        tone="accent"
        className="regions-hero-shell"
      >
        <div className="regions-command-grid">
          <OperatorPanel
            title="Deutschlandkarte"
            description="Zur Orientierung auf Bundesland-Level. Die Karte ist absichtlich keine Feinkarte und ersetzt nicht die Vergleichsliste."
            className="regions-map-panel"
          >
            <GermanyMap
              regions={activeMap.regions}
              selectedRegion={fallbackRegionCode}
              onSelectRegion={onSelectRegion}
            />

            <div className="workspace-note-list">
              <div className="workspace-note-card">
                <strong>Bundesland-Level:</strong> Die Karte zeigt nur, welches Bundesland im Ranking vorne liegt.
              </div>
              <div className="workspace-note-card">
                <strong>Kein City-Forecast:</strong> Die Farbe steht nur für Orientierung im Signalvergleich, nicht für punktgenaue lokale Sicherheit.
              </div>
              <div className="workspace-note-card">
                <strong>{signalLabel}:</strong> {signalNote}
              </div>
            </div>

            <div className="regions-list-panel">
              <div className="regions-list-panel__header">
                <div>
                  <div className="section-kicker">Vergleichsliste</div>
                  <h3 className="subsection-title" style={{ marginTop: 6 }}>{regionListTitle}</h3>
                </div>
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
                    Vergleichbar
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
                {filteredRegionRows.map(({ code, region: row, suggestion: rowSuggestion }) => {
                  const selected = fallbackRegionCode === code;
                  return (
                    <button
                      key={code}
                      type="button"
                      onClick={() => onSelectRegion(code)}
                      className={`campaign-list-card ${selected ? 'card-selected' : ''}`}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                        <div style={{ textAlign: 'left' }}>
                          <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>{row.name}</div>
                          <div className="ops-row-meta">
                            Bundesland-Level · Rang #{row.priority_rank ?? '-'}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div className="ops-number-emphasis">{formatFractionPercent(primarySignalScore(row), 0)}</div>
                          <div className="ops-row-meta">{signalLabel}</div>
                        </div>
                      </div>

                      <div className="regions-compare-list__meta">
                        <span className={`regions-status-chip ${hasInsufficientEvidence(row) ? 'regions-status-chip--warning' : ''}`}>
                          {rowSuggestion?.priority ? `Arbeitsstufe ${normalizeGermanText(rowSuggestion.priority)}` : 'Arbeitsstufe offen'}
                        </span>
                        <span className={`regions-status-chip ${hasInsufficientEvidence(row) ? 'regions-status-chip--warning' : ''}`}>
                          {evidenceLabel(row)}
                        </span>
                        <span className="regions-status-chip">
                          {row.forecast_direction || 'seitwärts'}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </OperatorPanel>

          <OperatorPanel
            eyebrow="Fokus-Bundesland"
            title={region ? `${region.name} zuerst prüfen` : 'Wähle ein Bundesland'}
            description={primaryReason}
            tone="accent"
            className="regions-command-rail"
          >
            <div className="operator-stat-grid">
              <OperatorStat
                label={signalLabel}
                value={formatFractionPercent(primarySignalScore(region || primaryRegion))}
                meta="Event-Signal auf Bundesland-Level"
                tone="accent"
              />
              <OperatorStat
                label="Arbeitsstufe"
                value={suggestion?.priority ? normalizeGermanText(suggestion.priority) : 'offen'}
                meta="Nicht aus der Flächenfarbe abgeleitet"
              />
              <OperatorStat
                label="Evidenz"
                value={selectedEvidence}
                meta="Schwache Evidenz wird explizit markiert"
              />
            </div>

            <div className="workspace-note-list">
              <div className="workspace-note-card">Warum: {primaryReason}</div>
              <div className="workspace-note-card">
                Scope: Bundesland-Level. Kein City-Forecast und keine pseudo-feine lokale Präzision.
              </div>
              <div className="workspace-note-card">
                Nächster Schritt: {region?.recommendation_ref?.card_id ? 'Bestehenden Vorschlag öffnen.' : 'Für diese Region einen Vorschlag anlegen.'}
              </div>
            </div>

            <div className="action-row">
              <button
                className="media-button"
                type="button"
                onClick={primaryAction}
                disabled={!fallbackRegionCode || regionActionLoading}
              >
                {regionActionLoading ? 'Wird vorbereitet…' : primaryActionLabel}
              </button>
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>

      <CollapsibleSection
        title={region ? `Mehr Details zu ${region.name}` : 'Mehr Details zur Region'}
        subtitle="Hier findest du die wichtigsten Gründe und Treiber noch einmal gesammelt."
      >
        <div className="workspace-two-column">
          <OperatorPanel
            title="Begründung"
            description="Die kurze Begründung bleibt zuerst sichtbar."
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">{primaryReason}</div>
              <div className="workspace-note-card">
                {region
                  ? 'Hier sehen wir den frühen Startpunkt zuerst. Wenn die Region passt, springst du direkt in den passenden Kampagnenpfad.'
                  : 'Sobald eine Region gewählt ist, steht hier genau ein klarer Arbeitsgrund.'}
              </div>
            </div>
          </OperatorPanel>

          <OperatorPanel
            title="Treiber und Rohdetails"
            description="Die signalgebenden Details bleiben gesammelt und gut lesbar."
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
                Signaländerung: {formatPercent(region?.change_pct || 0, 1)}
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
  );
};

export default RegionWorkbench;
