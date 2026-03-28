import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import LoginPage from './LoginPage';
import { login } from '../lib/api';

jest.mock('../lib/api', () => ({
  login: jest.fn(),
}));

describe('LoginPage', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  it('frames the product as a weekly steering workspace and submits credentials', async () => {
    const onLogin = jest.fn();
    (login as jest.Mock).mockResolvedValue(undefined);

    render(<LoginPage onLogin={onLogin} />);

    expect(
      screen.getByRole('heading', { name: 'Klar sehen, was diese Woche zuerst zählt.' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Willkommen in der Wochensteuerung' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Oder mit Firmenkonto fortfahren')).toBeInTheDocument();
    expect(screen.getByText(/Noch kein Zugang\?/i)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('name@firma.de'), {
      target: { value: 'test@example.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), {
      target: { value: 'secret123' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith('test@example.com', 'secret123', true);
      expect(onLogin).toHaveBeenCalled();
    });
  });
});
