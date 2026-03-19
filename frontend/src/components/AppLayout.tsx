import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useTheme, useAuth } from '../App';
import { apiFetch } from '../lib/api';
import { UI_COPY } from '../lib/copy';

interface Props {
  children: React.ReactNode;
}

const PRIMARY_NAV_ITEMS = [
  { label: 'Jetzt', path: '/jetzt', helper: 'Die klare Lage und die nächste Aktion' },
  { label: 'Regionen', path: '/regionen', helper: 'Regionale Arbeitspakete und Fokusmärkte' },
  { label: 'Kampagnen', path: '/kampagnen', helper: 'Empfehlungen, Cluster und Assets' },
] as const;

const UTILITY_NAV_ITEMS = [
  { label: 'Qualität', path: '/evidenz', helper: 'Datenqualität, Validierung und Readiness' },
  { label: 'Bericht', path: '/bericht', helper: 'Export und Management-Überblick' },
] as const;

const SECONDARY_NAV_ITEMS = [
  { label: 'Pilotansicht', path: '/pilot', helper: 'Kundentaugliche PEIX / GELO Surface' },
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
            <div className="operator-sidebar__brand-block">
              <Link to="/welcome" className="shell-brand operator-shell-brand" aria-label="ViralFlux Startseite">
                <span className="shell-logo-mark" aria-hidden="true">VF</span>
                <span className="shell-logo-copy">ViralFlux</span>
              </Link>
              <p className="operator-sidebar__brand-copy">Media Intelligence Curator</p>
            </div>
          </div>

          <div className="operator-sidebar__section-label">Arbeitsbereich</div>
          <nav className="operator-nav" role="navigation" aria-label="Operator Bereiche">
            {PRIMARY_NAV_ITEMS.map(({ label, path, helper }) => {
              const active = isActive(path);
              return (
                <button
                  key={path}
                  onClick={() => handleNavClick(path)}
                  className={`operator-nav-item ${active ? 'active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                >
                  <span className="operator-nav-item__label">{label}</span>
                  <span className="operator-nav-item__helper">{helper}</span>
                </button>
              );
            })}
          </nav>

          <div className="operator-sidebar__section-label">Hilfen</div>
          <div className="operator-nav operator-nav--secondary">
            {UTILITY_NAV_ITEMS.map(({ label, path, helper }) => {
              const active = isActive(path);
              return (
                <button
                  key={path}
                  onClick={() => handleNavClick(path)}
                  className={`operator-nav-item operator-nav-item--secondary ${active ? 'active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                >
                  <span className="operator-nav-item__label">{label}</span>
                  <span className="operator-nav-item__helper">{helper}</span>
                </button>
              );
            })}
          </div>

          <div className="operator-sidebar__section-label">Kundensicht</div>
          <div className="operator-nav operator-nav--secondary">
            {SECONDARY_NAV_ITEMS.map(({ label, path, helper }) => {
              const active = isActive(path);
              return (
                <button
                  key={path}
                  onClick={() => handleNavClick(path)}
                  className={`operator-nav-item operator-nav-item--secondary ${active ? 'active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                >
                  <span className="operator-nav-item__label">{label}</span>
                  <span className="operator-nav-item__helper">{helper}</span>
                </button>
              );
            })}
          </div>

          <div className="operator-sidebar__rail">
            <section className="operator-rail-card">
              <span className="operator-rail-card__kicker">{currentSection.kicker}</span>
              <strong>{currentSection.title}</strong>
              <p>{currentSection.description}</p>
            </section>

            <section className="operator-rail-card operator-rail-card--muted">
              <span className="operator-rail-card__kicker">Export</span>
              <button
                onClick={handlePdfDownload}
                disabled={pdfLoading}
                className="media-button operator-report-button"
                aria-busy={pdfLoading}
              >
                {pdfLoading ? 'Wird erstellt\u2026' : `${UI_COPY.weeklyReport} herunterladen`}
              </button>
              <p>Der Export zieht die aktuelle Lage in einen managementfähigen PDF-Stand.</p>
            </section>
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
                  <span className="operator-search-shell__icon" aria-hidden="true">⌕</span>
                  <span className="operator-search-shell__text">{operatorSearchLabel}</span>
                </div>
              </div>

              <div className="operator-header__actions">
                <span className="operator-header__status-pill">{operatorStatusLabel}</span>
                <button
                  onClick={() => handleNavClick('/pilot')}
                  className="operator-header__link"
                >
                  Zur Pilotansicht
                </button>
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
                >
                  {'\u23FB'}
                </button>
              </div>
            </div>

            <div className="operator-header__meta">
              <button
                type="button"
                className="operator-header__status-dot"
                aria-hidden="true"
              />
              <div className="operator-header__copy-block">
                <div className="operator-header__kicker">{currentSection.kicker}</div>
                <div className="operator-header__title-row">
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
