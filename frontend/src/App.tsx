import React, { useEffect, useState, Suspense, lazy } from 'react';
import { BrowserRouter as Router, Navigate, Route, Routes } from 'react-router-dom';

import ErrorBoundary from './components/ErrorBoundary';
import LoadingSkeleton from './components/LoadingSkeleton';
import {
  ThemeContext,
  ToastContext,
  type Theme,
  useToastController,
} from './lib/appContext';
import './index.css';

/**
 * App router — radically simplified on 2026-04-17.
 *
 * Until today the app carried an internal Media-Suite with login, /virus-radar,
 * /jetzt, /zeitgraph, /regionen, /kampagnen, /evidenz, etc. The product has
 * converged on the /cockpit view as the single user-facing surface for the
 * GELO pilot, and everything else is being retired.
 *
 * What this router does now:
 *   - / → /cockpit
 *   - /cockpit → the editorial cockpit (its own password gate handles access)
 *   - every retired route → /cockpit (soft redirect so old links don't 404)
 *
 * The underlying lazy-loaded Media pages are left in the codebase for now so
 * we can resurrect them if needed, but nothing in the router references
 * them any more. The bundler will tree-shake them out of the deployed
 * bundle.
 */

const CockpitShell = lazy(() => import('./pages/cockpit/CockpitShell'));
const DataOfficePage = lazy(() => import('./pages/cockpit/data/DataOfficePage'));

const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem('viralflux-theme');
    return stored === 'dark' ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('viralflux-theme', theme);
  }, [theme]);

  const toggle = () => setTheme((current) => (current === 'light' ? 'dark' : 'light'));

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
};

const PageFallback: React.FC = () => (
  <div style={{ padding: 32 }}>
    <LoadingSkeleton lines={6} />
  </div>
);

// Every retired route that used to exist ends up here. Keeps old bookmarks
// and existing links (including any internal /login redirects) pointing at
// the single live surface instead of returning a blank 404.
const RETIRED_ROUTES = [
  '/login',
  '/welcome',
  '/virus-radar',
  '/jetzt',
  '/zeitgraph',
  '/regionen',
  '/kampagnen',
  '/kampagnen/:id',
  '/evidenz',
  '/dashboard',
  '/dashboard/recommendations/:id',
  '/entscheidung',
  '/lagebild',
  '/pilot',
  '/bericht',
  '/empfehlungen',
  '/empfehlungen/:id',
  '/validierung',
  '/backtest',
];

const App: React.FC = () => {
  const { toasts, addToast, removeToast } = useToastController();

  return (
    <ThemeProvider>
      <ErrorBoundary>
        <ToastContext.Provider value={{ toast: addToast }}>
          <Router>
            <Suspense fallback={<PageFallback />}>
              <Routes>
                <Route path="/" element={<Navigate to="/cockpit" replace />} />
                <Route path="/cockpit" element={<CockpitShell />} />
                <Route path="/cockpit/data" element={<DataOfficePage />} />
                {RETIRED_ROUTES.map((path) => (
                  <Route
                    key={path}
                    path={path}
                    element={<Navigate to="/cockpit" replace />}
                  />
                ))}
                <Route path="*" element={<Navigate to="/cockpit" replace />} />
              </Routes>
            </Suspense>
          </Router>
        </ToastContext.Provider>
        <div
          className="toast-stack"
          aria-live="polite"
          style={{
            position: 'fixed',
            top: 136,
            right: 24,
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
            pointerEvents: 'none',
            maxWidth: 360,
          }}
        >
          {toasts.map((toast) => (
            <div
              key={toast.id}
              role="status"
              className={`toast toast--${toast.type}`}
              onClick={() => removeToast(toast.id)}
              style={{ pointerEvents: 'auto' }}
            >
              {toast.message}
            </div>
          ))}
        </div>
      </ErrorBoundary>
    </ThemeProvider>
  );
};

export default App;
