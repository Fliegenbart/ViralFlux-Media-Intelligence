import React from 'react';

import { MediaRegionsResponse, WorkspaceStatusSummary } from '../../types/media';
import { normalizeGermanText } from '../../lib/plainLanguage';
import CollapsibleSection from '../CollapsibleSection';
import { UI_COPY } from '../../lib/copy';
import GermanyMap from './GermanyMap';
import {
  formatDateShort,
  formatPercent,
  metricContractLabel,
  primarySignalScore,
  VIRUS_OPTIONS,
} from './cockpitUtils';
import WorkspaceStatusPanel from './WorkspaceStatusPanel';
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
  const activeMap = regionsView?.map;
  const region = selectedRegion ? activeMap?.regions?.[selectedRegion] : null;
  const suggestion = activeMap?.activation_suggestions?.find((item) => item.region === selectedRegion);
  const topRegions = (activeMap?.top_regions || []).slice(0, 5);
  const primaryRegion = region || topRegions[0] || null;
  const signalLabel = metricContractLabel(primaryRegion?.field_contracts, 'signal_score', UI_COPY.signalScore);

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

  const primaryReason = normalizeGermanText(
    region?.priority_explanation
      || suggestion?.reason
      || region?.tooltip?.recommendation_text
      || 'Diese Region zeigt aktuell die stärkste Dynamik aus Vorhersage, Versorgung und Nachfrage.',
  );
  const driverSummary = normalizeGermanText(
    region?.signal_drivers?.slice(0, 3).map((driver) => driver.label).join(' · ')
      || 'Die wichtigsten Treiber erscheinen nach Auswahl der Region.',
  );
  const decisionModeLabel = normalizeGermanText(region?.decision_mode_label || suggestion?.priority || 'Regionalsignal');
  const sourceTraceLabel = normalizeGermanText(
    (region?.source_trace || []).join(', ') || 'AMELAG, SurvStat, Vorhersage',
  );
  const primaryActionLabel = region?.recommendation_ref?.card_id
    ? 'Kampagnenvorschlag öffnen'
    : 'Vorschlag für Region erstellen';
  const primaryAction = () => {
    if (!selectedRegion) return;
    if (region?.recommendation_ref?.card_id) {
      onOpenRecommendation(region.recommendation_ref.card_id);
      return;
    }
    onGenerateRegionCampaign(selectedRegion);
  };

  return (
    <div className="page-stack">
      <OperatorSection
        kicker="Regionen"
        title="Hier sehen wir den wahrscheinlichen frühen Start"
        description="Hier findest du die Region, die du als Nächstes prüfen solltest."
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

          <span className="step-chip">Datenstand {formatDateShort(activeMap.date)}</span>
        </div>
      </OperatorSection>

      <OperatorSection
        kicker="Ausgewählte Region"
        title={region?.name || 'Wähle ein Bundesland auf der Karte'}
        description={primaryReason}
        tone="accent"
        className="now-hero-shell"
      >
        <div className="workspace-priority-grid now-hero-grid">
          <div className="now-focus-card">
            <div className="operator-stat-grid">
              <OperatorStat
                label={signalLabel}
                value={formatPercent(primarySignalScore(region || primaryRegion))}
                meta="Aktuelle Dynamik"
                tone="accent"
              />
              <OperatorStat
                label="Handlungsreife"
                value={formatPercent(Number(region?.actionability_score || primaryRegion?.actionability_score || 0))}
                meta="Prüfwert für die nächste Aktion"
              />
              <OperatorStat
                label="Tendenz"
                value={region?.forecast_direction || 'seitwärts'}
                meta="Richtung der Entwicklung"
              />
              <OperatorStat
                label="Budgethinweis"
                value={suggestion?.budget_shift_pct ? formatPercent(suggestion.budget_shift_pct) : 'zuerst prüfen'}
                meta="ohne voreilige Freigabe"
              />
            </div>

            <div className="action-row">
              <button
                className="media-button"
                type="button"
                onClick={primaryAction}
                disabled={!selectedRegion || regionActionLoading}
              >
                {regionActionLoading ? 'Wird vorbereitet…' : primaryActionLabel}
              </button>
            </div>
          </div>

          <OperatorPanel
            eyebrow="Warum diese Region"
            title={region ? `Die größte Dynamik sehen wir aktuell in ${region.name}.` : 'Wichtigste Region'}
            description={driverSummary}
            tone="muted"
          >
            <div className="workspace-note-list">
              <div className="workspace-note-card">
                Einordnung: {decisionModeLabel}
              </div>
              <div className="workspace-note-card">
                Produktfokus: {region?.tooltip?.recommended_product || 'GELO Portfolio'}
              </div>
              <div className="workspace-note-card">
                Veränderung: {formatPercent(region?.change_pct || 0, 1)}
              </div>
              <div className="workspace-note-card">
                Wichtige Quellen: {sourceTraceLabel}
              </div>
            </div>
          </OperatorPanel>
        </div>
      </OperatorSection>

      <WorkspaceStatusPanel
        status={workspaceStatus}
        title="Was vor dem Start noch geklärt sein sollte"
        intro="Hier siehst du, ob du für diese Region direkt weitermachen kannst."
      />

      <section className="workspace-two-column">
        <OperatorPanel
          title="Region auswählen"
          description="Klick auf ein Bundesland. Oben wechselt dann sofort der Fokus."
        >
          <GermanyMap
            regions={activeMap.regions}
            selectedRegion={selectedRegion}
            onSelectRegion={onSelectRegion}
          />
        </OperatorPanel>

        <OperatorPanel
          title="Weitere Regionen mit hoher Dynamik"
          description="Wenn die erste Region erledigt ist, findest du hier die nächsten sinnvollen Kandidaten."
        >
          <div className="workspace-note-list">
            {topRegions.map((item) => (
              <button
                type="button"
                key={item.code}
                onClick={() => onSelectRegion(item.code)}
                className="campaign-list-card"
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{item.name}</div>
                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                      {item.tooltip?.recommended_product || 'GELO'} · {normalizeGermanText(item.decision_mode_label || item.trend || '-')}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--accent-violet)' }}>
                      {formatPercent(Number(item.actionability_score || primarySignalScore(item) || 0))}
                    </div>
                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                      Priorität #{Math.round(Number(item.priority_rank || 0))}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </OperatorPanel>
      </section>

      <CollapsibleSection
        title={region ? `Warum ${region.name}?` : 'Warum diese Region?'}
        subtitle="Hier findest du die wichtigsten Gründe für die Auswahl dieser Region."
        defaultOpen
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
                Quellen: {sourceTraceLabel}
              </div>
            </div>
          </OperatorPanel>
        </div>
      </CollapsibleSection>
    </div>
  );
};

export default RegionWorkbench;
