import React from 'react';

import { MediaEvidenceResponse, ModelLineage, SignalStackResponse, SourceStatusItem, TruthSnapshot } from '../../../types/media';
import { formatDateTime, formatPercent } from '../cockpitUtils';
import { monitoringStatusLabel, runModeLabel, sanitizeEvidenceCopy, sourceFreshnessLabel } from './evidenceUtils';

interface Props {
  evidence: MediaEvidenceResponse | null;
  sourceItems: SourceStatusItem[];
  signalStack?: SignalStackResponse | null;
  driverGroups: Record<string, { label: string; contribution: number }>;
  modelLineage?: ModelLineage | null;
  recentRuns: Array<Record<string, unknown>>;
  truthSnapshot?: TruthSnapshot | null;
}

const SourceFreshnessSection: React.FC<Props> = ({
  evidence,
  sourceItems,
  signalStack,
  driverGroups,
  modelLineage,
  recentRuns,
  truthSnapshot,
}) => {
  return (
    <>
      <section className="cockpit-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Stand der Daten</h2>
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
          <h2 className="subsection-title">Stand der Quellen</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {sourceItems.map((item) => (
              <div key={item.source_key} className="evidence-row">
                <span>{item.label}</span>
                <strong style={{ color: item.status_color === 'green' ? '#047857' : item.status_color === 'amber' ? '#b45309' : '#b91c1c' }}>
                  {sourceFreshnessLabel(item.freshness_state)}
                </strong>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="cockpit-grid">
        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Signalquellen</h2>
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
                <strong>{item.is_core_signal ? 'Kernsignal' : monitoringStatusLabel(item.contribution_state)}</strong>
              </div>
            ))}
          </div>
          {signalStack?.summary?.decision_mode_reason && (
            <p className="section-copy" style={{ marginTop: 14 }}>
              {sanitizeEvidenceCopy(signalStack.summary.decision_mode_reason)}
            </p>
          )}
        </div>

        <div className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Modell und Datenbasis</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            <div className="evidence-row">
              <span>Datenbasis</span>
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
        <h2 className="subsection-title">Letzte Läufe</h2>
        <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
          {recentRuns.length > 0 ? recentRuns.slice(0, 6).map((run, index) => (
            <div key={`${String(run.mode)}-${index}`} className="evidence-row">
              <span>{runModeLabel(String(run.mode || 'Run'))}</span>
              <strong>{monitoringStatusLabel(String(run.status || '-'))}</strong>
            </div>
          )) : (
            <div style={{ color: 'var(--text-muted)' }}>Noch keine Laufhistorie vorhanden.</div>
          )}
        </div>
      </section>

      {(truthSnapshot?.known_limits || evidence?.known_limits || []).length > 0 && (
        <section className="card subsection-card" style={{ padding: 24 }}>
          <h2 className="subsection-title">Bekannte Grenzen</h2>
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {[...(truthSnapshot?.known_limits || []), ...(evidence?.known_limits || [])].map((item) => (
              <div key={item} className="evidence-row">
                <span>{item}</span>
                <strong>Grenze</strong>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
};

export default SourceFreshnessSection;
