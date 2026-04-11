import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import { MediaWorkflowProvider, useMediaWorkflow } from './workflowContext';

function BrandHarness() {
  const { brand } = useMediaWorkflow();
  return <div data-testid="brand-value">{brand || '(leer)'}</div>;
}

describe('MediaWorkflowProvider', () => {
  it('starts without a customer-specific default brand', () => {
    render(
      <MediaWorkflowProvider>
        <BrandHarness />
      </MediaWorkflowProvider>,
    );

    expect(screen.getByTestId('brand-value')).toHaveTextContent('(leer)');
  });
});
