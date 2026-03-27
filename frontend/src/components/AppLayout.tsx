import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useTheme, useAuth } from '../App';
import { apiFetch } from '../lib/api';
import { UI_COPY } from '../lib/copy';

interface Props {
  children: React.ReactNode;
}

const PRIMARY_NAV_ITEMS = [
  { label: 'Wochenplan', path: '/jetzt', helper: 'Was PEIX und GELO diese Woche tun sollten', icon: 'bolt' },
  { label: 'Regionen', path: '/regionen', helper: 'Welche Region zuerst wichtig ist', icon: 'location_on' },
  { label: 'Kampagnen', path: '/kampagnen', helper: 'Welcher Fall als Nächstes dran ist', icon: 'auto_awesome' },
  { label: 'Evidenz', path: '/evidenz', helper: 'Was noch geprüft werden muss', icon: 'verified' },
] as const;

const SECTION_META = [
  {
    path: '/jetzt',
    kicker: 'PEIX x GELO',
    title: 'Wochenplan',
    description: 'Was PEIX und GELO diese Woche tun sollten, wo zuerst, und warum.',
  },
  {
    path: '/regionen',
    kicker: 'Regionen',
    title: 'Bundesländer',
    description: 'Hier siehst du, welches Bundesland als Nächstes wichtig wird.',
  },
  {
    path: '/kampagnen',
    kicker: 'Maßnahmen',
    title: 'Kampagnen',
    description: 'Hier prüfst du die nächste sinnvolle GELO-Maßnahme.',
  },
  {
    path: '/evidenz',
    kicker: 'Evidenz',
    title: 'Evidenz',
    description: 'Hier siehst du, was die Wochenentscheidung trägt oder noch bremst.',
  },
] as const;

const AppLayout: React.FC<Props> = ({ children }) => {
  const { theme, toggle } = useTheme();
  const { handleLogout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [pdfLoading, setPdfLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const firstNavItemRef = useRef<HTMLButtonElement>(null);

  const isActive = (path: string) => location.pathname.startsWith(path);
  const currentSection = SECTION_META.find(({ path }) => location.pathname.startsWith(path)) || {
    kicker: 'Arbeitsbereich',
    title: 'Arbeitsansicht',
    description: 'Hier bleibt dein aktueller Arbeitsstand an einem Ort.',
  };
  const operatorStatusLabel = location.pathname.startsWith('/jetzt')
    ? 'GELO Wochenplan aktiv'
    : location.pathname.startsWith('/evidenz')
      ? 'Evidenz im Blick'
      : 'Pilotbereich aktiv';

  const handlePdfDownload = async () => {
    setPdfLoading(true);
    try {
      await apiFetch('/api/v1/media/weekly-brief/generate', { method: 'POST' });
      const res = await apiFetch('/api/v1/media/weekly-brief/latest');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'PEIX_GELO_Wochenbericht.pdf';
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

  useEffect(() => {
    if (!mobileMenuOpen) {
      mobileToggleRef.current?.focus();
      return undefined;
    }

    firstNavItemRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileMenuOpen(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [mobileMenuOpen]);

  return (
    <div className="app-shell app-shell--operator">
      <a href="#main-content" className="skip-link">Direkt zum Inhalt springen</a>
      <div className="operator-shell">
        <button
          type="button"
          className={`operator-backdrop ${mobileMenuOpen ? 'operator-backdrop--visible' : ''}`}
          onClick={() => setMobileMenuOpen(false)}
          aria-label="Navigationshintergrund schließen"
          aria-hidden={!mobileMenuOpen}
          tabIndex={mobileMenuOpen ? 0 : -1}
        />

        <aside
          id="operator-sidebar"
          className={`operator-sidebar ${mobileMenuOpen ? 'operator-sidebar--open' : ''}`}
          aria-label="Navigation Arbeitsansicht"
        >
          <div className="operator-sidebar__brand-row">
            <Link to="/welcome" className="operator-brand-lockup product-brand-lockup" aria-label="ViralFlux Startseite">
              <span className="operator-brand-lockup__mark product-brand-mark" aria-hidden="true">VF</span>
              <span className="operator-brand-lockup__copy product-brand-copy">
                <span className="operator-brand-lockup__wordmark">ViralFlux</span>
                <span className="operator-brand-lockup__subline">Media Intelligence</span>
              </span>
            </Link>
          </div>

          <div className="operator-sidebar__brand-block">
            <p className="operator-sidebar__brand-copy">PEIX x GELO Pilot</p>
            <p className="operator-sidebar__brand-note">
              Wöchentliche Media-Entscheidungen auf Bundesland-Level.
            </p>
          </div>

          <nav className="operator-nav" role="navigation" aria-label="Arbeitsbereiche">
            {PRIMARY_NAV_ITEMS.map(({ label, path, helper, icon }) => {
              const active = isActive(path);
              return (
                <button
                  key={path}
                  ref={path === PRIMARY_NAV_ITEMS[0].path ? firstNavItemRef : undefined}
                  type="button"
                  onClick={() => handleNavClick(path)}
                  className={`operator-nav-item ${active ? 'active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                  title={helper}
                >
                  <span className="material-symbols-outlined operator-nav-item__icon" aria-hidden="true">{icon}</span>
                  <span className="operator-nav-item__label">{label}</span>
                </button>
              );
            })}
          </nav>

          <div className="operator-sidebar__rail">
            <section className="operator-status-card">
              <span className="operator-status-card__kicker">Pilotstatus</span>
              <strong>{operatorStatusLabel}</strong>
              <p>{currentSection.title}</p>
              <button
                onClick={handlePdfDownload}
                disabled={pdfLoading}
                className="operator-status-card__button"
                aria-busy={pdfLoading}
              >
                {pdfLoading ? 'Wird erstellt...' : 'Bericht exportieren'}
              </button>
            </section>

            <div className="operator-sidebar__footer-links">
              <button
                type="button"
                className="operator-sidebar-link"
                onClick={() => handleNavClick('/welcome')}
              >
                <span className="material-symbols-outlined" aria-hidden="true">home</span>
                <span>Startseite</span>
              </button>
              <button
                type="button"
                className="operator-sidebar-link"
                onClick={handleLogout}
              >
                <span className="material-symbols-outlined" aria-hidden="true">logout</span>
                <span>Abmelden</span>
              </button>
            </div>
          </div>
        </aside>

        <div className="operator-stage">
          <header className="operator-header surface-header">
            <div className="operator-header__topbar">
              <div className="operator-header__context">
                <div className="operator-header__search-row">
                  <button
                    ref={mobileToggleRef}
                    type="button"
                    className="shell-mobile-toggle operator-mobile-toggle"
                    onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                    aria-label={mobileMenuOpen ? 'Navigation schließen' : 'Navigation öffnen'}
                    aria-expanded={mobileMenuOpen}
                    aria-controls="operator-sidebar"
                  >
                    <span style={{ fontSize: 20, lineHeight: 1 }}>
                      {mobileMenuOpen ? '\u2715' : '\u2630'}
                    </span>
                  </button>

                  <span className="operator-header__suite">ViralFlux</span>
                </div>
              </div>

              <div className="operator-header__actions">
                <button
                  onClick={handlePdfDownload}
                  disabled={pdfLoading}
                  className="operator-header__primary"
                  aria-busy={pdfLoading}
                >
                  {pdfLoading ? 'Wird erstellt...' : UI_COPY.weeklyReport}
                </button>
                <button
                  onClick={toggle}
                  className="operator-icon-button"
                  aria-label={theme === 'dark' ? 'Helles Design aktivieren' : 'Dunkles Design aktivieren'}
                >
                  <span className="material-symbols-outlined" aria-hidden="true">
                    {theme === 'dark' ? 'light_mode' : 'dark_mode'}
                  </span>
                </button>
                <button
                  onClick={handleLogout}
                  className="operator-profile-pill"
                  aria-label="Abmelden"
                  title="Abmelden"
                >
                  <span className="operator-avatar" aria-hidden="true">VF</span>
                  <span className="operator-profile-pill__copy">PEIX</span>
                  <span className="material-symbols-outlined" aria-hidden="true">logout</span>
                </button>
              </div>
            </div>

            <div className="operator-header__meta">
              <span className="operator-header__status-pill">{currentSection.kicker}</span>
              <div className="operator-header__copy-block">
                <div className="operator-header__kicker">{currentSection.kicker}</div>
                <div className="operator-header__title-row">
                  <span className="operator-header__status-dot" aria-hidden="true" />
                  <h1 id="operator-page-title" className="operator-header__title">{currentSection.title}</h1>
                </div>
                <p className="operator-header__copy">{currentSection.description}</p>
              </div>
            </div>
          </header>

          <main className="shell-main operator-main" id="main-content" tabIndex={-1} aria-labelledby="operator-page-title">
            <div className="shell-main-inner operator-main-inner">
              {children}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
};

export default AppLayout;
