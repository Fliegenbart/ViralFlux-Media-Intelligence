import React, { useState } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

const CollapsibleSection: React.FC<Props> = ({
  title,
  subtitle,
  defaultOpen = false,
  children,
}) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="collapsible-section">
      <button
        type="button"
        className="collapsible-trigger"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <div>
          <h2 className="subsection-title">{title}</h2>
          {subtitle && <p className="subsection-copy">{subtitle}</p>}
        </div>
        <span
          className="collapsible-chevron"
          style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }}
          aria-hidden="true"
        >
          &#9662;
        </span>
      </button>
      {open && <div className="collapsible-content">{children}</div>}
    </section>
  );
};

export default CollapsibleSection;
