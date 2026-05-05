import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import CockpitGate from './CockpitGate';

describe('CockpitGate', () => {
  it('keeps the password screen minimal and client-neutral', () => {
    render(<CockpitGate />);

    expect(screen.getByRole('heading', { name: 'Zugang' })).toBeInTheDocument();
    expect(screen.getByText('Bitte Passwort eingeben.')).toBeInTheDocument();
    expect(screen.getByLabelText('Passwort')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Öffnen' })).toBeInTheDocument();

    expect(document.body).not.toHaveTextContent(/GELO|peix|labpulse|Pilot/i);
  });
});
