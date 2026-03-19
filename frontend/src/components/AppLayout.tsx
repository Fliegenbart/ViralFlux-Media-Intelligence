import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useTheme, useAuth } from '../App';
import { apiFetch } from '../lib/api';
import { UI_COPY } from '../lib/copy';

interface Props {
  children: React.ReactNode;
}

const PRIMARY_NAV_ITEMS = [
  { label: 'Jetzt', path: '/jetzt', helper: 'Die klare Lage und die nächste Aktion', icon: 'bolt' },
  { label: 'Regionen', path: '/regionen', helper: 'Regionale Arbeitspakete und Fokusmärkte', icon: 'location_on' },
  { label: 'Kampagnen', path: '/kampagnen', helper: 'Empfehlungen, Cluster und Assets', icon: 'auto_awesome' },
] as const;

const UTILITY_NAV_ITEMS = [
  { label: 'Qualität', path: '/evidenz', helper: 'Datenqualität, Validierung und Readiness', icon: 'analytics' },
  { label: 'Bericht', path: '/bericht', helper: 'Export und Management-Überblick', icon: 'description' },
] as const;

const SECONDARY_NAV_ITEMS = [
  { label: 'Pilotansicht', path: '/pilot', helper: 'Kundentaugliche PEIX / GELO Surface', icon: 'travel_explore' },
] as const;

const HEADER_CONTEXT_TABS = [
  { label: 'Arbeitslage', path: '/jetzt' },
  { label: 'Prüfansicht', path: '/evidenz' },
] as const;

const SECTION_META = [
  {
    path: '/jetzt',
    kicker: 'Operator Workspace',
    title: 'Jetzt entscheiden',
    description: 'Hier stehen die klare Lage, die Fokusregion und die nächste sinnvolle Aktion an erster Stelle.',
  },
  {
    path: '/pilot',
    kicker: 'Pilot Surface',
    title: 'PEIX / GELO Pilot',
    description: 'Diese Ansicht bleibt als kundentaugliche Forecast-First-Oberfläche bewusst separat.',
  },
  {
    path: '/regionen',
    kicker: 'Operator Workspace',
    title: 'Regionensteuerung',
    description: 'Hier arbeiten wir eine Region nach der anderen ab, mit klarem Grund und nächstem Schritt.',
  },
  {
    path: '/kampagnen',
    kicker: 'Operator Workspace',
    title: 'Kampagnensteuerung',
    description: 'Hier prüfen und priorisieren wir konkrete Kampagnen statt lange Listen zu verwalten.',
  },
  {
    path: '/evidenz',
    kicker: 'Qualität',
    title: 'Evidenz und Readiness',
    description: 'Hier prüfen wir bewusst erst auf der zweiten Ebene, wie belastbar Daten und Freigabe wirklich sind.',
  },
  {
    path: '/bericht',
    kicker: 'Utility',
    title: 'Wochenbericht',
    description: 'Hier liegt der exportierbare Management-Überblick zur aktuellen Arbeitslage.',
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
  const isPilotRoute = location.pathname.startsWith('/pilot');
  const currentSection = SECTION_META.find(({ path }) => location.pathname.startsWith(path)) || {
    kicker: 'Operator Workspace',
    title: 'Media Intelligence',
    description: 'Die aktuelle Arbeitslage bleibt in einem kompakten Operator-Raum gebündelt.',
  };
  const operatorStatusLabel = location.pathname.startsWith('/jetzt')
    ? 'Live-Lage aktiv'
    : location.pathname.startsWith('/evidenz')
      ? 'Prüfmodus aktiv'
      : location.pathname.startsWith('/bericht')
        ? 'Export bereit'
        : 'Arbeitsbereich aktiv';
  const operatorSearchLabel = location.pathname.startsWith('/jetzt')
    ? 'Suche in der aktuellen Lage'
    : location.pathname.startsWith('/evidenz')
      ? 'Suche in Evidenz und Readiness'
      : `Suche in ${currentSection.title}`;

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

  if (isPilotRoute) {
    return (
      <div className="app-shell app-shell--pilot">
        <header className="shell-header media-header">
          <div className="shell-header-inner">
            <Link to="/welcome" className="shell-brand" aria-label="ViralFlux Startseite">
              <span className="shell-logo-mark" aria-hidden="true">VF</span>
              <span className="shell-logo-copy">ViralFlux</span>
            </Link>

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
              {[...PRIMARY_NAV_ITEMS, ...UTILITY_NAV_ITEMS, ...SECONDARY_NAV_ITEMS].map(({ label, path }) => {
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
  }

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

          <div className="operator-sidebar__section-label">Mehr</div>
          <nav className="operator-nav operator-nav--secondary" aria-label="Weitere Bereiche">
            {[...UTILITY_NAV_ITEMS, ...SECONDARY_NAV_ITEMS].map(({ label, path, helper, icon }) => {
              const active = isActive(path);
              return (
                <button
                  key={path}
                  onClick={() => handleNavClick(path)}
                  className={`operator-nav-item ${active ? 'active' : ''} operator-nav-item--secondary`}
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

                <div className="operator-search-shell" aria-label={operatorSearchLabel}>
                  <span className="material-symbols-outlined operator-search-shell__icon" aria-hidden="true">search</span>
                  <input
                    type="search"
                    className="operator-search-shell__input"
                    placeholder={`${operatorSearchLabel}...`}
                    aria-label={operatorSearchLabel}
                  />
                </div>

                <nav className="operator-top-tabs" aria-label="Kontextnavigation">
                  {HEADER_CONTEXT_TABS.map(({ label, path }) => {
                    const active = isActive(path);
                    return (
                      <button
                        key={path}
                        type="button"
                        onClick={() => handleNavClick(path)}
                        className={`operator-top-tabs__item ${active ? 'active' : ''}`}
                        aria-current={active ? 'page' : undefined}
                      >
                        {label}
                      </button>
                    );
                  })}
                </nav>
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
