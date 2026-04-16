import React from 'react';
import type { ShiftRecommendation } from '../../../pages/cockpit/types';
import { fmtEurCompactOrDash, fmtSignalStrength } from '../../../pages/cockpit/format';

interface Props {
  items: ShiftRecommendation[];
  /**
   * Whether the upstream event-score is calibrated. When false (the default
   * at the time of the 2026-04-16 audit) the per-item value is displayed as
   * a raw signal strength on [0,1], NOT as a "Konfidenz %".
   */
  calibrated?: boolean;
}

export const RecommendationList: React.FC<Props> = ({ items, calibrated = false }) => {
  if (items.length === 0) {
    return (
      <div className="peix-rec-empty" style={{ padding: '12px 0', color: 'var(--peix-ink-soft)' }}>
        Aktuell keine Shift-Empfehlungen verfügbar. Das kann zwei Gründe haben:
        das Modell meldet kein auslösendes Signal, oder es ist noch kein Media-Plan
        verbunden (EUR-Werte werden dann nicht berechnet).
      </div>
    );
  }
  return (
    <div className="peix-rec-list">
      {items.map((r) => (
        <article className="peix-rec" key={r.id}>
          <div className="flow">
            <span className="from">{r.fromName}</span>
            <span className="arr">→</span>
            <span className="to">{r.toName}</span>
          </div>
          <div className="why">{r.why}</div>
          <div className="conf peix-num">
            <span className="peix-dot cool" />
            {calibrated ? `Konfidenz ${(r.confidence * 100).toFixed(0)} %` : `Signalstärke ${fmtSignalStrength(r.confidence)}`}
          </div>
          <div className="amt peix-num">{fmtEurCompactOrDash(r.amountEur)}</div>
        </article>
      ))}
    </div>
  );
};

export default RecommendationList;
