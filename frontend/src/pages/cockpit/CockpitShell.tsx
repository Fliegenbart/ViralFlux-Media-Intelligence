import React, { useState } from 'react';
import '../../styles/peix.css';
import '../../styles/peix-gate.css';
import '../../styles/peix-exhibit.css';
import '../../styles/peix-instr.css';

import CockpitGate from './CockpitGate';
import { useCockpitSnapshot } from './useCockpitSnapshot';
import { Broadside } from './broadside/Broadside';

/**
 * Default virus at page load. Influenza B is today's strongest
 * combination of (RANKING_OK gate, no drift, MAPE 30 %, N=103) — the
 * "best data basis" rule. Deliberate static choice: the persona
 * walkthrough called it out, the composite score confirmed it. Review
 * monthly; a backend /virus-readiness endpoint that picks the
 * default dynamically is on the backlog.
 */
/**
 * 2026-04-20 Pitch-Revision: Default = Influenza A (Hero-Virus mit
 * höchster Korrelation 0.76 und dem kommerziell dominanten Produkt-
 * Portfolio bei GELO). SARS-CoV-2 aus dem Switcher entfernt — MAPE
 * 168 % + drift macht es für den Pitch eine Angriffsfläche ohne
 * Gegenwert. Flu B bleibt als zweite Flu-Linie (Breit-Portfolio),
 * RSV A als Pilot-Beispiel.
 */
const DEFAULT_VIRUS = 'Influenza A';
export const SUPPORTED_VIRUSES: readonly string[] = [
  'Influenza A',
  'Influenza B',
  'RSV A',
];

/**
 * CockpitShell — the single user-facing surface.
 *
 * Broadside-refresh (2026-04-18 evening):
 *   - Replaced the Exhibit + Drawer-Dock architecture with a one-page
 *     scrolling Broadside. All five sections (§ I Entscheidung,
 *     § II Wellen-Atlas, § III Forecast, § IV Wirkung, § V Backtest)
 *     are visible on scroll; a floating section-index at the right
 *     margin provides quick jumps with scroll-spy highlighting.
 *   - The previous Drawer components (AtlasDrawer, ForecastDrawer,
 *     ImpactDrawer, BacktestDrawer) live on as legacy exports for
 *     their Body components — which the Broadside reuses — but are
 *     no longer wired into the UI.
 *
 * Auth / gate behaviour is unchanged — a 401 from the snapshot fetch
 * renders <CockpitGate /> (shared-password flow).
 */

export const CockpitShell: React.FC = () => {
  const [virusTyp, setVirusTyp] = useState<string>(DEFAULT_VIRUS);
  const { snapshot, loading, error, reload } = useCockpitSnapshot({
    virusTyp,
    horizonDays: 14,
    leadTarget: 'ATEMWEGSINDEX',
  });

  const isAuth401 =
    error &&
    (((error as Error & { status?: number }).status === 401) ||
      /HTTP 401/.test(error.message));
  if (isAuth401 && !snapshot) {
    return <CockpitGate />;
  }

  if (loading && !snapshot) {
    return (
      <div className="peix">
        <div
          className="peix-shell flux-loading"
          style={{
            padding: '0 40px',
            textAlign: 'center',
            minHeight: '100svh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <div className="flux-loading-field" aria-hidden="true">
            <span className="flux-loading-ring ring-a" />
            <span className="flux-loading-ring ring-b" />
            <span className="flux-loading-ring ring-c" />
          </div>
          <div className="flux-loading-mark">◆</div>
        </div>
      </div>
    );
  }

  if (error && !snapshot) {
    return (
      <div className="peix">
        <div className="peix-shell" style={{ padding: 80 }}>
          <span className="peix-kicker">Cockpit nicht erreichbar</span>
          <p style={{ marginTop: 12 }}>
            Wir laden gerade einen sauberen Snapshot. Bitte gleich erneut
            versuchen — wir zeigen euch keine alten Zahlen, nur weil das
            einfacher wäre. Fehlermeldung: {error.message}
          </p>
          <button
            type="button"
            onClick={reload}
            style={{ marginTop: 12 }}
          >
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  if (!snapshot) return null;

  return (
    <Broadside
      snapshot={snapshot}
      virusTyp={virusTyp}
      onVirusChange={setVirusTyp}
      supportedViruses={SUPPORTED_VIRUSES}
      onReload={reload}
    />
  );
};

export default CockpitShell;
