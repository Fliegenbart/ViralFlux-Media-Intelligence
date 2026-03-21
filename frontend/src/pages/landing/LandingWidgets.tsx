import React, { useEffect, useRef, useState } from 'react';

export type ThemeName = 'light' | 'dark';

export interface ThemePalette {
  bg: string;
  bgCard: string;
  text: string;
  textSec: string;
  textMuted: string;
  indigo: string;
  indigoLight: string;
  indigoSoft: string;
  border: string;
  borderLight: string;
  rule: string;
}

const LIGHT: ThemePalette = {
  bg: '#faf9f7',
  bgCard: '#ffffff',
  text: '#1e293b',
  textSec: '#64748b',
  textMuted: '#94a3b8',
  indigo: '#4338ca',
  indigoLight: '#e0e7ff',
  indigoSoft: '#eef2ff',
  border: '#e2e8f0',
  borderLight: '#f1f5f9',
  rule: '#cbd5e1',
};

const DARK: ThemePalette = {
  bg: '#0c1222',
  bgCard: '#1e293b',
  text: '#f1f5f9',
  textSec: '#94a3b8',
  textMuted: '#64748b',
  indigo: '#6366f1',
  indigoLight: 'rgba(99,102,241,0.18)',
  indigoSoft: 'rgba(99,102,241,0.1)',
  border: '#334155',
  borderLight: '#1e293b',
  rule: '#475569',
};

export const createThemePalette = (theme: ThemeName): ThemePalette =>
  (theme === 'dark' ? DARK : LIGHT);

const useReveal = () => {
  const ref = useRef<HTMLElement>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setRevealed(true);
          obs.disconnect();
        }
      },
      { threshold: 0.12 },
    );

    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return { ref, revealed };
};

interface RevealSectionProps {
  children: React.ReactNode;
  delay?: number;
  className?: string;
  style?: React.CSSProperties;
}

export const RevealSection: React.FC<RevealSectionProps> = ({
  children,
  delay = 0,
  className,
  style,
}) => {
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

interface ScoreGaugeProps {
  score: number;
  label: string;
  palette: ThemePalette;
}

export const ScoreGauge: React.FC<ScoreGaugeProps> = ({ score, label, palette }) => {
  const [val, setVal] = useState(0);

  useEffect(() => {
    let frame = 0;
    const t0 = performance.now();
    const dur = 1400;
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);

    const tick = (now: number) => {
      const p = Math.min((now - t0) / dur, 1);
      setVal(score * ease(p));
      if (p < 1) frame = requestAnimationFrame(tick);
    };

    const delay = window.setTimeout(() => {
      frame = requestAnimationFrame(tick);
    }, 700);

    return () => {
      window.clearTimeout(delay);
      cancelAnimationFrame(frame);
    };
  }, [score]);

  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - val * circumference;
  const strokeColor =
    val > 0.7
      ? 'var(--status-danger, #dc2626)'
      : val > 0.5
        ? 'var(--status-warning, #d97706)'
        : val > 0.3
          ? 'var(--status-info, #2563eb)'
          : 'var(--status-success, #059669)';

  return (
    <div style={{ textAlign: 'center' }}>
      <svg width="148" height="148" viewBox="0 0 148 148" aria-hidden="true">
        <circle cx="74" cy="74" r={radius} fill="none" stroke={palette.borderLight} strokeWidth="9" />
        <circle
          cx="74"
          cy="74"
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 74 74)"
          style={{ transition: 'stroke 0.3s ease' }}
        />
        <text
          x="74"
          y="68"
          textAnchor="middle"
          style={{
            fontFamily: "'DM Serif Display', Georgia, 'Times New Roman', serif",
            fontSize: 30,
            fill: palette.text,
          }}
        >
          {val.toFixed(2)}
        </text>
        <text
          x="74"
          y="90"
          textAnchor="middle"
          style={{
            fontFamily: "'DM Sans', 'Inter', system-ui, sans-serif",
            fontSize: 10,
            fill: palette.textMuted,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          {label}
        </text>
      </svg>
    </div>
  );
};

interface VirusBarsProps {
  data?: Array<{ label: string; pct: number; color: string }>;
  palette: ThemePalette;
}

export const VirusBars: React.FC<VirusBarsProps> = ({ data: propData, palette }) => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 1000);
    return () => window.clearTimeout(timer);
  }, []);

  const data =
    propData || [
      { label: 'Influenza A', pct: 0, color: '#dc2626' },
      { label: 'SARS-CoV-2', pct: 0, color: '#2563eb' },
      { label: 'RSV', pct: 0, color: '#d97706' },
    ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {data.map((item, index) => (
        <div
          key={item.label}
          style={{
            opacity: visible ? 1 : 0,
            transform: visible ? 'translateX(0)' : 'translateX(8px)',
            transition: `all 0.4s ease ${index * 0.12}s`,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ fontSize: 11, color: palette.textSec, fontWeight: 500 }}>{item.label}</span>
            <span style={{ fontSize: 11, color: palette.textMuted }}>{item.pct}%</span>
          </div>
          <div style={{ height: 5, borderRadius: 3, background: palette.borderLight, overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                borderRadius: 3,
                background: item.color,
                width: visible ? `${item.pct}%` : '0%',
                transition: `width 0.9s ease ${1 + index * 0.15}s`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
};

interface MiniGermanyMapProps {
  palette: ThemePalette;
}

export const MiniGermanyMap: React.FC<MiniGermanyMapProps> = ({ palette }) => (
  <svg
    viewBox="0 0 220 280"
    style={{ width: '100%', maxWidth: 210, display: 'block', margin: '0 auto' }}
    aria-hidden="true"
  >
    <path
      d="M100 12L120 10L138 18L152 14L162 28L172 40L178 62L182 80L172 95L178 112L186 124L190 142L180 158L174 174L164 185L158 200L148 212L132 222L122 232L108 236L96 240L82 244L66 240L56 230L46 214L40 198L36 182L32 166L28 150L32 134L38 118L44 102L48 86L56 70L66 54L76 40L86 26Z"
      fill={palette.borderLight}
      stroke={palette.border}
      strokeWidth="1.5"
    />
    {[
      { cx: 80, cy: 88, r: 16, color: '#dc2626', inner: 5.5 },
      { cx: 145, cy: 110, r: 13, color: '#d97706', inner: 4.5 },
      { cx: 110, cy: 62, r: 10, color: '#2563eb', inner: 3.5 },
      { cx: 62, cy: 195, r: 9, color: '#059669', inner: 3 },
      { cx: 128, cy: 185, r: 12, color: '#dc2626', inner: 4 },
    ].map((hotspot, index) => (
      <g key={index}>
        <circle
          cx={hotspot.cx}
          cy={hotspot.cy}
          r={hotspot.r}
          fill={`${hotspot.color}14`}
          stroke={`${hotspot.color}40`}
          strokeWidth="1"
        />
        <circle cx={hotspot.cx} cy={hotspot.cy} r={hotspot.inner} fill={hotspot.color} />
      </g>
    ))}
  </svg>
);
