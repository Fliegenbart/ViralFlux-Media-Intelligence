import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
// Link used in logo below
import { useTheme } from '../App';
import { apiFetch } from '../lib/api';

interface Props {
  children: React.ReactNode;
}

const NAV_ITEMS = [
  { label: 'Entscheidung', path: '/entscheidung' },
  { label: 'Regionen', path: '/regionen' },
  { label: 'Kampagnen', path: '/kampagnen' },
  { label: 'Evidenz', path: '/evidenz' },
] as const;

const AppLayout: React.FC<Props> = ({ children }) => {
  const { theme, toggle } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [pdfLoading, setPdfLoading] = useState(false);

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
    <div className="app-shell">
      <header className="shell-header media-header">
        <div className="shell-header-inner">
          <Link to="/welcome" className="shell-brand">
            <span className="shell-logo-mark">VF</span>
            <span className="shell-logo-copy">ViralFlux</span>
          </Link>

          <nav className="shell-nav">
            {NAV_ITEMS.map(({ label, path }) => {
              const active = isActive(path);
              return (
                <button
                  key={path}
                  onClick={() => navigate(path)}
                  className={`shell-nav-item ${active ? 'active' : ''}`}
                >
                  {label}
                </button>
              );
            })}
          </nav>

          <div className="shell-header-spacer" />

          <button
            onClick={toggle}
            className="theme-toggle"
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
          >
            {theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19'}
          </button>
        </div>
      </header>

      <main className="shell-main">
        <div className="shell-main-inner">
          {children}
        </div>
      </main>

      <footer className="shell-footer">
        <div className="shell-footer-inner">
          <button
            onClick={handlePdfDownload}
            disabled={pdfLoading}
            className="media-button shell-footer-button"
          >
            {pdfLoading ? 'Wird erstellt\u2026' : 'PDF Action Brief herunterladen'}
          </button>
          <span className="shell-footer-note">
            Datenstand wird je Ansicht direkt ausgewiesen
          </span>
        </div>
      </footer>
    </div>
  );
};

export default AppLayout;
