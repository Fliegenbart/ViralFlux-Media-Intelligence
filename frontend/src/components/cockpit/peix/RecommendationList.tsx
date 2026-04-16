import React from 'react';
import type { ShiftRecommendation } from '../../../pages/cockpit/types';
import { fmtEurCompact, fmtPct } from '../../../pages/cockpit/format';

interface Props { items: ShiftRecommendation[]; }

export const RecommendationList: React.FC<Props> = ({ items }) => (
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
          Konfidenz {fmtPct(r.confidence)}
        </div>
        <div className="amt peix-num">{fmtEurCompact(r.amountEur)}</div>
      </article>
    ))}
  </div>
);

export default RecommendationList;
