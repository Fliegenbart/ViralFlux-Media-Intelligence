import React, { useEffect, useState } from 'react';
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

function fmtNextMondayCountdown(now: Date): string {
  const next = new Date(now);
  const dow = now.getDay();
  const daysToMon = ((8 - dow) % 7) || 7;
  next.setDate(next.getDate() + daysToMon);
  next.setHours(8, 0, 0, 0);
  const diffMs = Math.max(0, next.getTime() - now.getTime());
  const d = Math.floor(diffMs / 86_400_000);
  const h = String(Math.floor((diffMs % 86_400_000) / 3_600_000)).padStart(2, '0');
  const m = String(Math.floor((diffMs % 3_600_000) / 60_000)).padStart(2, '0');
  const s = String(Math.floor((diffMs % 60_000) / 1000)).padStart(2, '0');
  return `${d}d ${h}:${m}:${s}`;
}

const FooterTicker: React.FC = () => {
  const [now, setNow] = useState<Date>(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <>
      <div>
        EPOCH <b>{Math.floor(now.getTime() / 1000)}</b>
      </div>
      <div>
        NEXT RUN <b>{fmtNextMondayCountdown(now)}</b>
      </div>
    </>
  );
};

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
  const trainingLabel =
    trainingPanel && trainingPanel.maturityTier !== 'unknown'
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
        <FooterTicker />
      </div>
      <div>
        <div>Quellen</div>
        <div>RKI SURVSTAT · AI-AKI ED · {snapshot.client}-Media-Plan</div>
        <div>
          Kalibrierung: {calibMode}, {folds} Walk-forward Folds
        </div>
        {trainingLabel ? <div>{trainingLabel}</div> : null}
        <div>
          <Link to="/cockpit/data" className="page-foot-link">
            Data Office ↗
          </Link>
        </div>
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
