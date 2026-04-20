import React, { useMemo } from 'react';
import type { CockpitSnapshot } from '../types';
import './variante-terminal.css';

interface Props {
  snapshot: CockpitSnapshot;
  virusTyp: string;
  onVirusChange: (v: string) => void;
  supportedViruses: readonly string[];
}

const fmtPct = (v: number | null | undefined, d = 1): string =>
  v == null ? '—' : `${(v * 100).toFixed(d)}%`;

const fmtDeltaMono = (v: number | null | undefined): string => {
  if (v == null) return '   —  ';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(1).padStart(5, ' ')}%`;
};

const decisionGlyph = (label: string | null | undefined): string => {
  switch (label) {
    case 'Activate':
      return '▲';
    case 'Prepare':
      return '◆';
    case 'Watch':
      return '·';
    case 'TrainingPending':
      return '○';
    default:
      return '·';
  }
};

const healthGlyph = (h: string): string => {
  if (h === 'good') return '●';
  if (h === 'warn') return '◐';
  return '○';
};

export const VarianteTerminal: React.FC<Props> = ({
  snapshot,
  virusTyp,
  onVirusChange,
  supportedViruses,
}) => {
  const rec = snapshot.primaryRecommendation;
  const ranked = useMemo(() => {
    return [...snapshot.regions].sort(
      (a, b) => (b.delta7d ?? -Infinity) - (a.delta7d ?? -Infinity),
    );
  }, [snapshot.regions]);

  const timelineForecast = useMemo(
    () => snapshot.timeline.filter((t) => t.q50 != null).slice(0, 14),
    [snapshot.timeline],
  );

  const now = new Date(snapshot.generatedAt);

  return (
    <div className="vtr-root">
      {/* ─── Status Bar (top) ─────────────────────────────────── */}
      <header className="vtr-statusbar">
        <div className="vtr-brand">
          <span className="vtr-brand-mark">◆</span>
          <span className="vtr-brand-name">FLUXENGINE</span>
          <span className="vtr-brand-mode">OPS-TERMINAL</span>
        </div>
        <div className="vtr-status-cells">
          <StatusCell label="VIRUS" value={virusTyp} />
          <StatusCell label="WEEK" value={snapshot.isoWeek} />
          <StatusCell
            label="READINESS"
            value={snapshot.modelStatus.forecastReadiness}
            tone="info"
          />
          <StatusCell
            label="LEAD"
            value={
              snapshot.modelStatus.bestLagDays != null
                ? `${snapshot.modelStatus.bestLagDays >= 0 ? '+' : ''}${snapshot.modelStatus.bestLagDays}d`
                : '—'
            }
          />
          <StatusCell
            label="CORR"
            value={(snapshot.modelStatus.correlationAtHorizon ?? 0).toFixed(3)}
          />
          <StatusCell
            label="GATE"
            value={snapshot.modelStatus.overallPassed ? 'PASS' : 'WATCH'}
            tone={snapshot.modelStatus.overallPassed ? 'pass' : 'warn'}
          />
          <StatusCell
            label="UPDATED"
            value={now.toLocaleTimeString('de-DE', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          />
        </div>
        <div className="vtr-virus-switch">
          {supportedViruses.map((v) => (
            <button
              key={v}
              type="button"
              className={`vtr-virus-btn ${v === virusTyp ? 'active' : ''}`}
              onClick={() => onVirusChange(v)}
            >
              {v}
            </button>
          ))}
        </div>
      </header>

      {/* ─── Main 4-pane grid ─────────────────────────────────── */}
      <main className="vtr-grid">
        {/* Q1 — Primary Shift (top-left, biggest) */}
        <section className="vtr-pane vtr-pane-shift">
          <PaneHeader label="SHIFT RECOMMENDATION" num="01" />
          {rec ? (
            <div className="vtr-shift-body">
              <div className="vtr-shift-direction">
                <div className="vtr-shift-from">
                  <div className="vtr-shift-code">{rec.fromCode}</div>
                  <div className="vtr-shift-name">{rec.fromName}</div>
                  <div className="vtr-shift-tag">TOP-FALLER</div>
                </div>
                <div className="vtr-shift-arrow">
                  <svg viewBox="0 0 100 30" width="100%" height="30">
                    <line
                      x1="4"
                      y1="15"
                      x2="86"
                      y2="15"
                      stroke="currentColor"
                      strokeWidth="1.2"
                      strokeDasharray="4 3"
                    />
                    <polygon
                      points="96,15 82,8 82,22"
                      fill="currentColor"
                    />
                  </svg>
                  <div className="vtr-shift-amount">
                    {rec.amountEur
                      ? `${(rec.amountEur / 1000).toFixed(0)}k €`
                      : 'BUDGET'}
                  </div>
                </div>
                <div className="vtr-shift-to">
                  <div className="vtr-shift-code">{rec.toCode}</div>
                  <div className="vtr-shift-name">{rec.toName}</div>
                  <div className="vtr-shift-tag active">TOP-RISER</div>
                </div>
              </div>
              <div className="vtr-shift-meta">
                <div className="vtr-shift-meta-row">
                  <span className="vtr-label">CONFIDENCE</span>
                  <ConfidenceBar value={rec.confidence ?? 0} />
                </div>
                <div className="vtr-shift-meta-row">
                  <span className="vtr-label">MODE</span>
                  <span className="vtr-mono">
                    {rec.signalMode ? 'SIGNAL · EUR pending plan' : 'CALIBRATED'}
                  </span>
                </div>
                <div className="vtr-shift-meta-row">
                  <span className="vtr-label">RATIONALE</span>
                  <span className="vtr-rationale">{rec.why}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="vtr-empty">
              <div className="vtr-empty-glyph">○</div>
              <div className="vtr-empty-text">
                NO SIGNAL THIS WEEK
                <br />
                <span className="vtr-empty-sub">
                  {snapshot.averageWaveProbabilityContext ??
                    'Signal below activation threshold.'}
                </span>
              </div>
            </div>
          )}
        </section>

        {/* Q2 — Regions ranked (right column, tall) */}
        <section className="vtr-pane vtr-pane-regions">
          <PaneHeader label="REGIONS · 7-DAY DELTA" num="02" count={ranked.length} />
          <div className="vtr-region-header">
            <span className="vtr-col-code">BL</span>
            <span className="vtr-col-name">NAME</span>
            <span className="vtr-col-delta">Δ7D</span>
            <span className="vtr-col-prising">p(↑)</span>
            <span className="vtr-col-decision">GATE</span>
          </div>
          <div className="vtr-region-list">
            {ranked.map((r) => {
              const isFrom = r.code === rec?.fromCode;
              const isTo = r.code === rec?.toCode;
              return (
                <div
                  key={r.code}
                  className={`vtr-region-row ${isFrom ? 'from' : ''} ${
                    isTo ? 'to' : ''
                  }`}
                >
                  <span className="vtr-col-code">{r.code}</span>
                  <span className="vtr-col-name">{r.name}</span>
                  <span
                    className={`vtr-col-delta ${
                      (r.delta7d ?? 0) > 0 ? 'up' : 'down'
                    }`}
                  >
                    {fmtDeltaMono(r.delta7d)}
                  </span>
                  <span className="vtr-col-prising">
                    {fmtPct(r.pRising, 0).padStart(4, ' ')}
                  </span>
                  <span className="vtr-col-decision">
                    {decisionGlyph(r.decisionLabel)} {r.decisionLabel}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        {/* Q3 — Forecast trajectory (bottom-left) */}
        <section className="vtr-pane vtr-pane-timeline">
          <PaneHeader label="NATIONAL TRAJECTORY · Q10/Q50/Q90" num="03" />
          <MiniForecast points={timelineForecast} />
          <div className="vtr-timeline-legend">
            <span>
              <span className="vtr-legend-dot q50" /> Q50 median
            </span>
            <span>
              <span className="vtr-legend-dot q-band" /> Q10–Q90 cone
            </span>
            <span className="vtr-legend-note">
              lead {snapshot.modelStatus.bestLagDays ?? '—'}d vs AKTIN · T+7
              interpolated
            </span>
          </div>
        </section>

        {/* Q4 — Drivers (bottom-middle) */}
        <section className="vtr-pane vtr-pane-drivers">
          <PaneHeader label="SIGNAL STACK" num="04" />
          <div className="vtr-driver-list">
            {snapshot.topDrivers.map((d) => (
              <div key={d.label} className="vtr-driver-row">
                <div className="vtr-driver-label">{d.label}</div>
                <div className="vtr-driver-value">{d.value}</div>
                <div className="vtr-driver-subtitle">{d.subtitle}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Q5 — Sources (bottom-right) */}
        <section className="vtr-pane vtr-pane-sources">
          <PaneHeader label="DATA SOURCES" num="05" count={snapshot.sources.length} />
          <div className="vtr-source-list">
            {snapshot.sources.map((s) => (
              <div key={s.name} className="vtr-source-row">
                <span className={`vtr-source-glyph vtr-source-${s.health}`}>
                  {healthGlyph(s.health)}
                </span>
                <span className="vtr-source-name">{s.name}</span>
                <span className="vtr-source-latency">
                  {s.latencyDays === 0 ? 'LIVE' : `${s.latencyDays}d`}
                </span>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* ─── Footer: model metrics ticker ────────────────────── */}
      <footer className="vtr-footer">
        <FooterMetric
          label="TRAIN"
          value={snapshot.modelStatus.trainingPanel?.maturityLabel ?? '—'}
        />
        <FooterMetric
          label="P@3"
          value={fmtPct(snapshot.modelStatus.ranking?.precisionAtTop3, 1)}
        />
        <FooterMetric
          label="PR-AUC"
          value={(snapshot.modelStatus.ranking?.prAuc ?? 0).toFixed(2)}
        />
        <FooterMetric
          label="ECE"
          value={(snapshot.modelStatus.ranking?.ece ?? 0).toFixed(3)}
        />
        <FooterMetric
          label="CAL"
          value={snapshot.modelStatus.calibrationMode?.toUpperCase() ?? 'UNKNOWN'}
        />
        <FooterMetric
          label="MEDIA-PLAN"
          value={snapshot.mediaPlan?.connected ? 'CONNECTED' : 'DISCONNECTED'}
          tone={snapshot.mediaPlan?.connected ? 'pass' : 'warn'}
        />
        <FooterMetric label="CLIENT" value={snapshot.client ?? '—'} />
        <div className="vtr-footer-pulse">● {now.toISOString().slice(0, 19)}Z</div>
      </footer>
    </div>
  );
};

// ══════════════════════════════════════════════════════════════════
//  Sub-components
// ══════════════════════════════════════════════════════════════════

const PaneHeader: React.FC<{ label: string; num: string; count?: number }> = ({
  label,
  num,
  count,
}) => (
  <div className="vtr-pane-header">
    <span className="vtr-pane-num">§{num}</span>
    <span className="vtr-pane-label">{label}</span>
    {count != null && <span className="vtr-pane-count">N={count}</span>}
  </div>
);

const StatusCell: React.FC<{
  label: string;
  value: string;
  tone?: 'info' | 'pass' | 'warn' | 'fail';
}> = ({ label, value, tone }) => (
  <div className={`vtr-status-cell ${tone ? `tone-${tone}` : ''}`}>
    <div className="vtr-status-label">{label}</div>
    <div className="vtr-status-value">{value}</div>
  </div>
);

const FooterMetric: React.FC<{
  label: string;
  value: string;
  tone?: 'pass' | 'warn' | 'fail';
}> = ({ label, value, tone }) => (
  <div className={`vtr-footer-metric ${tone ? `tone-${tone}` : ''}`}>
    <span className="vtr-footer-label">{label}</span>
    <span className="vtr-footer-value">{value}</span>
  </div>
);

const ConfidenceBar: React.FC<{ value: number }> = ({ value }) => {
  const pct = Math.round(value * 100);
  const filled = Math.round(pct / 5);
  const bar = '█'.repeat(filled) + '░'.repeat(20 - filled);
  return (
    <span className="vtr-confidence-bar">
      <span className="vtr-confidence-fill">{bar}</span>
      <span className="vtr-confidence-pct">{pct}%</span>
    </span>
  );
};

const MiniForecast: React.FC<{
  points: CockpitSnapshot['timeline'];
}> = ({ points }) => {
  if (points.length === 0)
    return <div className="vtr-empty-timeline">No forecast trajectory available.</div>;

  const W = 720;
  const H = 180;
  const pad = 24;
  const minY = Math.min(...points.map((p) => p.q10 ?? p.q50 ?? 0)) * 0.9;
  const maxY = Math.max(...points.map((p) => p.q90 ?? p.q50 ?? 1)) * 1.1;
  const scale = (v: number) =>
    H - pad - ((v - minY) / (maxY - minY)) * (H - 2 * pad);
  const xAt = (i: number) => pad + (i / (points.length - 1)) * (W - 2 * pad);

  const q50Path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${xAt(i)},${scale(p.q50 ?? 0)}`)
    .join(' ');

  const bandTop = points.map((p, i) => `${xAt(i)},${scale(p.q90 ?? p.q50 ?? 0)}`);
  const bandBot = points
    .map((p, i) => `${xAt(i)},${scale(p.q10 ?? p.q50 ?? 0)}`)
    .reverse();
  const bandPath = `M ${bandTop.join(' L ')} L ${bandBot.join(' L ')} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="vtr-mini-forecast">
      <path d={bandPath} className="vtr-q-band" />
      <path d={q50Path} className="vtr-q-median" fill="none" />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={xAt(i)}
          cy={scale(p.q50 ?? 0)}
          r="2"
          className="vtr-q-dot"
        />
      ))}
    </svg>
  );
};

export default VarianteTerminal;
