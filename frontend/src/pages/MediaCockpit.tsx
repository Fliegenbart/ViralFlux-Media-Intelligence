import React from 'react';

import CampaignsPage from './media/CampaignsPage';
import DecisionPage from './media/DecisionPage';
import EvidencePage from './media/EvidencePage';
import RegionsPage from './media/RegionsPage';
import { MediaCockpitView } from '../components/cockpit/types';

interface Props {
  view: MediaCockpitView;
}

const MediaCockpit: React.FC<Props> = ({ view }) => {
  if (view === 'decision') return <DecisionPage />;
  if (view === 'regions') return <RegionsPage />;
  if (view === 'campaigns') return <CampaignsPage />;
  return <EvidencePage />;
};

export default MediaCockpit;
