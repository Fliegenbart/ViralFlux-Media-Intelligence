import React from 'react';
import type { SourceStatus } from '../../../pages/cockpit/types';
import { fmtDateShort } from '../../../pages/cockpit/format';

interface Props { sources: SourceStatus[]; }

/**
 * Sources row below the fold — calm, typographic, like an FT colophon.
 * Builds trust: reader sees *which* signal is fresh and which is lagging.
 */
export const SourcesStrip: React.FC<Props> = ({ sources }) => (
  <footer className="peix-sources" role="contentinfo">
    {sources.map((s) => (
      <div key={s.name}>
        <b>{s.name}</b>
        <span>
          <span className="peix-dot" style={{
            background: s.health === 'good' ? 'var(--peix-cool)'
                     : s.health === 'delayed' ? 'var(--peix-warm)'
                     : 'var(--peix-ink-mute)',
          }} />
          stand {fmtDateShort(s.lastUpdate)} · latenz {s.latencyDays}T
        </span>
        {s.note && <span style={{ fontFamily: 'var(--peix-font-display)', fontStyle: 'italic', textTransform: 'none', letterSpacing: 0 }}>{s.note}</span>}
      </div>
    ))}
  </footer>
);

export default SourcesStrip;
