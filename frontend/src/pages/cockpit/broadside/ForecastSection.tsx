import React, { useMemo, useState } from 'react';
import type { CockpitSnapshot, TimelinePoint } from '../types';
import SectionHeader from './SectionHeader';
import type { GateTone } from './SectionHeader';
// useCockpitSnapshot removed 2026-04-20 — virus is globally managed.
import { useBacktest } from '../useBacktest';
import {
  useForecastVintage,
  type VintageRun,
} from '../useForecastVintage';
import type { BacktestPayload } from '../backtestTypes';
import EphemerisFoot, { type EphemerisRowData } from './EphemerisFoot';
import { deriveForecastLeadHero } from './forecastLeadHero';

/**
 * § III — Forecast-Zeitreise.
 *
 * Instrumentation-Redesign v4 (2026-04-18): "Strip-Chart Recorder".
 *
 * Ein dreikanaliger Lab-Streifenschreiber. Papier feedet von links
 * (Vergangenheit) nach rechts (Zukunft). Drei parallele Kanäle mit
 * eigenen Skalen — kein Fan-Chart, keine geteilte Y-Achse:
 *
 *   CH.01  ED · NOTAUFNAHMEN    Lead-Indikator (tagesaktuell)
 *   CH.02  SURVSTAT · MELDEWESEN  Referenz-Pegel (verzögert)
 *   CH.03  MODELL · Q-QUANTILE    Forecast-Kegel (Q10/Q50/Q90)
 *
 * Oberhalb der drei Kanäle: eine Chronologie-Timeline mit vier
 * Event-Dots (ED-Peak · SURV-Peak · HEUTE · Q50-Horizont) — die
 * narrative Vor-Lesung bevor der Leser die Wellenformen sieht.
 *
 * HEUTE ist kein vertikaler Strich, sondern ein PAPIER-ÜBERGANG:
 * links "bedrucktes Papier" (paper, cool cream), rechts "frisches
 * Papier" (paper-warm, wärmer) — getrennt durch eine 1 px Ink-Naht.
 *
 * Der Lead-Zeit-Beweis ist visuell: die ED-Spur in Kanal 01 endet
 * SPÄTER als die SURVSTAT-Spur in Kanal 02. Die Lücke in Kanal 02
 * — zwischen SURVSTAT's Ende und HEUTE — ist der operationale
 * Lead. Proof by Gap, nicht durch Math-Claim.
 *
 * Q90-Plateau-Artefakte werden NICHT kaschiert — der Fan-Kegel
 * zeigt sie ehrlich als horizontale Obergrenze. Falls das Modell
 * ein Plateau liefert (bekanntes Symptom), steht es da.
 *
 * Unten: Ephemeris-Foot mit Lead-Time-Hero (+N TAGE, Supreme Thin)
 * und zweispaltigem Meta-Table (OBSERVED / FORECAST).
 */

interface Props {
  snapshot: CockpitSnapshot;
}

// -----------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------

function getISOWeek(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
}

function polyline(pts: Array<[number, number]>): string {
  if (pts.length < 2) return '';
  return `M ${pts[0][0]},${pts[0][1]}` +
    pts.slice(1).map(([x, y]) => ` L ${x},${y}`).join('');
}

function area(pts: Array<[number, number]>, baselineY: number): string {
  if (pts.length < 2) return '';
  const first = pts[0][0];
  const last = pts[pts.length - 1][0];
  return `${polyline(pts)} L ${last},${baselineY} L ${first},${baselineY} Z`;
}

// Cardinal spline for smoother forecast bands — tighter tension than defaults.
function spline(pts: Array<[number, number]>): string {
  if (pts.length < 2) return '';
  if (pts.length === 2) return `M ${pts[0][0]},${pts[0][1]} L ${pts[1][0]},${pts[1][1]}`;
  const t = 0.5;
  const out: string[] = [`M ${pts[0][0]},${pts[0][1]}`];
  for (let i = 0; i < pts.length - 1; i += 1) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const c1x = p1[0] + ((p2[0] - p0[0]) / 6) * t * 2;
    const c1y = p1[1] + ((p2[1] - p0[1]) / 6) * t * 2;
    const c2x = p2[0] - ((p3[0] - p1[0]) / 6) * t * 2;
    const c2y = p2[1] - ((p3[1] - p1[1]) / 6) * t * 2;
    out.push(`C ${c1x},${c1y} ${c2x},${c2y} ${p2[0]},${p2[1]}`);
  }
  return out.join(' ');
}

function splineBand(lower: Array<[number, number]>, upper: Array<[number, number]>): string {
  if (lower.length < 2 || upper.length < 2) return '';
  const up = spline(upper);
  const low = [...lower].reverse();
  const downPath = spline(low).replace(/^M /, ' L ');
  return `${up}${downPath} Z`;
}

// -----------------------------------------------------------------
// Strip Chart Recorder
// -----------------------------------------------------------------

interface ChartProps {
  timeline: TimelinePoint[];
  vintageRuns?: VintageRun[];
  showVintage?: boolean;
}

interface ChartSeries {
  // Index in points array, value
  pts: Array<{ i: number; v: number }>;
  peakIdx: number | null;
  peakValue: number;
  lastIdx: number | null;
}

function buildSeries(
  points: TimelinePoint[],
  accessor: (p: TimelinePoint) => number | null,
): ChartSeries {
  const pts = points
    .map((p, i) => ({ i, v: accessor(p) }))
    .filter((d): d is { i: number; v: number } =>
      d.v !== null && Number.isFinite(d.v),
    );
  if (pts.length === 0) {
    return { pts: [], peakIdx: null, peakValue: 0, lastIdx: null };
  }
  let peakIdx = pts[0].i;
  let peakValue = pts[0].v;
  pts.forEach((d) => {
    if (d.v > peakValue) { peakValue = d.v; peakIdx = d.i; }
  });
  return { pts, peakIdx, peakValue, lastIdx: pts[pts.length - 1].i };
}

const StripChart: React.FC<ChartProps> = ({ timeline, vintageRuns = [], showVintage = false }) => {
  const points = useMemo(() => timeline ?? [], [timeline]);

  if (points.length === 0) {
    return (
      <div className="strip-empty">
        Kein Forecast-Verlauf angebunden — Timeline leer.
      </div>
    );
  }

  // ---- Canvas geometry ------------------------------------------
  const W = 1400;
  const H = 760;
  const PAD_L = 148;
  const PAD_R = 72;
  const PAD_T = 96;   // Chronologie-Timeline lebt hier
  const PAD_B = 72;   // KW-Labels leben hier
  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;
  const chGap = 32;
  const chH = (plotH - chGap * 2) / 3;

  const ch1Top = PAD_T;
  const ch1Base = ch1Top + chH;
  const ch2Top = ch1Base + chGap;
  const ch2Base = ch2Top + chH;
  const ch3Top = ch2Base + chGap;
  const ch3Base = ch3Top + chH;

  // ---- Time & series --------------------------------------------
  const xN = points.length;

  // Compute effective date-range. When vintage-overlay is on, extend the
  // x-axis to the left so past run dates become visible — das ist der
  // eigentliche "Reise"-Aspekt: Blick in ältere Forecast-Stände.
  const tsTimeline = points.map((p) => new Date(p.date).getTime());
  let effTStart = Math.min(...tsTimeline);
  let effTEnd = Math.max(...tsTimeline);
  if (showVintage && vintageRuns.length > 0) {
    const tsVintage = vintageRuns.flatMap((r) =>
      r.points.map((p) => new Date(p.date).getTime()),
    );
    if (tsVintage.length > 0) {
      effTStart = Math.min(effTStart, ...tsVintage);
      effTEnd = Math.max(effTEnd, ...tsVintage);
    }
  }
  const effTRange = Math.max(effTEnd - effTStart, 86_400_000);

  const sxDate = (dateStrOrNum: string | number): number => {
    const t =
      typeof dateStrOrNum === 'number'
        ? dateStrOrNum
        : new Date(dateStrOrNum).getTime();
    return PAD_L + ((t - effTStart) / effTRange) * plotW;
  };
  const sx = (i: number) => sxDate(points[i].date);

  const edSeries = buildSeries(points, (p) => p.edActivity);
  const survSeries = buildSeries(points, (p) => p.observed);

  // HEUTE = letzter ED-Punkt (der schnellere Sensor).
  // Fallback: letzter SURVSTAT-Punkt. Fallback: Mitte.
  let todayIdx = edSeries.lastIdx ?? survSeries.lastIdx ?? Math.floor(xN / 2);

  // Forecast: Q-Werte ab HEUTE. Anchor Index = Q50 am HEUTE-Punkt (oder nahester).
  let fcAnchorIdx = todayIdx;
  if (points[fcAnchorIdx]?.q50 === null) {
    for (let d = 1; d < points.length; d += 1) {
      if (fcAnchorIdx + d < points.length && points[fcAnchorIdx + d]?.q50 !== null) {
        fcAnchorIdx += d; break;
      }
      if (fcAnchorIdx - d >= 0 && points[fcAnchorIdx - d]?.q50 !== null) {
        fcAnchorIdx -= d; break;
      }
    }
  }
  const fcAnchor = points[fcAnchorIdx]?.q50 ?? 0;

  const fcPts = points
    .map((p, i) => ({
      i,
      q10: p.q10 !== null && Number.isFinite(p.q10) && fcAnchor
        ? (p.q10 / fcAnchor) * 100 : null,
      q50: p.q50 !== null && Number.isFinite(p.q50) && fcAnchor
        ? (p.q50 / fcAnchor) * 100 : null,
      q90: p.q90 !== null && Number.isFinite(p.q90) && fcAnchor
        ? (p.q90 / fcAnchor) * 100 : null,
    }))
    .filter((p) => p.i >= todayIdx && p.q50 !== null);

  // ---- Per-channel Y-Scales -------------------------------------
  const syED = (val: number) =>
    ch1Base - (edSeries.peakValue > 0 ? (val / edSeries.peakValue) : 0) * chH * 0.82;
  const sySurv = (val: number) =>
    ch2Base - (survSeries.peakValue > 0 ? (val / survSeries.peakValue) : 0) * chH * 0.82;

  // Forecast (Channel 3) Y-Range
  const fcVals: number[] = [];
  fcPts.forEach((p) => {
    if (p.q10 !== null) fcVals.push(p.q10);
    if (p.q50 !== null) fcVals.push(p.q50);
    if (p.q90 !== null) fcVals.push(p.q90);
  });
  const fcMin = fcVals.length > 0 ? Math.min(...fcVals, 90) : 90;
  const fcMax = fcVals.length > 0 ? Math.max(...fcVals, 110) : 110;
  const fcRange = Math.max(fcMax - fcMin, 10);
  const syFC = (val: number) => {
    const norm = (fcMax - val) / fcRange;
    return ch3Top + chH * 0.08 + norm * chH * 0.82;
  };

  // ---- Build traces ---------------------------------------------
  const edTrace = edSeries.pts.map(
    (d) => [sx(d.i), syED(d.v)] as [number, number],
  );
  const survTrace = survSeries.pts.map(
    (d) => [sx(d.i), sySurv(d.v)] as [number, number],
  );

  const q50Trace = fcPts
    .filter((p) => p.q50 !== null)
    .map((p) => [sx(p.i), syFC(p.q50 as number)] as [number, number]);
  const q10Trace = fcPts
    .filter((p) => p.q10 !== null)
    .map((p) => [sx(p.i), syFC(p.q10 as number)] as [number, number]);
  const q90Trace = fcPts
    .filter((p) => p.q90 !== null)
    .map((p) => [sx(p.i), syFC(p.q90 as number)] as [number, number]);

  // ---- Lead-Time (Gap zwischen SURV-Ende und ED-Ende) ----------
  const survEndIdx = survSeries.lastIdx ?? todayIdx;
  const edEndIdx = edSeries.lastIdx ?? todayIdx;
  let leadDays: number | null = null;
  if (survEndIdx !== null && edEndIdx !== null && survEndIdx < edEndIdx) {
    const survEndDate = new Date(points[survEndIdx].date);
    const edEndDate = new Date(points[edEndIdx].date);
    leadDays = Math.round(
      (edEndDate.getTime() - survEndDate.getTime()) / 86_400_000,
    );
  }

  // Q90-Plateau-Erkennung: falls alle q90-Werte gleich sind → Messinstrument-Warnung
  const q90Values = fcPts.map((p) => p.q90).filter((v): v is number => v !== null);
  const q90Plateau = q90Values.length > 2 &&
    Math.max(...q90Values) - Math.min(...q90Values) < 0.5;

  const todayX = sx(todayIdx);

  // ---- X-Axis KW Labels (dedup pro Woche) -----------------------
  const xLabels: React.ReactElement[] = [];
  const seen = new Set<number>();
  points.forEach((p, i) => {
    const d = new Date(p.date);
    const kw = getISOWeek(d);
    if (seen.has(kw)) return;
    seen.add(kw);
    const isToday = i === todayIdx;
    xLabels.push(
      <g key={`kw-${kw}-${i}`}>
        <line
          x1={sx(i)} x2={sx(i)}
          y1={ch3Base + 1} y2={ch3Base + (isToday ? 14 : 8)}
          stroke="#0D0F12" strokeWidth={isToday ? 1 : 0.5}
          strokeOpacity={isToday ? 1 : 0.4}
        />
        <text
          x={sx(i)} y={ch3Base + 32}
          textAnchor="middle"
          fontFamily="JetBrains Mono" fontSize={isToday ? 12 : 10}
          fontWeight={isToday ? 600 : 400}
          fill="#0D0F12" fillOpacity={isToday ? 1 : 0.5}
          letterSpacing={isToday ? '0.14em' : 'normal'}
        >
          KW{String(kw).padStart(2, '0')}
        </text>
      </g>,
    );
  });

  // ---- Chronology-Timeline Events (oben) ------------------------
  interface ChronoEvent {
    xIdx: number;
    label: string;
    subLabel: string;
    tone: 'ink' | 'slate' | 'signal';
  }
  const chronoEvents: ChronoEvent[] = [];

  if (edSeries.peakIdx !== null) {
    const kw = getISOWeek(new Date(points[edSeries.peakIdx].date));
    chronoEvents.push({
      xIdx: edSeries.peakIdx,
      label: 'ED-PEAK',
      subLabel: `KW${String(kw).padStart(2, '0')}`,
      tone: 'ink',
    });
  }
  if (survSeries.peakIdx !== null) {
    const kw = getISOWeek(new Date(points[survSeries.peakIdx].date));
    chronoEvents.push({
      xIdx: survSeries.peakIdx,
      label: 'SURVSTAT-PEAK',
      subLabel: `KW${String(kw).padStart(2, '0')}`,
      tone: 'slate',
    });
  }
  // HEUTE
  {
    const kw = getISOWeek(new Date(points[todayIdx].date));
    chronoEvents.push({
      xIdx: todayIdx,
      label: 'HEUTE',
      subLabel: `KW${String(kw).padStart(2, '0')}`,
      tone: 'ink',
    });
  }
  // Q50-Horizont: letzter Punkt mit Q50
  let q50EndIdx = -1;
  for (let i = points.length - 1; i >= 0; i -= 1) {
    if (points[i].q50 !== null) { q50EndIdx = i; break; }
  }
  if (q50EndIdx > todayIdx) {
    const kw = getISOWeek(new Date(points[q50EndIdx].date));
    chronoEvents.push({
      xIdx: q50EndIdx,
      label: 'Q50-HORIZONT',
      subLabel: `KW${String(kw).padStart(2, '0')}`,
      tone: 'signal',
    });
  }

  // Dedup events at same xIdx (ED-Peak = HEUTE bei wenig Daten etc.)
  // und sortiere nach xIdx
  chronoEvents.sort((a, b) => a.xIdx - b.xIdx);

  // Event-Label-Positioning: wenn Labels zu nah sind, alternieren oben/unten.
  const chronoY = 44; // mittlere Position
  const chronoEventRows = chronoEvents.map((evt, idx) => {
    // alternate label above/below the line if next event is close
    const prevX = idx > 0 ? sx(chronoEvents[idx - 1].xIdx) : -Infinity;
    const thisX = sx(evt.xIdx);
    const closeToPrev = thisX - prevX < 160;
    const labelAbove = closeToPrev ? idx % 2 === 0 : true;
    return { evt, x: thisX, labelAbove };
  });

  // ---- Render ---------------------------------------------------
  return (
    <div className="strip-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        <defs>
          {/* Subtile Papier-Textur für die 3 Kanäle */}
          <pattern id="paperGrain" x="0" y="0" width="240" height="240" patternUnits="userSpaceOnUse">
            <rect width="240" height="240" fill="none" />
          </pattern>
          <linearGradient id="paperFreshTint" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#EDE8DC" stopOpacity="0" />
            <stop offset="30%" stopColor="#EDE8DC" stopOpacity="1" />
            <stop offset="100%" stopColor="#EDE8DC" stopOpacity="1" />
          </linearGradient>
          <pattern id="leadHatch" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="#4A5261" strokeWidth="0.8" strokeOpacity="0.35" />
          </pattern>
        </defs>

        {/* Paper backgrounds — past (printed) vs future (fresh) */}
        <rect x={0} y={0} width={todayX} height={H} fill="#F4F1EA" />
        <rect x={todayX} y={0} width={W - todayX} height={H} fill="url(#paperFreshTint)" />
        <rect x={todayX} y={0} width={W - todayX} height={H} fill="#EDE8DC" opacity={0} />

        {/* -------- CHRONOLOGY TIMELINE (oben) -------- */}
        <line
          x1={PAD_L} x2={W - PAD_R}
          y1={chronoY} y2={chronoY}
          stroke="#0D0F12" strokeWidth={0.5} strokeOpacity={0.35}
        />
        {/* Left-end chronology kicker — the label is the astronomy-nautical
             term for a position-over-time table; in this cockpit it's the
             timeline row that pins the Peaks of both truth sources and the
             HEUTE marker. Subtitle makes that explicit so nobody has to
             look up the Latin. */}
        <text
          x={PAD_L - 12} y={chronoY - 6}
          textAnchor="end"
          fontFamily="JetBrains Mono" fontSize={10} fontWeight={500}
          fill="#0D0F12" fillOpacity={0.45} letterSpacing="0.16em"
        >
          EPHEMERIDE
        </text>
        <text
          x={PAD_L - 12} y={chronoY + 7}
          textAnchor="end"
          fontFamily="JetBrains Mono" fontSize={9} fontWeight={400}
          fill="#0D0F12" fillOpacity={0.35} letterSpacing="0.14em"
        >
          ZEITACHSE · PEAKS + HEUTE
        </text>

        {chronoEventRows.map(({ evt, x, labelAbove }) => {
          const color = evt.tone === 'signal'
            ? '#C2542A' : evt.tone === 'slate'
              ? '#4A5261' : '#0D0F12';
          const labelY = labelAbove ? chronoY - 20 : chronoY + 22;
          const subY = labelAbove ? chronoY - 6 : chronoY + 38;
          return (
            <g key={`evt-${evt.label}-${evt.xIdx}`}>
              {/* Vertical tick from chronoY to ch1Top (thin dashed guide) */}
              <line
                x1={x} x2={x} y1={chronoY + 4} y2={ch1Top - 4}
                stroke={color} strokeWidth={0.4} strokeOpacity={0.25}
                strokeDasharray="2 3"
              />
              <circle cx={x} cy={chronoY} r={4} fill={color} />
              <text
                x={x} y={labelY}
                textAnchor="middle"
                fontFamily="JetBrains Mono" fontSize={10} fontWeight={600}
                fill={color} letterSpacing="0.14em"
              >
                {evt.label}
              </text>
              <text
                x={x} y={subY}
                textAnchor="middle"
                fontFamily="JetBrains Mono" fontSize={10} fontWeight={400}
                fill={color} fillOpacity={0.6}
              >
                {evt.subLabel}
              </text>
            </g>
          );
        })}

        {/* -------- CHANNEL 1: ED -------- */}
        <ChannelFrame
          top={ch1Top} bottom={ch1Base}
          left={PAD_L} right={W - PAD_R}
          chNo="CH·01"
          title="ED"
          subtitle="NOTAUFNAHMEN"
          hint="Lead-Indikator"
          peakLabel={edSeries.peakValue > 0
            ? `Peak ${edSeries.peakValue.toFixed(1)}` : 'keine Daten'}
        />
        {edTrace.length >= 2 && (
          <>
            <path d={area(edTrace, ch1Base)} fill="rgba(13,15,18,0.06)" />
            <path d={polyline(edTrace)}
                  stroke="#0D0F12" strokeWidth={2.25}
                  fill="none" strokeLinejoin="round" strokeLinecap="round" />
          </>
        )}
        {/* ED data-points */}
        {edTrace.map(([x, y], i) => (
          <circle key={`ed-pt-${i}`} cx={x} cy={y} r={2.5}
                  fill="#F4F1EA" stroke="#0D0F12" strokeWidth={1} />
        ))}
        {/* ED Peak marker */}
        {edSeries.peakIdx !== null && (
          <g>
            <line
              x1={sx(edSeries.peakIdx)} x2={sx(edSeries.peakIdx)}
              y1={syED(edSeries.peakValue)} y2={ch1Base}
              stroke="#0D0F12" strokeWidth={0.5}
              strokeDasharray="2 3" strokeOpacity={0.5}
            />
            <circle
              cx={sx(edSeries.peakIdx)} cy={syED(edSeries.peakValue)}
              r={5.5} fill="#F4F1EA" stroke="#0D0F12" strokeWidth={2}
            />
          </g>
        )}

        {/* -------- CHANNEL 2: AMELAG ABWASSER --------
           2026-04-21 Chart-Skalen-Fix: observed ist jetzt AMELAG
           viruslast (gleiche Skala wie Forecast), nicht mehr SURVSTAT
           incidence. Die Channel-Beschriftung folgt. */}
        <ChannelFrame
          top={ch2Top} bottom={ch2Base}
          left={PAD_L} right={W - PAD_R}
          chNo="CH·02"
          title="AMELAG"
          subtitle="ABWASSER"
          hint="Virus-Last · wöchentlich, ~13 d Latenz"
          peakLabel={survSeries.peakValue > 0
            ? `Peak ${Math.round(survSeries.peakValue)}` : 'keine Daten'}
        />
        {survTrace.length >= 2 && (
          <>
            <path d={area(survTrace, ch2Base)} fill="rgba(74,82,97,0.08)" />
            <path d={polyline(survTrace)}
                  stroke="#4A5261" strokeWidth={2.25}
                  fill="none" strokeLinejoin="round" strokeLinecap="round" />
          </>
        )}
        {survTrace.map(([x, y], i) => (
          <circle key={`surv-pt-${i}`} cx={x} cy={y} r={2.5}
                  fill="#F4F1EA" stroke="#4A5261" strokeWidth={1} />
        ))}
        {/* SURV Peak marker */}
        {survSeries.peakIdx !== null && (
          <g>
            <line
              x1={sx(survSeries.peakIdx)} x2={sx(survSeries.peakIdx)}
              y1={sySurv(survSeries.peakValue)} y2={ch2Base}
              stroke="#4A5261" strokeWidth={0.5}
              strokeDasharray="2 3" strokeOpacity={0.5}
            />
            <circle
              cx={sx(survSeries.peakIdx)} cy={sySurv(survSeries.peakValue)}
              r={5.5} fill="#F4F1EA" stroke="#4A5261" strokeWidth={2}
            />
          </g>
        )}

        {/* LEAD-ZONE in Kanal 2: Lücke zwischen SURV-Ende und HEUTE */}
        {leadDays !== null && leadDays > 0 && survEndIdx !== null && (
          <g>
            <rect
              x={sx(survEndIdx)}
              y={ch2Top + chH * 0.15}
              width={todayX - sx(survEndIdx)}
              height={chH * 0.7}
              fill="url(#leadHatch)"
              opacity={0.9}
            />
            <line
              x1={sx(survEndIdx)} x2={todayX}
              y1={ch2Base - 0.5} y2={ch2Base - 0.5}
              stroke="#C2542A" strokeWidth={1.5}
              strokeDasharray="4 3"
            />
            {/* Lead label */}
            <g transform={`translate(${(sx(survEndIdx) + todayX) / 2},${ch2Top + chH * 0.5})`}>
              <rect x={-60} y={-14} width={120} height={24}
                    fill="#C2542A" />
              <text
                x={0} y={2}
                textAnchor="middle"
                fontFamily="JetBrains Mono" fontSize={11} fontWeight={700}
                fill="#F4F1EA" letterSpacing="0.2em"
              >
                +{leadDays} TAGE LEAD
              </text>
            </g>
          </g>
        )}

        {/* -------- CHANNEL 3: FORECAST -------- */}
        <ChannelFrame
          top={ch3Top} bottom={ch3Base}
          left={PAD_L} right={W - PAD_R}
          chNo="CH·03"
          title="MODELL"
          subtitle="Q-QUANTILE"
          hint={q90Plateau ? '⚠ Q90 plateau · Modell-Warnung' : 'Forecast · Abwasser-Index (HEUTE=100)'}
          hintTone={q90Plateau ? 'warn' : 'normal'}
          peakLabel="AMELAG-Index · 100"
        />
        {/* 100-Linie in Kanal 3 */}
        <line
          x1={todayX} x2={W - PAD_R}
          y1={syFC(100)} y2={syFC(100)}
          stroke="#0D0F12" strokeWidth={0.5}
          strokeOpacity={0.3} strokeDasharray="2 3"
        />
        <text
          x={PAD_L - 6} y={syFC(100) + 3}
          textAnchor="end"
          fontFamily="JetBrains Mono" fontSize={9}
          fill="#0D0F12" fillOpacity={0.45}
        >
          100
        </text>
        {/* Fan-Bänder */}
        {q10Trace.length >= 2 && q90Trace.length >= 2 && (
          <path d={splineBand(q10Trace, q90Trace)}
                fill="rgba(194,84,42,0.20)" stroke="none" />
        )}
        {/* Q90-Plateau-Warnung: oberer Rand als explizite Linie zeigen */}
        {q90Plateau && q90Trace.length >= 2 && (
          <path d={spline(q90Trace)}
                stroke="#C2542A" strokeWidth={1}
                strokeDasharray="3 3" strokeOpacity={0.55} fill="none" />
        )}
        {/* Q50 Linie */}
        {q50Trace.length >= 2 && (
          <path d={spline(q50Trace)}
                stroke="#C2542A" strokeWidth={2.5}
                fill="none" strokeLinejoin="round" strokeLinecap="round" />
        )}
        {/* HEUTE anchor dot in Kanal 3 */}
        <circle
          cx={todayX} cy={syFC(100)}
          r={6} fill="#0D0F12" stroke="#F4F1EA" strokeWidth={2}
        />
        {/* Q50-End-Marker */}
        {q50Trace.length > 0 && (
          <g>
            <circle
              cx={q50Trace[q50Trace.length - 1][0]}
              cy={q50Trace[q50Trace.length - 1][1]}
              r={7} fill="#C2542A" stroke="#F4F1EA" strokeWidth={2}
            />
          </g>
        )}

        {/* -------- VINTAGE-Spuren auf CH.03 -------- */}
        {showVintage && vintageRuns.map((run, runIdx) => {
          // Normalize each run's q50 to its own anchor = 100
          const anchor = run.anchor_value ?? run.points[0]?.q50 ?? 0;
          if (!anchor || !Number.isFinite(anchor)) return null;
          const pts = run.points
            .map((p) => {
              if (p.q50 === null || !Number.isFinite(p.q50)) return null;
              const idx = (p.q50 / anchor) * 100;
              const x = sxDate(p.date);
              // soft-clip: only render when near the plot area
              if (x < PAD_L - 40 || x > PAD_L + plotW + 40) return null;
              return [x, syFC(idx)] as [number, number];
            })
            .filter((p): p is [number, number] => p !== null);
          if (pts.length === 0) return null;

          // Age-based styling: neuestere Runs kräftiger, ältere blasser.
          // runIdx=0 ist der neueste Run (Backend sortiert DESC).
          const totalRuns = Math.max(1, vintageRuns.length);
          const age = (totalRuns - runIdx) / totalRuns; // 1=neu, →0=alt
          const opacity = 0.25 + age * 0.35;
          const runX = sxDate(run.run_date);
          const runWithinPlot = runX >= PAD_L - 8 && runX <= PAD_L + plotW + 8;
          return (
            <g key={`vintage-${runIdx}`}>
              {pts.length >= 2 && (
                <path
                  d={polyline(pts)}
                  stroke="#4A5261"
                  strokeWidth={1.2}
                  strokeDasharray="3 3"
                  strokeOpacity={opacity}
                  fill="none"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              )}
              {pts.map(([x, y], j) => (
                <circle
                  key={`v-pt-${runIdx}-${j}`}
                  cx={x} cy={y} r={2.5}
                  fill="#F4F1EA"
                  stroke="#4A5261"
                  strokeWidth={1}
                  opacity={opacity + 0.2}
                />
              ))}
              {/* Run-date tick on top edge of CH.03 */}
              {runWithinPlot && (
                <g>
                  <line
                    x1={runX} x2={runX}
                    y1={ch3Top - 6} y2={ch3Top + 4}
                    stroke="#4A5261"
                    strokeWidth={0.8}
                    strokeOpacity={opacity + 0.2}
                  />
                  <text
                    x={runX} y={ch3Top - 10}
                    textAnchor="middle"
                    fontFamily="JetBrains Mono" fontSize={9}
                    fill="#4A5261" fillOpacity={opacity + 0.3}
                    letterSpacing="0.08em"
                  >
                    RUN {new Date(run.run_date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* -------- HEUTE divider — paper-seam across all channels -------- */}
        <line
          x1={todayX} x2={todayX}
          y1={chronoY + 12} y2={ch3Base + 1}
          stroke="#0D0F12" strokeWidth={1.25}
        />
        {/* Small horizontal "perforation" ticks every 40px */}
        {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15].map((i) => {
          const y = chronoY + 20 + i * 40;
          if (y > ch3Base - 8) return null;
          return (
            <line
              key={`perf-${i}`}
              x1={todayX - 4} x2={todayX + 4}
              y1={y} y2={y}
              stroke="#0D0F12" strokeWidth={0.5} strokeOpacity={0.5}
            />
          );
        })}

        {/* -------- X-Axis -------- */}
        <line
          x1={PAD_L} x2={W - PAD_R}
          y1={ch3Base + 1} y2={ch3Base + 1}
          stroke="#0D0F12" strokeWidth={0.5}
        />
        {xLabels}

        {/* -------- Corner marks an den Plot-Ecken -------- */}
        <CornerMark x={PAD_L} y={PAD_T} orient="tl" />
        <CornerMark x={W - PAD_R} y={PAD_T} orient="tr" />
        <CornerMark x={PAD_L} y={ch3Base} orient="bl" />
        <CornerMark x={W - PAD_R} y={ch3Base} orient="br" />
      </svg>
    </div>
  );
};

// -----------------------------------------------------------------
// ChannelFrame — Links-Label + Baseline + Deckel
// -----------------------------------------------------------------
const ChannelFrame: React.FC<{
  top: number;
  bottom: number;
  left: number;
  right: number;
  chNo: string;
  title: string;
  subtitle: string;
  hint: string;
  hintTone?: 'normal' | 'warn';
  peakLabel: string;
}> = ({ top, bottom, left, right, chNo, title, subtitle, hint, hintTone = 'normal', peakLabel }) => (
  <g>
    {/* Left column labels */}
    <text
      x={left - 18} y={top + 16}
      textAnchor="end"
      fontFamily="JetBrains Mono" fontSize={10} fontWeight={500}
      fill="#0D0F12" fillOpacity={0.5} letterSpacing="0.16em"
    >
      {chNo}
    </text>
    <text
      x={left - 18} y={top + 40}
      textAnchor="end"
      fontFamily="Supreme, sans-serif" fontSize={20} fontWeight={500}
      fill="#0D0F12" letterSpacing="-0.02em"
    >
      {title}
    </text>
    <text
      x={left - 18} y={top + 60}
      textAnchor="end"
      fontFamily="Supreme, sans-serif" fontSize={14} fontWeight={400}
      fill="#0D0F12" fillOpacity={0.7} letterSpacing="-0.01em"
    >
      {subtitle}
    </text>
    <text
      x={left - 18} y={top + 80}
      textAnchor="end"
      fontFamily="JetBrains Mono" fontSize={10}
      fill={hintTone === 'warn' ? '#C2542A' : '#0D0F12'}
      fillOpacity={hintTone === 'warn' ? 0.95 : 0.5}
      letterSpacing="0.04em"
    >
      {hint}
    </text>

    {/* Right-side peak readout */}
    <text
      x={right + 4} y={top + 16}
      textAnchor="start"
      fontFamily="JetBrains Mono" fontSize={10}
      fill="#0D0F12" fillOpacity={0.5} letterSpacing="0.12em"
    >
      {peakLabel}
    </text>

    {/* Top hairline (dashed) */}
    <line
      x1={left} x2={right} y1={top} y2={top}
      stroke="#0D0F12" strokeWidth={0.4}
      strokeOpacity={0.18} strokeDasharray="2 4"
    />
    {/* Baseline (solid) */}
    <line
      x1={left} x2={right} y1={bottom} y2={bottom}
      stroke="#0D0F12" strokeWidth={0.75} strokeOpacity={0.55}
    />

    {/* Left bracket at baseline */}
    <path
      d={`M ${left - 5},${bottom} L ${left},${bottom} L ${left},${bottom - 8}`}
      stroke="#0D0F12" strokeWidth={0.5} fill="none" strokeOpacity={0.6}
    />
    <path
      d={`M ${left - 5},${top} L ${left},${top} L ${left},${top + 8}`}
      stroke="#0D0F12" strokeWidth={0.5} fill="none" strokeOpacity={0.3}
    />
  </g>
);

const CornerMark: React.FC<{
  x: number;
  y: number;
  orient: 'tl' | 'tr' | 'bl' | 'br';
  size?: number;
}> = ({ x, y, orient, size = 10 }) => {
  const dx = orient === 'tr' || orient === 'br' ? -size : size;
  const dy = orient === 'bl' || orient === 'br' ? -size : size;
  return (
    <path
      d={`M ${x + dx},${y} L ${x},${y} L ${x},${y + dy}`}
      stroke="#0D0F12" strokeWidth={1} fill="none" strokeOpacity={0.75}
    />
  );
};

// -----------------------------------------------------------------
// ForecastControls — Virus-Switcher + Vintage-Toggle über dem Chart
// -----------------------------------------------------------------

// (VIRUS_CHOICES removed 2026-04-20 — virus selection moved to ChronoBar
//  so all five sections always tell the same story. Kept the constant
//  name reserved to ease a potential future in-section override.)

// -----------------------------------------------------------------
// DriftBanner — fires when reconciliation.drift_detected is true
// -----------------------------------------------------------------
// Why separate from the ModelProof/Reconciliation blocks: drift is a
// time-critical operational warning (the model has been systematically
// off over the recent window), not a summary metric. It deserves its
// own banner at the top of § III so a decision-maker notices it
// regardless of which panel they scroll to.
const DriftBanner: React.FC<{
  mape: number | null;
  correlation: number | null;
  samples: number;
  virusTyp: string;
}> = ({ mape, correlation, samples, virusTyp }) => (
  <div className="fc-drift-banner" role="alert">
    <div className="fc-drift-banner-head">
      <span className="fc-drift-badge">Drift erkannt</span>
      <span className="fc-drift-scope">{virusTyp} · {samples} Wochen-Paare</span>
    </div>
    <p className="fc-drift-body">
      Das Modell weicht auf den letzten {samples} Wochen systematisch vom
      Truth-Signal ab
      {mape !== null ? (
        <>
          {' '}(<b>MAPE {mape.toFixed(0)} %</b>)
        </>
      ) : null}
      {correlation !== null ? (
        <>
          , Korrelation {correlation >= 0 ? '+' : ''}{correlation.toFixed(2)}
        </>
      ) : null}
      . Empfehlungen aus diesem Forecast sind mit <b>Vorsicht</b> zu lesen,
      bis das nächste Retraining die Drift korrigiert oder die Abweichung
      sich stabilisiert.
    </p>
  </div>
);

const ForecastControls: React.FC<{
  showVintage: boolean;
  onToggleVintage: (v: boolean) => void;
  vintageRunCount: number;
  vintageLoading: boolean;
}> = ({ showVintage, onToggleVintage, vintageRunCount, vintageLoading }) => (
  <div className="fc-controls">
    <div className="fc-controls-left" />
    <div className="fc-controls-right">
      <label
        className={`fc-vintage-toggle${showVintage ? ' on' : ''}`}
        title={
          'Vintage-Spuren blenden frühere Forecast-Versionen als schwache ' +
          'graue Linien ein — so siehst du, ob das Modell in den letzten ' +
          'Wochen stabil dieselbe Welle vorhergesagt hat oder ob es hin ' +
          'und her geschwenkt ist. Ein Vertrauens-Indikator für die aktuelle ' +
          'Prognose.'
        }
      >
        <input
          type="checkbox"
          checked={showVintage}
          onChange={(e) => onToggleVintage(e.target.checked)}
        />
        <span className="fc-toggle-box" aria-hidden />
        <span className="fc-toggle-label">
          Vintage-Spuren
          {vintageLoading ? (
            <span className="fc-toggle-hint"> · lädt</span>
          ) : vintageRunCount > 0 ? (
            <span className="fc-toggle-hint"> · {vintageRunCount} frühere Runs</span>
          ) : (
            <span className="fc-toggle-hint"> · keine Historie</span>
          )}
        </span>
      </label>
    </div>
  </div>
);

// -----------------------------------------------------------------
// ModelProofPanel — "Modell-Gütenachweis" aus dem Regional-Backtest.
// Zieht die AUTORITÄREN Gütezahlen (PR-AUC, Precision@Top-3, Lead) aus
// /cockpit/backtest und zeigt sie als Legitimation des § III Forecast.
// Plus kompakter Hit-Barcode als Track-Record-Streifen.
// -----------------------------------------------------------------

const ModelProofPanel: React.FC<{
  data: BacktestPayload | null;
  loading: boolean;
  virusTyp: string;
}> = ({ data, loading, virusTyp }) => {
  if (loading && !data) {
    return (
      <div className="reconciliation">
        <div className="block-empty">Lädt Backtest-Metriken …</div>
      </div>
    );
  }
  if (!data || !data.available) {
    return (
      <div className="reconciliation">
        <div className="reconciliation-head">
          <div>
            <div className="col-kicker">Modell-Gütenachweis</div>
            <div className="recon-subline">
              Noch kein Regional-Backtest für {virusTyp} verfügbar.
            </div>
          </div>
        </div>
      </div>
    );
  }

  const prAuc = data.headline.pr_auc;
  const prAucBase = data.baselines.persistence_pr_auc;
  const prAucMult =
    prAuc !== null && prAucBase !== null && prAucBase > 0
      ? prAuc / prAucBase
      : null;

  const prec = data.headline.precision_at_top3;
  const precBase = data.baselines.persistence_precision_at_top3;
  const precPp =
    prec !== null && precBase !== null ? (prec - precBase) * 100 : null;

  const lead = data.headline.median_lead_days;

  const weekly = data.weekly_hits ?? [];
  const hitRate =
    weekly.length > 0
      ? weekly.filter((w) => w.was_hit).length / weekly.length
      : null;

  const windowStart = data.window.start ? new Date(data.window.start) : null;
  const windowEnd = data.window.end ? new Date(data.window.end) : null;
  const fmtDate = (d: Date | null) =>
    d
      ? d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit' })
      : '—';

  return (
    <div className="reconciliation">
      <div className="reconciliation-head">
        <div>
          <div className="col-kicker">Modell-Gütenachweis · Walk-Forward-Backtest</div>
          <div className="recon-subline">
            {virusTyp} · {data.window.folds} Folds über{' '}
            {fmtDate(windowStart)} → {fmtDate(windowEnd)} · Horizont {data.horizon_days} Tage
          </div>
        </div>
      </div>

      <div className="proof-monuments">
        <div className="proof-monument">
          <div className="m-kicker">PR-AUC Gesamt</div>
          <div className="m-value">
            {prAuc !== null ? prAuc.toFixed(3).replace(/^0/, '') : '—'}
          </div>
          <div className="m-ref">
            vs. Persistenz-Baseline{' '}
            <b>{prAucBase !== null ? prAucBase.toFixed(3).replace(/^0/, '') : '—'}</b>
            {prAucMult !== null && (
              <>
                {' · '}
                <span className="m-accent">{prAucMult.toFixed(1)}×</span> besser
              </>
            )}
          </div>
        </div>
        <div className="proof-monument">
          <div className="m-kicker">Precision @ Top-3</div>
          <div className="m-value">
            {prec !== null ? (prec * 100).toFixed(1) : '—'}
            <span className="m-unit">%</span>
          </div>
          <div className="m-ref">
            vs. Persistenz{' '}
            <b>
              {precBase !== null ? `${(precBase * 100).toFixed(1)} %` : '—'}
            </b>
            {precPp !== null && (
              <>
                {' · '}
                <span className="m-accent">
                  {precPp >= 0 ? '+' : ''}
                  {precPp.toFixed(1)}pp
                </span>
              </>
            )}
          </div>
        </div>
        <div className="proof-monument">
          <div className="m-kicker">Median Lead-Zeit</div>
          <div className="m-value">
            {lead !== null ? lead : '—'}
            <span className="m-unit">d</span>
          </div>
          <div className="m-ref">
            gegen Meldewesen &nbsp;·&nbsp; Hit-Rate{' '}
            <b>
              {hitRate !== null ? `${Math.round(hitRate * 100)} %` : '—'}
            </b>
          </div>
        </div>
      </div>

      {weekly.length > 0 && (
        <div className="proof-track">
          <div className="proof-track-head">
            <span className="col-kicker">Track-Record · {weekly.length} Wochen</span>
            <span className="proof-track-legend">
              <span><span className="sw hit" />Hit · Top-3 traf Welle</span>
              <span><span className="sw miss" />Miss · Top-3 verfehlt</span>
            </span>
          </div>
          <div className="proof-track-bars">
            {weekly.map((w, i) => (
              <span
                key={`wk-${i}`}
                className={`track-bar ${w.was_hit ? 'hit' : 'miss'}`}
                title={`${w.target_date.slice(0, 10)} — ${w.was_hit ? 'Hit' : 'Miss'}`}
              />
            ))}
          </div>
          <div className="proof-track-foot">
            <span>Ausführliches Ranking pro Bundesland → </span>
            <a href="#sec-backtest" className="proof-track-link">§ V Backtest</a>
          </div>
        </div>
      )}
    </div>
  );
};

// -----------------------------------------------------------------
// Root — § III ForecastSection
// -----------------------------------------------------------------

export const ForecastSection: React.FC<Props> = ({ snapshot: primarySnapshot }) => {
  // 2026-04-20: local virus state removed. The virus is now globally
  // selected via ChronoBar → CockpitShell → the primary snapshot, so
  // § I, § II, § III, § IV and § V always tell the same story. The
  // ForecastControls row keeps the Vintage-Spuren toggle, the virus
  // buttons are gone (they moved into ChronoBar).
  const virusTyp = primarySnapshot.virusTyp || 'Influenza A';
  const [showVintage, setShowVintage] = useState<boolean>(false);
  // 2026-04-20: § III has a lot going on (three channels + ephemeride +
  // q-quantile fan + vintage + ephemeris foot + model-proof panel). The
  // persona walkthrough flagged it as overwhelming for first-time readers.
  // Solution: default to a simple view (chart + lead-time hero only),
  // opt-in to the full lab-recorder detail via this toggle.
  const [detailMode, setDetailMode] = useState<boolean>(false);

  // Vintage-Runs (für Chart-Overlay)
  const { data: vintagePayload, loading: vintageLoading } = useForecastVintage(virusTyp, 5);
  const vintageRuns = vintagePayload?.runs ?? [];

  // Regional-Backtest = die AUTORITÄREN Gütezahlen des Cockpit-Modells.
  const { data: backtestData, loading: backtestLoading } = useBacktest({
    virusTyp, horizonDays: 7,
  });

  const snapshot = primarySnapshot;
  const localLoading = false;

  const timeline = snapshot.timeline ?? [];
  const cov80 = snapshot.modelStatus?.intervalCoverage80Pct ?? null;
  const cov95 = snapshot.modelStatus?.intervalCoverage95Pct ?? null;
  const bestLag = snapshot.modelStatus?.lead?.bestLagDays ?? null;
  const horizonDays = snapshot.modelStatus?.horizonDays ?? 14;

  const readiness = snapshot.modelStatus?.forecastReadiness ?? 'UNKNOWN';
  const gateTone: GateTone =
    readiness === 'GO_RANKING' || readiness === 'RANKING_OK'
      ? 'go'
      : readiness === 'WATCH' ||
        readiness === 'LEAD_ONLY' ||
        readiness === 'DATA_STALE' ||
        readiness === 'DRIFT_WARN' ||
        readiness === 'SEASON_OFF'
        ? 'watch'
        : 'unknown';
  const gateLabel =
    readiness === 'DATA_STALE'
      ? 'Forecast · data stale'
      : readiness === 'DRIFT_WARN'
        ? 'Forecast · drift warning'
        : readiness === 'SEASON_OFF'
          ? 'Forecast · season off'
          : gateTone === 'go'
            ? 'Forecast · usable'
            : gateTone === 'watch'
              ? 'Forecast · watch'
              : 'Forecast · review';

  // Build ephemeris rows from live data
  const edSeries = buildSeries(timeline, (p) => p.edActivity);
  const survSeries = buildSeries(timeline, (p) => p.observed);

  // Anchor + peak for forecast index
  let todayIdx = edSeries.lastIdx ?? survSeries.lastIdx ?? Math.floor(timeline.length / 2);
  let fcAnchorIdx = todayIdx;
  if (timeline[fcAnchorIdx]?.q50 === null) {
    for (let d = 1; d < timeline.length; d += 1) {
      if (fcAnchorIdx + d < timeline.length && timeline[fcAnchorIdx + d]?.q50 !== null) {
        fcAnchorIdx += d; break;
      }
      if (fcAnchorIdx - d >= 0 && timeline[fcAnchorIdx - d]?.q50 !== null) {
        fcAnchorIdx -= d; break;
      }
    }
  }
  const fcAnchor = timeline[fcAnchorIdx]?.q50 ?? 0;

  // Peak Q50 im Forecast-Bereich
  let q50PeakIdx = -1;
  let q50PeakVal = -Infinity;
  for (let i = todayIdx; i < timeline.length; i += 1) {
    const v = timeline[i]?.q50;
    if (v !== null && Number.isFinite(v) && v > q50PeakVal) {
      q50PeakVal = v;
      q50PeakIdx = i;
    }
  }
  const q50PeakIndex = q50PeakIdx >= 0 && fcAnchor
    ? ((q50PeakVal / fcAnchor) - 1) * 100 : null;
  const q50PeakKw = q50PeakIdx >= 0
    ? `KW${String(getISOWeek(new Date(timeline[q50PeakIdx].date))).padStart(2, '0')}`
    : null;

  // Q90 max index rel. HEUTE
  let q90MaxVal = -Infinity;
  for (let i = todayIdx; i < timeline.length; i += 1) {
    const v = timeline[i]?.q90;
    if (v !== null && Number.isFinite(v) && v > q90MaxVal) q90MaxVal = v;
  }
  const q90MaxIndex = q90MaxVal > 0 && fcAnchor
    ? ((q90MaxVal / fcAnchor) - 1) * 100 : null;

  const q90Vals: number[] = [];
  for (let i = todayIdx; i < timeline.length; i += 1) {
    const v = timeline[i]?.q90;
    if (v !== null && Number.isFinite(v)) q90Vals.push(v);
  }
  const q90Plateau = q90Vals.length > 2
    && (Math.max(...q90Vals) - Math.min(...q90Vals)) < 0.5;

  // Hero-Lead = Median Lead-Zeit aus dem Backtest. Strukturell robuste
  // Pitch-Zahl aus 68 Walk-forward-Folds, nicht aus dem aktuellen
  // Snapshot. Fallback: bestLagDays aus dem Live-Lead-Block (wenn
  // positiv) oder Timeline-Gap (Daten-Freshness als Notnagel).
  const backtestLead = backtestData?.headline?.median_lead_days ?? null;

  // Timeline-Gap nebenbei für die Ephemeris-Zeile (Daten-Freshness,
  // nicht Modell-Lead).
  let freshnessGap: number | null = null;
  if (
    survSeries.lastIdx !== null &&
    edSeries.lastIdx !== null &&
    edSeries.lastIdx > survSeries.lastIdx
  ) {
    const survLastDate = new Date(timeline[survSeries.lastIdx].date);
    const edLastDate = new Date(timeline[edSeries.lastIdx].date);
    freshnessGap = Math.round(
      (edLastDate.getTime() - survLastDate.getTime()) / 86_400_000,
    );
  }

  const hasShift = !!primarySnapshot.primaryRecommendation;
  const leadHero = deriveForecastLeadHero({ backtestLead, bestLag, hasShift });

  // Ephemeris observed rows
  const observedRows: EphemerisRowData[] = [];
  if (edSeries.peakIdx !== null) {
    const kw = getISOWeek(new Date(timeline[edSeries.peakIdx].date));
    observedRows.push({
      label: 'ED-Peak',
      value: `KW${String(kw).padStart(2, '0')} · ${edSeries.peakValue.toFixed(1)}`,
    });
  } else {
    observedRows.push({ label: 'ED-Peak', value: '—' });
  }
  if (survSeries.peakIdx !== null) {
    const kw = getISOWeek(new Date(timeline[survSeries.peakIdx].date));
    observedRows.push({
      label: 'SURVSTAT-Peak',
      value: `KW${String(kw).padStart(2, '0')} · ${Math.round(survSeries.peakValue)}`,
    });
  } else {
    observedRows.push({ label: 'SURVSTAT-Peak', value: '—' });
  }
  observedRows.push({
    label: 'Beobachtete Wochen',
    value: `${Math.max(edSeries.pts.length, survSeries.pts.length)} Tage`,
  });
  observedRows.push({
    label: 'ED ↔ SURVSTAT · Datenstand-Lücke',
    value: freshnessGap !== null
      ? `${freshnessGap >= 0 ? '+' : ''}${freshnessGap} Tage`
      : '—',
  });

  // Backend-bestLagDays = Modell vs. Target-Signal. Vorzeichen-Konvention:
  // >= 0 = Modell führt Target, < 0 = Modell hinkt Target hinterher.
  // Wird separat vom Hero-Lead gezeigt, weil es technisch eine andere
  // Frage beantwortet: "wie gut verfolgt das Modell den schnellen Sensor?"
  const modelTarget = snapshot.modelStatus?.lead?.targetLabel ?? 'Target';
  const modelLagLabel = bestLag !== null
    ? bestLag > 0
      ? `+${bestLag} Tage Vorlauf`
      : bestLag === 0
        ? 'synchron'
        : `${bestLag} Tage Rückstand`
    : '—';

  // Ephemeris forecast rows
  const forecastRows: EphemerisRowData[] = [
    {
      label: 'Q50-Horizont',
      value: q50PeakKw ?? '—',
    },
    {
      label: 'Q50-Index (vs. HEUTE)',
      value: q50PeakIndex !== null
        ? `${q50PeakIndex >= 0 ? '+' : ''}${q50PeakIndex.toFixed(1)} %`
        : '—',
    },
    {
      label: 'Q90-Zone',
      value: q90MaxIndex !== null
        ? `${q90MaxIndex >= 0 ? '+' : ''}${q90MaxIndex.toFixed(0)} %${q90Plateau ? ' · Plateau' : ''}`
        : '—',
      warn: q90Plateau,
    },
    {
      label: `Modell-Lag vs. ${modelTarget}`,
      value: modelLagLabel,
      warn: bestLag !== null && bestLag < 0,
    },
    {
      label: 'Coverage Q80',
      value: cov80 !== null ? `${cov80.toFixed(1)} %` : '—',
    },
    {
      label: 'Coverage Q95',
      value: cov95 !== null ? `${cov95.toFixed(1)} %` : '—',
    },
    {
      label: 'Horizont',
      value: `+${horizonDays} Tage`,
    },
  ];

  return (
    <section
      className={`instr-section fc-mode-${detailMode ? 'detail' : 'simple'}`}
      id="sec-forecast"
    >
      <SectionHeader
        numeral="III"
        title="Forecast-Zeitreise"
        subtitle={
          <>
            Drei Streifen wie ein Lab-Plotter: Notaufnahmen, Abwasser, Modell.
            {' '}Wenn der Modell-Streifen nach oben kippt, kippt nächste Woche die Welle.
            {localLoading && virusTyp !== primarySnapshot.virusTyp ? ' · lädt' : ''}
          </>
        }
        gate={{ label: gateLabel, tone: gateTone }}
        primer={
          <>
            Drei Streifen wie ein Lab-Messschreiber: <b>Notaufnahmen</b>,{' '}
            <b>Abwasser-Viruslast</b> (AMELAG) und <b>Q-Quantile</b> des
            Forecasts. Links die letzten Wochen als Ist-Wert, ab <b>HEUTE</b>{' '}
            der Fächer aus Q10 / Q50 / Q90 — alle auf derselben AMELAG-Skala.
            Enger Fächer = Modell ist sich sicher, breiter Fächer = mehr
            Unsicherheit, typisch kurz vor einem Wellenwechsel. Darunter die
            „Lead-Time" gegen das RKI-Meldewesen: wie viele Tage früher
            hätten Abwasser-Signale die Welle angekündigt als die offizielle
            Inzidenz-Meldung.
            {' '}
            <b>Glossar:</b> Die <b>Ephemeride</b> oben ist die Zeitachse
            mit den Peaks beider Truth-Quellen und dem HEUTE-Marker (der
            Begriff kommt aus der Astronomie — eine Tabelle der
            Position-zu-einem-Zeitpunkt). Aktivierst du{' '}
            <b>Vintage-Spuren</b>, werden vergangene Forecast-Versionen
            als schwache graue Linien eingeblendet — ein Vertrauens-Check:
            hat das Modell dieselbe Welle die letzten Wochen stabil
            vorhergesagt oder hin-und-her geschwenkt?
          </>
        }
      />

      <div className="fc-mode-toggle-row">
        <button
          type="button"
          className={`fc-mode-btn${!detailMode ? ' active' : ''}`}
          onClick={() => setDetailMode(false)}
        >
          Einfach
        </button>
        <button
          type="button"
          className={`fc-mode-btn${detailMode ? ' active' : ''}`}
          onClick={() => setDetailMode(true)}
        >
          Volle Labor-Ansicht
        </button>
        <span className="fc-mode-hint">
          {detailMode
            ? 'Drei Streifen · Ephemeride · Q-Quantile · Vintage-Spuren'
            : 'Nur Q50 + HEUTE + Lead-Time — komplett ehrlich, weniger Noise'}
        </span>
      </div>

      {detailMode ? (
        <ForecastControls
          showVintage={showVintage}
          onToggleVintage={setShowVintage}
          vintageRunCount={vintageRuns.length}
          vintageLoading={vintageLoading}
        />
      ) : null}

      {vintagePayload?.reconciliation?.drift_detected ? (
        <DriftBanner
          mape={vintagePayload.reconciliation.mape}
          correlation={vintagePayload.reconciliation.correlation}
          samples={vintagePayload.reconciliation.samples}
          virusTyp={virusTyp}
        />
      ) : null}

      <StripChart
        timeline={timeline}
        vintageRuns={vintageRuns}
        showVintage={showVintage}
      />

      <EphemerisFoot
        leadLabel={leadHero.leadLabel}
        leadNote={leadHero.leadNote}
        observed={observedRows}
        forecast={forecastRows}
      />

      {detailMode ? (
        <ModelProofPanel
          data={backtestData}
          loading={backtestLoading}
          virusTyp={virusTyp}
        />
      ) : null}
    </section>
  );
};

export default ForecastSection;
