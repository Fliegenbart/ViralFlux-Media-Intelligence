import React from 'react';
import { useNavigate } from 'react-router-dom';

const cardStyle: React.CSSProperties = {
  background: '#111b2d',
  border: '1px solid #24324a',
};

const CONTACT_EMAIL = 'sales@peix.de';

const COPY = {
  nav: {
    brandTitle: 'PEIX | ViralFlux Media Intelligence',
    brandSubtitle: 'Service-Plattform für Predictive Pharma Media',
    primaryCta: 'Beratungsgespräch starten',
    secondaryCta: 'Live-Demo ansehen',
  },
  hero: {
    badge: 'Bis zu 14 Tage Lead - verifiziert im Markt-Backtest',
    titleTop: 'Media-Budgets steuern,',
    titleBottom: 'bevor die Nachfragewelle sichtbar wird.',
    subtitle:
      'Viele Kampagnen reagieren zu spät auf Abverkaufs- und Indexdaten. ViralFlux nutzt behördliche Trigger, um Aktivierung regional früher und effizienter zu planen.',
    chips: ['bis zu 14 Tage Lead', 'regionale Aktivierung', 'BfArM-Engpass-Signal'],
  },
  valueCards: [
    {
      title: 'Timing-Vorteil für Marken',
      text: 'Abwasser- und Surveillance-Signale können steigenden Bedarf vor klassischen Marktdaten anzeigen. So wird Budget in frühe Nachfragefenster verschoben.',
    },
    {
      title: 'Effizienz im Budget-Shift',
      text: 'Regionale Unterschiede werden sichtbar. Hoher Bedarf wird priorisiert, Low-Demand-Regionen werden entlastet - bei gleichem Gesamtbudget.',
    },
    {
      title: 'Wettbewerbsfenster erkennen',
      text: 'BfArM-Engpasssignale werden als Trigger genutzt. Wenn Wettbewerber nicht lieferfähig sind, kann die Verfügbarkeitskommunikation gezielt hochgefahren werden.',
    },
  ],
  proof: {
    title: 'So belegen wir die Wirksamkeit',
    intro:
      'ViralFlux kombiniert Markt-Proxy-Backtests mit optionalem Kundenabgleich. Dadurch entsteht ein belastbarer Startpunkt, auch ohne initiale Sales-Datenfreigabe.',
    modes: [
      {
        title: 'Mode A: Markt-Check',
        text: 'Ohne Kundendaten. Vergleich unseres Signals mit öffentlichen Proxy-Reihen (z. B. RKI ARE, SURVSTAT).',
      },
      {
        title: 'Mode B: Realitäts-Check',
        text: 'Mit CSV-Upload. Ihre Verkaufs- oder Bestellhistorie wird gegen ViralFlux-Signale gespiegelt, inklusive Lead/Lag und Baseline-Vergleich.',
      },
    ],
    sources:
      'Datenbasis: AMELAG, RKI ARE, SURVSTAT, Notaufnahme, Wetter und BfArM-Engpassmeldungen.',
  },
  offer: {
    title: 'Nächster Schritt: PEIX Discovery + POC',
    intro:
      'Der Einstieg ist klar strukturiert und ohne Integrationsrisiko möglich. Ziel ist eine belastbare Entscheidung für einen Pilot je Marke.',
    steps: [
      '30-min Discovery Call mit Zielregionen, Markenfokus und Budgetrahmen.',
      'Markt-Backtest-Demo im Cockpit mit öffentlichen Datenquellen.',
      'Optionaler Kunden-CSV-Check zur Validierung von Korrelation und Lead-Zeit.',
    ],
    primaryCta: 'Jetzt Gespräch anfragen',
    secondaryCta: 'Direkt ins Media-Cockpit',
  },
  footer: 'PEIX ViralFlux Media Intelligence © 2026 - Predictive Service für Pharma Healthcare Marketing',
};

const buildMailtoLink = () => {
  const subject = 'POC Anfrage ViralFlux Media Intelligence';
  const body = [
    'Hallo PEIX Team,',
    '',
    'wir möchten ein kurzes Beratungsgespräch zu ViralFlux vereinbaren.',
    '',
    'Marke/Produkt:',
    'Regionen:',
    'Zielbild (z. B. Awareness, Effizienz, Wettbewerbsfenster):',
    'Gewünschter Termin:',
    '',
    'Viele Grüße',
  ].join('\n');

  return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
};

const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const mailtoLink = buildMailtoLink();

  return (
    <div className="min-h-screen overflow-x-hidden" style={{ background: '#091222' }}>
      <div
        className="absolute inset-0 opacity-30"
        style={{
          pointerEvents: 'none',
          background:
            'radial-gradient(circle at 12% 16%, rgba(14,165,233,0.22), transparent 35%), radial-gradient(circle at 84% 24%, rgba(245,158,11,0.16), transparent 30%), radial-gradient(circle at 52% 82%, rgba(59,130,246,0.18), transparent 34%)',
        }}
      />

      <nav className="relative max-w-[1240px] mx-auto px-4 sm:px-6 py-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4" style={{ zIndex: 10 }}>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #0ea5e9, #3b82f6)' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <path d="M3 12h4l2-4 3 8 2-4h7" />
            </svg>
          </div>
          <div>
            <div className="text-white font-bold tracking-tight">{COPY.nav.brandTitle}</div>
            <div className="text-[11px] text-slate-400">{COPY.nav.brandSubtitle}</div>
          </div>
        </div>
        <div className="flex w-full sm:w-auto flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
          <a
            href={mailtoLink}
            className="px-4 py-2 text-xs font-semibold rounded-lg text-center whitespace-nowrap"
            style={{ color: '#f59e0b', border: '1px solid #f59e0b55', background: 'rgba(245,158,11,0.08)' }}
          >
            {COPY.nav.primaryCta}
          </a>
          <button
            onClick={() => navigate('/dashboard')}
            className="px-4 py-2 text-xs font-semibold rounded-lg text-white text-center whitespace-nowrap"
            style={{ background: 'linear-gradient(135deg, #0ea5e9, #3b82f6)' }}
          >
            {COPY.nav.secondaryCta}
          </button>
        </div>
      </nav>

      <main className="relative max-w-[1240px] mx-auto px-4 sm:px-6 pb-16" style={{ zIndex: 5 }}>
        <section className="pt-12 pb-12 text-center">
          <div
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold mb-6"
            style={{
              color: '#38bdf8',
              border: '1px solid rgba(56,189,248,0.3)',
              background: 'rgba(14,165,233,0.1)',
            }}
          >
            {COPY.hero.badge}
          </div>

          <h1 className="text-4xl md:text-6xl font-extrabold leading-[1.05] text-white tracking-tight">
            {COPY.hero.titleTop}
            <br />
            <span style={{ color: '#38bdf8' }}>{COPY.hero.titleBottom}</span>
          </h1>

          <p className="mt-6 text-lg text-slate-300 max-w-4xl mx-auto leading-relaxed">{COPY.hero.subtitle}</p>

          <div className="mt-7 flex flex-wrap justify-center gap-2">
            {COPY.hero.chips.map((chip) => (
              <div
                key={chip}
                className="px-3 py-1.5 rounded-full text-xs font-semibold text-slate-200"
                style={{ border: '1px solid #2d3e5e', background: '#0b1527' }}
              >
                {chip}
              </div>
            ))}
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl md:text-3xl font-extrabold text-white mb-4">Warum das für Brand Manager relevant ist</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {COPY.valueCards.map((card) => (
              <article key={card.title} className="rounded-2xl p-5" style={cardStyle}>
                <div className="text-xs text-cyan-400 font-semibold mb-2">{card.title}</div>
                <p className="text-sm text-slate-300 leading-relaxed">{card.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-10">
          <div className="lg:col-span-2 rounded-2xl p-6" style={cardStyle}>
            <div className="text-xs uppercase tracking-widest text-slate-500 mb-3">{COPY.proof.title}</div>
            <p className="text-slate-200 text-sm leading-relaxed mb-4">{COPY.proof.intro}</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {COPY.proof.modes.map((mode) => (
                <div key={mode.title} className="rounded-lg p-4" style={{ background: '#0b1527', border: '1px solid #233149' }}>
                  <div className="text-cyan-400 text-xs font-semibold mb-2">{mode.title}</div>
                  <p className="text-sm text-slate-300 leading-relaxed">{mode.text}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl p-6" style={cardStyle}>
            <div className="text-xs uppercase tracking-widest text-slate-500 mb-3">Methodische Grundlage</div>
            <p className="text-sm text-slate-300 leading-relaxed">{COPY.proof.sources}</p>
          </div>
        </section>

        <section className="rounded-2xl p-6 md:p-8" style={{ ...cardStyle, background: 'linear-gradient(135deg, rgba(14,165,233,0.14), rgba(17,27,45,0.95))' }}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
            <div>
              <h3 className="text-2xl font-extrabold text-white mb-2">{COPY.offer.title}</h3>
              <p className="text-slate-200 text-sm leading-relaxed mb-3">{COPY.offer.intro}</p>
              <ol className="space-y-2 text-sm text-slate-200">
                {COPY.offer.steps.map((step) => (
                  <li key={step} className="flex gap-2">
                    <span className="text-cyan-300 font-semibold mt-0.5">•</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
            <div className="flex gap-3 md:justify-end flex-wrap">
              <a
                href={mailtoLink}
                className="px-5 py-3 rounded-xl text-sm font-semibold"
                style={{ color: '#ffffff', background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}
              >
                {COPY.offer.primaryCta}
              </a>
              <button
                onClick={() => navigate('/dashboard')}
                className="px-5 py-3 rounded-xl text-sm font-semibold text-white"
                style={{ background: 'linear-gradient(135deg, #0ea5e9, #2563eb)' }}
              >
                {COPY.offer.secondaryCta}
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="relative py-8 text-center text-xs text-slate-500" style={{ borderTop: '1px solid #1c2a42' }}>
        {COPY.footer}
      </footer>
    </div>
  );
};

export default LandingPage;
