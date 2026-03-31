import React, { useEffect } from 'react';

import { useToast } from '../../App';
import AnimatedPage from '../../components/AnimatedPage';
import { usePageHeader } from '../../components/AppLayout';
import { FocusRegionOutlookPanel } from '../../components/cockpit/BacktestVisuals';
import { formatDateShort, VIRUS_OPTIONS } from '../../components/cockpit/cockpitUtils';
import { useTimegraphPageData } from '../../features/media/useMediaData';
import { useMediaWorkflow } from '../../features/media/workflowContext';

const TimegraphPage: React.FC = () => {
  const { toast } = useToast();
  const { clearPageHeader } = usePageHeader();
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
    return clearPageHeader;
  }, [clearPageHeader]);

  /* ── derived insight values ── */
  const prediction = regionalBacktest?.timeline?.[regionalBacktest.timeline.length - 1] || null;
  const changePct = prediction
    ? ((prediction.expected_target_incidence - prediction.current_known_incidence) /
        (prediction.current_known_incidence || 1)) *
      100
    : null;

  const trendArrow = changePct != null ? (changePct > 5 ? '\u2197' : changePct < -5 ? '\u2198' : '\u2192') : '\u2014';
  const trendWord = changePct != null ? (changePct > 5 ? 'steigt' : changePct < -5 ? 'fällt' : 'stabil') : 'lädt';
  const trendState =
    changePct != null
      ? changePct > 20
        ? 'critical'
        : changePct > 5
          ? 'elevated'
          : changePct < -5
            ? 'clear'
            : 'watch'
      : 'watch';
  const changePctText =
    changePct != null ? `${changePct >= 0 ? '+' : ''}${changePct.toFixed(0)}% Veränderung` : 'Wird berechnet';
  const lastDataDate = prediction?.as_of_date ? formatDateShort(prediction.as_of_date) : null;

  return (
    <AnimatedPage>
      <div className="page-stack">
        <div className="answer-hero" data-state={trendState}>
          <div className="answer-hero__signal">
            <span className="answer-hero__dot" />
            <span className="answer-hero__probability">{trendArrow}</span>
          </div>
          <h2 className="answer-hero__title">
            {virus} {trendWord} — {regionalBacktest?.bundesland_name || selectedRegion || 'Kein Bundesland'}
          </h2>
          <p className="answer-hero__meta">
            {changePctText} · Horizont {horizonDays} Tage
            {lastDataDate && <> · Stand {lastDataDate}</>}
          </p>
          <div className="answer-hero__chips">
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
            <select
              aria-label="Bundesland wählen"
              className="timegraph-region-select"
              value={selectedRegion || ''}
              onChange={(event) => setSelectedRegion(event.target.value || null)}
              disabled={loading || regionOptions.length === 0}
            >
              {regionOptions.length > 0 ? (
                regionOptions.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.name}
                  </option>
                ))
              ) : (
                <option value="">{loading ? 'Regionen werden geladen' : 'Keine Region verfügbar'}</option>
              )}
            </select>
          </div>
        </div>

        <div className="timegraph-chart-container">
          <FocusRegionOutlookPanel
            prediction={selectedPrediction}
            backtest={regionalBacktest}
            loading={loading || backtestLoading}
            horizonDays={horizonDays}
            minimal
          />
        </div>
      </div>
    </AnimatedPage>
  );
};

export default TimegraphPage;
