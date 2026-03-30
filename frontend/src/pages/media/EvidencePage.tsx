import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import EvidencePanel from '../../components/cockpit/EvidencePanel';
import { useToast } from '../../App';
import AnimatedPage from '../../components/AnimatedPage';
import { usePageHeader } from '../../components/AppLayout';
import { useEvidencePageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const EvidencePage: React.FC = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { setPageHeader, clearPageHeader } = usePageHeader();
  const { virus, brand, dataVersion, invalidateData } = useMediaWorkflow();
  const {
    evidence,
    evidenceLoading,
    workspaceStatus,
    marketValidation,
    marketValidationLoading,
    customerValidation,
    customerValidationLoading,
    truthPreview,
    truthBatchDetail,
    truthActionLoading,
    truthBatchDetailLoading,
    submitTruthCsv,
    loadTruthBatchDetail,
  } = useEvidencePageData(virus, brand, dataVersion, toast);

  useEffect(() => {
    setPageHeader({
      primaryAction: {
        label: 'Importbereich öffnen',
        onClick: () => document.getElementById('evidence-import')?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      },
      secondaryAction: {
        label: 'Zum Wochenplan',
        onClick: () => navigate('/jetzt'),
      },
    });

    return clearPageHeader;
  }, [clearPageHeader, navigate, setPageHeader]);

  return (
    <AnimatedPage>
    <EvidencePanel
      evidence={evidence}
      workspaceStatus={workspaceStatus}
      loading={evidenceLoading}
      marketValidation={marketValidation}
      marketValidationLoading={marketValidationLoading}
      customerValidation={customerValidation}
      customerValidationLoading={customerValidationLoading}
      truthPreview={truthPreview}
      truthBatchDetail={truthBatchDetail}
      truthActionLoading={truthActionLoading}
      truthBatchDetailLoading={truthBatchDetailLoading}
      onSubmitTruthCsv={async (payload) => {
        await submitTruthCsv(payload);
        invalidateData();
      }}
      onLoadTruthBatchDetail={loadTruthBatchDetail}
    />
    </AnimatedPage>
  );
};

export default EvidencePage;
