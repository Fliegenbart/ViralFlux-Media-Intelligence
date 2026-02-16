import React from 'react';
import { useNavigate } from 'react-router-dom';

const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen" style={{ background: '#0f172a' }}>

      {/* ── Navigation ── */}
      <nav className="relative max-w-[1400px] mx-auto px-6 py-6 flex items-center justify-between" style={{ zIndex: 10 }}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #3b82f6, #06b6d4)' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
          </div>
          <span className="text-xl font-bold text-white tracking-tight">VIRAL FLUX</span>
          <span className="text-xs font-medium px-2 py-0.5 rounded" style={{ background: 'rgba(6,182,212,0.15)', color: '#22d3ee' }}>Core</span>
        </div>
        <button
          onClick={() => navigate('/dashboard')}
          className="px-6 py-2.5 text-sm font-semibold rounded-lg text-white transition-all hover:scale-105"
          style={{ background: 'linear-gradient(135deg, #3b82f6, #06b6d4)' }}
        >
          Zum Dashboard
        </button>
      </nav>

      {/* ── Hero Section ── */}
      <header className="relative overflow-hidden">
        <div className="absolute inset-0" style={{
          background: 'radial-gradient(ellipse at 30% 20%, rgba(59,130,246,0.15) 0%, transparent 50%), radial-gradient(ellipse at 70% 60%, rgba(6,182,212,0.08) 0%, transparent 50%)',
        }} />
        <div className="absolute inset-0 opacity-[0.03]" style={{
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
        }} />

        <div className="relative max-w-[1400px] mx-auto px-6 pt-16 pb-28 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium mb-8" style={{ background: 'rgba(6,182,212,0.12)', color: '#22d3ee', border: '1px solid rgba(6,182,212,0.2)' }}>
            <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            Federal Intelligence System &mdash; Live
          </div>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold text-white tracking-tight leading-[1.1] mb-6">
            Vom reagierenden Labor zum<br />
            <span style={{ background: 'linear-gradient(135deg, #3b82f6, #06b6d4, #22d3ee)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              agierenden Versorger.
            </span>
          </h1>

          <p className="text-lg md:text-xl text-slate-400 max-w-4xl mx-auto mb-12 leading-relaxed">
            <strong className="text-white">VIRAL FLUX Core</strong>: Das erste Intelligence-System, das Infektionswellen antizipiert,
            Versorgungsengp&auml;sse erkennt und Ihren Vertrieb steuert &mdash; bevor die erste Probe im Labor eintrifft.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="px-8 py-3.5 text-base font-semibold rounded-xl text-white transition-all hover:scale-105 shadow-lg shadow-blue-500/25"
              style={{ background: 'linear-gradient(135deg, #3b82f6, #06b6d4)' }}
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

      {/* ── Trust Bar / Data Sources ── */}
      <section style={{ background: '#1e293b', borderTop: '1px solid #334155', borderBottom: '1px solid #334155' }}>
        <div className="max-w-[1400px] mx-auto px-6 py-10">
          <div className="text-center mb-8">
            <h3 className="text-sm font-bold tracking-[0.2em] uppercase text-slate-500 mb-2">Powered by Data Excellence &amp; Federal Intelligence</h3>
            <p className="text-sm text-slate-400 max-w-2xl mx-auto">
              VIRAL FLUX fusioniert Ihre propriet&auml;ren Daten mit validierten Quellen &mdash; 100% DSGVO-konform gehostet.
            </p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { icon: '\u{1F6E1}\u{FE0F}', label: 'Hosted in Germany', desc: 'ISO 27001 zertifizierte Rechenzentren' },
              { icon: '\u{1F3DB}', label: 'BfArM', desc: 'Lieferengpass-Datenbank' },
              { icon: '\u{1F52C}', label: 'RKI', desc: 'AMELAG Abwassersentinel' },
              { icon: '\u{26C5}', label: 'DWD', desc: 'Bio-Wetter & Pollenflug' },
            ].map((item, i) => (
              <div key={i} className="flex items-center gap-3 p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #334155' }}>
                <span className="text-2xl">{item.icon}</span>
                <div>
                  <div className="text-sm font-bold text-white">{item.label}</div>
                  <div className="text-xs text-slate-500">{item.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Dashboard Bento Grid (Simulated Visuals) ── */}
      <section className="max-w-[1400px] mx-auto px-6 py-20">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-4">
            Alles auf einen Blick
          </h2>
          <p className="text-lg text-slate-400">Echtzeit-Dashboard mit Multi-Layer Fusion Engine</p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 auto-rows-[180px]">
          {/* Outbreak Score Gauge — span 2 rows */}
          <div className="row-span-2 rounded-2xl p-6 flex flex-col items-center justify-center" style={{ background: '#1e293b', border: '1px solid #334155' }}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-4">Outbreak Score</div>
            <div className="relative" style={{ width: 130, height: 130 }}>
              <svg viewBox="0 0 100 100" className="w-full h-full" style={{ transform: 'rotate(-90deg)' }}>
                <circle cx="50" cy="50" r="42" fill="none" stroke="#334155" strokeWidth="7" />
                <circle cx="50" cy="50" r="42" fill="none" stroke="#dc2626" strokeWidth="7"
                  strokeLinecap="round" strokeDasharray={`${90 * 2.64} 264`} />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-4xl font-black text-white">90</span>
                <span className="text-[10px] text-slate-500">von 100</span>
              </div>
            </div>
            <div className="mt-3 px-3 py-1 rounded-full text-xs font-bold" style={{ background: 'rgba(220,38,38,0.15)', color: '#dc2626' }}>
              Kritisches Risiko
            </div>
          </div>

          {/* Virus Cards — 2 small cards */}
          {[
            { name: 'Influenza A', score: 90, color: '#ef4444', trend: '+18%' },
            { name: 'SARS-CoV-2', score: 42, color: '#f59e0b', trend: '+3%' },
          ].map((v, i) => (
            <div key={i} className="rounded-2xl p-5 flex flex-col justify-between" style={{ background: '#1e293b', border: '1px solid #334155' }}>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">{v.name}</span>
                <span className="text-xs font-bold" style={{ color: v.color }}>{v.score}</span>
              </div>
              <div className="my-3">
                <div className="h-2 rounded-full overflow-hidden" style={{ background: '#0f172a' }}>
                  <div className="h-full rounded-full" style={{ width: `${v.score}%`, background: v.color }} />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-600">7-Tage-Trend</span>
                <span className="text-[10px] font-medium" style={{ color: v.color }}>{v.trend}</span>
              </div>
            </div>
          ))}

          {/* Alert Notification */}
          <div className="rounded-2xl p-5 flex flex-col justify-center" style={{ background: 'linear-gradient(135deg, rgba(239,68,68,0.08), #1e293b)', border: '1px solid rgba(239,68,68,0.2)' }}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
              <span className="text-[10px] uppercase tracking-wider text-red-400 font-bold">Live Alert</span>
            </div>
            <p className="text-xs text-slate-300 font-medium mb-1">BfArM: Antibiotika-Engpass</p>
            <p className="text-[10px] text-slate-500">12 neue Meldungen in den letzten 48h. P&auml;diatrische Pr&auml;parate betroffen.</p>
            <div className="mt-3 flex gap-2">
              <span className="text-[9px] px-2 py-0.5 rounded" style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>Antibiotika</span>
              <span className="text-[9px] px-2 py-0.5 rounded" style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>P&auml;diatrie</span>
            </div>
          </div>

          {/* Simulated Trend Chart — span 2 cols */}
          <div className="col-span-2 rounded-2xl p-5" style={{ background: '#1e293b', border: '1px solid #334155' }}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-400">Abwasser-Virenlast (AMELAG)</span>
              <span className="text-[10px] text-slate-600">letzte 12 Wochen</span>
            </div>
            <svg viewBox="0 0 400 100" className="w-full" style={{ height: 110 }}>
              {/* Grid lines */}
              {[0,25,50,75,100].map(y => (
                <line key={y} x1="0" y1={y} x2="400" y2={y} stroke="#334155" strokeWidth="0.5" strokeDasharray="4 4" />
              ))}
              {/* Influenza A — rising curve */}
              <polyline
                fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                points="0,85 33,82 66,78 100,72 133,68 166,55 200,48 233,38 266,25 300,18 333,12 366,8 400,5"
              />
              {/* SARS-CoV-2 — flat-ish */}
              <polyline
                fill="none" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 3"
                points="0,60 33,62 66,58 100,55 133,58 166,60 200,56 233,54 266,52 300,55 333,53 366,50 400,48"
              />
              {/* RSV — declining */}
              <polyline
                fill="none" stroke="#10b981" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                points="0,30 33,35 66,40 100,48 133,55 166,62 200,68 233,72 266,78 300,82 333,85 366,88 400,90"
              />
              {/* Legend dots */}
              <circle cx="320" cy="5" r="3" fill="#ef4444" /><text x="328" y="9" fill="#94a3b8" fontSize="8">Influenza A</text>
              <circle cx="320" cy="18" r="3" fill="#3b82f6" /><text x="328" y="22" fill="#94a3b8" fontSize="8">SARS-CoV-2</text>
              <circle cx="320" cy="31" r="3" fill="#10b981" /><text x="328" y="35" fill="#94a3b8" fontSize="8">RSV</text>
            </svg>
          </div>

          {/* Mini Germany Map — simplified */}
          <div className="rounded-2xl p-5 flex flex-col items-center justify-center" style={{ background: '#1e293b', border: '1px solid #334155' }}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Hotspots</div>
            <svg viewBox="0 0 100 140" className="w-full" style={{ maxWidth: 80, height: 100 }}>
              {/* Simplified Germany outline */}
              <path d="M50,5 L65,10 L75,20 L80,35 L82,50 L78,65 L85,80 L80,95 L70,110 L60,120 L50,130 L40,125 L30,115 L25,100 L20,85 L18,70 L22,55 L20,40 L25,25 L35,15 Z"
                fill="none" stroke="#334155" strokeWidth="1.5" />
              {/* Hotspot dots */}
              <circle cx="52" cy="35" r="6" fill="#ef4444" opacity="0.6"><animate attributeName="r" values="4;7;4" dur="2s" repeatCount="indefinite"/></circle>
              <circle cx="52" cy="35" r="3" fill="#ef4444" />
              <circle cx="38" cy="70" r="5" fill="#f59e0b" opacity="0.5"><animate attributeName="r" values="3;6;3" dur="2.5s" repeatCount="indefinite"/></circle>
              <circle cx="38" cy="70" r="2.5" fill="#f59e0b" />
              <circle cx="65" cy="55" r="4" fill="#3b82f6" opacity="0.4" />
              <circle cx="65" cy="55" r="2" fill="#3b82f6" />
            </svg>
            <div className="flex gap-2 mt-2">
              <span className="text-[8px] text-red-400">Berlin</span>
              <span className="text-[8px] text-amber-400">Frankfurt</span>
            </div>
          </div>

          {/* Signal Confidence */}
          <div className="rounded-2xl p-5 flex flex-col justify-between" style={{ background: '#1e293b', border: '1px solid #334155' }}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Signal-Konfidenz</div>
            <div className="space-y-2 my-2">
              {[
                { label: 'BIO', pct: 74, color: '#3b82f6' },
                { label: 'MARKET', pct: 100, color: '#ef4444' },
                { label: 'PSYCHO', pct: 45, color: '#8b5cf6' },
                { label: 'CONTEXT', pct: 62, color: '#10b981' },
              ].map((s, i) => (
                <div key={i}>
                  <div className="flex justify-between mb-0.5">
                    <span className="text-[9px] text-slate-500">{s.label}</span>
                    <span className="text-[9px] font-bold" style={{ color: s.color }}>{s.pct}%</span>
                  </div>
                  <div className="h-1.5 rounded-full overflow-hidden" style={{ background: '#0f172a' }}>
                    <div className="h-full rounded-full" style={{ width: `${s.pct}%`, background: s.color }} />
                  </div>
                </div>
              ))}
            </div>
            <div className="text-[9px] text-slate-600">4-Dimensionen Fusion</div>
          </div>
        </div>
      </section>

      {/* ── The Paradigm Shift ── */}
      <section style={{ background: '#1e293b', borderTop: '1px solid #334155', borderBottom: '1px solid #334155' }}>
        <div className="max-w-[1400px] mx-auto px-6 py-24">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 items-start">
            {/* Challenge */}
            <div className="p-8 rounded-2xl" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)' }}>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium mb-6" style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171' }}>
                Die Herausforderung
              </div>
              <h2 className="text-2xl md:text-3xl font-extrabold text-white mb-4">
                Blindflug im R&uuml;ckspiegel
              </h2>
              <p className="text-slate-400 leading-relaxed mb-6">
                Bisher basiert die Ressourcenplanung in der Labormedizin auf retrospektiven Daten. Wir reagieren auf das Probenaufkommen
                von gestern. Doch wenn die RKI-Kurven steigen, sind die Lieferketten oft schon belastet.
              </p>
              {/* Simulated "old way" timeline */}
              <div className="rounded-lg p-4" style={{ background: '#0f172a', border: '1px solid #33415580' }}>
                <div className="text-[10px] text-slate-600 mb-3">Reaktiver Workflow</div>
                <div className="flex items-center gap-2">
                  {['RKI meldet', 'Labor reagiert', 'Kits bestellt', 'Engpass'].map((step, i) => (
                    <React.Fragment key={i}>
                      {i > 0 && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#475569" strokeWidth="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>}
                      <div className="flex-1 text-center px-2 py-2 rounded text-[9px]" style={{
                        background: i === 3 ? 'rgba(239,68,68,0.1)' : 'rgba(255,255,255,0.03)',
                        color: i === 3 ? '#f87171' : '#64748b',
                        border: `1px solid ${i === 3 ? 'rgba(239,68,68,0.2)' : '#33415580'}`,
                      }}>
                        {step}
                      </div>
                    </React.Fragment>
                  ))}
                </div>
                <div className="text-[9px] text-red-400/60 text-right mt-2">+14 Tage Verz&ouml;gerung</div>
              </div>
            </div>

            {/* Solution */}
            <div className="p-8 rounded-2xl" style={{ background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.15)' }}>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium mb-6" style={{ background: 'rgba(16,185,129,0.1)', color: '#34d399' }}>
                Die L&ouml;sung
              </div>
              <h2 className="text-2xl md:text-3xl font-extrabold text-white mb-4">
                Operativer Zeitvorsprung
              </h2>
              <p className="text-slate-400 leading-relaxed mb-6">
                VIRAL FLUX transformiert Ihr Labor vom passiven Dienstleister zum strategischen Partner. Durch die Fusion
                von logistischen, meteorologischen und biologischen Fr&uuml;hindukatoren gewinnen Sie einen operativen Vorsprung
                von <strong className="text-emerald-400">14 Tagen</strong>.
              </p>
              {/* Simulated "new way" timeline */}
              <div className="rounded-lg p-4" style={{ background: '#0f172a', border: '1px solid #33415580' }}>
                <div className="text-[10px] text-emerald-500/60 mb-3">Proaktiver Workflow</div>
                <div className="flex items-center gap-2">
                  {['Signal erkannt', 'Auto-Alert', 'Kits bereit', 'Welle kommt'].map((step, i) => (
                    <React.Fragment key={i}>
                      {i > 0 && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>}
                      <div className="flex-1 text-center px-2 py-2 rounded text-[9px]" style={{
                        background: i === 3 ? 'rgba(16,185,129,0.1)' : 'rgba(16,185,129,0.04)',
                        color: i === 3 ? '#34d399' : '#10b981',
                        border: `1px solid ${i === 3 ? 'rgba(16,185,129,0.3)' : 'rgba(16,185,129,0.1)'}`,
                      }}>
                        {step}
                      </div>
                    </React.Fragment>
                  ))}
                </div>
                <div className="text-[9px] text-emerald-400/60 text-right mt-2">14 Tage Vorsprung</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Operational Core: Die 3 Säulen ── */}
      <section className="py-24">
        <div className="max-w-[1400px] mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-4">
              Die 3 S&auml;ulen der Labor-Steuerung
            </h2>
            <p className="text-lg text-slate-400">Operational Core &mdash; von Fr&uuml;hindukatoren zur pr&auml;zisen Steuerung</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* Säule 1: BfArM */}
            <div className="relative p-8 rounded-2xl" style={{ background: '#1e293b', border: '1px solid #334155' }}>
              <div className="text-6xl font-extrabold absolute top-4 right-6" style={{ color: '#3b82f6', opacity: 0.08 }}>01</div>
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(59,130,246,0.15)' }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              </div>
              <h3 className="text-xl font-bold text-white mb-2">Der Supply-Chain-Seismograph</h3>
              <p className="text-xs font-medium text-blue-400 mb-4">BfArM Versorgungsmonitor</p>
              <p className="text-slate-400 text-sm leading-relaxed mb-5">
                Ein Lieferabriss bei therapeutischen Medikamenten ist der verl&auml;sslichste Indikator
                f&uuml;r eine kommende diagnostische Welle &mdash; oft Wochen vor den offiziellen Meldezahlen.
              </p>

              {/* Simulated shortage bars */}
              <div className="rounded-lg p-4 mb-4" style={{ background: '#0f172a', border: '1px solid #33415580' }}>
                <div className="text-[10px] text-slate-600 mb-3">Aktuelle Engp&auml;sse (BfArM)</div>
                {[
                  { cat: 'Antibiotika', count: 47, pct: 85, alert: true },
                  { cat: 'Fieber/Schmerz', count: 23, pct: 55, alert: false },
                  { cat: 'Atemwege', count: 31, pct: 70, alert: true },
                  { cat: 'P&auml;diatrie', count: 18, pct: 45, alert: true },
                ].map((c, i) => (
                  <div key={i} className="flex items-center gap-2 mb-2">
                    <span className="text-[9px] text-slate-500 w-16 truncate">{c.cat}</span>
                    <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: '#1e293b' }}>
                      <div className="h-full rounded-full" style={{
                        width: `${c.pct}%`,
                        background: c.alert ? '#ef4444' : '#3b82f6',
                      }} />
                    </div>
                    <span className="text-[9px] font-mono" style={{ color: c.alert ? '#ef4444' : '#64748b' }}>{c.count}</span>
                  </div>
                ))}
              </div>

              <div className="p-3 rounded-lg" style={{ background: 'rgba(59,130,246,0.08)' }}>
                <p className="text-xs text-blue-300">
                  <strong>Ihr Vorteil:</strong> Einkauf und Lagerhaltung proaktiv anpassen, bevor die Welle kommt.
                </p>
              </div>
            </div>

            {/* Säule 2: Order Velocity */}
            <div className="relative p-8 rounded-2xl" style={{ background: '#1e293b', border: '1px solid #334155' }}>
              <div className="text-6xl font-extrabold absolute top-4 right-6" style={{ color: '#f59e0b', opacity: 0.08 }}>02</div>
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(245,158,11,0.15)' }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
              </div>
              <h3 className="text-xl font-bold text-white mb-2">Predictive Resource Management</h3>
              <p className="text-xs font-medium text-amber-400 mb-4">Interne Order Velocity</p>
              <p className="text-slate-400 text-sm leading-relaxed mb-5">
                Unser Algorithmus erkennt lokale Nachfrage-Cluster in Ihren Bestelldaten.
                Steigt die Nachfrage in einer PLZ-Region signifikant an, warnt das System proaktiv.
              </p>

              {/* Simulated order velocity chart */}
              <div className="rounded-lg p-4 mb-4" style={{ background: '#0f172a', border: '1px solid #33415580' }}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] text-slate-600">Order Velocity (4 Wochen)</span>
                  <span className="text-[10px] font-bold text-amber-400">+38%</span>
                </div>
                <svg viewBox="0 0 200 60" className="w-full" style={{ height: 60 }}>
                  {/* Area fill */}
                  <path d="M0,55 L40,50 L80,45 L120,38 L160,22 L200,8 L200,60 L0,60 Z" fill="#f59e0b" opacity="0.08" />
                  {/* Line */}
                  <polyline
                    fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                    points="0,55 40,50 80,45 120,38 160,22 200,8"
                  />
                  {/* Current dot */}
                  <circle cx="200" cy="8" r="4" fill="#f59e0b">
                    <animate attributeName="r" values="3;5;3" dur="1.5s" repeatCount="indefinite" />
                  </circle>
                  {/* Threshold line */}
                  <line x1="0" y1="30" x2="200" y2="30" stroke="#f59e0b" strokeWidth="0.5" strokeDasharray="4 3" opacity="0.4" />
                  <text x="140" y="28" fill="#f59e0b" fontSize="7" opacity="0.5">Schwellenwert</text>
                </svg>
                <div className="flex justify-between mt-1">
                  <span className="text-[8px] text-slate-600">KW 05</span>
                  <span className="text-[8px] text-slate-600">KW 06</span>
                  <span className="text-[8px] text-slate-600">KW 07</span>
                  <span className="text-[8px] text-amber-400 font-bold">KW 08</span>
                </div>
              </div>

              <div className="p-3 rounded-lg" style={{ background: 'rgba(245,158,11,0.08)' }}>
                <p className="text-xs text-amber-300">
                  <strong>Ihr Vorteil:</strong> Reagenzien und Personal pr&auml;zise dort allokieren, wo sie in 10 Tagen gebraucht werden.
                </p>
              </div>
            </div>

            {/* Säule 3: Deep Fusion */}
            <div className="relative p-8 rounded-2xl" style={{ background: '#1e293b', border: '1px solid #334155' }}>
              <div className="text-6xl font-extrabold absolute top-4 right-6" style={{ color: '#8b5cf6', opacity: 0.08 }}>03</div>
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(139,92,246,0.15)' }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 10 10"/><circle cx="12" cy="12" r="3"/></svg>
              </div>
              <h3 className="text-xl font-bold text-white mb-2">Deep Fusion: Triangulation</h3>
              <p className="text-xs font-medium text-violet-400 mb-4">Multi-Layer-Algorithmus</p>
              <p className="text-slate-400 text-sm leading-relaxed mb-5">
                Keine Fehlalarme durch Medien-Hype. Ein Warnsignal wird nur generiert, wenn biologische
                Daten und Marktdaten konvergieren.
              </p>

              {/* Simulated convergence diagram */}
              <div className="rounded-lg p-4 mb-4" style={{ background: '#0f172a', border: '1px solid #33415580' }}>
                <div className="text-[10px] text-slate-600 mb-3">Signal-Konvergenz</div>
                <div className="relative" style={{ height: 90 }}>
                  {/* Circles converging to center */}
                  <svg viewBox="0 0 200 80" className="w-full h-full">
                    {/* Data layer circles */}
                    <circle cx="40" cy="20" r="16" fill="none" stroke="#3b82f6" strokeWidth="1" opacity="0.6" />
                    <text x="40" y="23" fill="#3b82f6" fontSize="7" textAnchor="middle">BIO</text>

                    <circle cx="160" cy="20" r="16" fill="none" stroke="#ef4444" strokeWidth="1" opacity="0.6" />
                    <text x="160" y="23" fill="#ef4444" fontSize="7" textAnchor="middle">MARKET</text>

                    <circle cx="40" cy="60" r="16" fill="none" stroke="#8b5cf6" strokeWidth="1" opacity="0.6" />
                    <text x="40" y="63" fill="#8b5cf6" fontSize="7" textAnchor="middle">PSYCHO</text>

                    <circle cx="160" cy="60" r="16" fill="none" stroke="#10b981" strokeWidth="1" opacity="0.6" />
                    <text x="160" y="63" fill="#10b981" fontSize="7" textAnchor="middle">CONTEXT</text>

                    {/* Connecting lines to center */}
                    <line x1="56" y1="20" x2="88" y2="40" stroke="#3b82f6" strokeWidth="0.5" opacity="0.4" />
                    <line x1="144" y1="20" x2="112" y2="40" stroke="#ef4444" strokeWidth="0.5" opacity="0.4" />
                    <line x1="56" y1="60" x2="88" y2="40" stroke="#8b5cf6" strokeWidth="0.5" opacity="0.4" />
                    <line x1="144" y1="60" x2="112" y2="40" stroke="#10b981" strokeWidth="0.5" opacity="0.4" />

                    {/* Center fusion point */}
                    <circle cx="100" cy="40" r="12" fill="rgba(139,92,246,0.15)" stroke="#8b5cf6" strokeWidth="1">
                      <animate attributeName="r" values="10;14;10" dur="2s" repeatCount="indefinite" />
                    </circle>
                    <text x="100" y="43" fill="#e2e8f0" fontSize="7" textAnchor="middle" fontWeight="bold">SCORE</text>
                  </svg>
                </div>
              </div>

              <div className="p-3 rounded-lg" style={{ background: 'rgba(139,92,246,0.08)' }}>
                <p className="text-xs text-violet-300">
                  <strong>Ihr Vorteil:</strong> Logistik nur auf Basis valider Signale steuern, nicht auf Basis von Rauschen.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Revenue Intelligence Module ── */}
      <section style={{ background: '#1e293b' }}>
        <div className="max-w-[1400px] mx-auto px-6 py-24">
          <div className="text-center mb-4">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-bold tracking-wider uppercase mb-6" style={{ background: 'rgba(245,158,11,0.12)', color: '#fbbf24', border: '1px solid rgba(245,158,11,0.2)' }}>
              Revenue Intelligence Module
            </div>
          </div>
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-4">
              Vom Datenpunkt zum Umsatz:<br />
              <span style={{ color: '#f59e0b' }}>Der intelligente Vertriebsassistent</span>
            </h2>
            <p className="text-lg text-slate-400 max-w-3xl mx-auto">
              VIRAL FLUX schlie&szlig;t die L&uuml;cke zwischen Labor und Au&szlig;endienst.
              Komplexe epidemiologische Daten werden in konkrete Vertriebsimpulse verwandelt.
            </p>
          </div>

          {/* Bento Grid for Revenue Intelligence */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* A: Neighborhood Trigger + Visual */}
            <div className="rounded-2xl overflow-hidden" style={{ background: '#0f172a', border: '1px solid #334155' }}>
              <div className="p-6">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center mb-4 text-lg font-extrabold" style={{ background: 'rgba(245,158,11,0.15)', color: '#f59e0b' }}>A</div>
                <h3 className="text-lg font-bold text-white mb-1">Der Neighborhood-Trigger</h3>
                <p className="text-xs font-medium text-amber-400 mb-3">Predictive Sales</p>
                <p className="text-slate-400 text-sm leading-relaxed">
                  Wenn drei Praxen in einer PLZ-Region ihre Influenza-Best&auml;nde massiv aufstocken, erkennt das System ein Cluster.
                </p>
              </div>
              {/* Simulated alert card */}
              <div className="mx-4 mb-4 rounded-lg p-3" style={{ background: '#1e293b', border: '1px solid rgba(245,158,11,0.2)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                  <span className="text-[10px] font-bold text-amber-400">Cluster Alert &mdash; PLZ 60xxx</span>
                </div>
                <div className="space-y-1.5">
                  {['Dr. M&uuml;ller +120%', 'Praxis Weber +85%', 'MVZ S&uuml;d +200%'].map((p, i) => (
                    <div key={i} className="flex items-center gap-2 text-[10px]">
                      <span className="text-amber-400">&#x25B2;</span>
                      <span className="text-slate-400" dangerouslySetInnerHTML={{__html: p}} />
                    </div>
                  ))}
                </div>
                <div className="mt-2 pt-2" style={{ borderTop: '1px solid #33415580' }}>
                  <span className="text-[9px] text-slate-500">12 weitere Kunden in dieser Region noch ohne Bestellung</span>
                </div>
              </div>
            </div>

            {/* B: Consultative Selling + Visual */}
            <div className="rounded-2xl overflow-hidden" style={{ background: '#0f172a', border: '1px solid #334155' }}>
              <div className="p-6">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center mb-4 text-lg font-extrabold" style={{ background: 'rgba(16,185,129,0.15)', color: '#10b981' }}>B</div>
                <h3 className="text-lg font-bold text-white mb-1">Kontext-Sensitive Beratung</h3>
                <p className="text-xs font-medium text-emerald-400 mb-3">Consultative Selling</p>
                <p className="text-slate-400 text-sm leading-relaxed">
                  Medizinisch relevante Aufh&auml;nger statt generischer Verkaufsgespr&auml;che.
                </p>
              </div>
              {/* Simulated context card */}
              <div className="mx-4 mb-4 rounded-lg overflow-hidden" style={{ border: '1px solid rgba(16,185,129,0.2)' }}>
                <div className="px-3 py-2 flex items-center gap-2" style={{ background: 'rgba(16,185,129,0.08)' }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                  <span className="text-[10px] font-bold text-emerald-400">Kontext-Insight</span>
                </div>
                <div className="p-3 space-y-2" style={{ background: '#1e293b' }}>
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] text-slate-500 w-14">Szenario:</span>
                    <span className="text-[10px] text-emerald-300">Hoher Pollenflug + Niedrige Virenlast</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] text-slate-500 w-14">Insight:</span>
                    <span className="text-[10px] text-emerald-300">Patienten symptomatisch, nicht infekti&ouml;s</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] text-slate-500 w-14">Action:</span>
                    <span className="text-[10px] text-white font-medium">IgE-Allergie-Screenings platzieren</span>
                  </div>
                </div>
              </div>
            </div>

            {/* C: Automated Briefing + Visual */}
            <div className="rounded-2xl overflow-hidden" style={{ background: '#0f172a', border: '1px solid #334155' }}>
              <div className="p-6">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center mb-4 text-lg font-extrabold" style={{ background: 'rgba(139,92,246,0.15)', color: '#8b5cf6' }}>C</div>
                <h3 className="text-lg font-bold text-white mb-1">Automated Briefing</h3>
                <p className="text-xs font-medium text-violet-400 mb-3">LLM-Powered</p>
                <p className="text-slate-400 text-sm leading-relaxed">
                  KI-generierte Kommunikationspakete f&uuml;r Ihren Au&szlig;endienst.
                </p>
              </div>
              {/* Simulated briefing output */}
              <div className="mx-4 mb-4 rounded-lg overflow-hidden" style={{ border: '1px solid rgba(139,92,246,0.2)' }}>
                <div className="px-3 py-2 flex items-center gap-2" style={{ background: 'rgba(139,92,246,0.08)' }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="2">
                    <path d="M12 2l2.09 6.26L20.18 10l-6.09 1.74L12 18l-2.09-6.26L3.82 10l6.09-1.74L12 2z" />
                  </svg>
                  <span className="text-[10px] font-bold text-violet-400">KI-Briefing generiert</span>
                </div>
                <div className="p-3 space-y-2" style={{ background: '#1e293b' }}>
                  {[
                    { label: 'E-Mail', text: '"Influenza-Welle erreicht Ihre Region..."' },
                    { label: 'Telefon', text: '"Basierend auf BfArM-Daten empfehlen wir..."' },
                    { label: 'Talking Points', text: '3 Argumente f\u00FCr Bestandsauff\u00FCllung' },
                  ].map((b, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="text-violet-400 text-[10px] mt-0.5">&#10003;</span>
                      <div>
                        <span className="text-[9px] text-violet-400 font-medium">{b.label}: </span>
                        <span className="text-[10px] text-slate-400">{b.text}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Technologie & Compliance ── */}
      <section className="py-24">
        <div className="max-w-[1400px] mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-4">
              Hybrid Intelligence &amp; Digitale Souver&auml;nit&auml;t
            </h2>
            <p className="text-lg text-slate-400 max-w-2xl mx-auto">
              Wir verstehen die Sensibilit&auml;t Ihrer Daten. Deshalb ist VIRAL FLUX nicht nur intelligent, sondern kompromisslos sicher.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* No US-Cloud */}
            <div className="p-8 rounded-2xl" style={{ background: '#1e293b', border: '1px solid #334155' }}>
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(59,130,246,0.15)' }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              </div>
              <h3 className="text-lg font-bold text-white mb-1">No US-Cloud Policy</h3>
              <p className="text-xs font-medium text-blue-400 mb-4">Datenhoheit</p>
              <p className="text-slate-400 text-sm leading-relaxed">
                S&auml;mtliche Datenverarbeitung auf <strong className="text-slate-300">ISO 27001 zertifizierten Servern
                in Deutschland</strong>. Kein Datentransfer in Drittl&auml;nder. DSGVO &amp; KRITIS konform.
              </p>
            </div>

            {/* Annex-Konform */}
            <div className="p-8 rounded-2xl" style={{ background: '#1e293b', border: '1px solid #334155' }}>
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(16,185,129,0.15)' }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
              </div>
              <h3 className="text-lg font-bold text-white mb-1">3-Schicht-Architektur</h3>
              <p className="text-xs font-medium text-emerald-400 mb-4">Annex-Konform</p>
              <div className="space-y-3">
                <div className="p-3 rounded-lg" style={{ background: 'rgba(16,185,129,0.06)' }}>
                  <p className="text-xs text-emerald-300"><strong>Motor</strong>: Prophet &amp; XGBoost f&uuml;r pr&auml;zise Trendberechnung</p>
                </div>
                <div className="p-3 rounded-lg" style={{ background: 'rgba(16,185,129,0.06)' }}>
                  <p className="text-xs text-emerald-300"><strong>Dolmetscher</strong>: Lokales LLM &mdash; keine Daten verlassen den sicheren Raum</p>
                </div>
                <div className="p-3 rounded-lg" style={{ background: 'rgba(16,185,129,0.06)' }}>
                  <p className="text-xs text-emerald-300"><strong>W&auml;chter</strong>: Human-in-the-Loop &mdash; Freigabe durch Laborleiter</p>
                </div>
              </div>
            </div>

            {/* Value Toggle */}
            <div className="p-8 rounded-2xl" style={{ background: '#1e293b', border: '1px solid #334155' }}>
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-6" style={{ background: 'rgba(245,158,11,0.15)' }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
              </div>
              <h3 className="text-lg font-bold text-white mb-4">Der Unterschied</h3>
              <div className="space-y-2.5">
                {[
                  { old: 'Unklare Cloud', now: '100% German Cloud' },
                  { old: 'Engp\u00E4sse \u00FCberraschen', now: 'Beschaffung vor der Welle' },
                  { old: 'Generischer Vertrieb', now: 'Datengest\u00FCtzt & regional' },
                  { old: 'Passive Auftragsannahme', now: 'Aktiver Versorgungsberater' },
                ].map((row, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="text-red-400/60 line-through flex-1 text-right">{row.old}</span>
                    <span className="text-slate-600">&rarr;</span>
                    <span className="text-emerald-400 flex-1">{row.now}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA / Footer ── */}
      <section className="py-24" style={{ background: 'linear-gradient(135deg, rgba(59,130,246,0.08), rgba(6,182,212,0.08))' }}>
        <div className="max-w-[800px] mx-auto px-6 text-center">
          <h2 className="text-2xl md:text-3xl font-extrabold text-white mb-4">
            Sind Sie bereit f&uuml;r den sicheren Vorsprung?
          </h2>
          <p className="text-base text-slate-400 mb-3 leading-relaxed">
            Lassen Sie uns dar&uuml;ber sprechen, wie VIRAL FLUX Ihre Laborkapazit&auml;ten optimieren
            und Ihren Vertrieb durch Datenintelligenz steuern kann &mdash; auf souver&auml;ner Infrastruktur.
          </p>
          <h3 className="text-xl font-bold text-white mb-8">
            Vereinbaren Sie jetzt Ihren Strategie-Termin.
          </h3>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="px-8 py-3.5 text-base font-semibold rounded-xl text-white transition-all hover:scale-105 shadow-lg shadow-blue-500/25"
              style={{ background: 'linear-gradient(135deg, #3b82f6, #06b6d4)' }}
            >
              Kontakt aufnehmen
            </button>
            <button
              className="px-8 py-3.5 text-base font-semibold rounded-xl transition-all hover:scale-105"
              style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8', border: '1px solid #334155' }}
            >
              IT-Sicherheitskonzept anfordern
            </button>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="py-8 text-center text-sm text-slate-600" style={{ borderTop: '1px solid #1e293b' }}>
        <div className="max-w-[1400px] mx-auto px-6">
          <p>VIRAL FLUX Core &copy; 2026. Entwickelt f&uuml;r High-Throughput-Laboratories. Hosted in Germany.</p>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
