import React from 'react';

import { WorkspaceStatusSummary } from '../../types/media';
import { formatDateTime } from './cockpitUtils';
import { OperatorSection } from './operator/OperatorPrimitives';

interface Props {
  status: WorkspaceStatusSummary | null;
  title?: string;
  intro?: string;
}

const WorkspaceStatusPanel: React.FC<Props> = ({
  status,
  title = 'Was noch offen ist',
  intro = 'Hier siehst du schnell, ob du weitergehen kannst.',
}) => {
  if (!status) return null;

  return (
    <OperatorSection
      kicker="Arbeitsstatus"
      title={title}
      description={intro}
      tone="muted"
      className="workspace-status-panel"
    >
      <div className="workspace-status-grid">
        {status.items.slice(0, 3).map((item) => (
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
    </OperatorSection>
  );
};

export default WorkspaceStatusPanel;
