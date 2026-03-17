import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useTheme, useAuth } from '../App';
import { apiFetch } from '../lib/api';
import { UI_COPY } from '../lib/copy';

interface Props {
  children: React.ReactNode;
}

const NAV_ITEMS = [
  { label: 'Dashboard', path: '/dashboard' },
  { label: 'Entscheidung', path: '/entscheidung' },
  { label: 'Regionen', path: '/regionen' },
  { label: 'Kampagnen', path: '/kampagnen' },
  { label: 'Evidenz', path: '/evidenz' },
] as const;

const AppLayout: React.FC<Props> = ({ children }) => {
  const { theme, toggle } = useTheme();
  const { handleLogout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [pdfLoading, setPdfLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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
      a.download = 'ViralFlux_Wochenbericht.pdf';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('PDF download failed', e);
    } finally {
      setPdfLoading(false);
    }
  };

  const handleNavClick = (path: string) => {
    navigate(path);
    setMobileMenuOpen(false);
  };

  return (
    <div className="app-shell">
      <header className="shell-header media-header">
        <div className="shell-header-inner">
          <Link to="/welcome" className="shell-brand" aria-label="ViralFlux Startseite">
            <span className="shell-logo-mark" aria-hidden="true">VF</span>
            <span className="shell-logo-copy">ViralFlux</span>
          </Link>

          {/* Mobile hamburger */}
          <button
            className="shell-mobile-toggle"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label={mobileMenuOpen ? 'Navigation schließen' : 'Navigation öffnen'}
            aria-expanded={mobileMenuOpen}
            aria-controls="shell-nav-menu"
          >
            <span style={{ fontSize: 20, lineHeight: 1 }}>
              {mobileMenuOpen ? '\u2715' : '\u2630'}
            </span>
          </button>

          <nav
            id="shell-nav-menu"
            className={`shell-nav ${mobileMenuOpen ? 'shell-nav--open' : ''}`}
            role="navigation"
            aria-label="Hauptnavigation"
          >
            {NAV_ITEMS.map(({ label, path }) => {
              const active = isActive(path);
              return (
                <button
                  key={path}
                  onClick={() => handleNavClick(path)}
                  className={`shell-nav-item ${active ? 'active' : ''}`}
                  aria-current={active ? 'page' : undefined}
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
            aria-label={theme === 'dark' ? 'Helles Design aktivieren' : 'Dunkles Design aktivieren'}
          >
            {theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19'}
          </button>

          <button
            onClick={handleLogout}
            className="theme-toggle"
            aria-label="Abmelden"
            title="Abmelden"
            style={{ marginLeft: 4 }}
          >
            {'\u23FB'}
          </button>
        </div>
      </header>

      <main className="shell-main" id="main-content">
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
            aria-busy={pdfLoading}
          >
            {pdfLoading ? 'Wird erstellt\u2026' : `${UI_COPY.weeklyReport} herunterladen`}
          </button>
          <span className="shell-footer-note">
            Datenstand ist je Ansicht direkt sichtbar
          </span>
        </div>
      </footer>
    </div>
  );
};

export default AppLayout;
