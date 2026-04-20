import React from 'react';
import type { CockpitSnapshot } from '../types';

import ChronoBar from './ChronoBar';
import DecisionSection from './DecisionSection';
import AtlasSection from './AtlasSection';
import ForecastSection from './ForecastSection';
import ImpactSection from './ImpactSection';
import BacktestSection from './BacktestSection';

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

export const Broadside: React.FC<Props> = ({ snapshot }) => {
  const kwMatch = snapshot.isoWeek.match(/\d+/);
  const currentKw = kwMatch ? parseInt(kwMatch[0], 10) : 1;

  return (
    <div className="peix-instr">
      <ChronoBar currentKw={currentKw} client={snapshot.client} />
      <main className="page">
        <DecisionSection snapshot={snapshot} />
        <AtlasSection snapshot={snapshot} />
        <ForecastSection snapshot={snapshot} />
        <ImpactSection snapshot={snapshot} />
        <BacktestSection snapshot={snapshot} />
        <PageFooter snapshot={snapshot} />
      </main>
    </div>
  );
};

export default Broadside;
