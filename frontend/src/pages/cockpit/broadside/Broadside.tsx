import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import type { CockpitSnapshot } from '../types';

import ChronoBar from './ChronoBar';
import DecisionSection from './DecisionSection';
import AtlasSection from './AtlasSection';
import ForecastSection from './ForecastSection';
import ImpactSection from './ImpactSection';
import BacktestSection from './BacktestSection';
import NextStepsSection from './NextStepsSection';
import CeoPitchMode from './CeoPitchMode';
import EvidenceStatusBar from './EvidenceStatusBar';
import VirusWaveEvidencePanel from './VirusWaveEvidencePanel';
import { sellOutWeeks } from './snapshotAccessors';

/**
 * Broadside — Story-Scroll-Renovation 2026-04-22.
 *
 * Header (sticky, 56px): Brand · KW-Ticker (±2) · Virus-Switcher.
 * Body: ExecutiveHero + sechs Sections (Atlas, Decision, Forecast,
 * Impact, Backtest, NextSteps).
 * Footer: technische Meta (EPOCH live · NEXT RUN · Quellen · DATA-Link).
 *
 * StatusStrip wurde aufgelöst — die fünf Status-Werte wandern nach
 * Phase 2 in den ExecutiveHero. EPOCH-Live-Counter und Next-Run-
 * Countdown sind in den Footer gewandert (waren vorher Quellen visueller
 * Unruhe in der Kopfzone).
 */

interface Props {
  snapshot: CockpitSnapshot;
  virusTyp: string;
  onVirusChange: (v: string) => void;
  supportedViruses: readonly string[];
  onReload?: () => void;
}

const PageFooter: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  return (
    <footer className="page-foot">
      <div>
        <b>ViralFlux · Cockpit</b>
        <div>Ausgabe 1.0.0 · {snapshot.isoWeek} · Quellen: AMELAG, SurvStat</div>
      </div>
      <div>
        <div>
          <Link to="/cockpit/data" className="page-foot-link">
            Data Office ↗
          </Link>
          {' · '}
          <a href="#sec-backtest" className="page-foot-link">Methodik ↗</a>
        </div>
        <div>
          <Link to="/cockpit/tri-layer" className="page-foot-link">
            Tri-Layer Research ↗
          </Link>
          {' · '}
          <Link to="/cockpit/phase-lead" className="page-foot-link">
            Regional Media Watch ↗
          </Link>
        </div>
      </div>
      <div className="col-right">
        <div>
          <b>Pilot mit {snapshot.client} Marketing</b>
        </div>
      </div>
    </footer>
  );
};

const CalibrationBanner: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const [closed, setClosed] = useState(false);
  if (closed || sellOutWeeks(snapshot) > 0) return null;
  return (
    <div className="calibration-banner" role="status">
      <span>
        Cockpit läuft im Kalibrierungsfenster. Erste GELO-CSV anschließen,
        um das Modell auf eure Realität zu kalibrieren
      </span>
      <Link to="/cockpit/data">Erste GELO-CSV anschließen</Link>
      <button
        type="button"
        aria-label="Kalibrierungsbanner schließen"
        onClick={() => setClosed(true)}
      >
        ×
      </button>
    </div>
  );
};

export const Broadside: React.FC<Props> = ({
  snapshot,
  virusTyp,
  onVirusChange,
  supportedViruses,
  onReload,
}) => {
  const kwMatch = snapshot.isoWeek.match(/\d+/);
  const currentKw = kwMatch ? parseInt(kwMatch[0], 10) : 1;

  return (
    <div className="peix-instr">
      <ChronoBar
        currentKw={currentKw}
        virusTyp={virusTyp}
        onVirusChange={onVirusChange}
        supportedViruses={supportedViruses}
      />
      <EvidenceStatusBar snapshot={snapshot} />
      <main className="page">
        <CalibrationBanner snapshot={snapshot} />
        <CeoPitchMode snapshot={snapshot} supportedViruses={supportedViruses} onReload={onReload} />
        <VirusWaveEvidencePanel snapshot={snapshot} />
        <AtlasSection snapshot={snapshot} />
        <ForecastSection snapshot={snapshot} />
        <BacktestSection snapshot={snapshot} />
        <DecisionSection snapshot={snapshot} />
        <ImpactSection snapshot={snapshot} />
        <NextStepsSection snapshot={snapshot} />
        <PageFooter snapshot={snapshot} />
      </main>
    </div>
  );
};

export default Broadside;
