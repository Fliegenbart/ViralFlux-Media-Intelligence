import { formatForecastAxisTickLabel } from './ForecastChart';

describe('formatForecastAxisTickLabel', () => {
  it('keeps already formatted x-axis labels unchanged', () => {
    expect(formatForecastAxisTickLabel('09.12', 'x')).toBe('09.12');
    expect(formatForecastAxisTickLabel('13.01', 'x')).toBe('13.01');
  });

  it('keeps y-axis labels numeric', () => {
    expect(formatForecastAxisTickLabel(40, 'y')).toBe('40');
  });
});
