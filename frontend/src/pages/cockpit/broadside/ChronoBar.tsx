import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

/**
 * ChronoBar — der lebende Puls des Instruments.
 *
 * Die sticky schwarze Leiste am oberen Rand des Cockpits mit drei
 * Information-Feldern:
 *   - live Epoch-Counter (Unix-Sekunden), aktualisiert jede Sekunde
 *   - KW-Ticker als horizontale Zeitachse (10 Wochen zurück, 4 vor)
 *     mit der aktuellen KW in Signal-Terracotta
 *   - Next-Run-Countdown bis zum nächsten Montag 08:00
 *
 * Kein Gimmick — das verankert die Messung in der Zeit, wie ein
 * wissenschaftliches Instrument. Der pulsierende Punkt am Brand ist
 * der einzige bewusst rhythmische Moment des ganzen Layouts.
 *
 * Performance-Note: ein einziges setInterval auf Sekunden-Basis
 * reicht, weil der Counter nur drei DOM-Knoten aktualisiert (epoch,
 * next-run, aktive KW).
 */

interface Props {
  currentKw: number;  // z. B. 16 — aus snapshot.isoWeek parsed
  client: string;     // "GELO"
  virusTyp: string;
  onVirusChange: (v: string) => void;
  supportedViruses: readonly string[];
}

// Short labels for the ChronoBar switcher — full names are too long for
// the sticky top bar. Tooltip carries the full name for accessibility.
const VIRUS_SHORT: Record<string, string> = {
  'Influenza A': 'Flu-A',
  'Influenza B': 'Flu-B',
  'RSV A': 'RSV',
  'SARS-CoV-2': 'Cov-2',
};

function fmtEpoch(now: Date): string {
  return String(Math.floor(now.getTime() / 1000));
}

function fmtNextMondayCountdown(now: Date): string {
  // Zielzeit: nächster Montag 08:00 UTC. JS Date.getDay() → 0 = Sonntag, 1 = Montag.
  const next = new Date(now);
  const dow = now.getDay();
  // Tage bis Montag (exclusive today if it's already Monday past 08:00)
  const daysToMon = ((8 - dow) % 7) || 7;
  next.setDate(next.getDate() + daysToMon);
  next.setHours(8, 0, 0, 0);
  const diffMs = Math.max(0, next.getTime() - now.getTime());
  const d = Math.floor(diffMs / 86_400_000);
  const h = String(Math.floor((diffMs % 86_400_000) / 3_600_000)).padStart(2, '0');
  const m = String(Math.floor((diffMs % 3_600_000) / 60_000)).padStart(2, '0');
  const s = String(Math.floor((diffMs % 60_000) / 1000)).padStart(2, '0');
  return `${d}d ${h}:${m}:${s}`;
}

export const ChronoBar: React.FC<Props> = ({
  currentKw,
  client,
  virusTyp,
  onVirusChange,
  supportedViruses,
}) => {
  const [now, setNow] = useState<Date>(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  // KW-Ticker: 10 zurück, aktuelle, 4 vor → 15 Ticks
  const kwOffsets: number[] = [];
  for (let i = -10; i <= 4; i += 1) kwOffsets.push(i);

  return (
    <div className="chrono">
      <div className="chrono-inner">
        <div className="chrono-brand">
          <span className="dot" />
          FLUXENGINE
        </div>
        <div className="chrono-ticks">
          {kwOffsets.map((w) => {
            const kw = currentKw + w;
            // Normalize to 1..53 range for display
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
        <div className="chrono-meta">
          <span>EPOCH <b>{fmtEpoch(now)}</b></span>
        </div>
        <div className="chrono-meta">
          <span>NEXT RUN <b>{fmtNextMondayCountdown(now)}</b></span>
        </div>
        <div className="chrono-meta">
          <span>CLIENT <b>{client}</b></span>
        </div>
        <div className="chrono-virus-switcher" role="tablist" aria-label="Virus auswählen">
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
        <Link to="/cockpit/data" className="chrono-data-link" title="Data Office · Uploads & Coverage">
          DATA ↗
        </Link>
      </div>
    </div>
  );
};

export default ChronoBar;
