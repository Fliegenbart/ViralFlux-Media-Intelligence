import { UI_COPY } from './copy';

describe('UI_COPY', () => {
  it('uses the neutral ranking-signal wording for the source helper label', () => {
    expect(UI_COPY.signalScoreWithSource).toBe('Signal-Score (Ranking-Signal)');
  });
});
