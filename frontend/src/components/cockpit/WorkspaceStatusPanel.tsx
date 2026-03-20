import React from 'react';

import { WorkspaceStatusSummary } from '../../types/media';
import { formatDateTime } from './cockpitUtils';

interface Props {
  status: WorkspaceStatusSummary | null;
  title?: string;
  intro?: string;
}

const WorkspaceStatusPanel: React.FC<Props> = ({
  status,
  title = 'Wie sicher ist das?',
  intro = 'Vier schnelle Antworten, damit wir wissen, ob wir direkt handeln oder erst prüfen sollten.',
}) => {
  if (!status) return null;

  return (
    <section className="card subsection-card workspace-status-panel" style={{ padding: 24 }}>
      <div className="section-heading" style={{ gap: 6 }}>
        <h2 className="subsection-title">{title}</h2>
        <p className="subsection-copy">{intro}</p>
      </div>

      <div className="workspace-status-grid">
        {status.items.map((item) => (
          <article
            key={item.key}
            className={`workspace-status-card workspace-status-card--${item.tone}`}
          >
            <span className="workspace-status-card__question">{item.question}</span>
            <strong>{item.value}</strong>
            <p>{item.detail}</p>
          </article>
        ))}
      </div>

      <div className="workspace-status-panel__footer">
        <span>{status.summary}</span>
        <span>
          Letzter Kundendaten-Import: {status.last_import_at ? formatDateTime(status.last_import_at) : 'noch keiner'}
        </span>
      </div>
    </section>
  );
};

export default WorkspaceStatusPanel;
