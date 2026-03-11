import React from 'react';

import { UI_COPY } from '../../../lib/copy';
import { BacktestResponse, OutcomeLearningSummary, TruthCoverage } from '../../../types/media';
import { formatDateTime, formatPercent, learningStateLabel, truthFreshnessLabel, truthLayerLabel } from '../cockpitUtils';

interface Props {
  truthStatus?: TruthCoverage | null;
  truthGate?: {
    passed: boolean;
    state?: string;
    learning_state?: string;
  } | null;
  outcomeLearning?: OutcomeLearningSummary | null;
  legacyCustomer?: BacktestResponse | null;
  sourceStatusLabels: string[];
}

const TruthOutcomeSection: React.FC<Props> = ({
  truthStatus,
  truthGate,
  outcomeLearning,
  legacyCustomer,
  sourceStatusLabels,
}) => {
  return (
    <>
      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">{UI_COPY.customerData}</span>
          <h2 className="subsection-title">{truthLayerLabel(truthStatus)}</h2>
          <p className="subsection-copy">
            Dieser Bereich basiert auf validiertem CSV-Import mit Media Spend und echten Outcome-Metriken. Er bewertet Datenbreite, Aktualität und Anschlussfähigkeit an echte Kundenergebnisse.
          </p>
        </div>
        <div className="metric-strip">
          <div className="metric-box">
            <span>Wochen</span>
            <strong>{truthStatus?.coverage_weeks ?? 0}</strong>
          </div>
          <div className="metric-box">
            <span>Aktualität</span>
            <strong>{truthFreshnessLabel(truthStatus?.truth_freshness_state)}</strong>
          </div>
          <div className="metric-box">
            <span>Letzter Import</span>
            <strong>{formatDateTime(truthStatus?.last_imported_at)}</strong>
          </div>
        </div>
        <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
          <div className="evidence-row">
            <span>Truth-Gate</span>
            <strong>{truthGate?.passed ? 'freigeschaltet' : learningStateLabel(truthGate?.state)}</strong>
          </div>
          <div className="evidence-row">
            <span>Learning-State</span>
            <strong>{learningStateLabel(outcomeLearning?.learning_state || truthGate?.learning_state)}</strong>
          </div>
          <div className="evidence-row">
            <span>Outcome-Score</span>
            <strong>{formatPercent(outcomeLearning?.outcome_signal_score)}</strong>
          </div>
        </div>
        <div className="review-chip-row">
          {(sourceStatusLabels.length ? sourceStatusLabels : ['Noch keine Pflichtfelder vollständig vorhanden']).map((item) => (
            <span key={item} className="step-chip">{item}</span>
          ))}
        </div>
        {!truthStatus?.coverage_weeks && legacyCustomer && (
          <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
            <div className="campaign-focus-label">Explorativer Legacy-Run</div>
            <div className="review-body-copy" style={{ marginTop: 8 }}>
              {legacyCustomer.metrics?.data_points || 0} Punkte aus einem älteren Kunden-Backtest. Dieser Run bleibt als historischer Hinweis sichtbar, zählt aber nicht als aktiver Bereich für Kundendaten.
            </div>
          </div>
        )}
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">Outcome-Learning</span>
          <h2 className="subsection-title">Beobachtete Wirkung statt nur Forecast und Ranking</h2>
          <p className="subsection-copy">
            Dieser Block zeigt, was aus importierten Outcome-Daten bereits gelernt wurde. Die Werte priorisieren, sind aber keine Forecast-Wahrscheinlichkeiten.
          </p>
        </div>
        <div className="metric-strip" style={{ marginTop: 16 }}>
          <div className="metric-box">
            <span>Learning-State</span>
            <strong>{learningStateLabel(outcomeLearning?.learning_state)}</strong>
          </div>
          <div className="metric-box">
            <span>Outcome-Score</span>
            <strong>{formatPercent(outcomeLearning?.outcome_signal_score)}</strong>
          </div>
          <div className="metric-box">
            <span>Learning-Konfidenz</span>
            <strong>{formatPercent(outcomeLearning?.outcome_confidence_pct)}</strong>
          </div>
        </div>
        <div className="soft-panel" style={{ padding: 18, marginTop: 18, display: 'grid', gap: 10 }}>
          {(outcomeLearning?.top_pair_learnings?.length ? outcomeLearning.top_pair_learnings : []).slice(0, 3).map((item, index) => (
            <div key={`${item.product_key || 'product'}-${item.region_code || index}`} className="evidence-row">
              <span>{item.product_key || item.product || 'Produkt'} · {item.region_code || 'Region'}</span>
              <strong>{formatPercent(item.outcome_signal_score)} · {learningStateLabel(outcomeLearning?.learning_state)}</strong>
            </div>
          ))}
          {!outcomeLearning?.top_pair_learnings?.length && (
            <div className="review-muted-copy">
              Noch keine granularen Produkt-Region-Learnings vorhanden. Sobald mehr Outcome-Reihen vorliegen, werden sie hier sichtbar.
            </div>
          )}
        </div>
      </section>
    </>
  );
};

export default TruthOutcomeSection;
