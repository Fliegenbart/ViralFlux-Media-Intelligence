import { deriveForecastLeadHero } from './forecastLeadHero';

describe('deriveForecastLeadHero', () => {
  it('promotes the peak-week lead story when backtest data exists', () => {
    const hero = deriveForecastLeadHero({
      backtestLead: 1,
      bestLag: 7,
      hasShift: true,
    });

    expect(hero.leadDays).toBe(1);
    expect(hero.leadLabel).toBe('5–10');
    expect(hero.leadNote).toContain('Peak-Wochen');
    expect(hero.leadNote).toContain('Median über alle Wochen bleibt 1 Tage');
  });

  it('falls back to the live lead when no backtest lead exists', () => {
    const hero = deriveForecastLeadHero({
      backtestLead: null,
      bestLag: 7,
      hasShift: false,
    });

    expect(hero.leadDays).toBe(7);
    expect(hero.leadLabel).toBe('+7');
    expect(hero.leadNote).toContain('Notaufnahme-Spur');
  });

  it('marks the lead as unavailable when no positive signal exists', () => {
    const hero = deriveForecastLeadHero({
      backtestLead: null,
      bestLag: -2,
      hasShift: false,
    });

    expect(hero.leadDays).toBeNull();
    expect(hero.leadLabel).toBeNull();
    expect(hero.leadNote).toContain('nicht berechenbar');
  });
});
