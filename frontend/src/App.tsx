import React, { useEffect, useState, Suspense, lazy } from 'react';
import { BrowserRouter as Router, Navigate, Outlet, Route, Routes, useLocation, useParams } from 'react-router-dom';

import ErrorBoundary from './components/ErrorBoundary';
import LoadingSkeleton from './components/LoadingSkeleton';
import {
  AuthContext,
  ThemeContext,
  ToastContext,
  type Theme,
  useAuthController,
  useToastController,
} from './lib/appContext';
import LoginPage from './pages/LoginPage';
import './index.css';

const MediaShell = lazy(() => import('./pages/media/MediaShell'));
const NowPage = lazy(() => import('./pages/media/NowPage'));
const VirusRadarPage = lazy(() => import('./pages/media/VirusRadarPage'));
const TimegraphPage = lazy(() => import('./pages/media/TimegraphPage'));
const RegionsPage = lazy(() => import('./pages/media/RegionsPage'));
const CampaignsPage = lazy(() => import('./pages/media/CampaignsPage'));
const EvidencePage = lazy(() => import('./pages/media/EvidencePage'));

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

const LegacyRecommendationRedirect: React.FC = () => {
  const { id } = useParams<{ id?: string }>();
  return <Navigate to={id ? `/kampagnen/${id}` : '/kampagnen'} replace />;
};

const RootRoute: React.FC<{ authenticated: boolean }> = ({ authenticated }) => (
  authenticated ? <Navigate to="/virus-radar" replace /> : <Navigate to="/login" replace />
);

const LoginRoute: React.FC<{ authenticated: boolean; onLogin: () => void }> = ({
  authenticated,
  onLogin,
}) => {
  const location = useLocation();
  const from = (location.state as { from?: { pathname: string; search: string; hash: string } } | null)?.from;
  const target = from ? `${from.pathname}${from.search}${from.hash}` : '/virus-radar';

  return authenticated ? <Navigate to={target} replace /> : <LoginPage onLogin={onLogin} />;
};

const ProtectedRoute: React.FC<{ authenticated: boolean; children: React.ReactElement }> = ({
  authenticated,
  children,
}) => {
  const location = useLocation();

  return authenticated ? children : <Navigate to="/login" replace state={{ from: location }} />;
};

const PageFallback: React.FC = () => (
  <div style={{ padding: 32 }}>
    <LoadingSkeleton lines={6} />
  </div>
);

const App: React.FC = () => {
  const { authenticated, authReady, handleLogin, handleLogout } = useAuthController();
  const { toasts, addToast, removeToast } = useToastController();

  if (!authReady) {
    return (
      <ThemeProvider>
        <PageFallback />
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <ErrorBoundary>
        <ToastContext.Provider value={{ toast: addToast }}>
          <AuthContext.Provider value={{ authenticated, handleLogin, handleLogout }}>
            <Router>
              <Suspense fallback={<PageFallback />}>
                <Routes>
                  <Route path="/" element={<RootRoute authenticated={authenticated} />} />
                  <Route path="/welcome" element={<Navigate to="/login" replace />} />
                  <Route
                    path="/login"
                    element={<LoginRoute authenticated={authenticated} onLogin={handleLogin} />}
                  />
                  <Route
                    element={(
                      <ProtectedRoute authenticated={authenticated}>
                        <Outlet />
                      </ProtectedRoute>
                    )}
                  >
                    <Route element={<MediaShell />}>
                      <Route path="/virus-radar" element={<VirusRadarPage />} />
                      <Route path="/jetzt" element={<NowPage />} />
                      <Route path="/zeitgraph" element={<TimegraphPage />} />
                      <Route path="/regionen" element={<RegionsPage />} />
                    <Route path="/kampagnen" element={<CampaignsPage />} />
                    <Route path="/kampagnen/:id" element={<CampaignsPage />} />
                    <Route path="/evidenz" element={<EvidencePage />} />
                  </Route>
                    <Route path="/dashboard" element={<Navigate to="/virus-radar" replace />} />
                    <Route path="/entscheidung" element={<Navigate to="/virus-radar" replace />} />
                    <Route path="/lagebild" element={<Navigate to="/virus-radar" replace />} />
                    <Route path="/pilot" element={<Navigate to="/virus-radar" replace />} />
                    <Route path="/bericht" element={<Navigate to="/virus-radar" replace />} />
                    <Route path="/empfehlungen" element={<Navigate to="/kampagnen" replace />} />
                    <Route path="/empfehlungen/:id" element={<LegacyRecommendationRedirect />} />
                    <Route path="/validierung" element={<Navigate to="/evidenz" replace />} />
                    <Route path="/dashboard/recommendations/:id" element={<LegacyRecommendationRedirect />} />
                    <Route path="/backtest" element={<Navigate to="/evidenz" replace />} />
                  </Route>
                </Routes>
              </Suspense>
            </Router>
          </AuthContext.Provider>
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
              onClick={() => removeToast(toast.id)}
              className={`toast-notification toast-${toast.type}`}
              style={{ pointerEvents: 'auto' }}
            >
              <span className="toast-icon">
                {toast.type === 'success' && '\u2713'}
                {toast.type === 'error' && '\u2717'}
                {toast.type === 'info' && '\u24D8'}
              </span>
              {toast.message}
            </div>
          ))}
        </div>
      </ErrorBoundary>
    </ThemeProvider>
  );
};

export { useTheme, useToast, useAuth } from './lib/appContext';

export default App;
