import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import MediaCockpit from './pages/MediaCockpit';
import Datenimport from './pages/Datenimport';
import CampaignRecommendationDetail from './pages/CampaignRecommendationDetail';
import './index.css';

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<MediaCockpit />} />
        <Route path="/dashboard/recommendations/:id" element={<CampaignRecommendationDetail />} />
        <Route path="/map" element={<Navigate to="/dashboard?tab=map" replace />} />
        <Route path="/vertriebsradar" element={<Navigate to="/dashboard?tab=recommendations" replace />} />
        <Route path="/datenimport" element={<Datenimport />} />
      </Routes>
    </Router>
  );
};

export default App;
