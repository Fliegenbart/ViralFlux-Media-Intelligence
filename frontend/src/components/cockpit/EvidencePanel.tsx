import React from 'react';

import { BacktestResponse, MediaEvidenceResponse } from '../../types/media';
import { ValidationSection } from './BacktestVisuals';
import {
  formatDateTime,
  formatPercent,
  truthLayerLabel,
} from './cockpitUtils';

interface Props {
  evidence: MediaEvidenceResponse | null;
  loading: boolean;
  marketValidation: BacktestResponse | null;
  marketValidationLoading: boolean;
  customerValidation: BacktestResponse | null;
  customerValidationLoading: boolean;
}

const EvidencePanel: React.FC<Props> = ({
  evidence,
  loading,
  marketValidation,
  marketValidationLoading,
  customerValidation,
  customerValidationLoading,
}) => {
  const latestMarket = evidence?.proxy_validation;
  const latestCustomer = evidence?.truth_validation;
  const legacyCustomer = evidence?.truth_validation_legacy;
  const sourceItems = evidence?.source_status?.items || [];
  const recentRuns = evidence?.recent_runs || [];
  const truthCoverage = evidence?.truth_coverage;
  const signalStack = evidence?.signal_stack;
  const modelLineage = evidence?.model_lineage;
  const driverGroups = signalStack?.summary?.driver_groups || {};

  if (loading && !evidence) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade Evidenz...</div>;
  }

  return (
    <div className="page-stack">
      <section className="context-filter-rail">
        <div className="section-heading">
          <span className="section-kicker">Evidenz</span>
          <h1 className="section-title">Proxy, Truth, Signalquellen und Modellzustand</h1>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <span className="step-chip">Proxy-validiert</span>
          <span className="step-chip">Kunden-Check: {truthLayerLabel(truthCoverage || latestCustomer)}</span>
          {signalStack?.summary?.decision_mode_label && <span className="step-chip">{signalStack.summary.decision_mode_label}</span>}
          <span className="step-chip">Drift: {modelLineage?.drift_state || '-'}</span>
        </div>
      </section>

      <section className="evidence-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">Markt-Check (Proxy-Validierung)</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              {latestMarket?.quality_gate?.overall_passed ? 'GO' : 'WATCH'}
            </h2>
          </div>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Readiness</span>
              <strong>{latestMarket?.decision_metrics?.readiness_score_0_100 != null ? `${Math.round(latestMarket.decision_metrics.readiness_score_0_100)}/100` : '-'}</strong>
            </div>
            <div className="metric-box">
              <span>Hit-Rate</span>
              <strong>{formatPercent(latestMarket?.decision_metrics?.hit_rate_pct || 0)}</strong>
            </div>
            <div className="metric-box">
              <span>False Alarms</span>
              <strong>{formatPercent(latestMarket?.decision_metrics?.false_alarm_rate_pct || 0)}</strong>
            </div>
          </div>
          <p className="section-copy">
            Dieser Block zeigt, wie gut das System epidemiologische Trigger gegen Marktbewegungen trifft. Er ist ein Proxy für Planungsgüte, nicht der finale Kundenbeweis.
          </p>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <div>
            <div className="section-kicker">Kunden-Check</div>
            <h2 className="subsection-title" style={{ marginTop: 8 }}>
              {truthLayerLabel(truthCoverage || latestCustomer)}
            </h2>
          </div>
          <div className="metric-strip">
            <div className="metric-box">
              <span>Wochen</span>
              <strong>{truthCoverage?.coverage_weeks ?? 0}</strong>
            </div>
            <div className="metric-box">
              <span>Regionen</span>
              <strong>{truthCoverage?.regions_covered ?? 0}</strong>
            </div>
            <div className="metric-box">
              <span>Produkte</span>
              <strong>{truthCoverage?.products_covered ?? 0}</strong>
            </div>
          </div>
          <p className="section-copy">
            {truthCoverage?.coverage_weeks
              ? 'Der Truth-Layer basiert auf importierten Outcome-Daten. Er bewertet Datenbreite und Abdeckung, nicht pauschal die Produktqualität.'
              : 'Es gibt aktuell noch keinen aktiven Truth-Layer aus angebundenen Outcome-Daten. Bis dahin bleibt der Kundenbezug explorativ und blockiert harte Freigaben.'}
          </p>
          {!truthCoverage?.coverage_weeks && legacyCustomer && (
            <div className="soft-panel review-panel-soft" style={{ marginTop: 14 }}>
              <div className="campaign-focus-label">Explorativer Legacy-Run</div>
              <div className="review-body-copy" style={{ marginTop: 8 }}>
                {legacyCustomer.metrics?.data_points || 0} Punkte aus einem älteren Kunden-Backtest. Dieser Run bleibt sichtbar als historischer Hinweis, zählt aber nicht als aktiver Truth-Layer.
              </div>
            </div>
          )}
        </div>
      </section>

      <section style={{ display: 'grid', gap: 20 }}>
        <ValidationSection
          title="Markt-Validierung im Verlauf"
          subtitle="Forecast gegen Ist, inklusive Baselines. So sieht PEIX, ob das Modell die Welle früh genug erkennt und nicht nur nachzeichnet."
          result={marketValidation}
          loading={marketValidationLoading}
          emptyMessage="Noch keine detaillierten Markt-Validierungsdaten verfügbar."
        />
        {truthCoverage?.coverage_weeks ? (
          <ValidationSection
            title="Kunden-Validierung im Verlauf"
            subtitle="Proxy und Truth bleiben getrennt: Dieser Layer zeigt nur, wie gut das Modell an echte Kunden-Outcome-Daten anschließt."
            result={customerValidation}
            loading={customerValidationLoading}
            emptyMessage="Noch keine ausreichend langen Kundenreihen für eine belastbare Truth-Validierung verfügbar."
          />
        ) : (
          <section className="card subsection-card" style={{ padding: 24 }}>
            <div className="section-heading" style={{ gap: 6 }}>
              <h2 className="subsection-title">Kunden-Validierung im Verlauf</h2>
              <p className="subsection-copy">
                Dieser Block bleibt leer, bis echte Outcome-Daten angeschlossen sind. Legacy-Runs werden separat nur als explorativer Hinweis gezeigt.
              </p>
            </div>
            {legacyCustomer ? (
              <div className="soft-panel" style={{ padding: 16, marginTop: 14, display: 'grid', gap: 10 }}>
                <div className="evidence-row">
                  <span>Legacy-Run</span>
                  <strong>{legacyCustomer.run_id || '-'}</strong>
                </div>
                <div className="evidence-row">
                  <span>Datenpunkte</span>
                  <strong>{legacyCustomer.metrics?.data_points ?? 0}</strong>
                </div>
                <div className="evidence-row">
                  <span>R²</span>
                  <strong>{legacyCustomer.metrics?.r2_score ?? '-'}</strong>
                </div>
              </div>
            ) : (
              <div className="review-muted-copy" style={{ marginTop: 14 }}>
                Noch kein aktiver oder historischer Kunden-Run vorhanden.
              </div>
            )}
          </section>
        )}
      </section>

      <section className="cockpit-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Datenfrische</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {Object.entries(evidence?.data_freshness || {}).map(([key, value]) => (
              <div key={key} className="evidence-row">
                <span>{key}</span>
                <strong>{formatDateTime(value)}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Quellenstatus</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {sourceItems.map((item) => (
              <div key={item.source_key} className="evidence-row">
                <span>{item.label}</span>
                <strong style={{ color: item.status_color === 'green' ? '#047857' : item.status_color === 'amber' ? '#b45309' : '#b91c1c' }}>
                  {item.freshness_state}
                </strong>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="cockpit-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Signal-Stack</h2>
          <div className="review-chip-row" style={{ marginTop: 14 }}>
            {Object.entries(driverGroups).map(([key, group]) => (
              <span key={key} className="step-chip">
                {group.label} {formatPercent(group.contribution || 0)}
              </span>
            ))}
          </div>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {(signalStack?.items || []).map((item) => (
              <div key={item.source_key} className="evidence-row">
                <span>{item.label}</span>
                <strong>{item.is_core_signal ? 'epi-kern' : item.contribution_state}</strong>
              </div>
            ))}
          </div>
          {signalStack?.summary?.decision_mode_reason && (
            <p className="section-copy" style={{ marginTop: 14 }}>
              {signalStack.summary.decision_mode_reason}
            </p>
          )}
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Model Lineage</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            <div className="evidence-row">
              <span>Stack</span>
              <strong>{[...(modelLineage?.base_estimators || []), modelLineage?.meta_learner].filter(Boolean).join(' → ') || '-'}</strong>
            </div>
            <div className="evidence-row">
              <span>Version</span>
              <strong>{modelLineage?.model_version || '-'}</strong>
            </div>
            <div className="evidence-row">
              <span>Trainiert am</span>
              <strong>{formatDateTime(modelLineage?.trained_at)}</strong>
            </div>
            <div className="evidence-row">
              <span>Feature-Set</span>
              <strong>{modelLineage?.feature_set_version || '-'}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <h2 className="subsection-title">Recent Runs</h2>
        <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
          {recentRuns.length > 0 ? recentRuns.slice(0, 6).map((run, index) => (
            <div key={`${String(run.mode)}-${index}`} className="evidence-row">
              <span>{String(run.mode || 'Run')}</span>
              <strong>{String(run.status || '-')}</strong>
            </div>
          )) : (
            <div style={{ color: 'var(--text-muted)' }}>Noch keine Run-Historie im Cockpit vorhanden.</div>
          )}
        </div>
      </section>

      {(evidence?.known_limits || []).length > 0 && (
        <section className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Bekannte Grenzen</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {evidence!.known_limits.map((item) => (
              <div key={item} className="evidence-row">
                <span>{item}</span>
                <strong>Limit</strong>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default EvidencePanel;
