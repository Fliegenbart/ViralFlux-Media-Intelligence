import React, { useState } from 'react';
import type { CockpitSnapshot } from '../types';
import './variante-executive.css';

interface Props {
  snapshot: CockpitSnapshot;
  virusTyp: string;
  onVirusChange: (v: string) => void;
  supportedViruses: readonly string[];
}

const BL_PATHS: Record<string, { d: string; cx: number; cy: number }> = {
  SH: { d: 'M230 65 L285 55 L305 85 L275 115 L235 110 Z', cx: 265, cy: 85 },
  HH: { d: 'M248 105 L278 100 L285 130 L255 135 Z', cx: 268, cy: 118 },
  MV: { d: 'M295 75 L385 65 L400 115 L310 125 Z', cx: 345, cy: 95 },
  NI: { d: 'M180 130 L295 125 L310 180 L195 185 Z', cx: 245, cy: 155 },
  HB: { d: 'M215 140 L235 138 L240 158 L218 160 Z', cx: 227, cy: 150 },
  BB: { d: 'M330 135 L405 128 L420 195 L345 200 Z', cx: 375, cy: 165 },
  BE: { d: 'M370 165 L388 163 L392 183 L372 185 Z', cx: 381, cy: 174 },
  ST: { d: 'M295 180 L360 175 L372 230 L300 235 Z', cx: 335, cy: 205 },
  NW: { d: 'M130 180 L215 175 L225 260 L140 265 Z', cx: 175, cy: 220 },
  HE: { d: 'M200 235 L270 230 L280 295 L210 300 Z', cx: 240, cy: 265 },
  SN: { d: 'M330 225 L410 220 L425 275 L340 280 Z', cx: 378, cy: 250 },
  TH: { d: 'M270 240 L340 235 L350 290 L280 295 Z', cx: 310, cy: 265 },
  RP: { d: 'M150 290 L215 285 L225 340 L160 345 Z', cx: 188, cy: 315 },
  SL: { d: 'M135 335 L165 332 L170 360 L140 363 Z', cx: 153, cy: 347 },
  BW: { d: 'M190 335 L290 328 L300 410 L200 415 Z', cx: 245, cy: 370 },
  BY: { d: 'M280 320 L420 310 L435 420 L290 425 Z', cx: 360, cy: 370 },
};

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
              Verschiebe{' '}
              <span className="vex-budget">
                {rec.amountEur
                  ? `${(rec.amountEur / 1000).toLocaleString('de-DE')} k €`
                  : 'Budget'}
              </span>{' '}
              aus <em className="vex-from">{rec.fromName}</em>
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
            viewBox="0 0 500 500"
            className="vex-map"
            role="img"
            aria-label="Deutschland-Karte mit Shift-Empfehlung"
          >
            <defs>
              <filter id="vex-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            {Object.entries(BL_PATHS).map(([code, { d }]) => {
              const isTarget = code === toCode;
              const isFrom = code === fromCode;
              return (
                <path
                  key={code}
                  d={d}
                  className={`vex-bl ${isTarget ? 'vex-bl-to' : ''} ${
                    isFrom ? 'vex-bl-from' : ''
                  }`}
                  filter={isTarget ? 'url(#vex-glow)' : undefined}
                />
              );
            })}
            {fromRegion && fromCode && BL_PATHS[fromCode] && toCode && BL_PATHS[toCode] && (
              <g className="vex-arrow-group">
                <line
                  x1={BL_PATHS[fromCode].cx}
                  y1={BL_PATHS[fromCode].cy}
                  x2={BL_PATHS[toCode].cx}
                  y2={BL_PATHS[toCode].cy}
                  className="vex-arrow"
                  strokeDasharray="6 4"
                />
                <circle
                  cx={BL_PATHS[toCode].cx}
                  cy={BL_PATHS[toCode].cy}
                  r="6"
                  className="vex-arrow-tip"
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
