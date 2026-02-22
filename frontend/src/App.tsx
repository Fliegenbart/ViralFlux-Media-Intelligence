import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import MediaCockpit from './pages/MediaCockpit';
import DataIntegration from './pages/DataIntegration';
import SalesRadar from './pages/SalesRadar';
import CampaignRecommendationDetail from './pages/CampaignRecommendationDetail';
import './index.css';

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

/* ── App ────────────────────────────────────────────────────────── */
const App: React.FC = () => {
  return (
    <ThemeProvider>
      <ToastProvider>
        <Router>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/welcome" element={<LandingPage />} />
            <Route path="/dashboard" element={<MediaCockpit />} />
            <Route path="/dashboard/recommendations/:id" element={<CampaignRecommendationDetail />} />
            <Route path="/app" element={<Navigate to="/dashboard" replace />} />
            <Route path="/cockpit" element={<Navigate to="/dashboard" replace />} />
            <Route path="/map" element={<Navigate to="/dashboard?tab=map" replace />} />
            <Route path="/products" element={<Navigate to="/dashboard?tab=product-intel" replace />} />
            <Route path="/sales-radar" element={<SalesRadar />} />
            <Route path="/vertriebsradar" element={<Navigate to="/sales-radar" replace />} />
            <Route path="/data-integration" element={<DataIntegration />} />
            <Route path="/datenimport" element={<Navigate to="/data-integration" replace />} />
          </Routes>
        </Router>
      </ToastProvider>
    </ThemeProvider>
  );
};

export default App;
