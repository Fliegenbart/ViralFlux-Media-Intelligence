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

/* ─── Icon helpers for feature cards ───────────────────────────── */
const FeatureIcon: React.FC<{ idx: number }> = ({ idx }) => {
  const icons = [
    /* chart-bar */
    <svg key="0" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="12" width="4" height="9" rx="1" /><rect x="10" y="8" width="4" height="13" rx="1" /><rect x="17" y="3" width="4" height="18" rx="1" /></svg>,
    /* layers */
    <svg key="1" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2 2 7l10 5 10-5-10-5Z" /><path d="m2 17 10 5 10-5" /><path d="m2 12 10 5 10-5" /></svg>,
    /* shield-check */
    <svg key="2" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></svg>,
  ];
  return icons[idx % icons.length];
};

const iconBgColors = [
  'bg-violet-100 text-violet-600',
  'bg-pink-100 text-pink-600',
  'bg-orange-100 text-orange-600',
];

const stepAccentColors = [
  'from-violet-500 to-purple-600',
  'from-pink-500 to-rose-600',
  'from-orange-500 to-amber-600',
  'from-cyan-500 to-blue-600',
];

const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const mailtoLink = buildMailtoLink();

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-white bg-blobs">
      {/* ─── Navigation ─────────────────────────────────────────────── */}
      <nav className="relative z-10 max-w-[1180px] mx-auto px-4 sm:px-6 py-5 md:py-7 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="media-logo">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <path d="M3 12h4l2-4 3 8 2-4h7" />
            </svg>
          </div>
          <div>
            <div className="text-slate-900 font-bold tracking-tight text-sm">{COPY.nav.brandTitle}</div>
            <div className="text-[11px] text-slate-400">{COPY.nav.brandSubtitle}</div>
          </div>
        </div>
        <div className="flex w-full sm:w-auto flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
          <a
            href={mailtoLink}
            className="media-button secondary px-4 py-2.5 text-xs font-semibold text-center whitespace-nowrap"
          >
            {COPY.nav.primaryCta}
          </a>
          <button
            onClick={() => navigate('/dashboard?tab=product-intel')}
            className="media-button px-4 py-2.5 text-xs font-semibold text-center whitespace-nowrap"
          >
            {COPY.nav.secondaryCta}
          </button>
        </div>
      </nav>

      {/* ─── Main Content ───────────────────────────────────────────── */}
      <main className="relative z-[5] max-w-[1180px] mx-auto px-4 sm:px-6 pb-20 space-y-12 md:space-y-14">

        {/* ─── Hero ───────────────────────────────────────────────────── */}
        <section className="pt-6 md:pt-10 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-6 lg:gap-8 items-start fade-in">
          <div>
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold mb-5 bg-violet-50 text-violet-600 border border-violet-200">
              {COPY.hero.badge}
            </div>

            <h1 className="text-4xl md:text-5xl font-extrabold leading-[1.06] tracking-tight text-slate-900">
              {COPY.hero.titleTop}
              <br />
              <span className="gradient-text">{COPY.hero.titleBottom}</span>
            </h1>
            <p className="mt-5 text-base md:text-lg text-slate-500 max-w-3xl leading-relaxed">{COPY.hero.subtitle}</p>

            <div className="mt-6 flex flex-wrap gap-2">
              {COPY.hero.chips.map((chip) => (
                <div
                  key={chip}
                  className="px-3 py-1.5 rounded-full text-xs font-semibold text-slate-500 bg-slate-50 border border-slate-200"
                >
                  {chip}
                </div>
              ))}
            </div>

            <div className="mt-7 flex flex-wrap gap-3">
              <button
                onClick={() => navigate('/dashboard?tab=map')}
                className="media-button px-5 py-3 rounded-xl text-sm font-semibold"
              >
                Zum Cockpit starten
              </button>
              <button
                onClick={() => navigate('/dashboard?tab=product-intel')}
                className="px-5 py-3 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-orange-500 to-amber-500 shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5"
              >
                Produkt anlegen
              </button>
            </div>
          </div>

          {/* ─── Sidebar Card ─────────────────────────────────────────── */}
          <aside className="card p-5 md:p-6 h-full">
            <div className="text-[11px] text-slate-400 uppercase tracking-wider">In 30 Sekunden verstehen</div>
            <h3 className="mt-2 text-xl font-bold text-slate-900">Was macht das Tool konkret?</h3>
            <ul className="mt-4 space-y-3 text-sm text-slate-500 leading-relaxed">
              <li className="flex gap-2">
                <span className="mt-1 shrink-0 w-1.5 h-1.5 rounded-full bg-violet-400" />
                Regionale Signalquellen werden zu einer erwarteten Lage in 7-14 Tagen verdichtet.
              </li>
              <li className="flex gap-2">
                <span className="mt-1 shrink-0 w-1.5 h-1.5 rounded-full bg-pink-400" />
                Diese Lage wird mit eurem Gelo-Produktkatalog gematcht.
              </li>
              <li className="flex gap-2">
                <span className="mt-1 shrink-0 w-1.5 h-1.5 rounded-full bg-orange-400" />
                Freigabe bleibt immer menschlich: erst Review, dann Aktivierung.
              </li>
            </ul>
            <div className="mt-5 rounded-xl p-4 text-xs bg-gradient-to-br from-violet-50 to-pink-50 border border-violet-100">
              <div className="font-semibold gradient-text">Zielbild</div>
              <div className="text-slate-500 mt-2">Budget nach epidemiologischer Dynamik steuern statt nur nach Demografie.</div>
            </div>
          </aside>
        </section>

        {/* ─── Why Now ────────────────────────────────────────────────── */}
        <section className="fade-in">
          <h2 className="text-2xl md:text-3xl font-extrabold text-slate-900 mb-4 md:mb-5">
            Warum das <span className="gradient-text">heute relevant</span> ist
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-5">
            {COPY.whyNow.map((text, idx) => (
              <article key={text} className="card p-5 group hover:shadow-medium transition-all">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-4 ${iconBgColors[idx]}`}>
                  <FeatureIcon idx={idx} />
                </div>
                <p className="text-sm text-slate-500 leading-relaxed">{text}</p>
              </article>
            ))}
          </div>
        </section>

        {/* ─── Workflow Preview ────────────────────────────────────────── */}
        <section className="card p-5 md:p-6 fade-in">
          <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
            <h3 className="text-2xl font-bold text-slate-900">Workflow-Vorschau</h3>
            <div className="text-xs text-slate-400 font-medium">Signal {'>'} Erwartung {'>'} Produkt {'>'} Freigabe</div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {COPY.steps.map((step, idx) => (
              <article
                key={step.title}
                className="rounded-xl p-4 bg-slate-50 border border-slate-100 hover:border-violet-200 transition-colors"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className={`inline-flex items-center justify-center w-6 h-6 rounded-lg text-[10px] font-bold text-white bg-gradient-to-br ${stepAccentColors[idx]}`}>
                    {idx + 1}
                  </span>
                  <span className="text-[11px] text-slate-400 uppercase tracking-wider">Step {idx + 1}</span>
                </div>
                <div className="text-slate-800 font-semibold">{step.title}</div>
                <ul className="mt-3 text-sm text-slate-500 space-y-1.5">
                  {step.points.map((point) => (
                    <li key={point} className="flex gap-2">
                      <span className="mt-1.5 shrink-0 w-1 h-1 rounded-full bg-slate-300" />
                      {point}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>

        {/* ─── Bottom Two-Column ──────────────────────────────────────── */}
        <section className="grid grid-cols-1 xl:grid-cols-2 gap-4 md:gap-5 fade-in">
          {/* Background Info */}
          <div className="card p-6">
            <h3 className="text-2xl font-bold text-slate-900 mb-3">Was im Hintergrund passiert</h3>
            <p className="text-sm text-slate-500 leading-relaxed">{COPY.workflow.description}</p>
            <div className="mt-5 text-xs rounded-xl p-4 bg-gradient-to-br from-blue-50 to-cyan-50 border border-blue-100">
              <div className="font-semibold text-blue-600">Produkt-Intelligence</div>
              <div className="text-slate-500 mt-2">Jedes Produkt wird auf Signalklassen gemappt, mit Score, Regelquelle und Review-Status gespeichert.</div>
            </div>
          </div>

          {/* Offer / POC */}
          <div className="card p-6">
            <h3 className="text-2xl font-bold text-slate-900 mb-3">{COPY.offer.title}</h3>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-medium">Nächste Schritte im POC</div>
            <ol className="mt-3 text-sm text-slate-500 space-y-2">
              {COPY.offer.steps.map((step, idx) => (
                <li key={step} className="flex gap-2.5">
                  <span className={`shrink-0 w-6 h-6 rounded-lg flex items-center justify-center text-[10px] font-bold text-white bg-gradient-to-br ${stepAccentColors[idx]}`}>
                    {idx + 1}
                  </span>
                  <span className="pt-0.5">{step}</span>
                </li>
              ))}
            </ol>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                onClick={() => navigate('/dashboard?tab=map')}
                className="media-button px-4 py-2 text-xs font-semibold"
              >
                Signal-Board öffnen
              </button>
              <button
                onClick={() => navigate('/dashboard?tab=product-intel')}
                className="px-4 py-2 rounded-md text-xs font-semibold text-white bg-gradient-to-r from-orange-500 to-amber-500 shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5"
              >
                Direkt zu Produkt-Intelligence
              </button>
            </div>
          </div>
        </section>

        {/* ─── Footer ─────────────────────────────────────────────────── */}
        <footer className="relative pt-8 pb-2 text-center text-xs text-slate-400 border-t border-slate-200">
          {COPY.footer}
        </footer>
      </main>
    </div>
  );
};

export default LandingPage;
