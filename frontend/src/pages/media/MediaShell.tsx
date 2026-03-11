import React from 'react';
import { Outlet } from 'react-router-dom';

import AppLayout from '../../components/AppLayout';
import RecommendationOverlay from '../../features/media/RecommendationOverlay';
import { MediaWorkflowProvider } from '../../features/media/workflowContext';

const MediaShell: React.FC = () => {
  return (
    <MediaWorkflowProvider>
      <AppLayout>
        <>
          <Outlet />
          <RecommendationOverlay />
        </>
      </AppLayout>
    </MediaWorkflowProvider>
  );
};

export default MediaShell;
