import React from 'react';
import type { CockpitSnapshot } from '../types';
import { fmtEurCompactOrDash } from '../format';
import { Dash } from '../exhibit/primitives';

import SectionNav from './SectionNav';
import DecisionSection from './DecisionSection';
import AtlasSection from './AtlasSection';
import ForecastSection from './ForecastSection';
import ImpactSection from './ImpactSection';
import BacktestSection from './BacktestSection';

/**
 * Broadside — the one-page scrolling editorial layout.
 *
 * Replaces the Exhibit+Drawer architecture from 2026-04-18 with a
 * single long page: five sections (§ I–§ V) stacked top-down, every
 * piece of information visible on scroll, no click-to-reveal. A
 * floating right-rail section-index provides quick anchor navigation
 * with scroll-spy highlighting.
 *
 * Rhythm:
 *   § I   Entscheidung   (paper top-chrome + dark hero strip + paper body)
 *   § II  Wellen-Atlas   (full-bleed dark stage)
 *   § III Forecast       (paper)
 *   § IV  Wirkung        (paper, alternating strip)
 *   § V   Backtest       (paper)
 *   Redaktion-Footer
 */

interface Props {
  snapshot: CockpitSnapshot;
}

// ---------- TopChrome — same editorial masthead as before --------------
const TopChrome: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const generated = snapshot.generatedAt ? new Date(snapshot.generatedAt) : null;
  const editionShort = generated
    ? generated
        .toLocaleDateString('de-DE', { day: '2-digit', month: 'short', year: '2-digit' })
        .toUpperCase()
        .replace(/\./g, '')
        .replace(/ /g, '·')
    : '—';
  return (
    <div className="ex-chrome">
      <div className="ex-chrome-left ex-mono">
        <span>ViralFlux</span>
        <span style={{ color: 'var(--ex-ink-30)' }}>·</span>
        <span>peix / {snapshot.client}</span>
      </div>
      <div className="ex-chrome-center ex-mono">
        <span
          className="ex-serif-italic"
          style={{ fontSize: 14, color: 'var(--ex-ink-60)' }}
        >
          Wochenausgabe ·{' '}
        </span>
        <span>{snapshot.isoWeek}</span>
        <span style={{ margin: '0 10px', color: 'var(--ex-ink-30)' }}>·</span>
        <span>{snapshot.virusLabel}</span>
      </div>
      <div className="ex-chrome-right ex-mono">
        <span>ED. {editionShort}</span>
      </div>
    </div>
  );
};

// ---------- FootRail — edition stamp at bottom --------------------------
const FootRail: React.FC<{ snapshot: CockpitSnapshot }> = ({ snapshot }) => {
  const generated = snapshot.generatedAt ? new Date(snapshot.generatedAt) : null;
  const generatedLabel = generated
    ? generated.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: 'long',
        year: 'numeric',
      })
    : '—';
  const generatedTime = generated
    ? `${generated.toLocaleTimeString('de-DE', {
        hour: '2-digit',
        minute: '2-digit',
      })} MEZ`
    : '—';
  const currentKw = parseInt(snapshot.isoWeek.match(/\d+/)?.[0] || '0', 10);
  const nextKw = currentKw + 1;
  const rec = snapshot.primaryRecommendation;
  return (
    <section
      className="ex-section ex-section--paper"
      style={{ paddingTop: 48, paddingBottom: 48 }}
    >
      <div className="ex-section-body">
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'auto 1fr auto',
            alignItems: 'baseline',
            gap: 48,
          }}
        >
          <div className="ex-edition-mark">Redaktion</div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 48,
            }}
          >
            <div>
              <div
                className="ex-mono"
                style={{ color: 'var(--ex-ink-45)', marginBottom: 6 }}
              >
                Ausgabe
              </div>
              <div className="ex-serif-italic" style={{ fontSize: 18 }}>
                ViralFlux · Cockpit · {snapshot.isoWeek}
              </div>
            </div>
            <div>
              <div
                className="ex-mono"
                style={{ color: 'var(--ex-ink-45)', marginBottom: 6 }}
              >
                Redaktionsschluss
              </div>
              <div className="ex-num" style={{ fontSize: 18 }}>
                {generatedLabel} · {generatedTime}
              </div>
            </div>
            <div>
              <div
                className="ex-mono"
                style={{ color: 'var(--ex-ink-45)', marginBottom: 6 }}
              >
                Nächste
              </div>
              <div className="ex-num" style={{ fontSize: 18 }}>
                KW {nextKw} · Fr 09:00
              </div>
            </div>
          </div>
          <div className="ex-edition-mark" style={{ textAlign: 'right' }}>
            {rec ? (
              <span>
                {fmtEurCompactOrDash(rec.amountEur)} · {rec.fromName} →{' '}
                {rec.toName}
              </span>
            ) : (
              <Dash note="kein Shift diese Woche" />
            )}
          </div>
        </div>
      </div>
    </section>
  );
};

// ---------- Broadside root ---------------------------------------------
export const Broadside: React.FC<Props> = ({ snapshot }) => {
  const navItems = [
    { id: 'sec-decision', numeral: '§ I', label: 'Entscheidung' },
    { id: 'sec-atlas', numeral: '§ II', label: 'Wellen-Atlas' },
    { id: 'sec-forecast', numeral: '§ III', label: 'Forecast' },
    { id: 'sec-impact', numeral: '§ IV', label: 'Wirkung' },
    { id: 'sec-backtest', numeral: '§ V', label: 'Backtest' },
  ];

  return (
    <div className="peix-exhibit ex-broadside">
      <TopChrome snapshot={snapshot} />

      <section id="sec-decision" className="ex-section ex-section--paper">
        <DecisionSection snapshot={snapshot} />
      </section>

      <section id="sec-atlas" className="ex-section ex-section--paper">
        <AtlasSection snapshot={snapshot} />
      </section>

      <section id="sec-forecast" className="ex-section ex-section--paper-deep">
        <ForecastSection snapshot={snapshot} />
      </section>

      <section id="sec-impact" className="ex-section ex-section--paper">
        <ImpactSection snapshot={snapshot} />
      </section>

      <section id="sec-backtest" className="ex-section ex-section--paper-deep">
        <BacktestSection snapshot={snapshot} />
      </section>

      <FootRail snapshot={snapshot} />

      <SectionNav items={navItems} />
    </div>
  );
};

export default Broadside;
