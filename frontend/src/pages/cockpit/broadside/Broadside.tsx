import React from 'react';
import type { CockpitSnapshot } from '../types';

import ChronoBar from './ChronoBar';
import DecisionSection from './DecisionSection';
import AtlasSection from './AtlasSection';
import ForecastSection from './ForecastSection';
import ImpactSection from './ImpactSection';
import BacktestSection from './BacktestSection';
import NextStepsSection from './NextStepsSection';
import ExecutiveHero from './ExecutiveHero';

/**
 * StatusStrip — a compact "ja, das läuft"-Zeile unter der ChronoBar.
 * Beantwortet ohne Scroll die Frage "was seh ich hier": wie viele
 * Viren, wie viel regionale Tiefe, welcher Horizont, Outcome-State.
 * Pitch-orientiert.
 */
const StatusStrip: React.FC<{ snapshot: CockpitSnapshot; supportedViruses: readonly string[] }> = ({
  snapshot,
  supportedViruses,
}) => {
  const activeRegions = snapshot.regions.filter(
    (r) => r.decisionLabel !== 'TrainingPending',
  ).length;
  const totalRegions = snapshot.regions.length || 16;
  const horizon = snapshot.modelStatus?.horizonDays ?? 14;
  const outcomeConnected = snapshot.mediaPlan?.connected === true;
  return (
    <div className="status-strip">
      <div className="status-strip-inner">
        <div className="status-cell">
          <span className="status-label">Viren live</span>
          <span className="status-value">{supportedViruses.length} / 4</span>
        </div>
        <div className="status-cell">
          <span className="status-label">Regional ({snapshot.virusLabel ?? snapshot.virusTyp})</span>
          <span className="status-value">
            {activeRegions} / 16 Bundesländer
          </span>
        </div>
        <div className="status-cell">
          <span className="status-label">Forecast-Horizont</span>
          <span className="status-value">{horizon} Tage</span>
        </div>
        <div className="status-cell">
          <span className="status-label">Outcome-Loop</span>
          <span className={`status-value${outcomeConnected ? ' ok' : ' waiting'}`}>
            {outcomeConnected ? 'verbunden' : 'bereit · wartet auf CSV'}
          </span>
        </div>
      </div>
    </div>
  );
};

/**
 * Broadside — Instrumentation-Redesign 2026-04-18.
 *
 * Aesthetic: wissenschaftliches Messinstrument, nicht SaaS-Dashboard.
 * Der Layout-Rahmen ist radikal ruhig: ein sticky Chrono-Bar oben
 * (live Epoch + KW-Ticker + Next-Run), fünf Kapitel I…V stacked,
 * am Ende ein Redaktions-Footer. Kein floating TOC, keine Punk-Badges,
 * keine editorialen Serifen.
 *
 * Drei idiosynkratische Moves (pro Section):
 *   § I  Vernier-Skala für Konfidenz
 *   § II Atlas-HUD mit Corner-Brackets + Riser-Ticker
 *   § III SVG Fan-Chart mit HEUTE-Zäsur (dunkles Label-Rect oben)
 *
 * Palette strikt 5 Farben:
 *   Paper #F4F1EA · Ink #0D0F12 · Slate #4A5261
 *   Signal-Terracotta #C2542A · Oxid-Salbei #8B9788
 *
 * Typo: Supreme (Display) + General Sans (Body) + JetBrains Mono
 * (Ticks/Koordinaten). Alle Fontshare/Google, kostenlos.
 */

interface Props {
  snapshot: CockpitSnapshot;
  virusTyp: string;
  onVirusChange: (v: string) => void;
  supportedViruses: readonly string[];
}

const PageFooter: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const generated = snapshot.generatedAt ? new Date(snapshot.generatedAt) : null;
  const generatedLabel = generated
    ? generated.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      })
    : '—';

  const calibMode =
    snapshot.modelStatus?.calibrationMode === 'calibrated'
      ? 'isotonic'
      : snapshot.modelStatus?.calibrationMode === 'heuristic'
        ? 'heuristisch'
        : '—';
  const folds =
    snapshot.modelStatus?.ranking?.dataPoints ??
    snapshot.modelStatus?.lead?.horizonDays ??
    '—';

  const trainingPanel = snapshot.modelStatus?.trainingPanel;
  const trainingLabel = trainingPanel && trainingPanel.maturityTier !== 'unknown'
    ? `Training-Panel: ${trainingPanel.maturityLabel}`
    : null;

  return (
    <footer className="page-foot">
      <div>
        <div>
          <b>ViralFlux · Cockpit</b>
        </div>
        <div>Ausgabe {snapshot.isoWeek} · {generatedLabel}</div>
        <div>peix gmbh · Berlin</div>
      </div>
      <div>
        <div>Quellen</div>
        <div>RKI SURVSTAT · AI-AKI ED · {snapshot.client}-Media-Plan</div>
        <div>
          Kalibrierung: {calibMode}, {folds} Walk-forward Folds
        </div>
        {trainingLabel ? <div>{trainingLabel}</div> : null}
      </div>
      <div className="col-right">
        <div>Präsentiert für</div>
        <div>
          <b>{snapshot.client} · Marketing</b>
        </div>
        <div>Vertraulich · Pitch-Asset</div>
      </div>
    </footer>
  );
};

export const Broadside: React.FC<Props> = ({
  snapshot,
  virusTyp,
  onVirusChange,
  supportedViruses,
}) => {
  const kwMatch = snapshot.isoWeek.match(/\d+/);
  const currentKw = kwMatch ? parseInt(kwMatch[0], 10) : 1;

  return (
    <div className="peix-instr">
      <ChronoBar
        currentKw={currentKw}
        client={snapshot.client}
        virusTyp={virusTyp}
        onVirusChange={onVirusChange}
        supportedViruses={supportedViruses}
      />
      <StatusStrip snapshot={snapshot} supportedViruses={supportedViruses} />
      <main className="page">
        <ExecutiveHero snapshot={snapshot} />
        {/* 2026-04-20: Atlas promoted to § I — the 3D wave map is the
            consistent aha-moment for first-time readers (confirmed during
            persona walkthrough). Decision follows as § II because the
            recommendation reads as the verdict after the evidence. */}
        <AtlasSection snapshot={snapshot} />
        <DecisionSection snapshot={snapshot} />
        <ForecastSection snapshot={snapshot} />
        <ImpactSection snapshot={snapshot} />
        <BacktestSection snapshot={snapshot} />
        <NextStepsSection snapshot={snapshot} />
        <PageFooter snapshot={snapshot} />
      </main>
    </div>
  );
};

export default Broadside;
