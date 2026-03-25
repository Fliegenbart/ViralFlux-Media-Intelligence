import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import ConfirmDialog from './ConfirmDialog';

describe('ConfirmDialog', () => {
  it('renders a labeled dialog and closes on Escape', () => {
    const onCancel = jest.fn();

    render(
      <ConfirmDialog
        open
        title="Änderung bestätigen"
        message="Soll der aktuelle Vorschlag wirklich überschrieben werden?"
        onConfirm={jest.fn()}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Änderung bestätigen' })).toBeInTheDocument();
    expect(screen.getByText('Soll der aktuelle Vorschlag wirklich überschrieben werden?')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onCancel).toHaveBeenCalled();
  });

  it('marks the dialog busy while the confirm action is loading', () => {
    render(
      <ConfirmDialog
        open
        title="Löschen bestätigen"
        message="Dieser Schritt kann nicht rückgängig gemacht werden."
        loading
        variant="danger"
        onConfirm={jest.fn()}
        onCancel={jest.fn()}
      />,
    );

    expect(screen.getByRole('alertdialog', { name: 'Löschen bestätigen' })).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('button', { name: 'Bitte warten...' })).toBeDisabled();
  });
});
