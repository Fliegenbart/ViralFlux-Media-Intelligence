import React from 'react';

/**
 * ChronoBar — schlanke Sticky-Leiste, 56px hoch.
 *
 * Drei Zonen: Brand · KW-Ticker (±2 Wochen, aktive groß) · Virus-Switcher.
 * EPOCH-Counter, NEXT-RUN-Countdown, CLIENT-Label und DATA-Link sind in
 * den Footer gewandert (Renovation 2026-04-22, Story-Scroll).
 */

interface Props {
  currentKw: number;
  virusTyp: string;
  onVirusChange: (v: string) => void;
  supportedViruses: readonly string[];
}

const VIRUS_SHORT: Record<string, string> = {
  'Influenza A': 'Flu-A',
  'Influenza B': 'Flu-B',
  'RSV A': 'RSV',
  'SARS-CoV-2': 'Cov-2',
};

const KW_OFFSETS = [-2, -1, 0, 1, 2];

export const ChronoBar: React.FC<Props> = ({
  currentKw,
  virusTyp,
  onVirusChange,
  supportedViruses,
}) => {
  return (
    <div className="chrono">
      <div className="chrono-inner">
        <div className="chrono-brand">
          <span className="dot" />
          FLUXENGINE
        </div>
        <div className="chrono-ticks" role="presentation">
          {KW_OFFSETS.map((w) => {
            const kw = currentKw + w;
            const kwDisplay = ((kw - 1 + 53) % 53) + 1;
            return (
              <span
                key={w}
                className={`chrono-tick${w === 0 ? ' active' : ''}`}
              >
                KW{String(kwDisplay).padStart(2, '0')}
              </span>
            );
          })}
        </div>
        <div
          className="chrono-virus-switcher"
          role="tablist"
          aria-label="Virus auswählen"
        >
          {supportedViruses.map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={v === virusTyp}
              className={`chrono-virus-btn${v === virusTyp ? ' active' : ''}`}
              onClick={() => onVirusChange(v)}
              title={v}
            >
              {VIRUS_SHORT[v] ?? v}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ChronoBar;
