import React, { useCallback, useState } from 'react';
import '../../styles/peix.css';
import '../../styles/peix-gate.css';
import '../../styles/peix-exhibit.css';

import CockpitGate from './CockpitGate';
import { useCockpitSnapshot } from './useCockpitSnapshot';
import { Exhibit } from './exhibit/Exhibit';
import { DrawerDock, useBodyScrollLock, useKey } from './exhibit/Drawer';
import { AtlasDrawer } from './exhibit/AtlasDrawer';
import { ForecastDrawer } from './exhibit/ForecastDrawer';
import { ImpactDrawer } from './exhibit/ImpactDrawer';
import { BacktestDrawer } from './exhibit/BacktestDrawer';

/**
 * CockpitShell — the single user-facing surface.
 *
 * Gallery-refresh (2026-04-17) renamed as Museum-Exhibit edition
 * (2026-04-18) per the Claude Design handoff bundle
 * cFK0P9N815z30StKWtXAHw. The shell is now:
 *
 *   - one Exhibit screen (TopChrome, Hero, Rationale, Candidates,
 *     FootRail) as the single editorial voice
 *   - a drawer dock on the right (II Wellen-Atlas / III Forecast /
 *     IV Wirkung) with Roman catalogue numbers
 *   - three drawers that slide in over the exhibit with Esc + backdrop
 *     dismiss
 *
 * No tabs. No virus toggle. No separate masthead. The four pieces of
 * the week are hierarchised: the recommendation is the hauptakt, the
 * rest is evidence.
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

  // 401 → render the gate. SWR doesn't expose status on the Error, but
  // the snapshot hook prefixes "HTTP 401" into the message on unauth.
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

  return <CockpitExhibit snapshot={snapshot} />;
};

// --------------------------------------------------------------
// Inner shell — receives the resolved snapshot and wires the drawer
// dock + three drawers. Kept as a separate component so the useState /
// useKey / useBodyScrollLock hooks don't fire during the loading /
// error / gate branches above.
// --------------------------------------------------------------
const CockpitExhibit: React.FC<{
  snapshot: NonNullable<ReturnType<typeof useCockpitSnapshot>['snapshot']>;
}> = ({ snapshot }) => {
  const [openDrawer, setOpenDrawer] = useState<
    'atlas' | 'forecast' | 'impact' | 'backtest' | null
  >(null);

  const close = useCallback(() => setOpenDrawer(null), []);
  useKey('Escape', close);
  useBodyScrollLock(openDrawer !== null);

  return (
    <>
      <Exhibit snapshot={snapshot} onOpenDrawer={setOpenDrawer} />
      <DrawerDock onOpen={setOpenDrawer} />
      <AtlasDrawer
        open={openDrawer === 'atlas'}
        onClose={close}
        snapshot={snapshot}
      />
      <ForecastDrawer
        open={openDrawer === 'forecast'}
        onClose={close}
        snapshot={snapshot}
      />
      <ImpactDrawer
        open={openDrawer === 'impact'}
        onClose={close}
        snapshot={snapshot}
      />
      <BacktestDrawer
        open={openDrawer === 'backtest'}
        onClose={close}
        virusLabel={snapshot.virusLabel}
        virusTyp={snapshot.virusTyp}
      />
    </>
  );
};

export default CockpitShell;
