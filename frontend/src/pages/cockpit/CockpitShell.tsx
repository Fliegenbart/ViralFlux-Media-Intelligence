import React, { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import '../../styles/peix.css';
import '../../styles/peix-honesty.css';
import '../../styles/peix-sculpture.css';
import '../../styles/peix-timeline.css';

import Masthead from '../../components/cockpit/peix/Masthead';
import CockpitTabs, { type TabId } from '../../components/cockpit/peix/CockpitTabs';
import DecisionPage from './DecisionPage';
import AtlasPage from './AtlasPage';
import TimelinePage from './TimelinePage';
import ImpactPage from './ImpactPage';
import { useCockpitSnapshot } from './useCockpitSnapshot';

/**
 * Self-contained shell that bypasses the existing MediaShell/AppLayout.
 * The cockpit now fetches a live payload from
 * GET /api/v1/media/cockpit/snapshot?virus_typ=...
 *
 * After the 2026-04-16 math audit two UI-ehrlichkeits elements were added:
 *   1. Virus toggle (Influenza A regional / RSV A national).
 *   2. A modelStatus banner that surfaces WATCH readiness, uncalibrated
 *      signal warnings and "model loses to persistence" notes directly to
 *      the user.
 *
 * No silent fallback to a local fixture — if the API fails the UI renders
 * an explicit error state.
 */

type VirusOption = {
  value: 'Influenza A' | 'RSV A';
  label: string;
  hint: string;
};

const VIRUS_OPTIONS: VirusOption[] = [
  { value: 'Influenza A', label: 'Influenza A', hint: 'regional (16 BL)' },
  { value: 'RSV A', label: 'RSV A', hint: 'national, BL-Layer aus' },
];

function calibrationLabel(mode: string | undefined): string {
  switch (mode) {
    case 'calibrated':
      return 'kalibriert';
    case 'heuristic':
      return 'heuristisch (Sigmoid)';
    case 'skipped':
      return 'Kalibrierung übersprungen';
    default:
      return 'unbekannt';
  }
}

function readinessLabel(readiness: string | undefined): string {
  switch (readiness) {
    case 'GO_RANKING':
      return 'GO · Ranking';
    case 'RANKING_OK':
      return 'Ranking OK';
    case 'LEAD_ONLY':
      return 'Lead-Time';
    case 'WATCH':
      return 'Watch';
    default:
      return 'Unbekannt';
  }
}

function readinessBadgeClass(readiness: string | undefined): string {
  switch (readiness) {
    case 'GO_RANKING':
      return 'peix-readiness peix-readiness--go';
    case 'RANKING_OK':
    case 'LEAD_ONLY':
      return 'peix-readiness peix-readiness--watch';
    case 'WATCH':
      return 'peix-readiness peix-readiness--hold';
    default:
      return 'peix-readiness peix-readiness--unknown';
  }
}

function fmtPctValue(v: number | null | undefined, digits = 0): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  return `${(v * 100).toFixed(digits)} %`;
}

function fmtNumber(v: number | null | undefined, digits = 2): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  return v.toFixed(digits);
}

const ModelStatusBanner: React.FC<{ status: import('./types').ModelStatus; notes: string[] }> = ({
  status,
  notes,
}) => {
  const ranking = status.ranking;
  const lead = status.lead;
  return (
    <div className="peix-model-status" role="status">
      <div className="peix-model-status__header">
        <span className={readinessBadgeClass(status.forecastReadiness)}>
          {readinessLabel(status.forecastReadiness)}
        </span>
        <span className="peix-kicker">
          {status.virusTyp} · Lead-Story gegen {lead?.targetLabel ?? '—'} · Kalibrierung: {calibrationLabel(status.calibrationMode)}
        </span>
      </div>

      <div className="peix-model-status__grid">
        <div className="peix-model-status__col">
          <div className="peix-model-status__col-kicker">BL-Ranking · {ranking?.horizonDays ?? 7} Tage</div>
          <div className="peix-model-status__col-headline">
            {ranking?.precisionAtTop3 !== null && ranking?.precisionAtTop3 !== undefined
              ? `${fmtPctValue(ranking.precisionAtTop3)} Top-3-Präzision`
              : 'Ranking-Metriken liegen nicht vor'}
          </div>
          <div className="peix-model-status__col-sub">
            PR-AUC {fmtNumber(ranking?.prAuc)} · ECE {fmtNumber(ranking?.ece, 3)}
          </div>
          <div className="peix-model-status__col-footnote">
            Quelle: {ranking?.sourceLabel ?? 'regionales Panel'}
          </div>
        </div>
        <div className="peix-model-status__divider" aria-hidden />
        <div className="peix-model-status__col">
          <div className="peix-model-status__col-kicker">
            Lead-Zeit · {lead?.horizonDays ?? 14} Tage
          </div>
          <div className="peix-model-status__col-headline">
            {typeof lead?.bestLagDays === 'number'
              ? lead.bestLagDays >= 0
                ? `${lead.bestLagDays === 0 ? '0' : `+${lead.bestLagDays}`} Tage Vorlauf`
                : `${lead.bestLagDays} Tage Lag`
              : 'Lead-Metriken liegen nicht vor'}
            {lead?.correlationAtHorizon !== null && lead?.correlationAtHorizon !== undefined
              ? ` · corr ${fmtNumber(lead.correlationAtHorizon)}`
              : ''}
          </div>
          <div className="peix-model-status__col-sub">
            vs. Persistence {lead?.maeVsPersistencePct !== null && lead?.maeVsPersistencePct !== undefined
              ? `${lead.maeVsPersistencePct > 0 ? '+' : ''}${lead.maeVsPersistencePct.toFixed(1)} %`
              : '—'}
            {lead?.intervalCoverage80Pct
              ? ` · Abdeckung 80 % ≈ ${lead.intervalCoverage80Pct.toFixed(1)} %`
              : ''}
          </div>
          <div className="peix-model-status__col-footnote">
            Gegen {lead?.targetLabel ?? '—'}
          </div>
        </div>
      </div>

      {(notes.length > 0 || status.note) && (
        <ul className="peix-model-status__list">
          {status.note && <li>{status.note}</li>}
          {notes.map((note, idx) => (
            <li key={`note-${idx}`}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
};

const VirusToggle: React.FC<{
  value: VirusOption['value'];
  onChange: (value: VirusOption['value']) => void;
}> = ({ value, onChange }) => (
  <div className="peix-virus-toggle" role="tablist" aria-label="Virus-Scope">
    {VIRUS_OPTIONS.map((option) => (
      <button
        key={option.value}
        type="button"
        role="tab"
        aria-selected={value === option.value}
        className={
          value === option.value
            ? 'peix-virus-toggle__btn peix-virus-toggle__btn--active'
            : 'peix-virus-toggle__btn'
        }
        onClick={() => onChange(option.value)}
      >
        <span>{option.label}</span>
        <small>{option.hint}</small>
      </button>
    ))}
  </div>
);

export const CockpitShell: React.FC = () => {
  const [virusTyp, setVirusTyp] = useState<VirusOption['value']>('Influenza A');
  const { snapshot, loading, error, reload } = useCockpitSnapshot({
    virusTyp,
    horizonDays: 14,
    leadTarget: 'ATEMWEGSINDEX',
  });
  const [tab, setTab] = useState<TabId>('decision');

  if (loading && !snapshot) {
    return (
      <div className="peix">
        <div className="peix-shell" style={{ padding: 80, textAlign: 'center' }}>
          <span className="peix-kicker">loading cockpit…</span>
        </div>
      </div>
    );
  }

  if (error && !snapshot) {
    return (
      <div className="peix">
        <div className="peix-shell" style={{ padding: 80 }}>
          <span className="peix-kicker">Cockpit nicht verfügbar</span>
          <p style={{ marginTop: 12 }}>
            Der Cockpit-Endpoint antwortet gerade nicht. Das Cockpit fällt bewusst
            <strong> nicht </strong> auf alte Fixture-Zahlen zurück, weil das Produktions-Konfidenz
            vortäuschen würde. Fehlermeldung: {error.message}
          </p>
          <button type="button" onClick={reload} style={{ marginTop: 12 }}>
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  if (!snapshot) {
    return null;
  }

  return (
    <div className="peix">
      <div className="peix-shell">
        <Masthead
          client={snapshot.client}
          virusLabel={snapshot.virusLabel}
          isoWeek={snapshot.isoWeek}
          generatedAt={snapshot.generatedAt}
        />
        <VirusToggle value={virusTyp} onChange={setVirusTyp} />
        <ModelStatusBanner status={snapshot.modelStatus} notes={snapshot.notes} />
        <CockpitTabs active={tab} onChange={setTab} />

        <AnimatePresence mode="wait">
          {tab === 'decision' && <DecisionPage key="decision" snapshot={snapshot} />}
          {tab === 'atlas' && <AtlasPage key="atlas" snapshot={snapshot} />}
          {tab === 'timeline' && <TimelinePage key="timeline" snapshot={snapshot} />}
          {tab === 'impact' && <ImpactPage key="impact" snapshot={snapshot} />}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default CockpitShell;
