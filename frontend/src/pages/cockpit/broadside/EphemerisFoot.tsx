import React from 'react';

export interface EphemerisRowData {
  label: string;
  value: React.ReactNode;
  warn?: boolean;
}

interface Props {
  leadLabel: string | null;
  leadNote: string;
  observed: EphemerisRowData[];
  forecast: EphemerisRowData[];
}

const EphemerisFoot: React.FC<Props> = ({
  leadLabel,
  leadNote,
  observed,
  forecast,
}) => (
  <div className="ephemeris">
    <div className="ephemeris-hero">
      <div>
        <div className="hero-kicker">Lead-Time · ED führt SURVSTAT</div>
        <div className="hero-value">
          {leadLabel !== null ? (
            <>
              {leadLabel}
              <span className="hero-unit">TAGE</span>
            </>
          ) : (
            <>—</>
          )}
        </div>
      </div>
      <p className="hero-note">{leadNote}</p>
    </div>
    <div className="ephemeris-cols">
      <div className="ephemeris-col">
        <div className="col-kicker">Observed · bis HEUTE</div>
        {observed.map((row, index) => (
          <div className="ephem-row" key={`o-${index}`}>
            <span className="label">{row.label}</span>
            <span className={`value${row.warn ? ' warn' : ''}`}>{row.value}</span>
          </div>
        ))}
      </div>
      <div className="ephemeris-col">
        <div className="col-kicker">Forecast · Modell</div>
        {forecast.map((row, index) => (
          <div className="ephem-row" key={`f-${index}`}>
            <span className="label">{row.label}</span>
            <span className={`value${row.warn ? ' warn' : ''}`}>{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  </div>
);

export default EphemerisFoot;
