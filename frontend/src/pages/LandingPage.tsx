import React from 'react';
import { useNavigate } from 'react-router-dom';

const cardStyle: React.CSSProperties = {
  background: '#111b2d',
  border: '1px solid #24324a',
};

const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen" style={{ background: '#091222' }}>
      <div
        className="absolute inset-0 opacity-30"
        style={{
          pointerEvents: 'none',
          background:
            'radial-gradient(circle at 12% 16%, rgba(14,165,233,0.22), transparent 35%), radial-gradient(circle at 84% 24%, rgba(245,158,11,0.16), transparent 30%), radial-gradient(circle at 52% 82%, rgba(59,130,246,0.18), transparent 34%)',
        }}
      />

      <nav className="relative max-w-[1240px] mx-auto px-6 py-6 flex items-center justify-between" style={{ zIndex: 10 }}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #0ea5e9, #3b82f6)' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <path d="M3 12h4l2-4 3 8 2-4h7" />
            </svg>
          </div>
          <div>
            <div className="text-white font-bold tracking-tight">ViralFlux Media Intelligence</div>
            <div className="text-[11px] text-slate-400">by PEIX - Predictive Pharma Media</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/vertriebsradar')}
            className="px-4 py-2 text-xs font-semibold rounded-lg"
            style={{ color: '#f59e0b', border: '1px solid #f59e0b55', background: 'rgba(245,158,11,0.08)' }}
          >
            Use Cases
          </button>
          <button
            onClick={() => navigate('/dashboard')}
            className="px-4 py-2 text-xs font-semibold rounded-lg text-white"
            style={{ background: 'linear-gradient(135deg, #0ea5e9, #3b82f6)' }}
          >
            Demo öffnen
          </button>
        </div>
      </nav>

      <main className="relative max-w-[1240px] mx-auto px-6 pb-16" style={{ zIndex: 5 }}>
        <section className="pt-12 pb-12 text-center">
          <div
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold mb-6"
            style={{
              color: '#38bdf8',
              border: '1px solid rgba(56,189,248,0.3)',
              background: 'rgba(14,165,233,0.1)',
            }}
          >
            14-Tage-Frühsignal für pharmazeutische Media-Activation
          </div>

          <h1 className="text-4xl md:text-6xl font-extrabold leading-[1.05] text-white tracking-tight">
            Weg vom Rückspiegel.
            <br />
            Hin zu Echtzeit-Media auf
            <span style={{ color: '#38bdf8' }}> behördlich validierten Triggern.</span>
          </h1>

          <p className="mt-6 text-lg text-slate-300 max-w-4xl mx-auto leading-relaxed">
            PEIX nutzt <strong className="text-white">ViralFlux</strong>, um für Marken wie
            <strong className="text-white"> GeloMyrtol</strong> Budgets automatisch dort hochzufahren,
            wo die Welle anrollt - und sie dort einzusparen, wo kein Bedarf entsteht.
          </p>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          <div className="lg:col-span-2 rounded-2xl p-6" style={cardStyle}>
            <div className="text-xs uppercase tracking-widest text-slate-500 mb-3">Elevator Pitch (30 Sekunden)</div>
            <blockquote className="text-slate-200 leading-relaxed text-[15px] md:text-base">
              "Wussten Sie, dass wir eine Erkältungswelle 14 Tage früher sehen als jede Apotheke und jede Google-Suche?
              <br /><br />
              Aktuell steuern fast alle Pharma-Kampagnen nach dem Rückspiegel-Prinzip. Sie reagieren auf Verkaufszahlen oder Grippe-Indizes, wenn die Welle schon da ist.
              <br /><br />
              Unsere Engine ViralFlux nutzt behördliche Abwasserdaten, RKI-Meldedaten und Wetterprognosen als Live-Trigger für Ihren Media-Einkauf.
              <br /><br />
              Das bedeutet für GeloMyrtol: Wir fahren Ihre Budgets vollautomatisch dort hoch, wo die Welle anrollt - und sparen es dort ein, wo alle gesund sind.
              <br /><br />
              Und der Clou: Über BfArM-Daten erkennen wir sogar, wenn die Konkurrenz lieferunfähig ist, und schalten dann Sofort-verfügbar-Kampagnen frei."
            </blockquote>
          </div>

          <div className="rounded-2xl p-6" style={cardStyle}>
            <div className="text-xs uppercase tracking-widest text-slate-500 mb-3">Für PEIX Kunden</div>
            <div className="space-y-3 text-sm text-slate-300">
              <div className="p-3 rounded-lg" style={{ background: '#0b1527', border: '1px solid #233149' }}>
                <div className="text-cyan-400 font-semibold">Case</div>
                <div>GeloMyrtol</div>
              </div>
              <div className="p-3 rounded-lg" style={{ background: '#0b1527', border: '1px solid #233149' }}>
                <div className="text-cyan-400 font-semibold">Signal-Lead</div>
                <div>bis zu 14 Tage</div>
              </div>
              <div className="p-3 rounded-lg" style={{ background: '#0b1527', border: '1px solid #233149' }}>
                <div className="text-cyan-400 font-semibold">Steuerung</div>
                <div>PLZ-genaue Budget-Shift-Logik</div>
              </div>
              <div className="p-3 rounded-lg" style={{ background: '#0b1527', border: '1px solid #233149' }}>
                <div className="text-cyan-400 font-semibold">Differenzierung</div>
                <div>Behördlich validiert statt Bauchgefühl</div>
              </div>
            </div>
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl md:text-3xl font-extrabold text-white mb-4">Key Selling Points fürs Deck</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <article className="rounded-2xl p-5" style={cardStyle}>
              <div className="text-xs text-cyan-400 font-semibold mb-2">1. Zeit-Vorteil (Bio-Layer)</div>
              <p className="text-sm text-slate-300 leading-relaxed">
                AMELAG erkennt Infektionsdynamik, bevor Abverkaufsdaten reagieren.
                Ergebnis: Top-of-Mind-Präsenz für GeloMyrtol, bevor der erste Leidensdruck entsteht.
              </p>
            </article>

            <article className="rounded-2xl p-5" style={cardStyle}>
              <div className="text-xs text-cyan-400 font-semibold mb-2">2. Konkurrenz-Radar (Market-Layer)</div>
              <p className="text-sm text-slate-300 leading-relaxed">
                Der Resource-Scarcity-Detector scannt BfArM täglich.
                Bei Lieferengpässen der Konkurrenz startet ViralFlux automatisch verfügbarkeitsgetriebene Kampagnen.
              </p>
            </article>

            <article className="rounded-2xl p-5" style={cardStyle}>
              <div className="text-xs text-cyan-400 font-semibold mb-2">3. Symptom-Check (Context-Layer)</div>
              <p className="text-sm text-slate-300 leading-relaxed">
                Wetter, Pollen und Feinstaub verhindern False Positives.
                ViralFlux unterscheidet Allergie-Lagen von infektiösen Lagen und steuert Budgets entsprechend.
              </p>
            </article>
          </div>
        </section>

        <section className="rounded-2xl p-6 md:p-8" style={{ ...cardStyle, background: 'linear-gradient(135deg, rgba(14,165,233,0.14), rgba(17,27,45,0.95))' }}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
            <div>
              <h3 className="text-2xl font-extrabold text-white mb-2">Nächster Schritt für PEIX</h3>
              <p className="text-slate-200 text-sm leading-relaxed">
                Wir bauen ViralFlux von einem Bestandsmonitor auf ein dediziertes
                Pharma-Media-Activation-System um: Trigger, Segmentierung, Budget-Routing,
                Creative-Playbooks und Agentur-Reporting aus einer Plattform.
              </p>
            </div>
            <div className="flex gap-3 md:justify-end">
              <button
                onClick={() => navigate('/dashboard')}
                className="px-5 py-3 rounded-xl text-sm font-semibold text-white"
                style={{ background: 'linear-gradient(135deg, #0ea5e9, #2563eb)' }}
              >
                ViralFlux Dashboard
              </button>
              <button
                onClick={() => navigate('/datenimport')}
                className="px-5 py-3 rounded-xl text-sm font-semibold"
                style={{ color: '#cbd5e1', border: '1px solid #4b5a75', background: '#0b1527' }}
              >
                Data & Trigger Setup
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="relative py-8 text-center text-xs text-slate-500" style={{ borderTop: '1px solid #1c2a42' }}>
        ViralFlux Media Intelligence © 2026 - PEIX Service Platform für Pharma Healthcare Marketing
      </footer>
    </div>
  );
};

export default LandingPage;
