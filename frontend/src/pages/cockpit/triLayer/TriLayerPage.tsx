import React from 'react';
import { Link } from 'react-router-dom';

import '../../../styles/peix.css';
import '../../../styles/peix-gate.css';
import './tri-layer.css';

import CockpitGate from '../CockpitGate';
import { useTriLayerSnapshot } from './useTriLayerSnapshot';
import TriLayerBacktestPanel from './TriLayerBacktestPanel';
import TriLayerGateMatrix from './TriLayerGateMatrix';
import TriLayerRegionTable from './TriLayerRegionTable';
import TriLayerScoreCards from './TriLayerScoreCards';
import TriLayerSourceStatus from './TriLayerSourceStatus';

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return `${date.toLocaleDateString('de-DE')} · ${date.toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
  })}`;
}

export const TriLayerPage: React.FC = () => {
  const { snapshot, loading, error, reload } = useTriLayerSnapshot();
  const isAuth401 =
    error &&
    (((error as Error & { status?: number }).status === 401) ||
      /HTTP 401/.test(error.message));

  if (isAuth401 && !snapshot) {
    return <CockpitGate onUnlocked={reload} />;
  }

  if (loading && !snapshot) {
    return (
      <div className="peix tri-layer-page">
        <main className="tri-layer-shell">
          <div className="tri-layer-loading" role="status">
            Tri-Layer research layer loading…
          </div>
        </main>
      </div>
    );
  }

  if (error && !snapshot) {
    return (
      <div className="peix tri-layer-page">
        <main className="tri-layer-shell">
          <Link to="/cockpit" className="tri-layer-back">Back to cockpit</Link>
          <section className="tri-layer-panel tri-layer-error" role="alert">
            <div className="tri-layer-kicker">Tri-Layer unavailable</div>
            <h1>Research snapshot could not be loaded.</h1>
            <p>{error.message}</p>
            <button type="button" onClick={reload}>Retry</button>
          </section>
        </main>
      </div>
    );
  }

  if (!snapshot) return null;

  const topRegionName = snapshot.regions[0]?.region ?? 'Eine Region';

  return (
    <div className="peix tri-layer-page">
      <main className="tri-layer-shell">
        <header className="tri-layer-hero">
          <div>
            <Link to="/cockpit" className="tri-layer-back">Back to cockpit</Link>
            <div className="tri-layer-kicker">Experimental cockpit subpage</div>
            <h1>Tri-Layer Evidence Fusion — Research Layer</h1>
            <p>
              Diese Research-Seite bewertet konservativ, ob Cockpit-Signal,
              klinische Bestätigung und Sales-Kalibrierung gemeinsam tragen.
              Research-only. This page does not activate or change media budget.
            </p>
          </div>
          <aside className="tri-layer-hero-meta" aria-label="Tri-Layer metadata">
            <span>{snapshot.virus_typ}</span>
            <span>Horizon {snapshot.horizon_days} days</span>
            <span>{snapshot.version}</span>
            <span>{formatDateTime(snapshot.as_of)}</span>
          </aside>
        </header>

        <TriLayerScoreCards summary={snapshot.summary} />
        <section className="tri-layer-panel tri-layer-reconcile" aria-labelledby="tri-layer-reconcile-title">
          <div className="tri-layer-section-head">
            <div>
              <div className="tri-layer-kicker">Lesart</div>
              <h2 id="tri-layer-reconcile-title">Cockpit-Signal ≠ Tri-Layer-Freigabe</h2>
            </div>
            <p>
              Das Cockpit zeigt den heutigen regionalen Signal-Kandidaten.
              Der Tri-Layer prüft, ob Abwasser, Klinik und Sales gemeinsam
              stark genug sind.
            </p>
          </div>
          <div className="tri-layer-reconcile-grid">
            <div>
              <span>Cockpit</span>
              <b>aktueller regionaler Riser</b>
              <small>{topRegionName} kann sichtbar steigen, während der Tri-Layer niedrig bleibt.</small>
            </div>
            <div>
              <span>Tri-Layer</span>
              <b>konservative Tragfähigkeit</b>
              <small>Sales fehlt, Horizon {snapshot.horizon_days} days, Budget bleibt blockiert.</small>
            </div>
            <div>
              <span>Budget</span>
              <b>{String(snapshot.summary.budget_can_change)}</b>
              <small>Ein niedriger Cross-Layer-Score ändert keine Cockpit-Daten und gibt kein Budget frei.</small>
            </div>
          </div>
        </section>
        <TriLayerSourceStatus sourceStatus={snapshot.source_status} />
        <TriLayerGateMatrix regions={snapshot.regions} />
        <TriLayerRegionTable regions={snapshot.regions} />
        <TriLayerBacktestPanel />

        <section className="tri-layer-panel tri-layer-method">
          <div className="tri-layer-kicker">Method note</div>
          <p>Research-only. This page does not activate or change media budget.</p>
          <p>{snapshot.summary.reason}</p>
          {snapshot.model_notes.length > 0 ? (
            <ul>
              {snapshot.model_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </section>
      </main>
    </div>
  );
};

export default TriLayerPage;
