import React from 'react';

export type TabId = 'decision' | 'atlas' | 'timeline' | 'impact';

interface Props {
  active: TabId;
  onChange: (next: TabId) => void;
}

const TABS: Array<{ id: TabId; label: string; idx: string }> = [
  { id: 'decision', idx: '01', label: 'Die Entscheidung' },
  { id: 'atlas',    idx: '02', label: 'Wellen-Atlas' },
  { id: 'timeline', idx: '03', label: 'Forecast-Zeitreise' },
  { id: 'impact',   idx: '04', label: 'Wirkung & Feedback-Loop' },
];

export const CockpitTabs: React.FC<Props> = ({ active, onChange }) => (
  <nav className="peix-tabs" role="tablist" aria-label="Cockpit sections">
    {TABS.map((t) => (
      <button
        key={t.id}
        role="tab"
        aria-selected={active === t.id}
        className="peix-tab"
        onClick={() => onChange(t.id)}
      >
        <span className="idx">{t.idx}</span>
        {t.label}
      </button>
    ))}
  </nav>
);

export default CockpitTabs;
