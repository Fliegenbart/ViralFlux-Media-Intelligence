import React from 'react';

import CollapsibleSection from '../CollapsibleSection';
import type { NowPageViewModel } from '../../features/media/useMediaData';
import type { RegionalBacktestResponse, RegionalForecastResponse } from '../../types/media';
import { formatDateTime } from './cockpitUtils';
import { DecisionForecastChart } from './DecisionForecastChart';
import { buildSimplifiedDecisionModel } from './simplifiedDecisionWorkspace.utils';

interface Props {
  view: NowPageViewModel;
  forecast: RegionalForecastResponse | null;
  focusRegionBacktest: RegionalBacktestResponse | null;
  focusRegionBacktestLoading: boolean;
  horizonDays: number;
  primaryActionLabel: string;
  onPrimaryAction: () => void;
}

const SimplifiedDecisionWorkspace: React.FC<Props> = ({
  view,
  forecast,
  focusRegionBacktest,
  focusRegionBacktestLoading,
  horizonDays,
  primaryActionLabel,
  onPrimaryAction,
}) => {
  const model = buildSimplifiedDecisionModel({ view, forecast });
  const showDetailsFallback = primaryActionLabel === 'Details ansehen';
  const primaryActionDisabled = !showDetailsFallback && (view.heroRecommendation?.ctaDisabled ?? false);

  if (view.emptyState) {
    return (
      <div className="decision-home">
        <section className="decision-home__hero decision-home__hero--no_call">
          <div className="decision-home__eyebrow">ENTSCHEIDUNG DIESE WOCHE</div>
          <div className="decision-home__copy">
            <h1 className="decision-home__headline">{view.emptyState.title}</h1>
            <p className="decision-home__summary">{view.emptyState.body}</p>
          </div>
          <div className="decision-home__actions">
            <span className="decision-home__timestamp">
              Datenstand {formatDateTime(view.generatedAt)}
            </span>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="decision-home">
      <section className={`decision-home__hero decision-home__hero--${model.state}`}>
        <div className="decision-home__eyebrow">ENTSCHEIDUNG DIESE WOCHE</div>
        <div className="decision-home__copy">
          <h1 className="decision-home__headline">{model.headline}</h1>
          <p className="decision-home__summary">{model.summary}</p>
        </div>
        <div className="decision-home__actions">
          <button
            type="button"
            className="media-button decision-home__cta"
            onClick={onPrimaryAction}
            disabled={primaryActionDisabled}
          >
            {primaryActionLabel}
          </button>
          <span className="decision-home__timestamp">
            Datenstand {formatDateTime(view.generatedAt)}
          </span>
        </div>
      </section>

      <section className="decision-home__graph">
        <div className="decision-home__section-head">
          <h2 className="decision-home__section-title">Verlauf bisher und Prognose</h2>
          <p className="decision-home__section-copy">Links siehst du den bisherigen Verlauf, rechts das aktive {horizonDays}-Tage-Prognosefenster.</p>
        </div>
        <DecisionForecastChart
          prediction={model.focusPrediction}
          backtest={focusRegionBacktest}
          horizonDays={horizonDays}
        />
      </section>

      <section className="decision-home__facts" aria-label="Kernfakten">
        <div className="decision-home__section-head">
          <h2 className="decision-home__section-title">Drei Fakten</h2>
          <p className="decision-home__section-copy">Die kurze Einordnung, die man auf einen Blick lesen kann.</p>
        </div>
        <div className="decision-home__facts-grid">
          {model.facts.map((fact) => (
            <div key={fact.label} className="decision-home__fact workspace-note-card">
              <span className="decision-home__fact-label">{fact.label}</span>
              <strong className="decision-home__fact-value">{fact.value || '-'}</strong>
              {fact.detail ? <span className="decision-home__fact-detail">{fact.detail}</span> : null}
            </div>
          ))}
        </div>
      </section>

      <div className="decision-home__details">
        <CollapsibleSection
          title="Warum glauben wir das?"
          subtitle="Nur die Belege, die die Wochenentscheidung direkt tragen."
        >
          <div className="decision-home__note-list">
            {model.detailSections.why.map((item) => (
              <div key={item} className="workspace-note-card">
                {item}
              </div>
            ))}
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          title="Welche anderen Regionen wurden geprueft?"
          subtitle="Die naheliegenden Alternativen, ohne die Hauptempfehlung zu verwischen."
        >
          <div className="decision-home__note-list">
            {model.detailSections.alternatives.length > 0 ? (
              model.detailSections.alternatives.map((item) => (
                <div key={item} className="workspace-note-card">
                  {item}
                </div>
              ))
            ) : (
              <div className="workspace-note-card">Keine weitere Region ist aktuell naeher dran.</div>
            )}
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          title="Welche Risiken oder Blocker gibt es noch?"
          subtitle="Die ehrlichen Punkte, die wir vor dem Klick sichtbar lassen."
        >
          <div className="decision-home__note-list">
            {model.detailSections.risks.length > 0 ? (
              model.detailSections.risks.map((item) => (
                <div key={item} className="workspace-note-card">
                  {item}
                </div>
              ))
            ) : (
              <div className="workspace-note-card">Aktuell blockiert nichts Zentrales.</div>
            )}
          </div>
        </CollapsibleSection>
      </div>
    </div>
  );
};

export default SimplifiedDecisionWorkspace;
