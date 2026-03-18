import React from 'react';

type Tone = 'default' | 'accent' | 'muted';

function classNames(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(' ');
}

interface OperatorSectionProps {
  kicker?: string;
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}

export const OperatorSection: React.FC<OperatorSectionProps> = ({
  kicker,
  title,
  description,
  actions,
  children,
  tone = 'default',
  className,
}) => (
  <section className={classNames('operator-section-shell', `operator-section-shell--${tone}`, className)}>
    {(kicker || title || description || actions) && (
      <header className="operator-section-shell__header">
        <div className="operator-section-shell__headline">
          {kicker && <span className="operator-section-shell__kicker">{kicker}</span>}
          {title && <h2 className="operator-section-shell__title">{title}</h2>}
          {description && <p className="operator-section-shell__copy">{description}</p>}
        </div>
        {actions && <div className="operator-section-shell__actions">{actions}</div>}
      </header>
    )}
    <div className="operator-section-shell__body">
      {children}
    </div>
  </section>
);

interface OperatorPanelProps {
  eyebrow?: string;
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}

export const OperatorPanel: React.FC<OperatorPanelProps> = ({
  eyebrow,
  title,
  description,
  actions,
  children,
  tone = 'default',
  className,
}) => (
  <section className={classNames('operator-panel-shell', `operator-panel-shell--${tone}`, className)}>
    {(eyebrow || title || description || actions) && (
      <header className="operator-panel-shell__header">
        <div className="operator-panel-shell__headline">
          {eyebrow && <span className="operator-panel-shell__eyebrow">{eyebrow}</span>}
          {title && <h3 className="operator-panel-shell__title">{title}</h3>}
          {description && <p className="operator-panel-shell__copy">{description}</p>}
        </div>
        {actions && <div className="operator-panel-shell__actions">{actions}</div>}
      </header>
    )}
    <div className="operator-panel-shell__body">
      {children}
    </div>
  </section>
);

interface OperatorStatProps {
  label: string;
  value: React.ReactNode;
  meta?: React.ReactNode;
  tone?: Tone;
  className?: string;
}

export const OperatorStat: React.FC<OperatorStatProps> = ({
  label,
  value,
  meta,
  tone = 'default',
  className,
}) => (
  <div className={classNames('operator-stat-card', `operator-stat-card--${tone}`, className)}>
    <span className="operator-stat-card__label">{label}</span>
    <strong className="operator-stat-card__value">{value}</strong>
    {meta ? <div className="operator-stat-card__meta">{meta}</div> : null}
  </div>
);

interface OperatorChipRailProps {
  children: React.ReactNode;
  className?: string;
}

export const OperatorChipRail: React.FC<OperatorChipRailProps> = ({ children, className }) => (
  <div className={classNames('operator-chip-rail', className)}>
    {children}
  </div>
);
