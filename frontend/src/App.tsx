import React, { createContext, useCallback, useContext, useEffect, useRef, useState, Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useParams } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import ErrorBoundary from './components/ErrorBoundary';
import LoadingSkeleton from './components/LoadingSkeleton';
import { isAuthenticated, logout } from './lib/api';
import './index.css';

/* ── Lazy-loaded pages (code splitting) ────────────────────────── */
const LandingPage = lazy(() => import('./pages/LandingPage'));
const WeeklyReport = lazy(() => import('./pages/WeeklyReport'));
const MediaShell = lazy(() => import('./pages/media/MediaShell'));
const OperationalDashboardPage = lazy(() => import('./pages/media/OperationalDashboardPage'));
const DecisionPage = lazy(() => import('./pages/media/DecisionPage'));
const RegionsPage = lazy(() => import('./pages/media/RegionsPage'));
const CampaignsPage = lazy(() => import('./pages/media/CampaignsPage'));
const EvidencePage = lazy(() => import('./pages/media/EvidencePage'));

/* ── Theme ──────────────────────────────────────────────────────── */
type Theme = 'light' | 'dark';

const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({
  theme: 'light',
  toggle: () => {},
});

export const useTheme = () => useContext(ThemeContext);

const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem('viralflux-theme');
    return stored === 'dark' ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('viralflux-theme', theme);
  }, [theme]);

  const toggle = () => setTheme((t) => (t === 'light' ? 'dark' : 'light'));

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
};

/* ── Toast Notifications ────────────────────────────────────────── */
type ToastType = 'success' | 'error' | 'info';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

export const useToast = () => useContext(ToastContext);

let _nextToastId = 0;

const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const removeToast = useCallback((id: number) => {
    const timer = timersRef.current.get(id);
    if (timer) clearTimeout(timer);
    timersRef.current.delete(id);
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((message: string, type: ToastType = 'success') => {
    const id = ++_nextToastId;
    setToasts((prev) => [...prev.slice(-4), { id, message, type }]);
    const timer = setTimeout(() => removeToast(id), type === 'error' ? 6000 : 3500);
    timersRef.current.set(id, timer);
  }, [removeToast]);

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      <div
        aria-live="polite"
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          pointerEvents: 'none',
          maxWidth: 380,
        }}
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            onClick={() => removeToast(t.id)}
            className={`toast-notification toast-${t.type}`}
            style={{ pointerEvents: 'auto' }}
          >
            <span className="toast-icon">
              {t.type === 'success' && '\u2713'}
              {t.type === 'error' && '\u2717'}
              {t.type === 'info' && '\u24D8'}
            </span>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

const LegacyRecommendationRedirect: React.FC = () => {
  const { id } = useParams<{ id?: string }>();
  return <Navigate to={id ? `/kampagnen/${id}` : '/kampagnen'} replace />;
};

/* ── Auth Context ──────────────────────────────────────────────── */
interface AuthContextValue {
  authenticated: boolean;
  handleLogin: () => void;
  handleLogout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  authenticated: false,
  handleLogin: () => {},
  handleLogout: () => {},
});

export const useAuth = () => useContext(AuthContext);

/* ── Page Loading Fallback ─────────────────────────────────────── */
const PageFallback: React.FC = () => (
  <div style={{ padding: 32 }}>
    <LoadingSkeleton lines={6} />
  </div>
);

/* ── App ────────────────────────────────────────────────────────── */
const App: React.FC = () => {
  const [authenticated, setAuthenticated] = useState(isAuthenticated);

  const handleLogin = useCallback(() => setAuthenticated(true), []);
  const handleLogout = useCallback(() => {
    logout();
    setAuthenticated(false);
  }, []);

  if (!authenticated) {
    return (
      <ThemeProvider>
        <LoginPage onLogin={handleLogin} />
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <ErrorBoundary>
      <ToastProvider>
        <AuthContext.Provider value={{ authenticated, handleLogin, handleLogout }}>
          <Router>
            <Suspense fallback={<PageFallback />}>
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/welcome" element={<LandingPage />} />
                <Route element={<MediaShell />}>
                  <Route path="/dashboard" element={<OperationalDashboardPage />} />
                  <Route path="/entscheidung" element={<DecisionPage />} />
                  <Route path="/regionen" element={<RegionsPage />} />
                  <Route path="/kampagnen" element={<CampaignsPage />} />
                  <Route path="/kampagnen/:id" element={<CampaignsPage />} />
                  <Route path="/evidenz" element={<EvidencePage />} />
                  <Route path="/bericht" element={<WeeklyReport />} />
                </Route>
                {/* Legacy redirects */}
                <Route path="/lagebild" element={<Navigate to="/dashboard" replace />} />
                <Route path="/empfehlungen" element={<Navigate to="/kampagnen" replace />} />
                <Route path="/empfehlungen/:id" element={<LegacyRecommendationRedirect />} />
                <Route path="/validierung" element={<Navigate to="/evidenz" replace />} />
                <Route path="/dashboard/recommendations/:id" element={<LegacyRecommendationRedirect />} />
                <Route path="/backtest" element={<Navigate to="/evidenz" replace />} />
              </Routes>
            </Suspense>
          </Router>
        </AuthContext.Provider>
      </ToastProvider>
      </ErrorBoundary>
    </ThemeProvider>
  );
};

export default App;
