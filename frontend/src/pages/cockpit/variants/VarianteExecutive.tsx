import React, { useState } from 'react';
import type { CockpitSnapshot } from '../types';
import './variante-executive.css';

interface Props {
  snapshot: CockpitSnapshot;
  virusTyp: string;
  onVirusChange: (v: string) => void;
  supportedViruses: readonly string[];
}

/**
 * Hex-Tile-Karte für Deutschland — abstrakt, editorial, gut lesbar.
 * Jedes Bundesland = ein Hexagon in grob geografischer Position.
 * Konvention aus Editorial-Infografik (FT, Zeit, Guardian).
 *
 * Layout-Grid (col, row) → hex center (cx, cy) mit pointy-top-Geometrie:
 *   cx = 60 + col * 48 + (row % 2 === 1 ? 24 : 0)
 *   cy = 60 + row * 42
 */
const HEX_POSITIONS: Record<
  string,
  { cx: number; cy: number; name: string }
> = {
  SH: { cx: 204, cy: 60, name: 'Schleswig-Holstein' },
  HH: { cx: 180, cy: 102, name: 'Hamburg' },
  MV: { cx: 276, cy: 102, name: 'Mecklenburg-Vorpommern' },
  HB: { cx: 108, cy: 144, name: 'Bremen' },
  NI: { cx: 156, cy: 144, name: 'Niedersachsen' },
  BB: { cx: 252, cy: 144, name: 'Brandenburg' },
  BE: { cx: 300, cy: 144, name: 'Berlin' },
  NW: { cx: 180, cy: 186, name: 'Nordrhein-Westfalen' },
  ST: { cx: 228, cy: 186, name: 'Sachsen-Anhalt' },
  SN: { cx: 276, cy: 186, name: 'Sachsen' },
  HE: { cx: 204, cy: 228, name: 'Hessen' },
  TH: { cx: 252, cy: 228, name: 'Thüringen' },
  RP: { cx: 228, cy: 270, name: 'Rheinland-Pfalz' },
  SL: { cx: 156, cy: 312, name: 'Saarland' },
  BW: { cx: 204, cy: 312, name: 'Baden-Württemberg' },
  BY: { cx: 252, cy: 312, name: 'Bayern' },
};

// Pointy-top hexagon with radius r=24 (vertex-to-center)
const HEX_POINTS = '0,-24 20.78,-12 20.78,12 0,24 -20.78,12 -20.78,-12';

const fmtPct = (v: number | null | undefined, digits = 0): string =>
  v == null ? '—' : `${(v * 100).toFixed(digits)} %`;

const fmtDelta = (v: number | null | undefined): string => {
  if (v == null) return '—';
  const sign = v > 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(0)} %`;
};

export const VarianteExecutive: React.FC<Props> = ({
  snapshot,
  virusTyp,
  onVirusChange,
  supportedViruses,
}) => {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const rec = snapshot.primaryRecommendation;
  const fromCode = rec?.fromCode;
  const toCode = rec?.toCode;
  const toRegion = snapshot.regions.find((r) => r.code === toCode);
  const fromRegion = snapshot.regions.find((r) => r.code === fromCode);
  const confidence = rec?.confidence ?? null;
  const waveContext = snapshot.averageWaveProbabilityContext ?? null;

  return (
    <div className="vex-root">
      <header className="vex-topbar">
        <div className="vex-brand">
          <span className="vex-mark">◆</span>
          <span className="vex-brand-name">FluxEngine</span>
          <span className="vex-brand-tag">Executive Brief</span>
        </div>
        <div className="vex-topbar-right">
          <div className="vex-virus-switch">
            {supportedViruses.map((v) => (
              <button
                key={v}
                type="button"
                className={`vex-virus-btn ${v === virusTyp ? 'active' : ''}`}
                onClick={() => onVirusChange(v)}
              >
                {v}
              </button>
            ))}
          </div>
          <div className="vex-meta">
            {snapshot.isoWeek} · {snapshot.client}
          </div>
        </div>
      </header>

      <main className="vex-hero">
        <div className="vex-hero-content">
          <div className="vex-kicker">Entscheidung der Woche</div>

          {rec ? (
            <h1 className="vex-headline">
              Prüfe{' '}
              <span className="vex-budget">
                {rec.amountEur
                  ? `${(rec.amountEur / 1000).toLocaleString('de-DE')} k €`
                  : 'Budget'}
              </span>{' '}
              als Shift-Kandidat von <em className="vex-from">{rec.fromName}</em>
              <br />
              nach <em className="vex-to">{rec.toName}</em>.
            </h1>
          ) : (
            <h1 className="vex-headline vex-headline-quiet">
              Das Tool schweigt diese Woche.
            </h1>
          )}

          {rec && (
            <p className="vex-why">
              {rec.why}
            </p>
          )}

          {!rec && waveContext && (
            <p className="vex-why">{waveContext}</p>
          )}

          <div className="vex-stats">
            <div className="vex-stat">
              <div className="vex-stat-label">Konfidenz</div>
              <div className="vex-stat-value">
                {fmtPct(confidence, 1)}
              </div>
              <div className="vex-stat-note">
                Ranking-basiert · regional-pooled-panel
              </div>
            </div>
            <div className="vex-stat">
              <div className="vex-stat-label">Wellen-Lead</div>
              <div className="vex-stat-value">
                {snapshot.modelStatus.bestLagDays != null
                  ? `${Math.abs(snapshot.modelStatus.bestLagDays)} Tage`
                  : '—'}
              </div>
              <div className="vex-stat-note">
                Vorlauf vs. Notaufnahme-Signal
              </div>
            </div>
            <div className="vex-stat">
              <div className="vex-stat-label">Saison-Phase</div>
              <div className="vex-stat-value vex-stat-value-small">
                Post-Saison
              </div>
              <div className="vex-stat-note">
                KW 17 / 2026 · natürliches Tief
              </div>
            </div>
          </div>
        </div>

        <div className="vex-map-column">
          <svg
            viewBox="0 0 360 372"
            className="vex-map"
            role="img"
            aria-label="Deutschland Hex-Tile-Karte mit Shift-Empfehlung"
          >
            <defs>
              <filter id="vex-glow" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="5" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <marker
                id="vex-arrow-head"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#3e6a4a" />
              </marker>
            </defs>

            {/* Hex-Tiles für alle 16 Bundesländer */}
            {Object.entries(HEX_POSITIONS).map(([code, { cx, cy }]) => {
              const isTarget = code === toCode;
              const isFrom = code === fromCode;
              const cls = `vex-hex ${isTarget ? 'vex-hex-to' : ''} ${
                isFrom ? 'vex-hex-from' : ''
              }`;
              return (
                <g
                  key={code}
                  className={cls}
                  transform={`translate(${cx},${cy})`}
                >
                  <polygon
                    points={HEX_POINTS}
                    filter={isTarget ? 'url(#vex-glow)' : undefined}
                  />
                  <text className="vex-hex-code">{code}</text>
                </g>
              );
            })}

            {/* Verbindungslinie from → to */}
            {fromCode && toCode && HEX_POSITIONS[fromCode] && HEX_POSITIONS[toCode] && (
              <g className="vex-arrow-group">
                <line
                  x1={HEX_POSITIONS[fromCode].cx}
                  y1={HEX_POSITIONS[fromCode].cy}
                  x2={HEX_POSITIONS[toCode].cx}
                  y2={HEX_POSITIONS[toCode].cy}
                  className="vex-arrow"
                  markerEnd="url(#vex-arrow-head)"
                />
              </g>
            )}
          </svg>
          <div className="vex-map-legend">
            {fromRegion && (
              <div className="vex-map-legend-item vex-map-legend-from">
                <span className="vex-map-dot vex-map-dot-from" />
                <span className="vex-map-legend-text">
                  <b>{fromRegion.name}</b> · {fmtDelta(fromRegion.delta7d)} · Top-Faller
                </span>
              </div>
            )}
            {toRegion && (
              <div className="vex-map-legend-item vex-map-legend-to">
                <span className="vex-map-dot vex-map-dot-to" />
                <span className="vex-map-legend-text">
                  <b>{toRegion.name}</b> · {fmtDelta(toRegion.delta7d)} · Top-Riser
                </span>
              </div>
            )}
          </div>
        </div>
      </main>

      <footer className="vex-foot">
        <button
          type="button"
          className="vex-details-toggle"
          onClick={() => setDetailsOpen(!detailsOpen)}
          aria-expanded={detailsOpen}
        >
          {detailsOpen ? '–' : '+'} Daten, Backtest, Quellen
        </button>

        {detailsOpen && (
          <div className="vex-details">
            <div className="vex-details-grid">
              <div className="vex-details-block">
                <div className="vex-details-label">Modell-Reife</div>
                <div className="vex-details-value">
                  {snapshot.modelStatus.trainingPanel?.maturityLabel ?? '—'}
                </div>
                <div className="vex-details-sub">
                  Version {snapshot.modelStatus.trainingPanel?.modelVersion ?? '—'}
                </div>
              </div>
              <div className="vex-details-block">
                <div className="vex-details-label">Ranking-Präzision (Top-3)</div>
                <div className="vex-details-value">
                  {fmtPct(snapshot.modelStatus.ranking?.precisionAtTop3, 1)}
                </div>
                <div className="vex-details-sub">
                  PR-AUC {(snapshot.modelStatus.ranking?.prAuc ?? 0).toFixed(2)} · ECE{' '}
                  {(snapshot.modelStatus.ranking?.ece ?? 0).toFixed(3)}
                </div>
              </div>
              <div className="vex-details-block">
                <div className="vex-details-label">Lead-Correlation</div>
                <div className="vex-details-value">
                  {(snapshot.modelStatus.correlationAtHorizon ?? 0).toFixed(2)}
                </div>
                <div className="vex-details-sub">
                  Gegen {snapshot.modelStatus.lead?.targetLabel ?? 'Notaufnahme'}
                </div>
              </div>
              <div className="vex-details-block">
                <div className="vex-details-label">Media-Plan</div>
                <div className="vex-details-value vex-details-value-small">
                  {snapshot.mediaPlan?.connected ? 'Verbunden' : 'Nicht verbunden'}
                </div>
                <div className="vex-details-sub">
                  EUR-Shift wartet auf Plan-Anbindung
                </div>
              </div>
            </div>

            <div className="vex-sources">
              <div className="vex-sources-label">Aktuelle Datenquellen</div>
              <div className="vex-sources-list">
                {snapshot.sources.slice(0, 6).map((s) => (
                  <div key={s.name} className="vex-source-row">
                    <span
                      className={`vex-source-dot vex-source-${s.health}`}
                      aria-label={s.health}
                    />
                    <span className="vex-source-name">{s.name}</span>
                    <span className="vex-source-latency">
                      {s.latencyDays === 0 ? 'live' : `${s.latencyDays} Tage`}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <a href="/cockpit" className="vex-deepdive-link">
              → Vollständiges Cockpit mit allen Details
            </a>
          </div>
        )}

        <div className="vex-fine-print">
          Quelle: RKI ARE · AMELAG Abwasser · AKTIN Notaufnahme · BfArM Engpässe · Google Trends · ViralFlux Media Intelligence.{' '}
          Alle Modell-Metriken honest-by-default — keine Confidence-Angabe ohne
          empirische Deckung.
        </div>
      </footer>
    </div>
  );
};

export default VarianteExecutive;
