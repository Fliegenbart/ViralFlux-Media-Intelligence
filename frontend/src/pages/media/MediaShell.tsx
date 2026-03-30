import React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';

import AppLayout from '../../components/AppLayout';
import RecommendationOverlay from '../../features/media/RecommendationOverlay';
import { MediaWorkflowProvider } from '../../features/media/workflowContext';

const MediaShell: React.FC = () => {
  const location = useLocation();

  return (
    <MediaWorkflowProvider>
      <AppLayout>
        <>
          <AnimatePresence mode="wait">
            <Outlet key={location.pathname} />
          </AnimatePresence>
          <RecommendationOverlay />
        </>
      </AppLayout>
    </MediaWorkflowProvider>
  );
};

export default MediaShell;
