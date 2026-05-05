import React from 'react';
import { Link } from 'react-router-dom';

import '../../../styles/peix.css';
import '../../../styles/peix-gate.css';
import './phase-lead.css';

import CockpitGate from '../CockpitGate';
import { usePhaseLeadSnapshot } from './usePhaseLeadSnapshot';
import type { PhaseLeadRegion, PhaseLeadSnapshot } from './types';

const sourceLabels: Record<string, string> = {
  wastewater: 'AMELAG',
  survstat: 'SurvStat',
  are: 'ARE',
  notaufnahme: 'Notaufnahme',
};

function formatDate(value: string | null | undefined): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString('de-DE');
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return `${Math.round(value * 100)}%`;
}

function formatSigned(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
}

function formatOne(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return value.toFixed(1);
}

function actionForRegion(region: PhaseLeadRegion | undefined): {
  label: string;
  tone: 'prepare' | 'watch' | 'hold';
  explanation: string;
} {
  if (!region) {
    return {
      label: 'No region',
      tone: 'hold',
      explanation: 'Noch kein regionales Signal vorhanden.',
    };
  }
  if (region.p_surge_h7 >= 0.35 || region.p_up_h7 >= 0.75) {
    return {
      label: `Prepare ${region.region}`,
      tone: 'prepare',
      explanation: 'Creative, regionale Gebote und Apothekenabdeckung vorbereiten. Budget bleibt shadow-only.',
    };
  }
  if (region.p_up_h7 >= 0.55) {
    return {
      label: `Watch ${region.region}`,
      tone: 'watch',
      explanation: 'Region eng beobachten und Aktivierungspaket bereithalten.',
    };
  }
  return {
    label: `Hold ${region.region}`,
    tone: 'hold',
    explanation: 'Keine operative Vorbereitungsaktion noetig.',
  };
}

function confidenceLabel(snapshot: PhaseLeadSnapshot): string {
  if (snapshot.summary.converged && snapshot.summary.warning_count === 0) return 'hoch';
  if (snapshot.summary.fit_mode === 'map_optimization') return 'mittel';
  return 'vorlaeufig';
}

function sourceFreshness(snapshot: PhaseLeadSnapshot): string {
  const latestDates = Object.values(snapshot.sources)
    .map((source) => source.latest_event_date)
    .filter(Boolean)
    .sort();
  const latest = latestDates[latestDates.length - 1];
  return latest ? formatDate(latest) : '-';
}

function topRegionHeadline(topRegion: PhaseLeadRegion | undefined): string {
  if (!topRegion) return 'Kein regionaler Kandidat';
  return `${topRegion.region} zuerst vorbereiten`;
}

export const PhaseLeadResearchPage: React.FC = () => {
  const { snapshot, loading, error, reload } = usePhaseLeadSnapshot();
  const isAuth401 =
    error &&
    (((error as Error & { status?: number }).status === 401) ||
      /HTTP 401/.test(error.message));

  if (isAuth401 && !snapshot) {
    return <CockpitGate onUnlocked={reload} />;
  }

  if (loading && !snapshot) {
    return (
      <div className="peix phase-lead-page">
        <main className="phase-lead-shell">
          <div className="phase-lead-loading" role="status">
            Regional Media Watch loading...
          </div>
        </main>
      </div>
    );
  }

  if (error && !snapshot) {
    return (
      <div className="peix phase-lead-page">
        <main className="phase-lead-shell">
          <Link to="/cockpit" className="phase-lead-back">
            Back to cockpit
          </Link>
          <section className="phase-lead-panel phase-lead-error" role="alert">
            <div className="phase-lead-kicker">Signal unavailable</div>
            <h1>Regional Media Watch konnte nicht geladen werden.</h1>
            <p>{error.message}</p>
            <button type="button" onClick={reload}>
              Retry
            </button>
          </section>
        </main>
      </div>
    );
  }

  if (!snapshot) return null;

  const topRegions = snapshot.regions.slice(0, 8);
  const topRegion = snapshot.regions[0];
  const primaryAction = actionForRegion(topRegion);
  const connectedSources = Object.keys(snapshot.sources).length;
  const modelConfidence = confidenceLabel(snapshot);

  return (
    <div className="peix phase-lead-page">
      <main className="phase-lead-shell">
        <header className="phase-lead-hero phase-lead-hero--product">
          <div className="phase-lead-hero__copy">
            <Link to="/cockpit" className="phase-lead-back">
              Back to cockpit
            </Link>
            <div className="phase-lead-kicker">Live product signal</div>
            <h1>Regional Media Watch</h1>
            <p>
              Fruehwarnung fuer regionale Media-Vorbereitung. Das Signal sagt,
              welche Bundeslaender in den naechsten Tagen wahrscheinlicher
              steigen und wo Marketing heute vorbereitet sein sollte.
            </p>
          </div>
          <aside className="phase-lead-hero__meta" aria-label="Signal status">
            <span>{snapshot.virus_typ}</span>
            <span>{formatDate(snapshot.as_of)}</span>
            <span>{snapshot.horizons.join('/')} Tage Horizont</span>
            <span>{snapshot.summary.fit_mode === 'map_optimization' ? 'MAP optimiert' : 'Schnellmodus'}</span>
          </aside>
        </header>

        <section className={`phase-lead-panel phase-lead-action phase-lead-action--${primaryAction.tone}`}>
          <div>
            <div className="phase-lead-kicker">Naechste Aktion</div>
            <h2>{topRegionHeadline(topRegion)}</h2>
            <p>{primaryAction.explanation}</p>
          </div>
          <div className="phase-lead-action__command">{primaryAction.label}</div>
        </section>

        <section className="phase-lead-live-grid phase-lead-live-grid--product" aria-label="Signal metrics">
          <div className="phase-lead-live-metric">
            <span>p(up) 7 Tage</span>
            <strong>{formatPercent(topRegion?.p_up_h7)}</strong>
            <small>{topRegion?.region ?? 'Keine Region'}</small>
          </div>
          <div className="phase-lead-live-metric">
            <span>Surge-Risiko</span>
            <strong>{formatPercent(topRegion?.p_surge_h7)}</strong>
            <small>Schwelle fuer Vorbereitung</small>
          </div>
          <div className="phase-lead-live-metric">
            <span>Modellvertrauen</span>
            <strong>{modelConfidence}</strong>
            <small>{snapshot.summary.warning_count} Warnungen</small>
          </div>
          <div className="phase-lead-live-metric">
            <span>Datenstand</span>
            <strong>{connectedSources}</strong>
            <small>Quellen bis {sourceFreshness(snapshot)}</small>
          </div>
        </section>

        <section className="phase-lead-panel phase-lead-sales-gate" aria-labelledby="phase-lead-sales-gate-title">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">Budget-Gate</div>
              <h2 id="phase-lead-sales-gate-title">Budget bleibt shadow-only bis GELO-Sales angebunden sind.</h2>
            </div>
            <p>
              Das Signal priorisiert Vorbereitung, nicht automatische
              Umschichtung. Sales- und Outcome-Daten fehlen noch fuer echte
              Budgetfreigabe.
            </p>
          </div>
          <div className="phase-lead-decision-grid">
            <article>
              <span>Heute erlaubt</span>
              <b>Vorbereiten</b>
              <p>Regionale Creatives, Inventar, Zielgruppen und Apothekenlisten pruefen.</p>
            </article>
            <article>
              <span>Noch blockiert</span>
              <b>Budget verschieben</b>
              <p>Ohne GELO-Sales bleibt jede Aktivierung eine manuelle Business-Entscheidung.</p>
            </article>
            <article>
              <span>Naechster Datenhebel</span>
              <b>Sales anschliessen</b>
              <p>Danach kann das Signal gegen Nachfrage und Kampagnenwirkung kalibriert werden.</p>
            </article>
          </div>
        </section>

        <section className="phase-lead-panel" aria-labelledby="phase-lead-region-title">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">Regionale Priorisierung</div>
              <h2 id="phase-lead-region-title">Welche Bundeslaender jetzt Aufmerksamkeit brauchen.</h2>
            </div>
            <p>
              Sortiert nach GEGB: ein growth-weighted burden score fuer
              Media-Priorisierung. Hoeher bedeutet: mehr erwartete Last bei
              positivem Wachstum.
            </p>
          </div>
          <div className="phase-lead-table-wrap">
            <table className="phase-lead-table">
              <thead>
                <tr>
                  <th>Region</th>
                  <th>Empfehlung</th>
                  <th>p(up) h7</th>
                  <th>Surge h7</th>
                  <th>Wachstum</th>
                  <th>GEGB</th>
                </tr>
              </thead>
              <tbody>
                {topRegions.map((region) => {
                  const action = actionForRegion(region);
                  return (
                    <tr key={region.region_code}>
                      <td>{region.region_code} - {region.region}</td>
                      <td>
                        <span className={`phase-lead-badge phase-lead-badge--${action.tone}`}>
                          {action.label}
                        </span>
                      </td>
                      <td>{formatPercent(region.p_up_h7)}</td>
                      <td>{formatPercent(region.p_surge_h7)}</td>
                      <td>{formatSigned(region.current_growth)}</td>
                      <td>{formatOne(region.gegb)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="phase-lead-grid phase-lead-grid--two" aria-label="Operational context">
          <article className="phase-lead-panel phase-lead-output">
            <div className="phase-lead-kicker">Datenbasis</div>
            <h2>Live-Quellen sind verbunden.</h2>
            <div className="phase-lead-source-list">
              {Object.entries(snapshot.sources).map(([source, status]) => (
                <div key={source} className="phase-lead-source-pill">
                  <b>{sourceLabels[source] ?? source}</b>
                  <span>{status.rows} Zeilen</span>
                  <small>{formatDate(status.latest_event_date)} · {status.units.length} Einheiten</small>
                </div>
              ))}
            </div>
          </article>
          <article className="phase-lead-panel phase-lead-output">
            <div className="phase-lead-kicker">Modellstatus</div>
            <h2>{snapshot.summary.converged ? 'Optimierung konvergiert.' : 'Optimierung pruefen.'}</h2>
            <p>
              {snapshot.summary.fit_mode === 'map_optimization'
                ? 'Das Cockpit nutzt das gespeicherte MAP-Ergebnis aus dem Nachtlauf.'
                : 'Das Cockpit nutzt gerade den schnellen Fallback, bis ein MAP-Ergebnis vorliegt.'}
            </p>
            <div className="phase-lead-model-meta">
              <span>Beobachtungen: {snapshot.summary.observation_count}</span>
              <span>Fenster: {formatDate(snapshot.summary.window_start)} - {formatDate(snapshot.summary.window_end)}</span>
              <span>Objective: {formatOne(snapshot.summary.objective_value)}</span>
            </div>
          </article>
        </section>

        {snapshot.warnings.length > 0 ? (
          <section className="phase-lead-panel" aria-label="Model warnings">
            <div className="phase-lead-kicker">Modellhinweise</div>
            <ul className="phase-lead-warning-list">
              {snapshot.warnings.slice(0, 4).map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </section>
        ) : null}

        <footer className="phase-lead-footer">
          <div>
            <b>Produktstatus</b>
            <p>
              Live-Fruehwarnsignal fuer Vorbereitung. Budgetfreigabe bleibt
              blockiert, bis GELO-Sales und Outcome-Validierung angeschlossen sind.
            </p>
          </div>
          <Link to="/cockpit" className="phase-lead-footer__link">
            Return to cockpit
          </Link>
        </footer>
      </main>
    </div>
  );
};

export default PhaseLeadResearchPage;
