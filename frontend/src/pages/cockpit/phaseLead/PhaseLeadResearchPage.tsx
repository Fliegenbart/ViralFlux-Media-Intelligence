import React from 'react';
import { Link } from 'react-router-dom';

import '../../../styles/peix.css';
import '../../../styles/peix-gate.css';
import './phase-lead.css';

import CockpitGate from '../CockpitGate';
import { usePhaseLeadSnapshot } from './usePhaseLeadSnapshot';

const sensorRows = [
  {
    source: 'AMELAG Abwasser',
    phase: 'frueh',
    role: 'Sieht Viruslast oft, bevor gemeldete Faelle sichtbar steigen.',
  },
  {
    source: 'SurvStat',
    phase: 'spaeter',
    role: 'Kalibriert den pathogen-spezifischen Verlauf, aber mit Meldeverzug.',
  },
  {
    source: 'AGI / ARE',
    phase: 'symptomatisch',
    role: 'Liest Atemwegsaktivitaet naeher am Versorgungsgeschehen.',
  },
  {
    source: 'SARI / Hospital',
    phase: 'laggend',
    role: 'Verankert Schwere, ist fuer 3-14 Tage aber meist zu spaet.',
  },
];

const stateRows = [
  {
    symbol: 'x',
    label: 'verstecktes Infektionsniveau',
    plain: 'Wie viel Infektion gerade wahrscheinlich wirklich im Umlauf ist.',
  },
  {
    symbol: 'q',
    label: 'verstecktes Wachstum',
    plain: 'Ob die Lage gerade steigt oder faellt.',
  },
  {
    symbol: 'c',
    label: 'Beschleunigung',
    plain: 'Ob der Anstieg schneller wird oder wieder abbremst.',
  },
];

const methodSteps = [
  'Alle Datenquellen werden auf den Infektionszeitpunkt zurueckgedacht.',
  'Fruehe und spaete Sensoren werden als Verhaeltnis gelesen.',
  'Dieses Verhaeltnis schaetzt Wachstum q und, mit mehreren Quellen, Beschleunigung c.',
  'Ein regionaler Kontaktgraph sagt, wohin der Druck als Naechstes wandern kann.',
  'Die Prognose liefert Wahrscheinlichkeiten fuer 3 bis 14 Tage, keine festen Fakten.',
];

const validationRows = [
  'Nur historische As-of-Daten verwenden, also genau das, was damals bekannt war.',
  'Gegen Persistence, SurvStat-only, Wastewater-only und Graph-only testen.',
  'Top-k Recall, Brier Score, CRPS und Kalibrierung getrennt ausweisen.',
  'Die wichtigste Ablation: dasselbe Modell ohne Phase-Lead-Ratios.',
];

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
            Phase-Lead research layer loading...
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
            <div className="phase-lead-kicker">Phase-Lead unavailable</div>
            <h1>Research snapshot could not be loaded.</h1>
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

  const sourceRows = Object.entries(snapshot.sources);
  const topRegions = snapshot.regions.slice(0, 6);
  const topRegion = snapshot.regions[0];

  return (
    <div className="peix phase-lead-page">
      <main className="phase-lead-shell">
        <header className="phase-lead-hero">
          <div className="phase-lead-hero__copy">
            <Link to="/cockpit" className="phase-lead-back">
              Back to cockpit
            </Link>
            <div className="phase-lead-kicker">Experimental method subpage</div>
            <h1>Phase-Lead Graph Renewal Filter</h1>
            <p>
              Research-only Methode fuer regionale Virus-Fruehwarnung. Die
              Grundidee: Abwasser, Meldedaten, Syndromdaten und Klinikdaten
              sehen dieselbe Infektionswelle zu unterschiedlichen Zeitpunkten.
              Dieser Zeitversatz wird nicht weggeglattet, sondern als Messgeraet
              fuer verstecktes Wachstum genutzt.
            </p>
          </div>
          <aside className="phase-lead-hero__meta" aria-label="Research boundary">
            <span>{snapshot.virus_typ}</span>
            <span>{snapshot.version}</span>
            <span>{formatDate(snapshot.as_of)}</span>
            <span>{snapshot.horizons.join('/')} day horizons</span>
          </aside>
        </header>

        <section className="phase-lead-panel phase-lead-lede" aria-labelledby="phase-lead-short">
          <div>
            <div className="phase-lead-kicker">Kurz gesagt</div>
            <h2 id="phase-lead-short">Frueher Sensor hoch, spaeter Sensor noch niedrig: das ist ein Wachstumssignal.</h2>
          </div>
          <p>
            Wenn eine Welle beginnt, reagiert Abwasser oder ein frueher
            Symptom-Sensor haeufig vor den offiziellen Meldedaten. Das Modell
            liest deshalb nicht nur jede Kurve einzeln, sondern vor allem das
            Verhaeltnis zwischen fruehen und spaeten Sensoren.
          </p>
        </section>

        <section className="phase-lead-panel phase-lead-live" aria-labelledby="phase-lead-live-title">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">Live run</div>
              <h2 id="phase-lead-live-title">Rechnet mit echten AMELAG-, SurvStat- und ARE-Daten.</h2>
            </div>
            <p>
              Der Snapshot ist point-in-time gebaut: Es werden nur Daten genutzt,
              die am Ausgabedatum sichtbar waren.
            </p>
          </div>

          <div className="phase-lead-live-grid">
            <div className="phase-lead-live-metric">
              <span>Observations</span>
              <strong>{snapshot.summary.observation_count}</strong>
              <small>{formatDate(snapshot.summary.window_start)} - {formatDate(snapshot.summary.window_end)}</small>
            </div>
            <div className="phase-lead-live-metric">
              <span>Top region</span>
              <strong>{topRegion?.region_code ?? '-'}</strong>
              <small>{topRegion?.region ?? 'No region'}</small>
            </div>
            <div className="phase-lead-live-metric">
              <span>p(up) h7</span>
              <strong>{formatPercent(topRegion?.p_up_h7)}</strong>
              <small>Probability of rising latent incidence</small>
            </div>
            <div className="phase-lead-live-metric">
              <span>Fit</span>
              <strong>{snapshot.summary.converged ? 'Converged' : 'Diagnostic'}</strong>
              <small>{snapshot.summary.warning_count} warnings</small>
            </div>
          </div>

          <div className="phase-lead-live-columns">
            <div className="phase-lead-table-wrap">
              <table className="phase-lead-table">
                <thead>
                  <tr>
                    <th>Quelle</th>
                    <th>Rows</th>
                    <th>Latest event</th>
                    <th>Units</th>
                  </tr>
                </thead>
                <tbody>
                  {sourceRows.map(([source, status]) => (
                    <tr key={source}>
                      <td>{source}</td>
                      <td>{status.rows}</td>
                      <td>{formatDate(status.latest_event_date)}</td>
                      <td>{status.units.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="phase-lead-table-wrap">
              <table className="phase-lead-table">
                <thead>
                  <tr>
                    <th>Region</th>
                    <th>p(up) h7</th>
                    <th>p(surge) h7</th>
                    <th>Growth</th>
                    <th>GEGB</th>
                  </tr>
                </thead>
                <tbody>
                  {topRegions.map((region) => (
                    <tr key={region.region_code}>
                      <td>{region.region_code} - {region.region}</td>
                      <td>{formatPercent(region.p_up_h7)}</td>
                      <td>{formatPercent(region.p_surge_h7)}</td>
                      <td>{formatSigned(region.current_growth)}</td>
                      <td>{region.gegb.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {snapshot.warnings.length > 0 ? (
            <ul className="phase-lead-warning-list">
              {snapshot.warnings.slice(0, 4).map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="phase-lead-grid phase-lead-grid--three" aria-label="Hidden state">
          {stateRows.map((row) => (
            <article className="phase-lead-state" key={row.symbol}>
              <span>{row.symbol}</span>
              <h3>{row.label}</h3>
              <p>{row.plain}</p>
            </article>
          ))}
        </section>

        <section className="phase-lead-panel phase-lead-formula" aria-labelledby="phase-lead-core">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">Mathematischer Kern</div>
              <h2 id="phase-lead-core">Das Sensor-Verhaeltnis wird zum Messinstrument.</h2>
            </div>
            <p>
              In einfachen Worten: ein frueher Sensor geteilt durch einen
              spaeten Sensor ist eine monotone Funktion des versteckten
              Wachstums. Monoton bedeutet hier: wenn das Verhaeltnis steigt,
              steigt auch das geschaetzte Wachstum.
            </p>
          </div>

          <div className="phase-lead-equation">
            <code>early_sensor / late_sensor =&gt; hidden_growth_q</code>
            <code>growth_q + acceleration_c + graph_pressure =&gt; 3-14 day forecast</code>
          </div>

          <div className="phase-lead-explain-grid">
            <div>
              <b>Warum das funktioniert</b>
              <p>
                Jede Quelle hat einen eigenen Infektionsalter-Kernel: Abwasser
                sieht fruehere Infektionsalter, SurvStat spaetere. Der Unterschied
                enthaelt Information ueber die aktuelle Richtung.
              </p>
            </div>
            <div>
              <b>Was neu daran ist</b>
              <p>
                Der Lead-Lag-Effekt wird nicht als Stoerung behandelt. Er wird
                direkt genutzt, um Wachstum und Beschleunigung zu schaetzen.
              </p>
            </div>
          </div>
        </section>

        <section className="phase-lead-panel" aria-labelledby="phase-lead-sensors">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">Datenquellen</div>
              <h2 id="phase-lead-sensors">Jeder Datenstrom sieht die Welle in einer anderen Phase.</h2>
            </div>
            <p>
              Die Methode passt besonders zu RKI-nahen Quellen, weil diese
              fachlich verschiedene Beobachtungsfenster desselben Geschehens
              liefern.
            </p>
          </div>
          <div className="phase-lead-table-wrap">
            <table className="phase-lead-table">
              <thead>
                <tr>
                  <th>Quelle</th>
                  <th>Phase</th>
                  <th>Rolle im Modell</th>
                </tr>
              </thead>
              <tbody>
                {sensorRows.map((row) => (
                  <tr key={row.source}>
                    <td>{row.source}</td>
                    <td>{row.phase}</td>
                    <td>{row.role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="phase-lead-panel phase-lead-flow" aria-labelledby="phase-lead-flow-title">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">Forecast-Mechanik</div>
              <h2 id="phase-lead-flow-title">Lokales Signal plus regionaler Graph.</h2>
            </div>
            <p>
              Das lokale Wachstum sagt, was in einer Region gerade passiert.
              Der Graph sagt, welche Nachbar- oder Pendlerregionen diesen Druck
              bald weitergeben koennen.
            </p>
          </div>
          <ol className="phase-lead-stepper">
            {methodSteps.map((step) => (
              <li key={step}>
                <span />
                <p>{step}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="phase-lead-grid phase-lead-grid--two" aria-label="Forecast outputs">
          <article className="phase-lead-panel phase-lead-output">
            <div className="phase-lead-kicker">Output</div>
            <h2>Was die Seite spaeter liefern kann</h2>
            <p>
              Wahrscheinlichkeiten fuer steigende Regionen, erwartete
              Ueberlast gegen saisonale Baseline und ein growth-weighted
              burden score fuer Media-Priorisierung.
            </p>
            <code>EGB = expected future burden when q &gt; threshold</code>
          </article>
          <article className="phase-lead-panel phase-lead-output phase-lead-output--guardrail">
            <div className="phase-lead-kicker">Guardrail</div>
            <h2>Was sie bewusst nicht behauptet</h2>
            <p>
              Keine automatische Budgetumschichtung, keine medizinische
              Vorhersagegarantie und kein Beweis fuer Media-ROI ohne echte
              Outcome- und Holdout-Daten.
            </p>
            <code>Research signal != activation approval</code>
          </article>
        </section>

        <section className="phase-lead-panel" aria-labelledby="phase-lead-validation">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">Validierung</div>
              <h2 id="phase-lead-validation">Die Methode muss historisch ehrlich getestet werden.</h2>
            </div>
            <p>
              Der faire Test friert fuer jeden historischen Tag den damaligen
              Datenstand ein. Sonst wuerde das Modell Informationen aus der
              Zukunft sehen.
            </p>
          </div>
          <ul className="phase-lead-checklist">
            {validationRows.map((row) => (
              <li key={row}>{row}</li>
            ))}
          </ul>
        </section>

        <footer className="phase-lead-footer">
          <div>
            <b>Research boundary</b>
            <p>
              Diese Unterseite beschreibt eine Forschungs-Methode. Sie erweitert
              das Cockpit nicht um eine operative Freigabe-Logik und veraendert
              keine Budgets.
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
