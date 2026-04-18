import React, { useEffect } from 'react';

/**
 * Drawer — the right-side slide-in panel used for Atlas / Forecast /
 * Wirkung. Ported from the Claude Design handoff. Slides in from the
 * right, backdrop blurs the page behind it, ESC closes it, body scroll
 * is locked while open.
 *
 * The drawer lives at document level (fixed-positioned) so it's
 * intentionally rendered OUTSIDE .peix-exhibit — the CSS selectors for
 * .ex-drawer / .ex-drawer-backdrop are un-scoped, which is why we
 * keep those class names global.
 */

export type DrawerId = 'atlas' | 'forecast' | 'impact' | 'backtest' | null;

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  kicker: React.ReactNode;
  footLeft?: React.ReactNode;
  footRight?: React.ReactNode;
  stageVar?: boolean;            // dark background (Atlas)
  children: React.ReactNode;
}

export const Drawer: React.FC<DrawerProps> = ({
  open,
  onClose,
  title,
  kicker,
  footLeft,
  footRight,
  stageVar = false,
  children,
}) => (
  <>
    <div
      className={'ex-drawer-backdrop' + (open ? ' open' : '')}
      onClick={onClose}
    />
    <aside
      className={
        'ex-drawer' + (open ? ' open' : '') + (stageVar ? ' stage-var' : '')
      }
      aria-hidden={!open}
      role="dialog"
      aria-modal="true"
    >
      <header className="ex-drawer-head">
        <div>
          <div className="ex-kicker">{kicker}</div>
          <h3>{title}</h3>
        </div>
        <button type="button" className="ex-drawer-close" onClick={onClose}>
          × Schließen · Esc
        </button>
      </header>
      <div className="ex-drawer-body">{children}</div>
      <footer className="ex-drawer-foot">
        <span>{footLeft}</span>
        <span>{footRight}</span>
      </footer>
    </aside>
  </>
);

// --------------------------------------------------------------
// Drawer dock — the right-rail of Roman catalogue numbers.
// --------------------------------------------------------------
export const DrawerDock: React.FC<{
  onOpen: (id: Exclude<DrawerId, null>) => void;
}> = ({ onOpen }) => (
  <div className="ex-drawer-dock">
    <button type="button" className="ex-drawer-tab" onClick={() => onOpen('atlas')}>
      <span className="ex-tab-idx">II</span>Wellen-Atlas
    </button>
    <button type="button" className="ex-drawer-tab" onClick={() => onOpen('forecast')}>
      <span className="ex-tab-idx">III</span>Forecast
    </button>
    <button type="button" className="ex-drawer-tab" onClick={() => onOpen('impact')}>
      <span className="ex-tab-idx">IV</span>Wirkung
    </button>
    <button type="button" className="ex-drawer-tab" onClick={() => onOpen('backtest')}>
      <span className="ex-tab-idx">V</span>Backtest
    </button>
  </div>
);

// --------------------------------------------------------------
// useKey — small keyboard hook used by the shell (Esc → close).
// --------------------------------------------------------------
export function useKey(key: string, fn: (e: KeyboardEvent) => void): void {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === key) fn(e);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [key, fn]);
}

// --------------------------------------------------------------
// useBodyScrollLock — freezes the exhibit behind an open drawer so
// the backdrop's backdrop-filter doesn't get scrolled out from
// under the user.
// --------------------------------------------------------------
export function useBodyScrollLock(locked: boolean): void {
  useEffect(() => {
    if (!locked) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [locked]);
}
