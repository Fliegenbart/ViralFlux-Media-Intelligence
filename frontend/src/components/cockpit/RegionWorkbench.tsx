import React from 'react';

import { UI_COPY } from '../../lib/copy';
import { MediaRegionsResponse } from '../../types/media';
import GermanyMap from './GermanyMap';
import { formatDateShort, formatPercent, VIRUS_OPTIONS } from './cockpitUtils';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  regionsView: MediaRegionsResponse | null;
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

  if (loading && !regionsView) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade Regionen-Workbench...</div>;
  }

  if (!activeMap?.has_data) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Keine Kartendaten vorhanden.</div>;
  }

  return (
    <div className="page-stack">
      <section className="context-filter-rail">
        <div className="section-heading">
          <span className="section-kicker">Regionen priorisieren</span>
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
        </div>
        <span className="step-chip">Stand {formatDateShort(activeMap.date)}</span>
      </section>

      <section className="cockpit-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div className="section-heading" style={{ gap: 6, marginBottom: 12 }}>
            <h2 className="subsection-title">Deutschlandkarte</h2>
            <p className="subsection-copy">
              Klick auf ein Bundesland fuer Signalscore, Begruendung und naechsten Schritt.
            </p>
          </div>
          <GermanyMap
            regions={activeMap.regions}
            selectedRegion={selectedRegion}
            onSelectRegion={onSelectRegion}
          />
        </div>

        <div style={{ display: 'grid', gap: 16 }}>
          <div className="card subsection-card" style={{ padding: 24, display: 'grid', gap: 18 }}>
            <div>
              <div className="section-kicker">Regionen-Inspector</div>
              <h2 className="subsection-title" style={{ marginTop: 8 }}>
                {region?.name || 'Region wählen'}
              </h2>
            </div>

            {region ? (
              <>
                <div className="metric-strip">
                  <div className="metric-box">
                    <span>{UI_COPY.signalScore}</span>
                    <strong>{formatPercent(region.impact_probability || region.peix_score || 0)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Severity</span>
                    <strong>{formatPercent(region.severity_score || 0)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Momentum</span>
                    <strong>{formatPercent(region.momentum_score || 0)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Actionability</span>
                    <strong>{formatPercent(region.actionability_score || 0)}</strong>
                  </div>
                </div>

                <div className="soft-panel" style={{ padding: 16, display: 'grid', gap: 10 }}>
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Warum jetzt?</div>
                    <div style={{ marginTop: 4, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                      {region.priority_explanation || suggestion?.reason || region.tooltip?.recommendation_text || 'Regionale Auffälligkeit aus Abwasser, Forecast und Kontextsignalen.'}
                    </div>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Einordnung: <strong style={{ color: 'var(--text-primary)' }}>{region.decision_mode_label || 'Regionalsignal'}</strong>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Produktfokus: <strong style={{ color: 'var(--text-primary)' }}>{region.tooltip?.recommended_product || 'GELO Portfolio'}</strong>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Signaländerung: <strong style={{ color: 'var(--text-primary)' }}>{formatPercent(region.change_pct || 0, 1)}</strong>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Forecast-Richtung: <strong style={{ color: 'var(--text-primary)' }}>{region.forecast_direction || 'seitwärts'}</strong>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Budgetempfehlung: <strong style={{ color: 'var(--text-primary)' }}>{suggestion?.budget_shift_pct ? formatPercent(suggestion.budget_shift_pct) : 'zuerst pruefen'}</strong>
                  </div>
                </div>

                <div className="soft-panel" style={{ padding: 16, display: 'grid', gap: 10 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Treiber dieser Region</div>
                  <div className="review-chip-row">
                    {(region.signal_drivers || []).map((driver) => (
                      <span key={driver.label} className="step-chip">
                        {driver.label} {formatPercent(driver.strength_pct || 0)}
                      </span>
                    ))}
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Ableitung aus: <strong style={{ color: 'var(--text-primary)' }}>{(region.source_trace || []).join(', ') || 'AMELAG, SurvStat, Forecast'}</strong>
                  </div>
                </div>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                  {region.recommendation_ref?.card_id ? (
                    <button className="media-button" type="button" onClick={() => onOpenRecommendation(region.recommendation_ref!.card_id)}>
                      Kampagnenvorschlag oeffnen
                    </button>
                  ) : (
                    <button
                      className="media-button"
                      type="button"
                      onClick={() => selectedRegion && onGenerateRegionCampaign(selectedRegion)}
                      disabled={!selectedRegion || regionActionLoading}
                    >
                      {regionActionLoading ? 'Wird erstellt...' : 'Vorschlag fuer Region erstellen'}
                    </button>
                  )}
                  <button className="media-button secondary" type="button" onClick={() => selectedRegion && onGenerateRegionCampaign(selectedRegion)} disabled={!selectedRegion || regionActionLoading}>
                    Empfehlung neu berechnen
                  </button>
                </div>
              </>
            ) : (
              <div style={{ color: 'var(--text-muted)' }}>Wähle ein Bundesland aus der Karte.</div>
            )}
          </div>

          <div className="card subsection-card" style={{ padding: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Top-Regionen</h2>
                <p className="subsection-copy">
                  Direkt priorisiert für die Wochenplanung.
                </p>
              </div>
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
                      <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--accent-violet)' }}>{formatPercent(Number(item.actionability_score || item.impact_probability || item.peix_score || 0))}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                        Priorität #{Math.round(Number(item.priority_rank || 0))}
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default RegionWorkbench;
