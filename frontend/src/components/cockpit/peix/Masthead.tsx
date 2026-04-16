import React from 'react';

interface Props {
  client: string;
  virusLabel: string;
  isoWeek: string;
  generatedAt: string;
}

/**
 * Editorial masthead — Financial-Times vibe, with live client chip on the right.
 */
export const Masthead: React.FC<Props> = ({ client, virusLabel, isoWeek, generatedAt }) => {
  const time = new Date(generatedAt).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  return (
    <header className="peix-masthead">
      <div className="peix-masthead-brand">
        <span className="mark">
          viralflux <em>·</em> cockpit
        </span>
        <span className="peix-mono">peix healthcare media</span>
      </div>
      <div className="peix-masthead-meta">
        <span>{isoWeek}</span>
        <span>·</span>
        <span>{virusLabel}</span>
        <span>·</span>
        <span>
          <span className="dot" /> live · client <b style={{ color: 'var(--peix-ink)', letterSpacing: '0.08em' }}>{client}</b>
        </span>
        <span>·</span>
        <span>{time} Uhr</span>
      </div>
    </header>
  );
};

export default Masthead;
