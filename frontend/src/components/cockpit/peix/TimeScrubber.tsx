import React from 'react';

interface Props {
  min: number;
  max: number;
  value: number;
  onChange: (v: number) => void;
  labelLeft?: string;
  labelMid?: string;
  labelRight?: string;
}

/**
 * Editorial timeline scrubber. Rail split into observed (ink) and forecast (warm).
 */
export const TimeScrubber: React.FC<Props> = ({
  min, max, value, onChange,
  labelLeft = '−14 Tage (beobachtet)',
  labelMid  = 'heute',
  labelRight = '+7 Tage (forecast)',
}) => {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="peix-scrubber">
      <div className="peix-scrubber-track">
        <div className="peix-scrubber-rail" />
        <div className="peix-scrubber-thumb" style={{ left: `${pct}%` }} aria-hidden />
        <input
          className="peix-scrubber-input"
          type="range" min={min} max={max} value={value}
          onChange={(e) => onChange(parseInt(e.target.value, 10))}
          step={1}
          aria-label="Zeitachse"
        />
      </div>
      <div className="peix-scrubber-labels">
        <span>{labelLeft}</span>
        <span style={{ color: 'var(--peix-ink)' }}>{labelMid}</span>
        <span>{labelRight}</span>
      </div>
    </div>
  );
};

export default TimeScrubber;
