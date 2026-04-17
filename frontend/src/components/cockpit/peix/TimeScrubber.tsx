import React, { useMemo } from 'react';

interface Props {
  min: number;
  max: number;
  value: number;
  onChange: (v: number) => void;
  /** ISO date strings aligned to the horizon indices; optional — if present,
   *  the handle caption shows the real date instead of "+N Tage". */
  dateFor?: (horizonDay: number) => string | null;
  labelLeft?: string;
  labelMid?: string;
  labelRight?: string;
}

/**
 * Editorial timeline scrubber.
 *
 * Rendered as a pressed-paper horizontal rail with week ticks (every 7
 * horizon days), a soft nowcast fill on the left, a warm forecast fill on
 * the right, a clear "heute" tick in the middle, and a pin-shaped handle
 * carrying the selected date as its caption.
 *
 * The underlying interaction is still a native <input type="range"> for
 * keyboard accessibility and drag support; everything else is decorative
 * and sits under the invisible range track via absolute positioning.
 */
export const TimeScrubber: React.FC<Props> = ({
  min,
  max,
  value,
  onChange,
  dateFor,
  labelLeft = 'beobachtet',
  labelMid = 'heute',
  labelRight = 'prognose',
}) => {
  const span = Math.max(max - min, 1);
  const pct = ((value - min) / span) * 100;
  const todayPct = ((0 - min) / span) * 100;

  // Week ticks — every 7 horizon days within [min, max].
  const ticks = useMemo(() => {
    const out: Array<{ day: number; pct: number; isWeek: boolean; isBoundary: boolean }> = [];
    for (let d = min; d <= max; d++) {
      const isWeek = d % 7 === 0;
      if (isWeek) {
        out.push({
          day: d,
          pct: ((d - min) / span) * 100,
          isWeek,
          isBoundary: d === min || d === max,
        });
      }
    }
    return out;
  }, [min, max, span]);

  const handleLabel = (() => {
    const iso = dateFor?.(value);
    if (iso) {
      try {
        return new Date(iso).toLocaleDateString('de-DE', {
          day: '2-digit',
          month: 'short',
        });
      } catch {
        /* fall through */
      }
    }
    if (value === 0) return 'heute';
    return value > 0 ? `+${value} Tage` : `${value} Tage`;
  })();

  return (
    <div className="peix-time-scrubber" role="group" aria-label="Zeitachse">
      <div className="peix-time-scrubber__track">
        {/* Observed side */}
        <div
          className="peix-time-scrubber__band peix-time-scrubber__band--observed"
          style={{ left: 0, width: `${todayPct}%` }}
        />
        {/* Forecast side */}
        <div
          className="peix-time-scrubber__band peix-time-scrubber__band--forecast"
          style={{ left: `${todayPct}%`, width: `${100 - todayPct}%` }}
        />

        {/* Week ticks */}
        {ticks.map((t) => (
          <span
            key={t.day}
            className={
              'peix-time-scrubber__tick ' +
              (t.day === 0 ? 'peix-time-scrubber__tick--today ' : '') +
              (t.isBoundary ? 'peix-time-scrubber__tick--boundary' : '')
            }
            style={{ left: `${t.pct}%` }}
            aria-hidden
          >
            <span className="peix-time-scrubber__tick-label">
              {t.day === 0 ? 'heute' : t.day < 0 ? `${t.day}d` : `+${t.day}d`}
            </span>
          </span>
        ))}

        {/* Handle (pin) */}
        <div
          className="peix-time-scrubber__handle"
          style={{ left: `${pct}%` }}
          aria-hidden
        >
          <span className="peix-time-scrubber__handle-caption">{handleLabel}</span>
          <span className="peix-time-scrubber__handle-pin" />
          <span className="peix-time-scrubber__handle-stem" />
        </div>

        {/* Invisible but accessible range input on top of everything */}
        <input
          className="peix-time-scrubber__input"
          type="range"
          min={min}
          max={max}
          value={value}
          step={1}
          onChange={(e) => onChange(parseInt(e.target.value, 10))}
          aria-label="Zeitachse verschieben"
        />
      </div>

      <div className="peix-time-scrubber__legend">
        <span>{labelLeft}</span>
        <span className="peix-time-scrubber__legend-mid">{labelMid}</span>
        <span>{labelRight}</span>
      </div>
    </div>
  );
};

export default TimeScrubber;
