import React from 'react';

import { CockpitResponse } from './types';
import GermanyMap from './GermanyMap';
import { formatDateShort, formatPercent, VIRUS_OPTIONS } from './cockpitUtils';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  cockpit: CockpitResponse | null;
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
  cockpit,
  loading,
  selectedRegion,
  onSelectRegion,
  onOpenRecommendation,
  onGenerateRegionCampaign,
  regionActionLoading,
}) => {
  const activeMap = cockpit?.map;
  const region = selectedRegion ? activeMap?.regions?.[selectedRegion] : null;
  const suggestion = activeMap?.activation_suggestions?.find((item) => item.region === selectedRegion);
  const topRegions = (activeMap?.top_regions || []).slice(0, 5);

  if (loading) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade Regionen-Workbench...</div>;
  }

  if (!activeMap?.has_data) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Keine Kartendaten vorhanden.</div>;
  }

  return (
    <div style={{ display: 'grid', gap: 20 }}>
      <section className="context-filter-rail">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
            Regionen priorisieren
          </span>
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
        <div className="card" style={{ padding: 20 }}>
          <div style={{ marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>Deutschlandkarte</h2>
            <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
              Klick auf ein Bundesland für Signal-Score und Kampagnenaktion.
            </p>
          </div>
          <GermanyMap
            regions={activeMap.regions}
            selectedRegion={selectedRegion}
            onSelectRegion={onSelectRegion}
          />
        </div>

        <div style={{ display: 'grid', gap: 16 }}>
          <div className="card" style={{ padding: 20, display: 'grid', gap: 14 }}>
            <div>
              <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
                Regionen-Inspector
              </div>
              <h2 style={{ margin: '8px 0 0', fontSize: 24, color: 'var(--text-primary)' }}>
                {region?.name || 'Region wählen'}
              </h2>
            </div>

            {region ? (
              <>
                <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
                  <div className="metric-box">
                    <span>Signal-Score</span>
                    <strong>{formatPercent(region.impact_probability || region.peix_score || 0)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Trend</span>
                    <strong style={{ fontSize: 18 }}>{region.trend}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Shift</span>
                    <strong>{formatPercent(suggestion?.budget_shift_pct || 0)}</strong>
                  </div>
                </div>

                <div className="soft-panel" style={{ padding: 16, display: 'grid', gap: 10 }}>
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Warum jetzt?</div>
                    <div style={{ marginTop: 4, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                      {suggestion?.reason || region.tooltip?.recommendation_text || 'Regionale Auffälligkeit aus Abwasser, Forecast und Kontextsignalen.'}
                    </div>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Produktfokus: <strong style={{ color: 'var(--text-primary)' }}>{region.tooltip?.recommended_product || 'GELO Portfolio'}</strong>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Signaländerung: <strong style={{ color: 'var(--text-primary)' }}>{formatPercent(region.change_pct || 0, 1)}</strong>
                  </div>
                </div>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                  {region.recommendation_ref?.card_id ? (
                    <button className="media-button" type="button" onClick={() => onOpenRecommendation(region.recommendation_ref!.card_id)}>
                      Kampagnenpaket öffnen
                    </button>
                  ) : (
                    <button
                      className="media-button"
                      type="button"
                      onClick={() => selectedRegion && onGenerateRegionCampaign(selectedRegion)}
                      disabled={!selectedRegion || regionActionLoading}
                    >
                      {regionActionLoading ? 'Wird erzeugt...' : 'Kampagne für Region generieren'}
                    </button>
                  )}
                  <button className="media-button secondary" type="button" onClick={() => selectedRegion && onGenerateRegionCampaign(selectedRegion)} disabled={!selectedRegion || regionActionLoading}>
                    Region aktualisieren
                  </button>
                </div>
              </>
            ) : (
              <div style={{ color: 'var(--text-muted)' }}>Wähle ein Bundesland aus der Karte.</div>
            )}
          </div>

          <div className="card" style={{ padding: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)' }}>Top-Regionen</h2>
                <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
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
                        {item.tooltip?.recommended_product || 'GELO'} · {item.trend}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--accent-violet)' }}>{formatPercent(item.impact_probability || item.peix_score || 0)}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                        Priorität {Math.round(item.recommendation_ref?.urgency_score || 0)}
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
