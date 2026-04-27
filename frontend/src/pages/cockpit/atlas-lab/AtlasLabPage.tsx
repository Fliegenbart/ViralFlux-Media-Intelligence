import React from 'react';
import { useCockpitSnapshot } from '../useCockpitSnapshot';
import AtlasRidge from './AtlasRidge';
import AtlasConstellation from './AtlasConstellation';
// 2026-04-23: Choropleth wandert in den broadside-Folder, weil sie
// jetzt die produktive Atlas-Variante im Cockpit ist. Lab importiert
// von dort (single source of truth).
import AtlasChoropleth from '../broadside/AtlasChoropleth';
import AtlasSparklines from './AtlasSparklines';
import './atlas-lab.css';

/**
 * AtlasLabPage — interner Designspielplatz für Atlas-Alternativen.
 *
 * Erreichbar über /cockpit/atlas-lab. Nutzt denselben Snapshot-Hook
 * wie der Cockpit (Cookie-Auth — Nutzer muss zuerst /cockpit besucht
 * und freigeschaltet haben).
 *
 * Drei Konzepte werden untereinander gerendert:
 *   A · Wave-Ridge    — Joy-Plot-Stil, alle BL als gestapelte Wellen
 *   B · Constellation — geo-positionierte Stars, atmosphärisch
 *   C · Sparkline-Grid — 4×4 Karten mit 28-Tage-Verlauf
 *
 * Hinweis: Sparkline-/Ridge-Verläufe sind synthetisch (deterministisch
 * aus Code+Delta), bis ein echter 28-Tage-History im Snapshot landet.
 */

const AtlasLabPage: React.FC = () => {
  const { snapshot, loading, error } = useCockpitSnapshot();

  if (loading || !snapshot) {
    return (
      <div className="atlas-lab atlas-lab-state">
        <p>Snapshot lädt…</p>
        <p className="lab-back">
          <a href="/cockpit">← zurück zum Cockpit</a>
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="atlas-lab atlas-lab-state">
        <p>Snapshot konnte nicht geladen werden: {error.message}</p>
        <p>
          Bitte erst <a href="/cockpit">/cockpit</a> öffnen und das
          Passwort eingeben — diese Lab-Seite teilt das Auth-Cookie.
        </p>
      </div>
    );
  }

  return (
    <div className="atlas-lab">
      <header className="lab-head">
        <p className="lab-eyebrow">Atlas-Lab</p>
        <h1>Drei alternative Designs für den Wellen-Atlas</h1>
        <p className="lab-intro">
          Echte Daten aus dem aktuellen Snapshot ({snapshot.virusLabel ?? snapshot.virusTyp},
          {' '}{snapshot.regions.length} Bundesländer). Sparkline-/Ridge-Verläufe
          sind für den Lab-Test deterministisch synthetisiert — der Look stimmt,
          die Wellenform ist Demo. Top-Riser ist farblich abgesetzt.
        </p>
        <p className="lab-back">
          <a href="/cockpit">← zurück zum Cockpit</a>
        </p>
      </header>

      <section className="lab-section">
        <header>
          <p className="lab-tag">Konzept A</p>
          <h2>Wave-Ridge</h2>
          <p>
            16 Bundesländer als gestapelte Wellenkurven (Joy-Division-Stil).
            Sehr „Wellen-Atlas"-Mood — die Welle wird visuell wörtlich.
            Vertikal scannbar, ein Riser sticht durch Farbfüllung heraus.
          </p>
        </header>
        <div className="lab-canvas lab-canvas-dark">
          <AtlasRidge snapshot={snapshot} />
        </div>
      </section>

      <section className="lab-section">
        <header>
          <p className="lab-tag">Konzept B · v2.1 (live im Cockpit)</p>
          <h2>Choropleth — kontinuierliche Schattierung + Puls</h2>
          <p>
            <b>Farbe</b>: HSL-Interpolation zwischen dunklem Neutral und
            Rot (Riser) bzw. Grün (Faller). +4 % ist sichtbar dunkler
            als +18 %, +25 % knallt — feinere Rangfolge allein durch Farbe.
            <b> Puls</b>: jeder Riser pulsiert, Geschwindigkeit proportional
            zur Stärke (Strong ≥10 % = 1.8 s, Mild 3–10 % = 3.5 s, Faller
            & Flat statisch). Top-Riser zusätzlich mit weißem Stroke +
            kräftigem Glow. <b>Diese Variante ist ab 2026-04-23 die
            produktive Atlas-Section im Cockpit.</b>
          </p>
        </header>
        <div className="lab-canvas lab-canvas-night">
          <AtlasChoropleth snapshot={snapshot} />
        </div>
      </section>

      <section className="lab-section">
        <header>
          <p className="lab-tag">Konzept B · v1 (vorher)</p>
          <h2>Constellation (abstrakt)</h2>
          <p>
            Originale Variante ohne Karte — Sterne nur an approximierten
            Positions, Hintergrund ist Sternennebel. Zum Vergleich.
          </p>
        </header>
        <div className="lab-canvas lab-canvas-night">
          <AtlasConstellation snapshot={snapshot} />
        </div>
      </section>

      <section className="lab-section">
        <header>
          <p className="lab-tag">Konzept C</p>
          <h2>Sparkline-Grid</h2>
          <p>
            4×4 Karten, eine pro Bundesland. Jede zeigt die letzte
            28-Tage-Verlaufskurve + aktuellen Delta. Tufte-Style,
            info-dense, perfekt zum täglichen Scannen — Trend statt
            nur Stand.
          </p>
        </header>
        <div className="lab-canvas lab-canvas-dark">
          <AtlasSparklines snapshot={snapshot} />
        </div>
      </section>

      <footer className="lab-foot">
        <p>
          Sag welches Konzept du in den Cockpit nehmen willst — oder ob
          du eine Mischung möchtest. Auch „keins davon, nochmal anders"
          ist eine valide Antwort.
        </p>
      </footer>
    </div>
  );
};

export default AtlasLabPage;
