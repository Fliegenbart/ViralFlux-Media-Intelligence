import React from 'react';

import { UI_COPY } from '../../../lib/copy';
import { normalizeGermanText } from '../../../lib/plainLanguage';
import { BacktestResponse, BusinessValidationSummary, OutcomeLearningSummary, TruthCoverage } from '../../../types/media';
import {
  businessValidationLabel,
  decisionScopeLabel,
  evidenceTierLabel,
  formatDateTime,
  formatPercent,
  learningStateLabel,
  truthFreshnessLabel,
  truthLayerLabel,
} from '../cockpitUtils';
import { sanitizeEvidenceCopy } from './evidenceUtils';

interface Props {
  truthStatus?: TruthCoverage | null;
  truthGate?: {
    passed: boolean;
    state?: string;
    learning_state?: string;
  } | null;
  businessValidation?: BusinessValidationSummary | null;
  outcomeLearning?: OutcomeLearningSummary | null;
  legacyCustomer?: BacktestResponse | null;
  sourceStatusLabels: string[];
}

const TruthOutcomeSection: React.FC<Props> = ({
  truthStatus,
  truthGate,
  businessValidation,
  outcomeLearning,
  legacyCustomer,
  sourceStatusLabels,
}) => {
  return (
    <>
      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">{UI_COPY.customerData}</span>
          <h2 className="subsection-title">Kundendatenbasis {truthLayerLabel(truthStatus)}</h2>
          <p className="subsection-copy">
            Dieser Bereich basiert auf validiertem CSV-Import mit Mediabudget und echten Kundendaten. Er zeigt, wie gut die Daten die Empfehlung zusätzlich stützen.
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
            <span>Freigabestatus Kundendaten</span>
            <strong>{truthGate?.passed ? 'freigeschaltet' : learningStateLabel(truthGate?.state)}</strong>
          </div>
          <div className="evidence-row">
            <span>Lernstand</span>
            <strong>{learningStateLabel(outcomeLearning?.learning_state || truthGate?.learning_state)}</strong>
          </div>
          <div className="evidence-row">
            <span>Wirkungssignal</span>
            <strong>{formatPercent(outcomeLearning?.outcome_signal_score)}</strong>
          </div>
        </div>
        <div className="review-chip-row">
          {(sourceStatusLabels.length ? sourceStatusLabels : ['Noch keine Pflichtfelder vollständig vorhanden']).map((item) => (
            <span key={item} className="step-chip">{normalizeGermanText(item)}</span>
          ))}
        </div>
        <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
          <div className="evidence-row">
            <span>Freigabestatus</span>
            <strong>{businessValidationLabel(businessValidation?.validation_status)}</strong>
          </div>
          <div className="evidence-row">
            <span>Belegstufe</span>
            <strong>{evidenceTierLabel(businessValidation?.evidence_tier)}</strong>
          </div>
          <div className="evidence-row">
            <span>Entscheidungsrahmen</span>
            <strong>{decisionScopeLabel(businessValidation?.decision_scope)}</strong>
          </div>
          <div className="evidence-row">
            <span>Vergleichsgruppentest</span>
            <strong>{businessValidation?.holdout_ready ? 'bereit' : 'noch offen'}</strong>
          </div>
        </div>
        {(businessValidation?.message || businessValidation?.guidance) && (
          <div className="soft-panel" style={{ padding: 16, marginTop: 14, fontSize: 14, color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--text-primary)' }}>{sanitizeEvidenceCopy(businessValidation?.message) || 'Die Freigabe auf Basis von Kundendaten ist noch im Aufbau.'}</strong>
            {businessValidation?.guidance && (
              <div style={{ marginTop: 8 }}>
                {sanitizeEvidenceCopy(businessValidation.guidance)}
              </div>
            )}
          </div>
        )}
        {!truthStatus?.coverage_weeks && legacyCustomer && (
          <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
            <div className="campaign-focus-label">Früherer Kundenlauf</div>
            <div className="review-body-copy" style={{ marginTop: 8 }}>
              {legacyCustomer.metrics?.data_points || 0} Punkte aus einem älteren Kunden-Backtest. Dieser Run bleibt als historischer Hinweis sichtbar, zählt aber nicht als aktiver Bereich für Kundendaten.
            </div>
          </div>
        )}
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">Beobachtete Wirkung</span>
          <h2 className="subsection-title">Was die Kundendaten zusätzlich stützen</h2>
          <p className="subsection-copy">
            Dieser Block zeigt, was aus importierten Kundendaten bereits gelernt wurde. Die Werte helfen bei der Priorisierung, sind aber keine Aussage über eine sichere Welle.
          </p>
        </div>
        <div className="metric-strip" style={{ marginTop: 16 }}>
          <div className="metric-box">
            <span>Lernstand</span>
            <strong>{learningStateLabel(outcomeLearning?.learning_state)}</strong>
          </div>
          <div className="metric-box">
            <span>Wirkungssignal</span>
            <strong>{formatPercent(outcomeLearning?.outcome_signal_score)}</strong>
          </div>
          <div className="metric-box">
            <span>Sicherheit aus Kundendaten</span>
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
              Noch keine granularen Produkt-Region-Lernmuster vorhanden. Sobald mehr Reihen aus Kundendaten vorliegen, werden sie hier sichtbar.
            </div>
          )}
        </div>
      </section>
    </>
  );
};

export default TruthOutcomeSection;
