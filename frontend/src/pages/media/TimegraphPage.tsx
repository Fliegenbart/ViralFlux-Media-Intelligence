import React, { useEffect } from 'react';

import { useToast } from '../../App';
import { usePageHeader } from '../../components/AppLayout';
import { FocusRegionOutlookPanel } from '../../components/cockpit/BacktestVisuals';
import { VIRUS_OPTIONS } from '../../components/cockpit/cockpitUtils';
import {
  OperatorChipRail,
  OperatorSection,
} from '../../components/cockpit/operator/OperatorPrimitives';
import { useTimegraphPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const TimegraphPage: React.FC = () => {
  const { toast } = useToast();
  const { setPageHeader, clearPageHeader } = usePageHeader();
  const { virus, setVirus, dataVersion } = useMediaWorkflow();
  const {
    selectedRegion,
    setSelectedRegion,
    selectedPrediction,
    regionOptions,
    regionalBacktest,
    loading,
    backtestLoading,
    horizonDays,
  } = useTimegraphPageData(virus, dataVersion, toast);

  useEffect(() => {
    setPageHeader({
      contextNote: 'Nur bestätigter Verlauf plus vermutete Fortführung für die nächsten sieben Tage.',
    });

    return clearPageHeader;
  }, [clearPageHeader, setPageHeader]);

  return (
    <OperatorSection
      kicker="Zeitgraph"
      title="Verlauf und 7-Tage-Fortführung"
      description="Reduzierte Ansicht nur für die Kurve: Virus wählen, Bundesland wählen, Verlauf lesen."
      tone="accent"
      className="timegraph-page"
    >
      <div className="timegraph-page__toolbar">
        <OperatorChipRail className="timegraph-page__virus-rail">
          {VIRUS_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setVirus(option)}
              className={`tab-chip ${option === virus ? 'active' : ''}`}
              aria-pressed={option === virus}
            >
              {option}
            </button>
          ))}
        </OperatorChipRail>

        <label className="timegraph-page__region-control">
          <span className="timegraph-page__control-label">Bundesland</span>
          <select
            aria-label="Bundesland wählen"
            className="media-input ops-command-filter__select"
            value={selectedRegion || ''}
            onChange={(event) => setSelectedRegion(event.target.value || null)}
            disabled={loading || regionOptions.length === 0}
          >
            {regionOptions.length > 0 ? regionOptions.map((option) => (
              <option key={option.code} value={option.code}>
                {option.name}
              </option>
            )) : (
              <option value="">
                {loading ? 'Regionen werden geladen' : 'Keine Region verfügbar'}
              </option>
            )}
          </select>
        </label>

        <div className="timegraph-page__horizon-note">
          <span className="timegraph-page__control-label">Horizont</span>
          <strong>{horizonDays} Tage</strong>
        </div>
      </div>

      <FocusRegionOutlookPanel
        prediction={selectedPrediction}
        backtest={regionalBacktest}
        loading={loading || backtestLoading}
        horizonDays={horizonDays}
        minimal
      />
    </OperatorSection>
  );
};

export default TimegraphPage;
