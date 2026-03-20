import React from 'react';

import { MediaRegionsResponse, WorkspaceStatusSummary } from '../../types/media';
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
      <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
        Lade Regionen-Workbench...
      </div>
    );
  }

  if (!activeMap?.has_data) {
    return (
      <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
        Keine Kartendaten vorhanden.
      </div>
    );
  }

  const primaryReason = region?.priority_explanation
    || suggestion?.reason
    || region?.tooltip?.recommendation_text
    || 'Diese Region bündelt aktuell das stärkste Signal aus Forecast, Kontext und Nachfrage.';
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
      <section className="context-filter-rail">
        <div className="section-heading" style={{ marginBottom: 0 }}>
          <span className="section-kicker">Regionen</span>
          <h1 className="section-title">Eine Region. Ein Grund. Ein nächster Schritt.</h1>
          <p className="section-copy">
            Die Karte hilft nur bei der Auswahl. Die eigentliche Arbeit passiert an einer Region nach der anderen.
          </p>
        </div>

        <div style={{ display: 'grid', gap: 12, justifyItems: 'start' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
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
          </div>
          <span className="step-chip">Stand {formatDateShort(activeMap.date)}</span>
        </div>
      </section>

      <section className="card subsection-card workspace-priority-card" style={{ padding: 28 }}>
        <div className="workspace-priority-grid">
          <div>
            <div className="section-heading" style={{ gap: 8 }}>
              <span className="section-kicker">Ausgewählte Region</span>
              <h2 className="section-title workspace-priority-card__title">
                {region?.name || 'Wähle ein Bundesland auf der Karte'}
              </h2>
              <p className="section-copy">{primaryReason}</p>
            </div>

            <div className="metric-strip" style={{ marginTop: 18 }}>
              <div className="metric-box">
                <span>{signalLabel}</span>
                <strong>{formatPercent(primarySignalScore(region || primaryRegion))}</strong>
              </div>
              <div className="metric-box">
                <span>Actionability</span>
                <strong>{formatPercent(Number(region?.actionability_score || primaryRegion?.actionability_score || 0))}</strong>
              </div>
              <div className="metric-box">
                <span>Forecast-Richtung</span>
                <strong style={{ fontSize: 18 }}>{region?.forecast_direction || 'seitwärts'}</strong>
              </div>
              <div className="metric-box">
                <span>Budgethinweis</span>
                <strong>{suggestion?.budget_shift_pct ? formatPercent(suggestion.budget_shift_pct) : 'zuerst prüfen'}</strong>
              </div>
            </div>

            <div className="action-row" style={{ marginTop: 20 }}>
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

          <aside className="soft-panel workspace-priority-card__aside">
            <div>
              <div className="section-kicker">Kurz erklärt</div>
              <div className="summary-headline" style={{ fontSize: '1.55rem', marginTop: 8 }}>
                {region?.tooltip?.recommended_product || 'GELO Portfolio'}
              </div>
              <div className="summary-note" style={{ marginTop: 8 }}>
                {region?.signal_drivers?.slice(0, 3).map((driver) => driver.label).join(' · ') || 'Treiber folgen nach Auswahl der Region.'}
              </div>
            </div>

            <div style={{ display: 'grid', gap: 10 }}>
              <div className="evidence-row">
                <span>Einordnung</span>
                <strong>{region?.decision_mode_label || suggestion?.priority || 'Regionalsignal'}</strong>
              </div>
              <div className="evidence-row">
                <span>Produktfokus</span>
                <strong>{region?.tooltip?.recommended_product || 'GELO Portfolio'}</strong>
              </div>
              <div className="evidence-row">
                <span>Signaländerung</span>
                <strong>{formatPercent(region?.change_pct || 0, 1)}</strong>
              </div>
              <div className="evidence-row">
                <span>Ableitung</span>
                <strong>{(region?.source_trace || []).join(', ') || 'AMELAG, SurvStat, Forecast'}</strong>
              </div>
            </div>
          </aside>
        </div>
      </section>

      <WorkspaceStatusPanel
        status={workspaceStatus}
        title="Bevor wir handeln"
        intro="Diese vier Antworten helfen uns, ob die Region direkt in die Kampagnenarbeit gehen kann."
      />

      <section className="workspace-two-column">
        <section className="card subsection-card" style={{ padding: '18px 18px 12px' }}>
          <div className="section-heading" style={{ gap: 6, marginBottom: 0 }}>
            <h2 className="subsection-title">Region auswählen</h2>
            <p className="subsection-copy">
              Die Karte ist nur die Auswahlhilfe. Klick auf ein Bundesland, um oben den Fokus zu wechseln.
            </p>
          </div>
          <div style={{ marginTop: 10 }}>
            <GermanyMap
              regions={activeMap.regions}
              selectedRegion={selectedRegion}
              onSelectRegion={onSelectRegion}
            />
          </div>
        </section>

        <section className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading" style={{ gap: 6 }}>
            <h2 className="subsection-title">Weitere priorisierte Regionen</h2>
            <p className="subsection-copy">
              Falls die Fokusregion erledigt ist, sind das die nächsten sinnvollen Kandidaten.
            </p>
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
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
                      {item.tooltip?.recommended_product || 'GELO'} · {item.decision_mode_label || item.trend || '-'}
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
        </section>
      </section>

      <CollapsibleSection
        title={region ? `Warum ${region.name}?` : 'Warum diese Region?'}
        subtitle="Die wichtigsten Gründe und Treiber liegen hier gesammelt und bleiben für den zweiten Blick aufklappbar."
        defaultOpen
      >
        <div className="workspace-two-column">
          <div className="soft-panel workspace-detail-panel">
            <div className="section-kicker">Begründung</div>
            <div className="workspace-note-list" style={{ marginTop: 12 }}>
              <div className="workspace-note-card">{primaryReason}</div>
              <div className="workspace-note-card">
                {region
                  ? 'Wenn die Region passt, springst du direkt in den passenden Kampagnenpfad.'
                  : 'Sobald eine Region gewählt ist, steht hier genau ein klarer Arbeitsgrund.'}
              </div>
            </div>
          </div>

          <div className="soft-panel workspace-detail-panel">
            <div className="section-kicker">Treiber und Rohdetails</div>
            <div className="review-chip-row" style={{ marginTop: 12 }}>
              {(region?.signal_drivers || []).map((driver) => (
                <span key={driver.label} className="step-chip">
                  {driver.label} {formatPercent(driver.strength_pct || 0)}
                </span>
              ))}
            </div>
            <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
              <div className="evidence-row">
                <span>Signaländerung</span>
                <strong>{formatPercent(region?.change_pct || 0, 1)}</strong>
              </div>
              <div className="evidence-row">
                <span>Forecast-Richtung</span>
                <strong>{region?.forecast_direction || 'seitwärts'}</strong>
              </div>
              <div className="evidence-row">
                <span>Quellen</span>
                <strong>{(region?.source_trace || []).join(', ') || 'AMELAG, SurvStat, Forecast'}</strong>
              </div>
            </div>
          </div>
        </div>
      </CollapsibleSection>
    </div>
  );
};

export default RegionWorkbench;
