import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import ExpandablePanel from './ExpandablePanel';

describe('ExpandablePanel', () => {
  it('renders the title', () => {
    render(
      <ExpandablePanel title="Evidenz">
        <div>Versteckter Inhalt</div>
      </ExpandablePanel>,
    );

    expect(screen.getByText('Evidenz')).toBeInTheDocument();
  });

  it('keeps content hidden by default', () => {
    render(
      <ExpandablePanel title="Evidenz">
        <div>Nicht sichtbar</div>
      </ExpandablePanel>,
    );

    expect(screen.getByRole('button', { name: /Evidenz/i })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('Nicht sichtbar')).not.toBeVisible();
  });

  it('shows content on click', () => {
    render(
      <ExpandablePanel title="Evidenz">
        <div>Sichtbarer Inhalt</div>
      </ExpandablePanel>,
    );

    const trigger = screen.getByRole('button', { name: /Evidenz/i });
    fireEvent.click(trigger);

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Sichtbarer Inhalt')).toBeVisible();
  });

  it('toggles with keyboard', () => {
    render(
      <ExpandablePanel title="Nachvollziehbarkeit">
        <div>Trace-Inhalt</div>
      </ExpandablePanel>,
    );

    const trigger = screen.getByRole('button', { name: /Nachvollziehbarkeit/i });

    fireEvent.keyDown(trigger, { key: 'Enter' });
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Trace-Inhalt')).toBeVisible();

    fireEvent.keyDown(trigger, { key: ' ' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('Trace-Inhalt')).not.toBeVisible();
  });
});
