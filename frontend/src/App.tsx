import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import './index.css';

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        {/* Weitere Routes können hier ergänzt werden */}
        {/* <Route path="/forecast" element={<ForecastPage />} /> */}
        {/* <Route path="/recommendations" element={<RecommendationsPage />} /> */}
        {/* <Route path="/settings" element={<SettingsPage />} /> */}
      </Routes>
    </Router>
  );
};

export default App;
