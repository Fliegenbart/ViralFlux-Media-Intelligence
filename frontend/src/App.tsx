import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import Dashboard from './pages/Dashboard';
import GermanyMap from './pages/GermanyMap';
import Vertriebsradar from './pages/Vertriebsradar';
import Datenimport from './pages/Datenimport';
import Calibration from './pages/Calibration';
import './index.css';

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/map" element={<GermanyMap />} />
        <Route path="/vertriebsradar" element={<Vertriebsradar />} />
        <Route path="/datenimport" element={<Datenimport />} />
        <Route path="/calibration" element={<Calibration />} />
      </Routes>
    </Router>
  );
};

export default App;
