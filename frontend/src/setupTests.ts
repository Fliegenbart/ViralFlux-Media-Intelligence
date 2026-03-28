// Keep the CRA/Jest test stack on React.act to avoid noisy deprecation warnings
// from older react-dom test-utils bridges.
jest.mock('react-dom/test-utils', () => {
  const actual = jest.requireActual('react-dom/test-utils');
  const React = jest.requireActual('react');

  return {
    ...actual,
    act: React.act,
  };
});

export {};
