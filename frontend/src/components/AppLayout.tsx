import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useTheme, useAuth } from '../App';
import { apiFetch } from '../lib/api';
import { UI_COPY } from '../lib/copy';

interface Props {
  children: React.ReactNode;
}

const PRIMARY_NAV_ITEMS = [
  { label: 'Jetzt', path: '/jetzt', helper: 'Die wichtigste Wochenentscheidung und der nächste Schritt', icon: 'bolt' },
  { label: 'Regionen', path: '/regionen', helper: 'Eine Region fokussiert prüfen und weiterbearbeiten', icon: 'location_on' },
  { label: 'Kampagnen', path: '/kampagnen', helper: 'Den wichtigsten Fall zuerst prüfen und freigeben', icon: 'auto_awesome' },
  { label: 'Qualität', path: '/evidenz', helper: 'Forecast, Quellen, Kundendaten und Blocker prüfen', icon: 'verified' },
] as const;

const SECTION_META = [
  {
    path: '/jetzt',
    kicker: 'PEIX Arbeitsansicht',
    title: 'Jetzt',
    description: 'Hier steht nur das, was diese Woche wirklich wichtig ist: Lage, Grund, nächster Schritt und Vertrauen.',
  },
  {
    path: '/regionen',
    kicker: 'PEIX Arbeitsansicht',
    title: 'Regionen',
    description: 'Hier prüfen wir genau eine Region nach der anderen und halten die Hauptaktion klar sichtbar.',
  },
  {
    path: '/kampagnen',
    kicker: 'PEIX Arbeitsansicht',
    title: 'Kampagnen',
    description: 'Hier landet immer zuerst der wichtigste Fall. Alles Weitere ordnet sich danach.',
  },
  {
    path: '/evidenz',
    kicker: 'Qualität',
    title: 'Qualität',
    description: 'Hier beantworten wir nur vier Fragen: Ist der Forecast stabil, sind die Daten frisch, sind Kundendaten da und gibt es Blocker?',
  },
] as const;

const AppLayout: React.FC<Props> = ({ children }) => {
  const { theme, toggle } = useTheme();
  const { handleLogout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [pdfLoading, setPdfLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isActive = (path: string) => location.pathname.startsWith(path);
  const currentSection = SECTION_META.find(({ path }) => location.pathname.startsWith(path)) || {
    kicker: 'PEIX Arbeitsansicht',
    title: 'Media Intelligence',
    description: 'Die Arbeitslage bleibt in einer kompakten PEIX-Ansicht gebündelt.',
  };
  const operatorStatusLabel = location.pathname.startsWith('/jetzt')
    ? 'Live-Lage aktiv'
    : location.pathname.startsWith('/evidenz')
      ? 'Qualität aktiv'
      : 'Arbeitsbereich aktiv';

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
    <div className="app-shell app-shell--operator">
      <div className="operator-shell">
        <button
          className={`operator-backdrop ${mobileMenuOpen ? 'operator-backdrop--visible' : ''}`}
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden={!mobileMenuOpen}
          tabIndex={mobileMenuOpen ? 0 : -1}
        />

        <aside
          id="operator-sidebar"
          className={`operator-sidebar ${mobileMenuOpen ? 'operator-sidebar--open' : ''}`}
          aria-label="Operator Navigation"
        >
          <div className="operator-sidebar__brand-row">
            <Link to="/welcome" className="operator-wordmark" aria-label="ViralFlux Startseite">
              ViralFlux
            </Link>
          </div>

          <div className="operator-sidebar__brand-block">
            <p className="operator-sidebar__brand-copy">Media Intelligence</p>
            <p className="operator-sidebar__brand-note">
              Dein Operator-Raum für klare Signale, nächste Schritte und schnelle Prüfung.
            </p>
          </div>

          <nav className="operator-nav" role="navigation" aria-label="Operator Bereiche">
            {PRIMARY_NAV_ITEMS.map(({ label, path, helper, icon }) => {
              const active = isActive(path);
              return (
                <button
                  key={path}
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
              <span className="operator-status-card__kicker">Status</span>
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
          <header className="operator-header">
            <div className="operator-header__topbar">
              <div className="operator-header__search-row">
                <button
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

                <span className="operator-header__status-pill">PEIX Arbeitsansicht</span>
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
                  type="button"
                  className="operator-icon-button"
                  aria-label="Benachrichtigungen"
                >
                  <span className="material-symbols-outlined" aria-hidden="true">notifications</span>
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
                  <span className="operator-profile-pill__copy">Operator</span>
                  <span className="material-symbols-outlined" aria-hidden="true">logout</span>
                </button>
              </div>
            </div>

            <div className="operator-header__meta">
              <div className="operator-header__copy-block">
                <div className="operator-header__kicker">{currentSection.kicker}</div>
                <div className="operator-header__title-row">
                  <span className="operator-header__status-dot" aria-hidden="true" />
                  <h1 className="operator-header__title">{currentSection.title}</h1>
                </div>
                <p className="operator-header__copy">{currentSection.description}</p>
              </div>
            </div>
          </header>

          <main className="shell-main operator-main" id="main-content">
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
