import React, { ReactNode, useId, useState } from 'react';

interface ExpandablePanelProps {
  title: string;
  icon?: ReactNode;
  badge?: string | ReactNode;
  defaultExpanded?: boolean;
  children: ReactNode;
  className?: string;
}

const ExpandablePanel: React.FC<ExpandablePanelProps> = ({
  title,
  icon,
  badge,
  defaultExpanded = false,
  children,
  className,
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const contentId = useId();

  const toggleExpanded = () => {
    setExpanded((current) => !current);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggleExpanded();
    }
  };

  return (
    <section className={['expandable-panel', className].filter(Boolean).join(' ')}>
      <div
        role="button"
        tabIndex={0}
        className="expandable-panel__header"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={toggleExpanded}
        onKeyDown={handleKeyDown}
      >
        <div className="expandable-panel__title-row">
          {icon ? <span className="expandable-panel__icon" aria-hidden="true">{icon}</span> : null}
          <span className="expandable-panel__title">{title}</span>
          {badge ? <span className="expandable-panel__badge">{badge}</span> : null}
        </div>
        <span
          className={['expandable-panel__chevron', expanded ? 'is-expanded' : ''].filter(Boolean).join(' ')}
          aria-hidden="true"
        >
          &#9662;
        </span>
      </div>
      <div
        id={contentId}
        className={['expandable-panel__content', expanded ? 'is-expanded' : ''].filter(Boolean).join(' ')}
        aria-hidden={!expanded}
        style={{
          maxHeight: expanded ? '1000px' : '0px',
          opacity: expanded ? 1 : 0,
          visibility: expanded ? 'visible' : 'hidden',
        }}
      >
        <div className="expandable-panel__content-inner">{children}</div>
      </div>
    </section>
  );
};

export default ExpandablePanel;
