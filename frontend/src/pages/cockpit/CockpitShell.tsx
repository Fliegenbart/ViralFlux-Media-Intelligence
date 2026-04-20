import React from 'react';
import '../../styles/peix.css';
import '../../styles/peix-gate.css';
import '../../styles/peix-exhibit.css';
import '../../styles/peix-instr.css';

import CockpitGate from './CockpitGate';
import { useCockpitSnapshot } from './useCockpitSnapshot';
import { Broadside } from './broadside/Broadside';

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
  const { snapshot, loading, error, reload } = useCockpitSnapshot({
    virusTyp: 'Influenza A',
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
          className="peix-shell"
          style={{ padding: 80, textAlign: 'center' }}
        >
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
            Der Cockpit-Endpoint antwortet gerade nicht. Das Cockpit fällt
            bewusst <strong>nicht</strong> auf alte Fixture-Zahlen
            zurück, weil das Produktions-Konfidenz vortäuschen würde.
            Fehlermeldung: {error.message}
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

  return <Broadside snapshot={snapshot} />;
};

export default CockpitShell;
