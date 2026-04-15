import React, { useEffect } from 'react';

import EvidencePanel from '../../components/cockpit/EvidencePanel';
import AnimatedPage from '../../components/AnimatedPage';
import { usePageHeader } from '../../components/AppLayout';
import { useEvidencePageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';
import { useToast } from '../../lib/appContext';

const EvidencePage: React.FC = () => {
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
  const sourceAttentionCount = (evidence?.source_status?.items || []).filter((item) => (
    String(item.status_color || '').toLowerCase() !== 'green'
  )).length;
  const truthStatus = evidence?.truth_snapshot?.coverage || evidence?.truth_coverage;
  const hasTruthData = Boolean((truthStatus?.coverage_weeks || 0) > 0);
  const hasBlockers = Boolean(workspaceStatus?.blocker_count);
  const importNeedsAttention = !hasTruthData || hasBlockers || sourceAttentionCount > 0;
  const primaryActionLabel = importNeedsAttention ? 'Fehlende Daten klären' : 'Datenlage prüfen';
  const primaryActionHref = importNeedsAttention ? '#evidence-import' : '#evidence-onboarding';

  useEffect(() => {
    setPageHeader({
      primaryAction: {
        label: primaryActionLabel,
        href: primaryActionHref,
      },
      secondaryAction: {
        label: 'Zum Virus-Radar',
        to: '/virus-radar',
      },
    });

    return clearPageHeader;
  }, [clearPageHeader, primaryActionHref, primaryActionLabel, setPageHeader]);

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
