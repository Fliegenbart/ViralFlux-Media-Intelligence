import React from 'react';
import { useNavigate } from 'react-router-dom';

const CONTACT_EMAIL = 'sales@peix.de';

const COPY = {
  nav: {
    brandTitle: 'PEIX | ViralFlux Media Intelligence',
    brandSubtitle: 'Media Intelligence für Gelo',
    primaryCta: 'Beratungsgespräch starten',
    secondaryCta: 'Zum Produkt-Flow',
  },
  hero: {
    badge: 'Epidemiologie vor Kampagnenstart',
    titleTop: 'Medienplanung starten, bevor der Abverkauf hochläuft.',
    titleBottom: 'Regional, datenbasiert und review-sicher.',
    subtitle:
      'ViralFlux verbindet regionale Epidemielagen mit eurem Gelo-Produktprofil und leitet daraus direkte Media-Hinweise ab: Wo muss gebremst werden, wo lohnt der Push?',
    chips: ['14-Tage-Horizont', 'Bundesland-Fokus', 'Review-first Flow'],
  },
  whyNow: [
    'Das Tool erkennt frühere Aktivitätstrends aus ARE-, SURVSTAT- und weiteren Quellen.',
    'Es ordnet diese Lage automatisch in Produkt-Profile (Zielgruppe, Indikation, Form, Alterskontext) ein.',
    'Kein blindes Auto-Push: Jedes Match bleibt zuerst Review-pflichtig.',
  ],
  steps: [
    {
      title: 'In 30 Sek. verstehen',
      points: [
        'Wo ist epidemiologische Aktivität regional am stärksten?',
        'Welche Kampagnen-Rollen folgen daraus?',
        'Welches Produkt passt laut KI derzeit am besten?',
      ],
    },
    {
      title: 'Signal-zu-Content-Flow',
      points: [
        'Datenlage auf Karte prüfen',
        'Regionale Vorschlags-Regionen priorisieren',
        'Produkt-Matching auf diese Regionen anwenden',
      ],
    },
    {
      title: 'Was im Hintergrund passiert',
      points: [
        'Dateningest + Regel-Matching',
        'KI-Helligkeit auf Lageklassen',
        'Mapp-Log inkl. Unsicherheitsgrad persistiert',
      ],
    },
    {
      title: 'Nächste Schritte',
      points: [
        'Produkt im Katalog anlegen',
        'Match-Qualität prüfen und freigeben',
        'Kampagnenkarten aktivieren',
      ],
    },
  ],
  workflow: {
    title: 'Wie läuft der Produkt-Flow heute?',
    description:
      'Lege ein Produkt an, lass den KI-Abgleich laufen, prüfe die Mapping-Empfehlungen, gebe nur die passenden Kontexte frei und nutze nur diese danach im Kampagnenvorschlag.',
  },
  offer: {
    title: 'Start für PEIX Discovery + POC',
    steps: [
      'Cockpit öffnen und Lagebild prüfen',
      'Gelo-Produkt in den Katalog aufnehmen',
      'Match-Status im Audit freigeben',
      'Kampagnenhypothese gegen Zielgebiet aktivieren',
    ],
  },
  footer: 'PEIX ViralFlux Media Intelligence © 2026 · Predictive Pharma Media Intelligence',
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

      <nav className="relative max-w-[1180px] mx-auto px-4 sm:px-6 py-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4" style={{ zIndex: 10 }}>
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
            onClick={() => navigate('/dashboard?tab=product-intel')}
            className="px-4 py-2 text-xs font-semibold rounded-lg text-white text-center whitespace-nowrap"
            style={{ background: 'linear-gradient(135deg, #0ea5e9, #3b82f6)' }}
          >
            {COPY.nav.secondaryCta}
          </button>
        </div>
      </nav>

      <main className="relative max-w-[1180px] mx-auto px-4 sm:px-6 pb-16" style={{ zIndex: 5 }}>
        <section className="pt-10 pb-12">
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

          <h1 className="text-4xl md:text-5xl font-extrabold leading-[1.05] text-white tracking-tight">
            {COPY.hero.titleTop}
            <br />
            <span style={{ color: '#38bdf8' }}>{COPY.hero.titleBottom}</span>
          </h1>
          <p className="mt-6 text-lg text-slate-300 max-w-4xl leading-relaxed">{COPY.hero.subtitle}</p>

          <div className="mt-7 flex flex-wrap gap-2">
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

          <div className="mt-8 flex flex-wrap gap-3">
            <button
              onClick={() => navigate('/dashboard?tab=map')}
              className="px-5 py-3 rounded-xl text-sm font-semibold"
              style={{ color: '#ffffff', background: 'linear-gradient(135deg, #0ea5e9, #2563eb)' }}
            >
              Zum Cockpit starten
            </button>
            <button
              onClick={() => navigate('/dashboard?tab=product-intel')}
              className="px-5 py-3 rounded-xl text-sm font-semibold"
              style={{ color: '#ffffff', background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}
            >
              Produkt anlegen
            </button>
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl md:text-3xl font-extrabold text-white mb-4">Warum das heute relevant ist</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {COPY.whyNow.map((text) => (
              <article key={text} className="rounded-2xl p-5" style={{ background: '#111b2d', border: '1px solid #24324a' }}>
                <p className="text-sm text-slate-300 leading-relaxed">• {text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-2 gap-5 mb-10">
          <div className="rounded-2xl p-6" style={{ background: '#111b2d', border: '1px solid #24324a' }}>
            <h3 className="text-2xl font-bold text-white mb-4">Workflow-Vorschau</h3>
            <div className="relative pl-6 border-l border-slate-700 space-y-5">
              {COPY.steps.map((step, idx) => (
                <div key={step.title} className="relative">
                  <div
                    className="absolute -left-[11px] top-2 w-4 h-4 rounded-full"
                    style={{ background: idx === 0 ? '#22c55e' : '#64748b' }}
                  />
                  <div className="text-xs text-slate-400 uppercase tracking-wider">Step {idx + 1}</div>
                  <div className="text-white font-semibold mt-1">{step.title}</div>
                  <ul className="mt-2 text-sm text-slate-300 space-y-1">
                    {step.points.map((point) => (
                      <li key={point}>- {point}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl p-6" style={{ background: '#111b2d', border: '1px solid #24324a' }}>
            <h3 className="text-2xl font-bold text-white mb-3">Was im Hintergrund passiert</h3>
            <p className="text-sm text-slate-300 leading-relaxed">{COPY.workflow.description}</p>
            <div className="mt-5 text-xs rounded-xl p-4" style={{ background: '#0b1527', border: '1px solid #233149' }}>
              <div className="text-cyan-300 font-semibold">Produkt-Intelligence</div>
              <div className="text-slate-300 mt-2">Jedes Product wird auf Signalklassen gemappt, mit Score, Regelquelle und Review-Status gespeichert.</div>
            </div>
            <div className="mt-5">
              <div className="text-xs text-slate-400 uppercase tracking-wider">Nächste Schritte im POC</div>
              <ol className="mt-2 text-sm text-slate-300 space-y-2">
                {COPY.offer.steps.map((step) => (
                  <li key={step}>• {step}</li>
                ))}
              </ol>
            </div>
          </div>
        </section>

        <footer className="relative pt-8 pb-4 text-center text-xs text-slate-500" style={{ borderTop: '1px solid #1c2a42' }}>
          {COPY.footer}
        </footer>
      </main>
    </div>
  );
};

export default LandingPage;
