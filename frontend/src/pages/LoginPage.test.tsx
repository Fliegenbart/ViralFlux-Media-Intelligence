import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import LoginPage from './LoginPage';
import { login } from '../lib/api';

jest.mock('../lib/api', () => ({
  login: jest.fn(),
}));

describe('LoginPage', () => {
  let consoleErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
    jest.resetAllMocks();
  });

  it('frames the login as the weekly steering entry and removes distracting placeholders', async () => {
    const onLogin = jest.fn();
    (login as jest.Mock).mockResolvedValue(undefined);

    render(<LoginPage onLogin={onLogin} />);

    expect(
      screen.getByRole('heading', { name: 'Der zentrale Einstieg in die aktuelle Lage' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Ins Virus-Radar' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Melde dich an, um Radar, Bundesländer und Evidenz zu öffnen.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('ViralFlux Radarzugang')).toBeInTheDocument();
    expect(
      screen.getByText('Radar, Regionen, Kampagnen und Evidenz in einer Arbeitsfläche.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Operational Access')).toBeInTheDocument();
    expect(screen.getByText('Demo-Zugang über das Produktteam anfragen.')).toBeInTheDocument();
    expect(screen.queryByText('Oder mit Firmenkonto fortfahren')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Google' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Azure AD' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Passwort vergessen?' })).not.toBeInTheDocument();
    expect(screen.queryByText('Pilot-Scope')).not.toBeInTheDocument();
    expect(screen.queryByText('Bitte intern freischalten lassen.')).not.toBeInTheDocument();
    expect(screen.getByText(/Noch kein Zugang\?/i)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('name@firma.de'), {
      target: { value: 'test@example.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), {
      target: { value: 'secret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Radar öffnen' }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith('test@example.com', 'secret123', true);
      expect(onLogin).toHaveBeenCalled();
    });
  });
});
