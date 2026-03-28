import React from 'react';

import { COCKPIT_SEMANTICS, evidenceStatusHelper } from '../../../lib/copy';
import { normalizeGermanText } from '../../../lib/plainLanguage';
import { BacktestResponse, BusinessValidationSummary, OutcomeLearningSummary, TruthCoverage } from '../../../types/media';
import {
  businessValidationLabel,
  decisionScopeLabel,
  evidenceTierLabel,
  formatDateTime,
  formatPercent,
  learningStateLabel,
  metricContractBadge,
  metricContractDisplayLabel,
  metricContractNote,
  truthFreshnessLabel,
} from '../cockpitUtils';
import { sanitizeEvidenceCopy } from './evidenceUtils';

interface Props {
  customerDataCoverage?: TruthCoverage | null;
  customerDataGate?: {
    passed: boolean;
    state?: string;
    learning_state?: string;
  } | null;
  businessValidation?: BusinessValidationSummary | null;
  regionalImpact?: OutcomeLearningSummary | null;
  legacyCustomerValidation?: BacktestResponse | null;
  connectedFieldLabels: string[];
}

const WaveValidationSection: React.FC<Props> = ({
  customerDataCoverage,
  customerDataGate,
  businessValidation,
  regionalImpact,
  legacyCustomerValidation,
  connectedFieldLabels,
}) => {
  const hasCustomerData = Boolean(customerDataCoverage?.coverage_weeks);
  const customerDataHelper = hasCustomerData
    ? evidenceStatusHelper('truth_backed')
    : COCKPIT_SEMANTICS.insufficientTruth.helper;

  const impactSignalLabel = metricContractDisplayLabel(
    regionalImpact?.field_contracts,
    'outcome_signal_score',
    'Tatsächliche Wirkung (Kundendaten)',
  );
  const impactSignalBadge = metricContractBadge(
    regionalImpact?.field_contracts,
    'outcome_signal_score',
    'Wirkungshinweis',
  );
  const impactSignalNote = metricContractNote(
    regionalImpact?.field_contracts,
    'outcome_signal_score',
    'Zeigt, ob Kundendaten die Empfehlung in der Region stützen. Kein Wirkungsversprechen.',
  );
  const impactConfidenceLabel = metricContractDisplayLabel(
    regionalImpact?.field_contracts,
    'outcome_confidence_pct',
    'Sicherheitsgrad',
  );
  const impactConfidenceBadge = metricContractBadge(
    regionalImpact?.field_contracts,
    'outcome_confidence_pct',
    'Sicherheitsgrad',
  );
  const impactConfidenceNote = metricContractNote(
    regionalImpact?.field_contracts,
    'outcome_confidence_pct',
    'Schätzt, wie stabil dieser Hinweis ist.',
  );

  return (
    <>
      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">GELO-Kundendaten</span>
          <h2 className="subsection-title">Tatsächliche regionale Wirkung (Actual Regional Impact)</h2>
          <p className="subsection-copy">
            Dieser Bereich zeigt, ob Kundendaten die Empfehlungen in der Region bereits sichtbar stützen. Wenn hier noch wenig steht, ist das kein Fehler, sondern meist ein Import- oder Abdeckungs-Thema.
          </p>
        </div>
        <div className="metric-strip">
          <div className="metric-box">
            <span>Wochen</span>
            <strong>{customerDataCoverage?.coverage_weeks ?? 0}</strong>
          </div>
          <div className="metric-box">
            <span>Datenstand</span>
            <strong>{truthFreshnessLabel(customerDataCoverage?.truth_freshness_state)}</strong>
          </div>
          <div className="metric-box">
            <span>Letzter Import</span>
            <strong>{formatDateTime(customerDataCoverage?.last_imported_at)}</strong>
          </div>
        </div>
        <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
          <div className="evidence-row">
            <span>Nutzbar in Empfehlungen</span>
            <strong>{customerDataGate?.passed ? 'bereit' : learningStateLabel(customerDataGate?.state)}</strong>
          </div>
          <div className="evidence-row">
            <span>Stand der Auswertung</span>
            <strong>{learningStateLabel(regionalImpact?.learning_state || customerDataGate?.learning_state)}</strong>
          </div>
          <div className="evidence-row">
            <span>{impactSignalLabel}</span>
            <strong>{formatPercent(regionalImpact?.outcome_signal_score)}</strong>
          </div>
        </div>
        <div className="review-muted-copy" style={{ marginTop: 12 }}>
          {customerDataHelper}
        </div>
        <div className="review-chip-row">
          {(connectedFieldLabels.length ? connectedFieldLabels : ['Noch keine Pflichtfelder vollständig vorhanden']).map((item) => (
            <span key={item} className="step-chip">{normalizeGermanText(item)}</span>
          ))}
        </div>
        <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
          <div className="evidence-row">
            <span>Freigabe-Status</span>
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
        {!hasCustomerData && legacyCustomerValidation && (
          <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
            <div className="campaign-focus-label">Historischer Hinweis (Backtest)</div>
            <div className="review-body-copy" style={{ marginTop: 8 }}>
              {legacyCustomerValidation.metrics?.data_points || 0} Datenpunkte aus einem älteren Vergleichslauf. Dieser Lauf bleibt als historischer Hinweis sichtbar, zählt aber nicht als aktueller Kundendaten-Stand.
            </div>
          </div>
        )}
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading">
          <span className="section-kicker">Wirkungs-Hinweise</span>
          <h2 className="subsection-title">Was Kundendaten bereits zeigen</h2>
          <p className="subsection-copy">
            Dieser Block fasst die Hinweise zusammen, die aus Kundendaten abgeleitet werden. Sie helfen beim Einordnen und Priorisieren, sind aber keine Garantie für eine sichere Wirkung.
          </p>
        </div>
        <div className="review-muted-copy" style={{ marginTop: 12 }}>
          {customerDataHelper}
        </div>
        <div className="metric-strip" style={{ marginTop: 16 }}>
          <div className="metric-box">
            <span>Stand</span>
            <strong>{learningStateLabel(regionalImpact?.learning_state)}</strong>
          </div>
          <div className="metric-box">
            <span>{impactSignalLabel}</span>
            <strong>{formatPercent(regionalImpact?.outcome_signal_score)}</strong>
          </div>
          <div className="metric-box">
            <span>{impactConfidenceLabel}</span>
            <strong>{formatPercent(regionalImpact?.outcome_confidence_pct)}</strong>
          </div>
        </div>
        <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
          <div className="evidence-row">
            <span>{impactSignalLabel}</span>
            <strong>{impactSignalBadge}</strong>
          </div>
          <div className="review-body-copy" style={{ marginTop: 8 }}>
            {impactSignalNote}
          </div>
          <div className="evidence-row" style={{ marginTop: 14 }}>
            <span>{impactConfidenceLabel}</span>
            <strong>{impactConfidenceBadge}</strong>
          </div>
          <div className="review-body-copy" style={{ marginTop: 8 }}>
            {impactConfidenceNote}
          </div>
        </div>
        <div className="soft-panel" style={{ padding: 18, marginTop: 18, display: 'grid', gap: 10 }}>
          {(regionalImpact?.top_pair_learnings?.length ? regionalImpact.top_pair_learnings : []).slice(0, 3).map((item, index) => (
            <div key={`${item.product_key || 'product'}-${item.region_code || index}`} className="evidence-row">
              <span>{item.product_key || item.product || 'Produkt'} · {item.region_code || 'Region'}</span>
              <strong>{formatPercent(item.outcome_signal_score)} · {learningStateLabel(regionalImpact?.learning_state)}</strong>
            </div>
          ))}
          {!regionalImpact?.top_pair_learnings?.length && (
            <div className="review-muted-copy">
              Noch keine sichtbaren Produkt-Region-Hinweise vorhanden. Sobald mehr Kundendaten vorliegen, werden hier erste Muster angezeigt.
            </div>
          )}
        </div>
      </section>
    </>
  );
};

export default WaveValidationSection;
