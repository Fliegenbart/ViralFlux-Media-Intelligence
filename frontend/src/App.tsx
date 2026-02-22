import React, { createContext, useContext, useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import MediaCockpit from './pages/MediaCockpit';
import DataIntegration from './pages/DataIntegration';
import SalesRadar from './pages/SalesRadar';
import CampaignRecommendationDetail from './pages/CampaignRecommendationDetail';
import './index.css';

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

const App: React.FC = () => {
  return (
    <ThemeProvider>
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
    </ThemeProvider>
  );
};

export default App;
