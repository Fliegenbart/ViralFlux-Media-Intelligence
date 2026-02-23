import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useTheme } from '../App';
import { apiFetch } from '../lib/api';

interface Props {
  children: React.ReactNode;
}

const NAV_ITEMS = [
  { label: 'Lagebild', path: '/lagebild' },
  { label: 'Empfehlungen', path: '/empfehlungen' },
  { label: 'Produkte', path: '/produkte' },
  { label: 'Backtest', path: '/backtest' },
] as const;

const AppLayout: React.FC<Props> = ({ children }) => {
  const { theme, toggle } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [pdfLoading, setPdfLoading] = useState(false);
  const [lastUpdate] = useState(() => {
    const d = new Date();
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  });

  const isActive = (path: string) => location.pathname.startsWith(path);

  const handlePdfDownload = async () => {
    setPdfLoading(true);
    try {
      await apiFetch('/api/v1/media/weekly-brief/generate', { method: 'POST' });
      const res = await apiFetch('/api/v1/media/weekly-brief/latest');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'ViralFlux_Action_Brief.pdf';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('PDF download failed', e);
    } finally {
      setPdfLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-primary)' }}>
      {/* ── Top Navigation ─────────────────────────────────────────── */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 50,
        display: 'flex', alignItems: 'center', gap: 24,
        padding: '0 24px', height: 56,
        background: 'var(--bg-card)',
        borderBottom: '1px solid var(--border-color)',
        backdropFilter: 'blur(12px)',
      }}>
        {/* Logo */}
        <Link to="/welcome" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none' }}>
          <span style={{
            fontWeight: 800, fontSize: 18, letterSpacing: '-0.02em',
            color: 'var(--accent-violet)', background: 'var(--bg-secondary)',
            borderRadius: 6, padding: '2px 7px',
          }}>VF</span>
          <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>
            ViralFlux
          </span>
        </Link>

        {/* Nav items */}
        <nav style={{ display: 'flex', gap: 4, marginLeft: 16, height: '100%' }}>
          {NAV_ITEMS.map(({ label, path }) => {
            const active = isActive(path);
            return (
              <button
                key={path}
                onClick={() => navigate(path)}
                style={{
                  all: 'unset', cursor: 'pointer',
                  display: 'flex', alignItems: 'center',
                  padding: '0 14px', height: '100%',
                  fontSize: 13, fontWeight: active ? 600 : 500,
                  color: active ? 'var(--accent-violet)' : 'var(--text-secondary)',
                  borderBottom: active ? '2px solid var(--accent-violet)' : '2px solid transparent',
                  transition: 'color 0.15s, border-color 0.15s',
                }}
              >
                {label}
              </button>
            );
          })}
        </nav>

        <div style={{ flex: 1 }} />

        {/* Right actions */}
        <Link to="/admin" style={{ fontSize: 18, textDecoration: 'none', color: 'var(--text-muted)', lineHeight: 1 }} title="Admin">
          &#9881;
        </Link>
        <button
          onClick={toggle}
          style={{
            all: 'unset', cursor: 'pointer', fontSize: 18, lineHeight: 1,
            color: 'var(--text-muted)',
          }}
          title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
        >
          {theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19'}
        </button>
      </header>

      {/* ── Page content ───────────────────────────────────────────── */}
      <main style={{ flex: 1, padding: '24px 24px 96px' }}>
        {children}
      </main>

      {/* ── Sticky bottom bar ──────────────────────────────────────── */}
      <footer style={{
        position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 40,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 24px', height: 52,
        background: 'var(--bg-card)',
        borderTop: '1px solid var(--border-color)',
        backdropFilter: 'blur(12px)',
      }}>
        <button
          onClick={handlePdfDownload}
          disabled={pdfLoading}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '8px 20px', borderRadius: 8, border: 'none',
            background: 'var(--accent-violet)', color: '#fff',
            fontSize: 13, fontWeight: 600, cursor: pdfLoading ? 'wait' : 'pointer',
            opacity: pdfLoading ? 0.7 : 1, transition: 'opacity 0.2s',
          }}
        >
          {pdfLoading ? 'Wird erstellt\u2026' : 'PDF Action Brief herunterladen'}
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Letzte Daten: {lastUpdate}
        </span>
      </footer>
    </div>
  );
};

export default AppLayout;
