import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

/* ═══ Design Tokens ══════════════════════════════════════════════════ */
const C = {
  bg: '#faf9f7',
  bgCard: '#ffffff',
  text: '#1e293b',
  textSec: '#64748b',
  textMuted: '#94a3b8',
  indigo: '#4338ca',
  indigoLight: '#e0e7ff',
  indigoSoft: '#eef2ff',
  amber: '#d97706',
  border: '#e2e8f0',
  borderLight: '#f1f5f9',
  rule: '#cbd5e1',
};

const FONT_SERIF = "'DM Serif Display', Georgia, 'Times New Roman', serif";
const FONT_SANS = "'DM Sans', 'Inter', system-ui, sans-serif";

const MAILTO = (() => {
  const subject = 'POC Anfrage ViralFlux Media Intelligence';
  const body = [
    'Hallo PEIX Team,', '',
    'wir möchten ein kurzes Beratungsgespräch zu ViralFlux vereinbaren.', '',
    'Marke/Produkt:', 'Regionen:', 'Gewünschter Termin:', '', 'Viele Grüße',
  ].join('\n');
  return `mailto:sales@peix.de?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
})();

/* ═══ Score Gauge ════════════════════════════════════════════════════ */
const ScoreGauge: React.FC<{ score: number; label: string }> = ({ score, label }) => {
  const [val, setVal] = useState(0);

  useEffect(() => {
    let frame: number;
    const t0 = performance.now();
    const dur = 1400;
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);
    const tick = (now: number) => {
      const p = Math.min((now - t0) / dur, 1);
      setVal(score * ease(p));
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    const delay = setTimeout(() => { frame = requestAnimationFrame(tick); }, 700);
    return () => { clearTimeout(delay); cancelAnimationFrame(frame); };
  }, [score]);

  const R = 54, circ = 2 * Math.PI * R;
  const offset = circ - val * circ;
  const col = val > 0.7 ? '#dc2626' : val > 0.5 ? '#d97706' : val > 0.3 ? '#2563eb' : '#059669';

  return (
    <div style={{ textAlign: 'center' }}>
      <svg width="148" height="148" viewBox="0 0 148 148">
        <circle cx="74" cy="74" r={R} fill="none" stroke={C.borderLight} strokeWidth="9" />
        <circle
          cx="74" cy="74" r={R} fill="none"
          stroke={col} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={offset}
          transform="rotate(-90 74 74)"
          style={{ transition: 'stroke 0.3s ease' }}
        />
        <text x="74" y="68" textAnchor="middle" style={{ fontFamily: FONT_SERIF, fontSize: 30, fill: C.text }}>
          {val.toFixed(2)}
        </text>
        <text x="74" y="90" textAnchor="middle" style={{
          fontFamily: FONT_SANS, fontSize: 10, fill: C.textMuted,
          textTransform: 'uppercase', letterSpacing: '0.08em',
        }}>
          {label}
        </text>
      </svg>
    </div>
  );
};

/* ═══ Virus Level Bars ═══════════════════════════════════════════════ */
const VirusBars: React.FC<{ data?: Array<{ label: string; pct: number; color: string }> }> = ({ data: propData }) => {
  const [vis, setVis] = useState(false);
  useEffect(() => { const t = setTimeout(() => setVis(true), 1000); return () => clearTimeout(t); }, []);

  const data = propData || [
    { label: 'Influenza A', pct: 0, color: '#dc2626' },
    { label: 'SARS-CoV-2', pct: 0, color: '#2563eb' },
    { label: 'RSV', pct: 0, color: '#d97706' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {data.map((d, i) => (
        <div key={d.label} style={{
          opacity: vis ? 1 : 0, transform: vis ? 'translateX(0)' : 'translateX(8px)',
          transition: `all 0.4s ease ${i * 0.12}s`,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ fontFamily: FONT_SANS, fontSize: 11, color: C.textSec, fontWeight: 500 }}>{d.label}</span>
            <span style={{ fontFamily: FONT_SANS, fontSize: 11, color: C.textMuted }}>{d.pct}%</span>
          </div>
          <div style={{ height: 5, borderRadius: 3, background: C.borderLight, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 3, background: d.color,
              width: vis ? `${d.pct}%` : '0%',
              transition: `width 0.9s ease ${1 + i * 0.15}s`,
            }} />
          </div>
        </div>
      ))}
    </div>
  );
};

/* ═══ Reveal Hook ════════════════════════════════════════════════════ */
const useReveal = () => {
  const ref = useRef<HTMLElement>(null);
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setRevealed(true); obs.disconnect(); } },
      { threshold: 0.12 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return { ref, revealed };
};

const RevealSection: React.FC<{
  children: React.ReactNode; delay?: number; className?: string; style?: React.CSSProperties;
}> = ({ children, delay = 0, className, style }) => {
  const { ref, revealed } = useReveal();
  return (
    <section
      ref={ref as React.RefObject<HTMLElement>}
      className={className}
      style={{
        opacity: revealed ? 1 : 0,
        transform: revealed ? 'translateY(0)' : 'translateY(28px)',
        transition: `opacity 0.65s ease ${delay}s, transform 0.65s ease ${delay}s`,
        ...style,
      }}
    >
      {children}
    </section>
  );
};

/* ═══ Simplified Germany Map ═════════════════════════════════════════ */
const MiniGermanyMap: React.FC = () => (
  <svg viewBox="0 0 220 280" style={{ width: '100%', maxWidth: 210, display: 'block', margin: '0 auto' }}>
    <path
      d="M100 12L120 10L138 18L152 14L162 28L172 40L178 62L182 80L172 95L178 112L186 124L190 142L180 158L174 174L164 185L158 200L148 212L132 222L122 232L108 236L96 240L82 244L66 240L56 230L46 214L40 198L36 182L32 166L28 150L32 134L38 118L44 102L48 86L56 70L66 54L76 40L86 26Z"
      fill={C.borderLight} stroke={C.border} strokeWidth="1.5"
    />
    {/* Hotspot indicators */}
    {[
      { cx: 80, cy: 88, r: 16, color: '#dc2626', inner: 5.5 },
      { cx: 145, cy: 110, r: 13, color: '#d97706', inner: 4.5 },
      { cx: 110, cy: 62, r: 10, color: '#2563eb', inner: 3.5 },
      { cx: 62, cy: 195, r: 9, color: '#059669', inner: 3 },
      { cx: 128, cy: 185, r: 12, color: '#dc2626', inner: 4 },
    ].map((h, i) => (
      <g key={i}>
        <circle cx={h.cx} cy={h.cy} r={h.r} fill={h.color + '14'} stroke={h.color + '40'} strokeWidth="1" />
        <circle cx={h.cx} cy={h.cy} r={h.inner} fill={h.color} />
      </g>
    ))}
  </svg>
);

/* ═══ Section Number ═════════════════════════════════════════════════ */
const SectionHead: React.FC<{ num: string; children: React.ReactNode }> = ({ num, children }) => (
  <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 32 }}>
    <span style={{ fontFamily: FONT_SERIF, fontSize: 14, color: C.textMuted, userSelect: 'none' }}>{num}</span>
    <h2 style={{ fontFamily: FONT_SERIF, fontSize: 32, margin: 0, letterSpacing: '-0.01em', color: C.text }}>
      {children}
    </h2>
  </div>
);

/* ═══ Hover helper ═══════════════════════════════════════════════════ */
const hoverLift = {
  onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
    const t = e.currentTarget;
    t.style.transform = 'translateY(-4px)';
    t.style.boxShadow = '0 8px 32px rgba(0,0,0,0.06)';
    t.style.borderColor = C.indigo + '40';
  },
  onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
    const t = e.currentTarget;
    t.style.transform = 'translateY(0)';
    t.style.boxShadow = 'none';
    t.style.borderColor = C.border;
  },
};

/* ═══ Responsive CSS ═════════════════════════════════════════════════ */
const RESPONSIVE_CSS = `
  .lp-hero-grid { display: grid; grid-template-columns: 1fr 380px; gap: 48px; align-items: start; }
  .lp-evidence-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
  .lp-flow-grid { display: grid; grid-template-columns: repeat(4, 1fr); position: relative; }
  .lp-preview-grid { display: grid; grid-template-columns: 210px 1fr; gap: 40px; align-items: center; }
  .lp-nav-actions { display: flex; gap: 10px; align-items: center; }
  .lp-flow-line { position: absolute; top: 32px; left: 12.5%; right: 12.5%; height: 2px;
    background: linear-gradient(90deg, ${C.indigo}30, ${C.indigo}60, ${C.indigo}30); z-index: 0; }

  @media (max-width: 960px) {
    .lp-hero-grid { grid-template-columns: 1fr; gap: 28px; }
    .lp-evidence-grid { grid-template-columns: 1fr; }
    .lp-flow-grid { grid-template-columns: repeat(2, 1fr); gap: 28px; }
    .lp-flow-line { display: none; }
    .lp-preview-grid { grid-template-columns: 1fr; gap: 24px; }
    .lp-hero-title { font-size: 38px !important; }
  }
  @media (max-width: 640px) {
    .lp-flow-grid { grid-template-columns: 1fr; }
    .lp-nav-actions { flex-direction: column; width: 100%; }
    .lp-nav-actions > * { width: 100%; text-align: center; }
    .lp-hero-title { font-size: 30px !important; }
  }
`;

/* ═══ Main Component ═════════════════════════════════════════════════ */
const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const [heroVis, setHeroVis] = useState(false);
  const [peixScore, setPeixScore] = useState(0.72);
  const [virusData, setVirusData] = useState([
    { label: 'Influenza A', pct: 0, color: '#dc2626' },
    { label: 'SARS-CoV-2', pct: 0, color: '#2563eb' },
    { label: 'RSV', pct: 0, color: '#d97706' },
  ]);

  useEffect(() => { const t = setTimeout(() => setHeroVis(true), 80); return () => clearTimeout(t); }, []);

  // Fetch live PEIX score + virus data
  useEffect(() => {
    fetch('/api/v1/outbreak-score/peix-score')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        const ns = data.national_score ?? data.score;
        if (typeof ns === 'number') setPeixScore(ns / 100);
        const vs = data.virus_scores;
        if (vs) {
          const updated = [
            { label: 'Influenza A', pct: Math.round((vs['influenza']?.epi_score ?? vs['Influenza']?.epi_score ?? 0) * 100), color: '#dc2626' },
            { label: 'SARS-CoV-2', pct: Math.round((vs['covid']?.epi_score ?? vs['COVID-19']?.epi_score ?? 0) * 100), color: '#2563eb' },
            { label: 'RSV', pct: Math.round((vs['rsv']?.epi_score ?? vs['RSV']?.epi_score ?? 0) * 100), color: '#d97706' },
          ];
          setVirusData(updated);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div style={{ minHeight: '100vh', background: C.bg, fontFamily: FONT_SANS, color: C.text, overflowX: 'hidden' }}>
      <style>{RESPONSIVE_CSS}</style>

      {/* Grid-paper background */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        backgroundImage: `linear-gradient(${C.border}1a 1px, transparent 1px), linear-gradient(90deg, ${C.border}1a 1px, transparent 1px)`,
        backgroundSize: '52px 52px',
      }} />

      {/* ─── Navigation ──────────────────────────────────────────── */}
      <nav style={{
        position: 'relative', zIndex: 10, maxWidth: 1120, margin: '0 auto',
        padding: '20px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8, background: C.indigo,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
              <path d="M3 12h4l2-4 3 8 2-4h7" />
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: '-0.01em' }}>
              PEIX <span style={{ color: C.textMuted, fontWeight: 400 }}>|</span> ViralFlux
            </div>
            <div style={{ fontSize: 11, color: C.textMuted }}>Media Intelligence</div>
          </div>
        </div>
        <div className="lp-nav-actions">
          <a
            href={MAILTO}
            style={{
              fontSize: 13, fontWeight: 600, color: C.textSec, textDecoration: 'none',
              padding: '8px 16px', borderRadius: 8, border: `1px solid ${C.border}`,
              background: 'white', transition: 'border-color 0.2s', display: 'inline-block',
            }}
          >
            Kontakt
          </a>
          <button
            onClick={() => navigate('/dashboard')}
            style={{
              fontSize: 13, fontWeight: 600, color: 'white', padding: '8px 16px',
              borderRadius: 8, border: 'none', background: C.indigo, cursor: 'pointer',
              transition: 'all 0.2s', boxShadow: `0 2px 8px ${C.indigo}25`,
            }}
          >
            Zum Dashboard
          </button>
        </div>
      </nav>

      {/* ─── Hero ────────────────────────────────────────────────── */}
      <div
        className="lp-hero-grid"
        style={{
          position: 'relative', zIndex: 5, maxWidth: 1120, margin: '0 auto',
          padding: '40px 24px 0',
          opacity: heroVis ? 1 : 0, transform: heroVis ? 'translateY(0)' : 'translateY(18px)',
          transition: 'opacity 0.7s ease, transform 0.7s ease',
        }}
      >
        {/* Left: Copy */}
        <div>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 14px',
            borderRadius: 4, background: C.indigoSoft, color: C.indigo,
            fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', marginBottom: 24,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.indigo, opacity: 0.5 }} />
            Epidemiologische Intelligence
          </div>

          <h1
            className="lp-hero-title"
            style={{
              fontFamily: FONT_SERIF, fontSize: 52, lineHeight: 1.08,
              letterSpacing: '-0.02em', color: C.text, margin: 0, maxWidth: 560,
            }}
          >
            Medienplanung starten,{' '}
            <span style={{ color: C.indigo }}>bevor</span>{' '}
            der Abverkauf hochläuft.
          </h1>

          <p style={{ marginTop: 20, fontSize: 17, lineHeight: 1.65, color: C.textSec, maxWidth: 480 }}>
            ViralFlux verbindet regionale Epidemielagen mit eurem Produktprofil
            und leitet daraus direkte Media-Hinweise ab — bundeslandgenau,
            mit 14-Tage-Horizont.
          </p>

          <div style={{ marginTop: 28, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <button
              onClick={() => navigate('/dashboard?tab=map')}
              style={{
                fontSize: 14, fontWeight: 600, color: 'white', padding: '12px 24px',
                borderRadius: 8, border: 'none', background: C.indigo, cursor: 'pointer',
                transition: 'all 0.2s', boxShadow: `0 2px 8px ${C.indigo}30`,
              }}
            >
              Signal-Board starten
            </button>
            <button
              onClick={() => navigate('/dashboard?tab=product-intel')}
              style={{
                fontSize: 14, fontWeight: 600, color: C.amber, padding: '12px 24px',
                borderRadius: 8, border: `2px solid ${C.amber}`, background: 'transparent',
                cursor: 'pointer', transition: 'all 0.2s',
              }}
            >
              Produkt anlegen
            </button>
          </div>

          {/* Thin rule + stats */}
          <div style={{ marginTop: 36, width: 56, height: 1, background: C.rule }} />
          <div style={{ marginTop: 14, display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            {['16 Bundesländer', '4 Virustypen', '14-Tage-Prognose'].map(s => (
              <span key={s} style={{ fontSize: 12, color: C.textMuted, fontWeight: 500 }}>{s}</span>
            ))}
          </div>
        </div>

        {/* Right: Live Score Widget */}
        <div style={{
          background: 'white', border: `1px solid ${C.border}`, borderRadius: 16,
          padding: '24px 20px',
          boxShadow: '0 4px 24px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.03)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{
              fontSize: 11, fontWeight: 600, color: C.textMuted,
              textTransform: 'uppercase', letterSpacing: '0.06em',
            }}>
              Live Lagebild
            </span>
            <span style={{
              fontSize: 10, fontWeight: 700, color: '#059669',
              background: '#ecfdf5', padding: '2px 8px', borderRadius: 4,
            }}>
              LIVE
            </span>
          </div>
          <div style={{ fontSize: 12, color: C.textMuted, marginBottom: 16 }}>
            PeixEpiScore — Gesamtindex
          </div>

          <ScoreGauge score={peixScore} label="PeixEpiScore" />

          <div style={{ marginTop: 20, borderTop: `1px solid ${C.borderLight}`, paddingTop: 16 }}>
            <div style={{
              fontSize: 11, fontWeight: 600, color: C.textMuted,
              textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 10,
            }}>
              Viruslast-Signale
            </div>
            <VirusBars data={virusData} />
          </div>

          <div style={{
            marginTop: 16, padding: '10px 14px', borderRadius: 8,
            background: C.indigoSoft, fontSize: 12, color: C.textSec, lineHeight: 1.55,
          }}>
            <strong style={{ color: C.indigo, fontWeight: 600 }}>Empfehlung:</strong>{' '}
            Budgets in NW, BY, SN erhöhen
          </div>
        </div>
      </div>

      {/* ─── Main Content ────────────────────────────────────────── */}
      <main style={{ position: 'relative', zIndex: 5, maxWidth: 1120, margin: '0 auto', padding: '0 24px 80px' }}>

        {/* ── Divider ──────────────────────────────────────────── */}
        <div style={{ margin: '64px 0', borderTop: `1px solid ${C.border}` }} />

        {/* ═══ 01 — Evidence / Features ══════════════════════════ */}
        <RevealSection>
          <SectionHead num="01">
            Was macht <span style={{ color: C.indigo }}>ViralFlux</span> anders
          </SectionHead>

          <div className="lp-evidence-grid">
            {[
              {
                icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={C.indigo} strokeWidth="2" strokeLinecap="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></svg>,
                title: 'Epidemiologische Signale',
                text: 'Abwasser-Monitoring, ARE-Inzidenz, Versorgungsengpässe und Wetterdaten fließen in den PeixEpiScore ein.',
              },
              {
                icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={C.indigo} strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="10" r="3" /><path d="M12 2a8 8 0 0 0-8 8c0 5.4 7 12 8 12s8-6.6 8-12a8 8 0 0 0-8-8Z" /></svg>,
                title: 'Regionale Zuordnung',
                text: 'Jede Empfehlung ist bundeslandgenau. Kein Gießkannenprinzip — Budget wird dort aktiviert, wo die Epidemie ankommt.',
              },
              {
                icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={C.indigo} strokeWidth="2" strokeLinecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></svg>,
                title: 'Review-First',
                text: 'Kein Auto-Push in die Kampagne. Jedes Match durchläuft eine Freigabe — algorithmisch transparent und auditierbar.',
              },
            ].map((card) => (
              <div
                key={card.title}
                style={{
                  background: 'white', border: `1px solid ${C.border}`, borderRadius: 12,
                  padding: '28px 24px', transition: 'all 0.25s ease', cursor: 'default',
                }}
                {...hoverLift}
              >
                <div style={{
                  width: 42, height: 42, borderRadius: 10, background: C.indigoLight,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16,
                }}>
                  {card.icon}
                </div>
                <h3 style={{ fontFamily: FONT_SANS, fontSize: 16, fontWeight: 700, margin: '0 0 8px' }}>
                  {card.title}
                </h3>
                <p style={{ fontSize: 14, lineHeight: 1.6, color: C.textSec, margin: 0 }}>
                  {card.text}
                </p>
              </div>
            ))}
          </div>
        </RevealSection>

        {/* ── Divider ──────────────────────────────────────────── */}
        <div style={{ margin: '64px 0', borderTop: `1px solid ${C.border}` }} />

        {/* ═══ 02 — Workflow Flow ════════════════════════════════ */}
        <RevealSection>
          <SectionHead num="02">Von Signal zu Freigabe</SectionHead>

          <div className="lp-flow-grid">
            <div className="lp-flow-line" />
            {[
              { num: '01', label: 'Signal', desc: 'Epidemiologische Daten aus Abwasser, Wetter und Versorgung erkennen.' },
              { num: '02', label: 'Erwartung', desc: '14-Tage-Prognose pro Bundesland mit PeixEpiScore berechnen.' },
              { num: '03', label: 'Produkt', desc: 'Gelo-Produkt automatisch dem passenden Indikationsfeld zuordnen.' },
              { num: '04', label: 'Freigabe', desc: 'Match manuell prüfen, Kampagne aktivieren oder verwerfen.' },
            ].map((step, i) => (
              <div key={step.num} style={{ position: 'relative', zIndex: 1, textAlign: 'center', padding: '0 12px' }}>
                <div style={{
                  width: 64, height: 64, borderRadius: '50%', margin: '0 auto 16px',
                  background: i === 3 ? C.indigo : 'white',
                  border: `2px solid ${i === 3 ? C.indigo : C.border}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: FONT_SERIF, fontSize: 20,
                  color: i === 3 ? 'white' : C.text,
                  boxShadow: i === 3 ? `0 4px 16px ${C.indigo}30` : '0 2px 8px rgba(0,0,0,0.04)',
                }}>
                  {step.num}
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>{step.label}</div>
                <p style={{ fontSize: 13, lineHeight: 1.55, color: C.textSec, margin: 0 }}>{step.desc}</p>
              </div>
            ))}
          </div>
        </RevealSection>

        {/* ── Divider ──────────────────────────────────────────── */}
        <div style={{ margin: '64px 0', borderTop: `1px solid ${C.border}` }} />

        {/* ═══ 03 — Live Data Preview ═══════════════════════════ */}
        <RevealSection>
          <SectionHead num="03">Regionale Lagebeurteilung</SectionHead>

          <div
            className="lp-preview-grid"
            style={{
              background: 'white', border: `1px solid ${C.border}`, borderRadius: 16, padding: 32,
            }}
          >
            <MiniGermanyMap />
            <div>
              <div style={{
                fontSize: 11, fontWeight: 600, color: C.textMuted,
                textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12,
              }}>
                Dashboard-Vorschau
              </div>
              <h3 style={{ fontFamily: FONT_SERIF, fontSize: 24, margin: '0 0 12px' }}>
                So sieht das Lagebild aus
              </h3>
              <p style={{ fontSize: 14, lineHeight: 1.65, color: C.textSec, margin: '0 0 20px', maxWidth: 440 }}>
                Die Deutschlandkarte zeigt Viruslast-Hotspots in Echtzeit.
                Beim Hovern über ein Bundesland erscheint ein konkreter
                Kampagnenvorschlag mit epidemiologischer Begründung.
              </p>

              {/* Mock data rows */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  { bl: 'NW', name: 'Nordrhein-Westfalen', score: 0.82, trend: 'steigend', col: '#dc2626' },
                  { bl: 'BY', name: 'Bayern', score: 0.68, trend: 'steigend', col: '#d97706' },
                  { bl: 'SN', name: 'Sachsen', score: 0.71, trend: 'stabil', col: '#d97706' },
                ].map(r => (
                  <div key={r.bl} style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '8px 12px', borderRadius: 8, background: C.borderLight, fontSize: 13,
                  }}>
                    <span style={{ fontWeight: 700, width: 28 }}>{r.bl}</span>
                    <span style={{ color: C.textSec, flex: 1 }}>{r.name}</span>
                    <span style={{
                      fontSize: 12, fontWeight: 600, color: r.col,
                      background: r.col + '15', padding: '2px 8px', borderRadius: 4,
                    }}>
                      {r.score.toFixed(2)}
                    </span>
                    <span style={{ fontSize: 11, color: C.textMuted }}>
                      {r.trend === 'steigend' ? '↑' : r.trend === 'fallend' ? '↓' : '→'} {r.trend}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </RevealSection>

        {/* ── Divider ──────────────────────────────────────────── */}
        <div style={{ margin: '64px 0', borderTop: `1px solid ${C.border}` }} />

        {/* ═══ CTA ══════════════════════════════════════════════ */}
        <RevealSection style={{ textAlign: 'center' }}>
          <h2 style={{
            fontFamily: FONT_SERIF, fontSize: 36, margin: '0 0 16px', letterSpacing: '-0.01em',
          }}>
            Bereit für datenbasierte Medienplanung?
          </h2>
          <p style={{ fontSize: 16, color: C.textSec, marginBottom: 28, maxWidth: 480, marginLeft: 'auto', marginRight: 'auto' }}>
            Starten Sie direkt im Dashboard oder vereinbaren Sie ein kurzes Beratungsgespräch.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button
              onClick={() => navigate('/dashboard')}
              style={{
                fontSize: 15, fontWeight: 600, color: 'white', padding: '14px 32px',
                borderRadius: 10, border: 'none', background: C.indigo, cursor: 'pointer',
                transition: 'all 0.2s', boxShadow: `0 4px 16px ${C.indigo}30`,
              }}
            >
              Dashboard öffnen
            </button>
            <a
              href={MAILTO}
              style={{
                fontSize: 15, fontWeight: 600, color: C.amber, padding: '14px 32px',
                borderRadius: 10, border: `2px solid ${C.amber}`, background: 'transparent',
                textDecoration: 'none', display: 'inline-flex', alignItems: 'center',
                transition: 'all 0.2s',
              }}
            >
              Beratung anfragen
            </a>
          </div>
        </RevealSection>

        {/* ─── Footer ──────────────────────────────────────────── */}
        <footer style={{
          marginTop: 80, paddingTop: 20, paddingBottom: 12,
          borderTop: `1px solid ${C.border}`, textAlign: 'center', fontSize: 12, color: C.textMuted,
        }}>
          PEIX ViralFlux Media Intelligence &copy; 2026 &middot; Predictive Pharma Media Intelligence
        </footer>
      </main>
    </div>
  );
};

export default LandingPage;
