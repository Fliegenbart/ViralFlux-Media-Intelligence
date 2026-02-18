import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import MediaCockpit from './pages/MediaCockpit';
import DataIntegration from './pages/DataIntegration';
import SalesRadar from './pages/SalesRadar';
import CampaignRecommendationDetail from './pages/CampaignRecommendationDetail';
import './index.css';

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/welcome" element={<LandingPage />} />
        <Route path="/dashboard" element={<MediaCockpit />} />
        <Route path="/dashboard/recommendations/:id" element={<CampaignRecommendationDetail />} />
        <Route path="/map" element={<Navigate to="/dashboard?tab=map" replace />} />
        <Route path="/sales-radar" element={<SalesRadar />} />
        <Route path="/vertriebsradar" element={<Navigate to="/sales-radar" replace />} />
        <Route path="/data-integration" element={<DataIntegration />} />
        <Route path="/datenimport" element={<Navigate to="/data-integration" replace />} />
      </Routes>
    </Router>
  );
};

export default App;
