import React, { useEffect, useMemo, useState } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { NameType, ValueType } from 'recharts/types/component/DefaultTooltipContent';

import { OPERATOR_LABELS } from '../../constants/operatorLabels';
import {
  BacktestResponse,
  RegionalBacktestResponse,
  RegionalForecastPrediction,
  WaveRadarResponse,
} from '../../types/media';
import {
  VIRUS_OPTIONS,
  formatDateShort,
  formatDateTime,
  formatPercent,
} from './cockpitUtils';
import { OperatorStat } from './operator/OperatorPrimitives';
import HistoricalWaveMap from './HistoricalWaveMap';
import { sanitizeEvidenceCopy } from './evidence/evidenceUtils';
import {
  buildFocusRegionChartRows,
  buildUncertaintyText,
  buildValidationRows,
  buildWaveSpreadRows,
  describeForecastDelta,
  detectWaveMarkers,
  formatSampleCoverage,
  formatVirusLevel,
  getWaveFreshnessHint,
  isNumber,
  passStateLabel,
  readBooleanFlag,
  readNumberValue,
} from './backtestVisuals.utils';
import type {
  FocusRegionChartRow,
  ValidationRow,
  WaveMarkers,
  WaveSpreadRow,
} from './backtestVisuals.utils';

export { buildValidationRows, detectWaveMarkers, getWaveFreshnessHint } from './backtestVisuals.utils';

function chartLegendItem(label: string, swatch: React.CSSProperties, detail: string): React.JSX.Element {
  return (
    <div key={label} className="workspace-note-card backtest-note-card">
      <div className="backtest-note-card__head">
        <span aria-hidden="true" className="backtest-note-card__swatch" style={swatch} />
        <strong className="backtest-note-card__title">{label}</strong>
      </div>
      <div className="backtest-note-card__detail">
        {detail}
      </div>
    </div>
  );
}

function ChartSemanticsPanel({
  title = 'So liest du die Grafik',
  items,
  note,
}: {
  title?: string;
  items: Array<{ label: string; swatch: React.CSSProperties; detail: string }>;
  note?: string;
}) {
  return (
    <div className="workspace-note-list backtest-block-gap" aria-label={title}>
      <div className="workspace-note-card backtest-note-panel">
        <strong className="backtest-note-card__title">{title}</strong>
        <div className="backtest-semantics-grid">
          {items.map((item) => chartLegendItem(item.label, item.swatch, item.detail))}
        </div>
        {note ? (
          <div className="backtest-note-panel__note">
            {note}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ChartAxisHint({
  xLabel,
  yLabel,
}: {
  xLabel: string;
  yLabel: string;
}) {
  return (
    <div className="soft-panel backtest-axis-hint">
      <strong className="decision-inline-strong">Achsen-Hinweis:</strong> X-Achse = {xLabel}. Y-Achse = {yLabel}.
    </div>
  );
}

function renderChartTooltip({
  active,
  payload,
  label,
  title,
}: {
  active?: boolean;
  payload?: Array<{ name?: NameType; value?: ValueType | null; color?: string }>;
  label?: string;
  title?: string;
}) {
  if (!active || !payload?.length) return null;
  const visibleItems = payload.filter((entry) => entry.value != null && entry.value !== '');
  if (!visibleItems.length) return null;

  return (
    <div className="backtest-tooltip">
      <div className="backtest-tooltip__title">{title || 'Kurvenpunkt'}</div>
      <div className="backtest-tooltip__label">{label}</div>
        <div className="backtest-tooltip__list">
          {visibleItems.map((entry) => (
            <div key={`${String(entry.name)}-${String(entry.value)}`} className="backtest-tooltip__row">
              <span style={{ color: entry.color || '#bfdbfe' }}>{String(entry.name ?? '-')}</span>
              <strong>{typeof entry.value === 'number' ? formatVirusLevel(entry.value, 1) : String(entry.value)}</strong>
            </div>
          ))}
        </div>
      </div>
  );
}

interface WaveOutlookPanelProps {
  virus: string;
  onVirusChange: (value: string) => void;
  result: BacktestResponse | null;
  loading: boolean;
  showVirusSelector?: boolean;
  title?: string;
  subtitle?: string;
}

interface WaveSpreadPanelProps {
  virus: string;
  result: WaveRadarResponse | null;
  loading: boolean;
  title?: string;
  subtitle?: string;
}

interface FocusRegionOutlookPanelProps {
  prediction: RegionalForecastPrediction | null;
  backtest: RegionalBacktestResponse | null;
  loading: boolean;
  horizonDays: number;
  minimal?: boolean;
  title?: string;
  subtitle?: string;
}

export const FocusRegionOutlookPanel: React.FC<FocusRegionOutlookPanelProps> = ({
  prediction,
  backtest,
  loading,
  horizonDays,
  minimal = false,
  title,
  subtitle,
}) => {
  const rows = useMemo(() => buildFocusRegionChartRows(prediction, backtest), [prediction, backtest]);
  const regionName = prediction?.bundesland_name || backtest?.bundesland_name || 'deine Fokusregion';
  const currentDate = formatDateShort(prediction?.last_data_date || prediction?.as_of_date);
  const targetDate = formatDateShort(prediction?.target_date);
  const deltaText = describeForecastDelta(prediction);
  const uncertaintyText = buildUncertaintyText(prediction);
  const hasHistorical = rows.some((row) => isNumber(row.actual));
  const hasForecast = rows.some((row) => isNumber(row.forecast));
  const chartReady = rows.length >= 2 && (hasHistorical || hasForecast);
  const qualityGatePassed = readBooleanFlag(prediction?.quality_gate || null, ['overall_passed', 'passed']);
  const calibrationPassed = readBooleanFlag(prediction?.quality_gate || null, ['calibration_passed']);
  const sampleCoverage = readNumberValue(prediction?.source_coverage || null, ['sample_coverage_pct', 'coverage_pct', 'usable_source_share']);
  const panelTitle = title || (minimal ? 'Verlauf und 7-Tage-Fortführung' : 'Forecast zur Fokusregion');
  const panelSubtitle = subtitle || (minimal
    ? `Bestätigte Werte links, vermutete Fortführung für ${regionName} rechts.`
    : 'Das ist Support-Inhalt für die Wochenempfehlung auf Bundesland-Level. Wir trennen hier bewusst bestätigte Ist-Werte, Forecast und Unsicherheitsintervall.');

  if (loading) {
    return (
      <div className="card" style={{ padding: 20, color: 'var(--text-muted)' }}>
        Forecast zur Fokusregion wird geladen...
      </div>
    );
  }

  if (!prediction && !backtest?.timeline?.length) {
    return (
      <div className="card" style={{ padding: 20, display: 'grid', gap: 14 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>{panelTitle}</h2>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
            {minimal
              ? 'Sobald für das gewählte Bundesland Daten vorliegen, erscheint hier die Kurve mit Ist-Wert und 7-Tage-Fortführung.'
              : 'Hier würden wir den bestätigten Stand, den Forecast und den Unsicherheitskorridor als Support für die Wochenempfehlung getrennt zeigen.'}
          </p>
        </div>
        <div className="soft-panel" style={{ padding: 20, color: 'var(--text-muted)' }}>
          Noch kein aktiver Forecast oder regionaler Rückblick für dieses Bundesland verfügbar.
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>{panelTitle}</h2>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
            {panelSubtitle}
          </p>
        </div>
        <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-muted)' }}>
          {regionName}
        </div>
      </div>

      {!minimal ? (
        <>
          <div className="soft-panel" style={{ padding: 18, marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 18, lineHeight: 1.5, color: 'var(--text-primary)', fontWeight: 800 }}>
              {prediction
                ? `In ${horizonDays} Tagen erwarten wir für ${regionName} einen Viruslage-Wert von ca. ${formatVirusLevel(prediction.expected_target_incidence)}, also ${deltaText}.`
                : `Für ${regionName} können wir gerade noch keine klare ${horizonDays}-Tage-Aussage formulieren.`}
            </p>
            <p style={{ margin: '10px 0 0', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
              {prediction
                ? `Letzter bestätigter Ist-Wert vom ${currentDate}. Forecast-Ziel für ${targetDate}.`
                : 'Sobald ein frischer Forecast vorliegt, zeigen wir hier den Zieltag und den letzten bestätigten Stand.'}
            </p>
            <p style={{ margin: '8px 0 0', fontSize: 13, lineHeight: 1.6, color: 'var(--text-muted)' }}>
              {uncertaintyText}
            </p>
          </div>

          <div className="review-chip-row" style={{ marginBottom: 16 }}>
            <span className="step-chip">Bundesland-Level</span>
            <span className="step-chip">Kein {OPERATOR_LABELS.ranking_signal}</span>
            <span className="step-chip">Kein City-Forecast</span>
          </div>

          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', marginBottom: 16 }}>
            <div className="soft-panel" style={{ padding: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Fokusregion
              </div>
              <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
                {regionName}
              </div>
            </div>
            <div className="soft-panel" style={{ padding: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Letzter bestätigter Wert
              </div>
              <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: '#0a84ff' }}>
                {formatVirusLevel(prediction?.current_known_incidence)}
              </div>
            </div>
            <div className="soft-panel" style={{ padding: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Forecast-Ziel in {horizonDays} Tagen
              </div>
              <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: '#5e5ce6' }}>
                {formatVirusLevel(prediction?.expected_target_incidence)}
              </div>
            </div>
            <div className="soft-panel" style={{ padding: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Bandbreite
              </div>
              <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
                {isNumber(prediction?.prediction_interval?.lower) && isNumber(prediction?.prediction_interval?.upper)
                  ? `${formatVirusLevel(prediction?.prediction_interval?.lower)} bis ${formatVirusLevel(prediction?.prediction_interval?.upper)}`
                  : '-'}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', marginBottom: 16 }}>
            <div className="soft-panel" style={{ padding: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Quality Gate
              </div>
              <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
                {passStateLabel(qualityGatePassed)}
              </div>
            </div>
            <div className="soft-panel" style={{ padding: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Kalibrierung
              </div>
              <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
                {passStateLabel(calibrationPassed)}
              </div>
            </div>
            <div className="soft-panel" style={{ padding: 16 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Sample Coverage
              </div>
              <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
                {formatSampleCoverage(sampleCoverage)}
              </div>
            </div>
          </div>

          <ChartSemanticsPanel
            title="Chart-Konventionen Forecast"
            items={[
              {
                label: 'Truth / Ist-Wert',
                swatch: { background: '#0a84ff' },
                detail: 'Bestätigte Beobachtung. Das ist die sichtbare Wahrheit bis zum letzten bekannten Stand.',
              },
              {
                label: 'Forecast',
                swatch: { background: '#5e5ce6' },
                detail: 'Modellierter Zielwert. Das ist eine Erwartung, kein gemessener Ist-Wert.',
              },
              {
                label: 'Unsicherheitsintervall',
                swatch: { background: 'rgba(94,92,230,0.22)' },
                detail: 'Zeigt den möglichen Bereich um den Forecast. Breiteres Band bedeutet mehr Unsicherheit.',
              },
              {
                label: 'Forecast-Fenster',
                swatch: { background: 'rgba(94,92,230,0.08)', border: '1px dashed rgba(94,92,230,0.5)' },
                detail: 'Markiert den Abschnitt zwischen letztem bestätigtem Stand und Forecast-Ziel.',
              },
              {
                label: 'Fehlende Werte',
                swatch: { background: 'repeating-linear-gradient(45deg, rgba(148,163,184,0.2), rgba(148,163,184,0.2) 4px, rgba(255,255,255,0.8) 4px, rgba(255,255,255,0.8) 8px)' },
                detail: 'Wenn Punkte fehlen, bedeutet das fehlende Beobachtung oder fehlenden Modellwert, nicht Stabilität.',
              },
            ]}
            note={`${OPERATOR_LABELS.forecast_event_probability} und ${OPERATOR_LABELS.ranking_signal} bleiben bewusst außerhalb dieses Diagramms. Hier geht es nur um bestätigte Werte, Forecast und Unsicherheit.`}
          />
        </>
      ) : (
        <div className="soft-panel" style={{ padding: 16, marginBottom: 16, fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          {prediction
            ? `Letzter bestätigter Ist-Wert vom ${currentDate}. Forecast-Ziel für ${targetDate}. ${uncertaintyText}`
            : `Für ${regionName} liegt noch kein frischer 7-Tage-Forecast vor.`}
        </div>
      )}

      {chartReady ? (
        <div style={{ height: 400 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <defs>
                <linearGradient id="forecastGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="#4f46e5" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="actualGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0a84ff" stopOpacity={0.12} />
                  <stop offset="100%" stopColor="#0a84ff" stopOpacity={0.01} />
                </linearGradient>
                <filter id="forecastGlow">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.12)" vertical={false} />
              <XAxis dataKey="dateLabel" tick={{ fill: '#94a3b8', fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
              <Tooltip content={(props) => renderChartTooltip({ ...props, title: 'Fokusregion-Forecast' })} />

              {/* Forecast window — the "future zone" */}
              <ReferenceArea
                x1={formatDateShort(prediction?.last_data_date || prediction?.as_of_date)}
                x2={formatDateShort(prediction?.target_date)}
                fill="rgba(79, 70, 229, 0.06)"
                strokeOpacity={0}
              />

              {/* "Today" cliff edge — solid line, not dashed */}
              <ReferenceLine
                x={formatDateShort(prediction?.last_data_date || prediction?.as_of_date)}
                stroke="#4f46e5"
                strokeWidth={2}
                label={{ value: 'Heute', position: 'insideTopRight', fill: '#4f46e5', fontSize: 11, fontWeight: 600 }}
              />

              {/* Target date marker */}
              <ReferenceLine
                x={formatDateShort(prediction?.target_date)}
                stroke="#4f46e5"
                strokeDasharray="6 4"
                strokeWidth={1.5}
                label={{ value: `+${horizonDays}d`, position: 'insideTopRight', fill: '#4f46e5', fontSize: 11, fontWeight: 600 }}
              />

              {/* Uncertainty band — more visible */}
              <Area type="monotone" dataKey="bandBase" stackId="forecastBand" stroke="none" fill="transparent" activeDot={false} legendType="none" />
              <Area type="monotone" dataKey="bandRange" stackId="forecastBand" stroke="none" fill="rgba(79,70,229,0.14)" activeDot={false} name="Unsicherheitsintervall" />

              {/* Historical fill gradient */}
              <Area type="monotone" dataKey="actual" stroke="none" fill="url(#actualGradient)" activeDot={false} legendType="none" />

              {/* Lines — clear hierarchy */}
              <Line type="monotone" dataKey="actual" name="Ist-Wert" stroke="#0a84ff" strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="validated" name={`${horizonDays}d-Rückblick`} stroke="#94a3b8" strokeWidth={1.5} dot={false} strokeDasharray="5 4" />
              <Line type="monotone" dataKey="forecast" name={`${horizonDays}d-Forecast`} stroke="#4f46e5" strokeWidth={3.5} dot={false} filter="url(#forecastGlow)" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="soft-panel" style={{ padding: 20, color: 'var(--text-muted)' }}>
          {`Für die Fokusregion fehlen gerade ausreichende Verlaufsdaten. Die ${horizonDays}-Tage-Aussage oben bleibt sichtbar, die Grafik selbst bleibt absichtlich zurückhaltend.`}
        </div>
      )}

      {!minimal ? (
        <>
          <ChartAxisHint
            xLabel="Zeitpunkte vom letzten bestätigten Stand bis zum Forecast-Ziel"
            yLabel="Viruslage-Wert für das ausgewählte Bundesland"
          />

          <div className="workspace-note-list" style={{ marginTop: 16 }}>
            <div className="workspace-note-card">
              {`Bestätigte Daten links, Forecast rechts: So siehst du sofort, was schon beobachtet ist und was nur die ${horizonDays}-Tage-Erwartung des Modells ist.`}
            </div>
            {!backtest?.timeline?.length ? (
              <div className="workspace-note-card">
                Für den sauberen regionalen Rückblick fehlen gerade ausreichend historische Punkte. Deshalb zeigen wir den Fokus hier stärker über den aktuellen Forecast.
              </div>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
};

export const WaveOutlookPanel: React.FC<WaveOutlookPanelProps> = ({
  virus,
  onVirusChange,
  result,
  loading,
  showVirusSelector = true,
  title = 'Historischer Markt-Rückblick',
  subtitle,
}) => {
  const rows = useMemo(() => buildValidationRows(result, 36), [result]);
  const markers = useMemo(() => detectWaveMarkers(rows), [rows]);
  const freshnessHint = useMemo(() => getWaveFreshnessHint(rows, markers), [rows, markers]);
  const targetLabel = result?.target_label || result?.target_source || 'Market Check';
  const selectedVirus = result?.virus_typ || virus;
  const effectiveSubtitle = subtitle || `Hier siehst du den zuletzt validierten Verlauf für ${selectedVirus}. Diese Karte ist bewusst der zweite Blick: ein ehrlicher Rückblick bis zum letzten bestätigten Ist-Wert und kein Live-Ticker von heute.`;

  if (loading) {
    return (
      <div className="card" style={{ padding: 20, color: 'var(--text-muted)' }}>
        Validierte Marktansicht wird geladen...
      </div>
    );
  }

  if (rows.length < 4) {
    return (
      <div className="card" style={{ padding: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>{title}</h2>
        <div className="soft-panel" style={{ padding: 20, marginTop: 14, color: 'var(--text-muted)' }}>
          Noch keine ausreichend detaillierten Validierungsdaten für diese Rückblick-Kurve verfügbar.
        </div>
      </div>
    );
  }

  const startDate = rows[markers.startIndex]?.dateLabel || '-';
  const observedDate = rows[markers.lastObservedIndex]?.dateLabel || '-';
  const peakDate = rows[markers.peakIndex]?.dateLabel || '-';
  const cooldownDate = rows[markers.cooldownIndex]?.dateLabel || '-';

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, color: 'var(--text-primary)' }}>{title}</h2>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
            {effectiveSubtitle}
          </p>
        </div>
        <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-muted)' }}>
          {targetLabel}
        </div>
      </div>

      {showVirusSelector ? (
        <div className="review-chip-row" style={{ marginBottom: 16 }}>
          {VIRUS_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onVirusChange(option)}
              className={`tab-chip ${option === selectedVirus ? 'active' : ''}`}
            >
              {option}
            </button>
          ))}
        </div>
      ) : null}

      <ChartSemanticsPanel
        title="Chart-Konventionen Markt-Rückblick"
        items={[
          {
            label: 'Truth / Ist-Wert',
            swatch: { background: '#0a84ff' },
            detail: 'Tatsächlich beobachteter Verlauf bis zum letzten bestätigten Stand.',
          },
          {
            label: 'Validierte Prognose',
            swatch: { background: '#475569', border: '1px dashed rgba(71,85,105,0.7)' },
            detail: 'Historisch gegen echte Werte geprüfter Modellverlauf, nicht der aktuelle Live-Forecast.',
          },
          {
            label: 'Forecast / Ausblick',
            swatch: { background: '#5e5ce6' },
            detail: 'Nur falls im validierten Lauf bereits vorausgerechnete Punkte vorliegen.',
          },
          {
            label: 'Unsicherheitsintervall',
            swatch: { background: 'rgba(59,130,246,0.18)' },
            detail: 'Zeigt die Bandbreite des Modells. Ein breites Band bedeutet: Richtung okay, Höhe unsicherer.',
          },
          {
            label: 'Fehlende Werte',
            swatch: { background: 'repeating-linear-gradient(45deg, rgba(148,163,184,0.2), rgba(148,163,184,0.2) 4px, rgba(255,255,255,0.8) 4px, rgba(255,255,255,0.8) 8px)' },
            detail: 'Leerstellen bedeuten fehlende Beobachtung oder unbelegte Slots, nicht automatisch Ruhe.',
          },
        ]}
        note={`${OPERATOR_LABELS.ranking_signal} und ${OPERATOR_LABELS.forecast_event_probability} werden hier nicht gemischt. Diese Grafik zeigt nur den validierten Verlauf und seine Unsicherheit.`}
      />

      <div className="soft-panel" style={{ padding: 16, marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
        Die markierten Punkte helfen dir, den Start, den letzten bestätigten Stand und den im validierten Lauf sichtbar gewordenen Höhepunkt schnell zu erkennen.
      </div>

      {freshnessHint && (
        <div className="soft-panel" style={{ padding: 16, marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
          {freshnessHint}
        </div>
      )}

      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', marginBottom: 16 }}>
        {[
          { label: 'Welle beginnt', value: startDate, tone: '#2aa198' },
          { label: 'Letzter Ist-Wert', value: observedDate, tone: '#0a84ff' },
          { label: 'Erwarteter Peak', value: peakDate, tone: '#ff453a' },
          { label: 'Rückgang', value: cooldownDate, tone: '#ff9f0a' },
        ].map((item) => (
          <div key={item.label} className="soft-panel" style={{ padding: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              {item.label}
            </div>
            <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: item.tone }}>
              {item.value}
            </div>
          </div>
        ))}
      </div>

      <div style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.22)" />
              <XAxis dataKey="dateLabel" tick={{ fill: '#64748b', fontSize: 11 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
              <Tooltip content={(props) => renderChartTooltip({ ...props, title: 'Markt-Rückblick' })} />
              <Legend />

            <ReferenceArea
              x1={rows[markers.lastObservedIndex]?.dateLabel}
              x2={rows[markers.lastValuedIndex]?.dateLabel || rows[markers.lastObservedIndex]?.dateLabel}
              fill="rgba(10, 132, 255, 0.06)"
            />
            <ReferenceLine x={rows[markers.startIndex]?.dateLabel} stroke="#2aa198" strokeDasharray="4 4" label={{ value: 'Beginn', position: 'top', fill: '#2aa198', fontSize: 10 }} />
            <ReferenceLine x={rows[markers.lastObservedIndex]?.dateLabel} stroke="#0a84ff" strokeDasharray="4 4" label={{ value: 'Ist-Wert', position: 'top', fill: '#0a84ff', fontSize: 10 }} />
            <ReferenceLine x={rows[markers.peakIndex]?.dateLabel} stroke="#ff453a" strokeDasharray="4 4" label={{ value: 'Peak', position: 'top', fill: '#ff453a', fontSize: 10 }} />

            <Area type="linear" dataKey="ci95Base" stackId="ci95" stroke="none" fill="transparent" activeDot={false} legendType="none" />
            <Area type="linear" dataKey="ci95Range" stackId="ci95" stroke="none" fill="rgba(59,130,246,0.08)" activeDot={false} legendType="none" />
            <Area type="linear" dataKey="ci80Base" stackId="ci80" stroke="none" fill="transparent" activeDot={false} legendType="none" />
            <Area type="linear" dataKey="ci80Range" stackId="ci80" stroke="none" fill="rgba(59,130,246,0.18)" activeDot={false} legendType="none" />

            <Line type="linear" dataKey="actual" name="Truth / Ist-Wert" stroke="#0a84ff" strokeWidth={2.5} dot={false} />
            <Line type="linear" dataKey="model" name="Validierte Prognose" stroke="#475569" strokeWidth={1.8} dot={false} strokeDasharray="5 4" />
            <Line type="linear" dataKey="forecast" name="Forecast / Ausblick" stroke="#5e5ce6" strokeWidth={2.8} dot={false} />
            <Line type="linear" dataKey="seasonal" name="Saison-Baseline" stroke="#ff9f0a" strokeWidth={1.6} dot={false} strokeDasharray="3 3" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <ChartAxisHint
        xLabel="kalibrierte Beobachtungs- und Forecast-Zeitpunkte"
        yLabel="Markt- oder Signalhöhe im validierten Verlauf"
      />

      <p style={{ margin: '14px 0 0', fontSize: 14, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
        {markers.narrative}
      </p>
      <p style={{ margin: '8px 0 0', fontSize: 12, lineHeight: 1.6, color: 'var(--text-muted)' }}>
        Diese Kurve bleibt bewusst rückblick-orientiert. Für den aktuellen Arbeitsstand solltest du immer zusätzlich auf den frischen Planungsausblick schauen.
      </p>
    </div>
  );
};

export const WaveSpreadPanel: React.FC<WaveSpreadPanelProps> = ({
  virus,
  result,
  loading,
  title = 'Historische Ausbreitungsreihenfolge',
  subtitle,
}) => {
  const rows = useMemo(() => buildWaveSpreadRows(result), [result]);
  const [selectedBundesland, setSelectedBundesland] = useState<string | null>(null);
  const summary = result?.summary;
  const firstOnset = summary?.first_onset;
  const lastOnset = summary?.last_onset;
  const firstDateLabel = formatDateShort(firstOnset?.date);
  const lastDateLabel = formatDateShort(lastOnset?.date);
  const affectedRegions = Number(summary?.regions_affected ?? rows.length);
  const totalRegions = Number(summary?.regions_total ?? 16);
  const spreadDays = Number(summary?.spread_days ?? 0);
  const maxOffset = Math.max(spreadDays, ...rows.map((row) => row.offsetDays), 1);
  const effectiveSubtitle = subtitle || `So sah die Ausbreitung von ${virus} in der zuletzt verfügbaren Saison aus. Diese Ansicht ist bewusst Hintergrund für den zweiten Blick und kein Live-Forecast für heute.`;
  const defaultBundesland = firstOnset?.bundesland || rows[0]?.bundesland || null;
  const selectedRegion = useMemo(
    () => (result?.regions || []).find((region) => region.bundesland === selectedBundesland) || null,
    [result, selectedBundesland],
  );
  const selectedRank = Number(selectedRegion?.wave_rank || 0);
  const selectedThreshold = selectedRegion?.threshold != null ? formatVirusLevel(selectedRegion.threshold, 1) : '-';
  const selectedPeak = selectedRegion?.peak_incidence != null ? formatVirusLevel(selectedRegion.peak_incidence, 1) : '-';

  useEffect(() => {
    setSelectedBundesland(defaultBundesland);
  }, [defaultBundesland]);

  if (loading) {
    return (
      <div className="card" style={{ padding: 20, color: 'var(--text-muted)' }}>
        Historische Ausbreitung wird geladen...
      </div>
    );
  }

  if (!rows.length || result?.error) {
    return (
      <div className="card backtest-card">
        <h2 className="backtest-card__title">{title}</h2>
        <div className="soft-panel backtest-empty-panel">
          Für diese historische Ausbreitung liegen gerade nicht genug regionale Daten vor.
        </div>
      </div>
    );
  }

  return (
    <div className="card backtest-card">
      <div className="backtest-card__header">
        <div>
          <h2 className="backtest-card__title">{title}</h2>
          <p className="backtest-card__subtitle">
            {effectiveSubtitle}
          </p>
        </div>
        <div className="backtest-card__meta">
          Saison {result?.season || '-'}
        </div>
      </div>

      <div className="soft-panel backtest-story-panel">
        <p className="backtest-story-panel__lead">
          {firstOnset?.bundesland
            ? `${firstOnset.bundesland} war in der letzten verfügbaren Saison der erste sichtbare Startpunkt. Von dort breitete sich die Welle innerhalb von ${spreadDays} Tagen bis zur letzten erfassten Region aus.`
            : 'Der erste regionale Startpunkt ist für diese Saison noch nicht eindeutig sichtbar.'}
        </p>
        <p className="backtest-story-panel__body">
          {lastOnset?.bundesland
            ? `Erster Start am ${firstDateLabel}, letzter späterer Start in ${lastOnset.bundesland} am ${lastDateLabel}.`
            : `Erster sichtbarer Start am ${firstDateLabel}.`}
        </p>
        <p className="backtest-story-panel__note">
          Diese Karte zeigt die zuletzt verfügbare historische Saison und hilft dir, die typische Reihenfolge besser einzuordnen. Sie ersetzt nicht den aktuellen Forecast.
        </p>
      </div>

      <div className="backtest-stat-grid">
        <div className="soft-panel backtest-stat-card">
          <div className="backtest-stat-card__label">
            Erster Start
          </div>
          <div className="backtest-stat-card__value backtest-stat-card__value--teal">
            {firstOnset?.bundesland || '-'}
          </div>
          <div className="backtest-stat-card__meta">
            {firstDateLabel}
          </div>
        </div>
        <div className="soft-panel backtest-stat-card">
          <div className="backtest-stat-card__label">
            Letzter Start
          </div>
          <div className="backtest-stat-card__value backtest-stat-card__value--amber">
            {lastOnset?.bundesland || '-'}
          </div>
          <div className="backtest-stat-card__meta">
            {lastDateLabel}
          </div>
        </div>
        <div className="soft-panel backtest-stat-card">
          <div className="backtest-stat-card__label">
            Ausbreitungsdauer
          </div>
          <div className="backtest-stat-card__value backtest-stat-card__value--violet">
            {`${spreadDays} Tage`}
          </div>
        </div>
        <div className="soft-panel backtest-stat-card">
          <div className="backtest-stat-card__label">
            Betroffene Regionen
          </div>
          <div className="backtest-stat-card__value">
            {`${affectedRegions}/${totalRegions}`}
          </div>
        </div>
      </div>

      <div className="backtest-map-grid">
        <div className="soft-panel backtest-map-panel">
          <div className="backtest-map-panel__hint">
            Deutschlandkarte der historischen Startreihenfolge. Je früher ein Bundesland gestartet ist, desto stärker ist es eingefärbt.
          </div>
          <HistoricalWaveMap
            result={result}
            selectedBundesland={selectedBundesland}
            onSelectBundesland={setSelectedBundesland}
          />
        </div>

        <div className="soft-panel backtest-region-panel">
          <div className="backtest-stat-card__label">
            Ausgewählte Region
          </div>
          <div className="backtest-region-panel__title">
            {selectedBundesland || firstOnset?.bundesland || '-'}
          </div>
          <p className="backtest-region-panel__body">
            {selectedRegion?.wave_rank
              ? `${selectedBundesland} lag in dieser Saison auf Rang ${selectedRank} der sichtbaren Ausbreitung.`
              : `${selectedBundesland || 'Diese Region'} hat in dieser Saison keinen klaren Wellenstart über der gewählten Schwelle gezeigt.`}
          </p>

          <div className="operator-stat-grid">
            <OperatorStat
              label="Historischer Rang"
              value={selectedRegion?.wave_rank ? `#${selectedRank}` : '-'}
              meta={selectedRegion?.wave_start ? formatDateShort(selectedRegion.wave_start) : 'kein klarer Start'}
              tone="accent"
            />
            <OperatorStat
              label="Peak-Woche"
              value={selectedRegion?.peak_week || '-'}
              meta={selectedPeak !== '-' ? `Peak ${selectedPeak}` : 'keine Peak-Angabe'}
            />
            <OperatorStat
              label="Schwelle"
              value={selectedThreshold}
              meta="historischer Startwert"
            />
            <OperatorStat
              label="Datenpunkte"
              value={selectedRegion?.data_points != null ? String(selectedRegion.data_points) : '-'}
              meta="Wochen in der Saison"
            />
          </div>
        </div>
      </div>

      <div className="workspace-note-list">
        {rows.map((row) => (
          <div key={`${row.rank}-${row.bundesland}`} className="soft-panel backtest-rank-card">
            <div className="backtest-rank-card__head">
              <div className="backtest-rank-card__identity">
                <span className="backtest-rank-card__rank">
                  #{row.rank}
                </span>
                <span className="backtest-rank-card__name">
                  {row.bundesland}
                </span>
              </div>
              <span className="backtest-rank-card__date">
                {row.dateLabel}
              </span>
            </div>
            <div className="backtest-rank-card__bar">
              <div
                style={{
                  height: '100%',
                  width: `${Math.max((row.offsetDays / maxOffset) * 100, 10)}%`,
                  borderRadius: 999,
                  background: row.offsetDays === 0
                    ? 'linear-gradient(90deg, #2aa198 0%, #4fd1c5 100%)'
                    : 'linear-gradient(90deg, #5e5ce6 0%, #0a84ff 100%)',
                }}
              />
            </div>
            <div className="backtest-rank-card__note">
              {row.offsetDays === 0
                ? 'Hier begann die Welle in dieser Saison zuerst.'
                : `${row.offsetDays} Tage nach dem ersten Start sichtbar geworden.`}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

interface ValidationSectionProps {
  title: string;
  subtitle: string;
  result: BacktestResponse | null;
  loading: boolean;
  emptyMessage: string;
}

export const ValidationSection: React.FC<ValidationSectionProps> = ({
  title,
  subtitle,
  result,
  loading,
  emptyMessage,
}) => {
  const rows = useMemo(() => buildValidationRows(result, 72), [result]);
  const hasBio = rows.some((row) => isNumber(row.bio));
  const chartReady = rows.some((row) => isNumber(row.actual) || isNumber(row.model));
  const decisionMetrics = result?.decision_metrics;
  const metrics = result?.metrics;
  const qualityGatePassed = Boolean(result?.quality_gate?.overall_passed);
  const thresholdLabel = result?.decision_metrics?.event_threshold_pct != null
    ? formatPercent(result.decision_metrics.event_threshold_pct, 0)
    : '-';
  const missingRows = rows.filter((row) => !isNumber(row.actual) && !isNumber(row.model) && !isNumber(row.forecast)).length;

  return (
    <div className="card backtest-card backtest-card--compact">
      <div className="backtest-card__header">
        <div>
          <h2 className="backtest-card__title">{title}</h2>
          <p className="backtest-card__subtitle">{subtitle}</p>
        </div>
        <div className="backtest-card__meta">
          {result?.created_at ? formatDateTime(result.created_at) : '-'}
        </div>
      </div>

      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
        <div className="metric-box">
          <span>R²</span>
          <strong>{metrics?.r2_score != null ? metrics.r2_score.toFixed(2) : '-'}</strong>
        </div>
        <div className="metric-box">
          <span>Korrelation</span>
          <strong>{formatPercent((metrics?.correlation_pct ?? ((metrics?.correlation ?? 0) * 100)) as number)}</strong>
        </div>
        <div className="metric-box">
          <span>Datenpunkte</span>
          <strong>{metrics?.data_points ?? rows.length}</strong>
        </div>
        {decisionMetrics ? (
          <div className="metric-box">
            <span>Trefferquote</span>
            <strong>{formatPercent(decisionMetrics.hit_rate_pct || 0)}</strong>
          </div>
        ) : (
          <div className="metric-box">
            <span>Abweichung (sMAPE)</span>
            <strong>{metrics?.smape != null ? `${metrics.smape.toFixed(1)}%` : '-'}</strong>
          </div>
        )}
      </div>

      <div className="review-chip-row">
        <span className="step-chip">Quality Gate: {qualityGatePassed ? 'erfüllt' : 'beobachten'}</span>
        <span className="step-chip">Action Line: {thresholdLabel}</span>
        <span className="step-chip">Fehlende Punkte: {missingRows}</span>
      </div>

      <ChartSemanticsPanel
        title="Chart-Konventionen Validierung"
        items={[
          {
            label: 'Truth / Ist',
            swatch: { background: '#0a84ff' },
            detail: 'Gemessener Verlauf. Daran prüfen wir das Modell.',
          },
          {
            label: 'Forecast / Modell',
            swatch: { background: '#5e5ce6' },
            detail: 'Modellierter Verlauf. Er wird gegen Truth verglichen und nicht als Tatsache gelesen.',
          },
          {
            label: 'Unsicherheitsband',
            swatch: { background: 'rgba(59,130,246,0.18)' },
            detail: 'Zeigt die Bandbreite des Modells. Breiter bedeutet unsicherer.',
          },
          {
            label: 'Action Line / Schwelle',
            swatch: { background: '#ef4444' },
            detail: 'Operative Schwelle aus dem Quality Gate, falls vorhanden. Sie ist keine Forecast-Linie.',
          },
          {
            label: 'Missing Data',
            swatch: { background: 'repeating-linear-gradient(45deg, rgba(148,163,184,0.2), rgba(148,163,184,0.2) 4px, rgba(255,255,255,0.8) 4px, rgba(255,255,255,0.8) 8px)' },
            detail: 'Fehlende Daten bedeuten Lücke, nicht automatisch Null oder Stabilität.',
          },
        ]}
        note={`${OPERATOR_LABELS.forecast_event_probability} und ${OPERATOR_LABELS.ranking_signal} sind absichtlich nicht Teil dieser Validierungskurve.`}
      />

      {loading ? (
        <div className="soft-panel backtest-empty-panel backtest-empty-panel--lg">
          Validierungsdaten werden geladen...
        </div>
      ) : chartReady ? (
        <div style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.22)" />
              <XAxis dataKey="dateLabel" tick={{ fill: '#64748b', fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fill: '#64748b', fontSize: 11 }} />
              {hasBio && <YAxis yAxisId="right" orientation="right" tick={{ fill: '#64748b', fontSize: 11 }} />}
              <Tooltip content={(props) => renderChartTooltip({ ...props, title })} />
              <Legend />

              {result?.decision_metrics?.event_threshold_pct != null ? (
                <ReferenceLine
                  yAxisId="left"
                  y={result.decision_metrics.event_threshold_pct}
                  stroke="#ef4444"
                  strokeDasharray="4 4"
                  label={{ value: 'Action Line', position: 'insideTopRight', fill: '#ef4444', fontSize: 10 }}
                />
              ) : null}

              <Area yAxisId="left" type="linear" dataKey="ci95Base" stackId="ci95" stroke="none" fill="transparent" activeDot={false} legendType="none" />
              <Area yAxisId="left" type="linear" dataKey="ci95Range" stackId="ci95" stroke="none" fill="rgba(59,130,246,0.08)" activeDot={false} legendType="none" />
              <Area yAxisId="left" type="linear" dataKey="ci80Base" stackId="ci80" stroke="none" fill="transparent" activeDot={false} legendType="none" />
              <Area yAxisId="left" type="linear" dataKey="ci80Range" stackId="ci80" stroke="none" fill="rgba(59,130,246,0.18)" activeDot={false} name="Unsicherheitsband" />

              <Line yAxisId="left" type="linear" dataKey="actual" name="Truth / Ist" stroke="#0a84ff" strokeWidth={2.5} dot={false} />
              <Line yAxisId="left" type="linear" dataKey="model" name="Forecast / Modell" stroke="#5e5ce6" strokeWidth={2.2} dot={false} />
              <Line yAxisId="left" type="linear" dataKey="seasonal" name="Saison-Baseline" stroke="#ff9f0a" strokeWidth={1.6} dot={false} strokeDasharray="3 3" />
              <Line yAxisId="left" type="linear" dataKey="persistence" name="Persistenz-Basis" stroke="#64748b" strokeWidth={1.4} dot={false} strokeDasharray="3 3" />
              {hasBio && <Line yAxisId="right" type="linear" dataKey="bio" name={`${OPERATOR_LABELS.ranking_signal} (getrennte Achse)`} stroke="#7c3aed" strokeWidth={1.8} dot={false} />}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="soft-panel backtest-empty-panel backtest-empty-panel--lg">
          {emptyMessage}
        </div>
      )}

      <ChartAxisHint
        xLabel="validierte Zeitpunkte im Rückblicktest"
        yLabel={hasBio ? `Truth und Forecast links, ${OPERATOR_LABELS.ranking_signal} rechts` : 'Truth und Forecast'}
      />

      {(result?.proof_text || result?.llm_insight) && (
        <div className="soft-panel backtest-proof-panel">
          <div className="backtest-proof-panel__label">Einordnung</div>
          <div className="backtest-proof-panel__body">
            {sanitizeEvidenceCopy(result?.proof_text || result?.llm_insight)}
          </div>
        </div>
      )}
    </div>
  );
};
