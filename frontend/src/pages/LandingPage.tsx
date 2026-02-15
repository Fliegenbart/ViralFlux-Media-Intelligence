import React from 'react';
import { useNavigate } from 'react-router-dom';

const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen" style={{ background: '#0f172a' }}>

      {/* ── Hero Section ── */}
      <header className="relative overflow-hidden">
        <div className="absolute inset-0" style={{
          background: 'radial-gradient(ellipse at 30% 20%, rgba(59,130,246,0.15) 0%, transparent 50%), radial-gradient(ellipse at 70% 80%, rgba(139,92,246,0.1) 0%, transparent 50%)',
        }} />
        <nav className="relative max-w-[1400px] mx-auto px-6 py-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            </div>
            <span className="text-xl font-bold text-white tracking-tight">LabPulse Pro</span>
          </div>
          <button
            onClick={() => navigate('/dashboard')}
            className="px-6 py-2.5 text-sm font-semibold rounded-lg text-white transition-all hover:scale-105"
            style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}
          >
            Zum Dashboard
          </button>
        </nav>

        <div className="relative max-w-[1400px] mx-auto px-6 pt-20 pb-32 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium mb-8" style={{ background: 'rgba(59,130,246,0.15)', color: '#60a5fa', border: '1px solid rgba(59,130,246,0.2)' }}>
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            Echtzeit-Monitoring aktiv
          </div>

          <h1 className="text-5xl md:text-7xl font-extrabold text-white tracking-tight leading-tight mb-6">
            Vom reaktiven Labor zur<br />
            <span style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6, #06b6d4)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              prädiktiven High-Performance-Einheit
            </span>
          </h1>

          <p className="text-xl text-slate-400 max-w-3xl mx-auto mb-4 leading-relaxed">
            LabPulse ist nicht nur ein Corona-Dashboard. Es ist das <strong className="text-white">SAP für die operative Laborsteuerung</strong>.
            Wir nutzen externe epidemiologische Daten, um die interne Supply-Chain und Personalplanung
            vollautomatisch zu justieren.
          </p>
          <p className="text-lg text-slate-500 max-w-2xl mx-auto mb-12">
            Wir verwandeln reaktive Labore in prädiktive High-Performance-Einheiten.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="px-8 py-3.5 text-base font-semibold rounded-xl text-white transition-all hover:scale-105 shadow-lg shadow-blue-500/25"
              style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}
            >
              Dashboard starten
            </button>
            <button
              onClick={() => navigate('/vertriebsradar')}
              className="px-8 py-3.5 text-base font-semibold rounded-xl text-white transition-all hover:scale-105"
              style={{ background: 'rgba(245,158,11,0.15)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.3)' }}
            >
              Vertriebsradar
            </button>
            <button
              onClick={() => navigate('/map')}
              className="px-8 py-3.5 text-base font-semibold rounded-xl transition-all hover:scale-105"
              style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8', border: '1px solid #334155' }}
            >
              Deutschlandkarte
            </button>
          </div>
        </div>
      </header>

      {/* ── KPI Bar ── */}
      <div style={{ background: '#1e293b', borderTop: '1px solid #334155', borderBottom: '1px solid #334155' }}>
        <div className="max-w-[1400px] mx-auto px-6 py-8 grid grid-cols-2 md:grid-cols-4 gap-8">
          {[
            { value: '20%', label: 'Weniger Lagerkosten', sub: 'durch prädiktive Bestelloptimierung' },
            { value: '100%', label: 'Stockout-Prävention', sub: 'ML-gestützte Bedarfsprognose' },
            { value: '14', label: 'Tage Prognose-Horizont', sub: 'Holt-Winters + Ridge Ensemble' },
            { value: '8+', label: 'Datenquellen integriert', sub: 'RKI, BfArM, Google Trends, OpenWeather, ...' },
          ].map((kpi, i) => (
            <div key={i} className="text-center">
              <div className="text-3xl md:text-4xl font-extrabold text-white mb-1">{kpi.value}</div>
              <div className="text-sm font-medium text-slate-300">{kpi.label}</div>
              <div className="text-xs text-slate-500 mt-1">{kpi.sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── USP Section ── */}
      <section className="max-w-[1400px] mx-auto px-6 py-24">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-4">
            Was LabPulse Pro einzigartig macht
          </h2>
          <p className="text-lg text-slate-400 max-w-2xl mx-auto">
            Fünf Säulen für die vollautomatisierte Laborsteuerung
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* USP 1 */}
          <div className="card p-8 hover:scale-[1.02] transition-transform">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(59,130,246,0.15)' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            </div>
            <h3 className="text-xl font-bold text-white mb-3">Epidemiologische Früherkennung</h3>
            <p className="text-slate-400 leading-relaxed mb-4">
              Echtzeit-Integration von RKI-Abwasserdaten (AMELAG), GrippeWeb, Google Trends, Wetterdaten und Schulferien.
              Erkennung von Ausbrüchen <strong className="text-slate-300">2-3 Wochen vor</strong> dem klinischen Peak.
            </p>
            <ul className="space-y-2 text-sm text-slate-500">
              <li className="flex items-center gap-2"><span className="text-blue-400">&#10003;</span> 160+ Kläranlagen bundesweit</li>
              <li className="flex items-center gap-2"><span className="text-blue-400">&#10003;</span> 16 Bundesländer Heatmap</li>
              <li className="flex items-center gap-2"><span className="text-blue-400">&#10003;</span> ARE/ILI Surveillance (GrippeWeb)</li>
            </ul>
          </div>

          {/* USP 2 */}
          <div className="card p-8 hover:scale-[1.02] transition-transform">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(245,158,11,0.15)' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            </div>
            <h3 className="text-xl font-bold text-white mb-3">ML-gestützte Prognose</h3>
            <p className="text-slate-400 leading-relaxed mb-4">
              Holt-Winters + Ridge Regression Ensemble-Modell für präzise 14-Tage-Vorhersagen.
              Automatische Bedarfsberechnung mit <strong className="text-slate-300">Konfidenzintervallen</strong>.
            </p>
            <ul className="space-y-2 text-sm text-slate-500">
              <li className="flex items-center gap-2"><span className="text-amber-400">&#10003;</span> 14-Tage Forecast pro Virus</li>
              <li className="flex items-center gap-2"><span className="text-amber-400">&#10003;</span> Fusion Engine Outbreak Score</li>
              <li className="flex items-center gap-2"><span className="text-amber-400">&#10003;</span> Automatische Saisonbereinigung</li>
            </ul>
          </div>

          {/* USP 3 */}
          <div className="card p-8 hover:scale-[1.02] transition-transform">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(16,185,129,0.15)' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2"><rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
            </div>
            <h3 className="text-xl font-bold text-white mb-3">One-Click Nachbestellung</h3>
            <p className="text-slate-400 leading-relaxed mb-4">
              Automatische Stockout-Simulation mit SAP/ERP-kompatiblem Export.
              <strong className="text-slate-300"> 20% weniger Lagerkosten</strong> bei gleichzeitiger 100% Versorgungssicherheit.
            </p>
            <ul className="space-y-2 text-sm text-slate-500">
              <li className="flex items-center gap-2"><span className="text-green-400">&#10003;</span> SAP MM CSV-Export</li>
              <li className="flex items-center gap-2"><span className="text-green-400">&#10003;</span> Prädiktive Sicherheitsbestände</li>
              <li className="flex items-center gap-2"><span className="text-green-400">&#10003;</span> Standort-übergreifende Transfers</li>
            </ul>
          </div>
        </div>

        {/* Row 2: Neue Features */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-8">
          {/* USP 4: Lieferengpassmeldung */}
          <div className="card p-8 hover:scale-[1.02] transition-transform">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(239,68,68,0.15)' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            </div>
            <h3 className="text-xl font-bold text-white mb-3">BfArM Lieferengpass-Monitoring</h3>
            <p className="text-slate-400 leading-relaxed mb-4">
              Automatische Analyse der BfArM-Lieferengpassmeldungen. Erkennung von <strong className="text-slate-300">Antibiotika-, Atemwegs- und Fiebermittel-Engpässen</strong> mit Risiko-Scoring und Wellentyp-Klassifikation.
            </p>
            <ul className="space-y-2 text-sm text-slate-500">
              <li className="flex items-center gap-2"><span className="text-red-400">&#10003;</span> BfArM CSV-Import und Analyse</li>
              <li className="flex items-center gap-2"><span className="text-red-400">&#10003;</span> Pädiatrie-Warnungen</li>
              <li className="flex items-center gap-2"><span className="text-red-400">&#10003;</span> Fusion mit Outbreak Score</li>
            </ul>
          </div>

          {/* USP 5: Vertriebsradar */}
          <div className="card p-8 hover:scale-[1.02] transition-transform">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(245,158,11,0.15)' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 10 10"/><circle cx="12" cy="12" r="3"/><path d="M12 9v-4"/></svg>
            </div>
            <h3 className="text-xl font-bold text-white mb-3">KI-Vertriebsradar</h3>
            <p className="text-slate-400 leading-relaxed mb-4">
              Automatische Erkennung von Vertriebschancen aus <strong className="text-slate-300">Lieferengpässen, Wetter/UV-Daten und Bestellverhalten</strong>. Generiert priorisierte Sales Pitches und CRM-fertiges JSON.
            </p>
            <ul className="space-y-2 text-sm text-slate-500">
              <li className="flex items-center gap-2"><span className="text-amber-400">&#10003;</span> 3 Opportunity-Detektoren</li>
              <li className="flex items-center gap-2"><span className="text-amber-400">&#10003;</span> Automatische Sales Pitches</li>
              <li className="flex items-center gap-2"><span className="text-amber-400">&#10003;</span> CRM-JSON Export</li>
            </ul>
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="py-24" style={{ background: '#1e293b' }}>
        <div className="max-w-[1400px] mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-4">So funktioniert LabPulse Pro</h2>
            <p className="text-lg text-slate-400">Von externen Daten zu automatisierten Entscheidungen in 5 Schritten</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-5">
            {[
              { step: '01', title: 'Daten sammeln', desc: 'RKI AMELAG, GrippeWeb, BfArM-Engpässe, Google Trends, Wetter + UV-Index', color: '#3b82f6' },
              { step: '02', title: 'Fusion Engine', desc: 'Alle Signale fließen in den Outbreak Score (0-100) mit Konfidenz-Bewertung', color: '#8b5cf6' },
              { step: '03', title: 'Prognose', desc: 'ML-Modell berechnet 14-Tage-Vorhersagen und Stockout-Risiken', color: '#f59e0b' },
              { step: '04', title: 'Vertriebsradar', desc: 'KI erkennt Vertriebschancen aus Engpässen, UV-Daten und Bestellverhalten', color: '#ef4444' },
              { step: '05', title: 'Handeln', desc: 'SAP-Export, CRM-Push, automatische Bestellvorschläge und Sales Pitches', color: '#10b981' },
            ].map((s, i) => (
              <div key={i} className="relative p-6 rounded-xl" style={{ background: '#0f172a', border: '1px solid #334155' }}>
                <div className="text-5xl font-extrabold mb-4" style={{ color: s.color, opacity: 0.2 }}>{s.step}</div>
                <h3 className="text-lg font-bold text-white mb-2">{s.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{s.desc}</p>
                {i < 4 && (
                  <div className="hidden md:block absolute top-1/2 -right-4 w-8 text-center text-slate-600 text-2xl" style={{ transform: 'translateY(-50%)' }}>&#8594;</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Data Sources ── */}
      <section className="max-w-[1400px] mx-auto px-6 py-24">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-4">Integrierte Datenquellen</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {[
            { name: 'RKI AMELAG', desc: 'Abwasser-Surveillance', icon: '🧬' },
            { name: 'GrippeWeb', desc: 'ARE/ILI Inzidenz', icon: '🏥' },
            { name: 'BfArM', desc: 'Lieferengpassmeldungen', icon: '💊' },
            { name: 'Google Trends', desc: 'Suchverhalten', icon: '📊' },
            { name: 'OpenWeather', desc: 'Wetter + UV-Index', icon: '🌡' },
            { name: 'Schulferien', desc: 'Ferienzeiten', icon: '📅' },
            { name: 'ERP/SAP', desc: 'Bestelldaten', icon: '📦' },
            { name: 'Fusion Engine', desc: 'Outbreak Score', icon: '🔬' },
          ].map((src, i) => (
            <div key={i} className="card p-5 text-center">
              <div className="text-3xl mb-3">{src.icon}</div>
              <div className="text-sm font-bold text-white">{src.name}</div>
              <div className="text-xs text-slate-500 mt-1">{src.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-24" style={{ background: 'linear-gradient(135deg, rgba(59,130,246,0.1), rgba(139,92,246,0.1))' }}>
        <div className="max-w-[800px] mx-auto px-6 text-center">
          <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-6">
            Bereit für prädiktive Laborsteuerung?
          </h2>
          <p className="text-lg text-slate-400 mb-8">
            Starten Sie jetzt mit LabPulse Pro und senken Sie Ihre Lagerkosten um 20%
            bei gleichzeitiger 100% Versorgungssicherheit.
          </p>
          <button
            onClick={() => navigate('/dashboard')}
            className="px-10 py-4 text-lg font-bold rounded-xl text-white transition-all hover:scale-105 shadow-lg shadow-blue-500/30"
            style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}
          >
            Dashboard starten
          </button>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="py-8 text-center text-sm text-slate-600" style={{ borderTop: '1px solid #1e293b' }}>
        <div className="max-w-[1400px] mx-auto px-6">
          <p>LabPulse Pro v1.0 &mdash; Intelligentes Frühwarnsystem für Labordiagnostik</p>
          <p className="text-xs text-slate-700 mt-2">Powered by RKI AMELAG, GrippeWeb, BfArM, Google Trends, OpenWeather, Fusion Engine ML</p>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
