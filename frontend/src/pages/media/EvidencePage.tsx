import React from 'react';

import EvidencePanel from '../../components/cockpit/EvidencePanel';
import { useToast } from '../../App';
import { useEvidencePageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const EvidencePage: React.FC = () => {
  const { toast } = useToast();
  const { virus, brand, dataVersion, invalidateData } = useMediaWorkflow();
  const {
    evidence,
    evidenceLoading,
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

  return (
    <EvidencePanel
      evidence={evidence}
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
  );
};

export default EvidencePage;
