import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useTheme, useAuth } from '../App';
import { apiFetch } from '../lib/api';

interface Props {
  children: React.ReactNode;
}

type DensityMode = 'guided' | 'dense';
type PageHeaderChromeMode = 'full' | 'hidden';

export interface PageHeaderAction {
  label: string;
  onClick: () => void | Promise<void>;
  disabled?: boolean;
}

export interface PageHeaderConfig {
  chromeMode?: PageHeaderChromeMode;
  contextNote?: string;
  primaryAction?: PageHeaderAction | null;
  secondaryAction?: PageHeaderAction | null;
}

interface PageHeaderContextValue {
  setPageHeader: (config: PageHeaderConfig | null) => void;
  clearPageHeader: () => void;
  exportWeeklyReport: () => Promise<void>;
  pdfLoading: boolean;
  densityMode: DensityMode;
  setDensityMode: (mode: DensityMode) => void;
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  handleLogout: () => void;
  mobileMenuOpen: boolean;
  toggleMobileMenu: () => void;
}

const DENSITY_STORAGE_KEY = 'viralflux-density-mode';

const PRIMARY_NAV_ITEMS = [
  { label: 'Wochenplan', path: '/jetzt', helper: 'Was PEIX diese Woche zuerst tun sollte', icon: 'bolt' },
  { label: 'Zeitgraph', path: '/zeitgraph', helper: 'Nur Verlauf und 7-Tage-Ausblick', icon: 'show_chart' },
  { label: 'Regionen', path: '/regionen', helper: 'Wo sich diese Woche genaueres Hinsehen lohnt', icon: 'location_on' },
  { label: 'Kampagnen', path: '/kampagnen', helper: 'Welcher Fall als Nächstes geprüft werden sollte', icon: 'auto_awesome' },
  { label: 'Evidenz', path: '/evidenz', helper: 'Ob die Empfehlung für diese Woche trägt', icon: 'verified' },
] as const;

const SECTION_META = [
  {
    path: '/jetzt',
    kicker: 'Wochenplan',
    title: 'Was PEIX diese Woche tun sollte',
    description: 'Eine klare Wochensteuerung: zuerst die wichtigste Richtung, dann Vertrauen und nächste sinnvolle Schritte.',
    signal: 'Fokus diese Woche',
    note: 'Eine Hauptentscheidung zuerst. Details erst im zweiten Blick.',
  },
  {
    path: '/zeitgraph',
    kicker: 'Zeitgraph',
    title: 'Nur Verlauf und 7-Tage-Ausblick',
    description: 'Die Kurve bleibt bewusst allein: bestätigte Werte bis zum letzten Stand und danach die vermutete Fortführung für die nächsten sieben Tage.',
    signal: 'Verlauf + Forecast',
    note: 'Ein reduzierter Blick nur auf die Kurve.',
  },
  {
    path: '/regionen',
    kicker: 'Regionen',
    title: 'Wo diese Woche genauer hingesehen werden sollte',
    description: 'Bundesländer werden vergleichbar, damit PEIX schneller sieht, wo Fokus sinnvoll ist und wo noch Zurückhaltung gilt.',
    signal: 'Bundesland-Fokus',
    note: 'Die Karte unterstützt die Entscheidung, sie ersetzt sie nicht.',
  },
  {
    path: '/kampagnen',
    kicker: 'Kampagnen',
    title: 'Welcher Fall als Nächstes geprüft werden sollte',
    description: 'Die Freigabe-Pipeline startet mit genau einem Fokusfall und hält die nächsten Fälle bewusst dahinter.',
    signal: 'Prüfen & Freigeben',
    note: 'Erst der Fokusfall, dann die restliche Pipeline.',
  },
  {
    path: '/evidenz',
    kicker: 'Evidenz',
    title: 'Ob die Empfehlung für diese Woche trägt',
    description: 'Die Evidenzansicht trennt sauber zwischen belastbar, noch offen und nur mit Vorsicht lesbar.',
    signal: 'Belastbarkeit',
    note: 'GELO sichtbar halten, ohne Scheinsicherheit zu erzeugen.',
  },
] as const;

const PageHeaderContext = createContext<PageHeaderContextValue>({
  setPageHeader: () => {},
  clearPageHeader: () => {},
  exportWeeklyReport: async () => {},
  pdfLoading: false,
  densityMode: 'guided',
  setDensityMode: () => {},
  theme: 'light',
  toggleTheme: () => {},
  handleLogout: () => {},
  mobileMenuOpen: false,
  toggleMobileMenu: () => {},
});

export const usePageHeader = () => useContext(PageHeaderContext);

interface PageChromeMobileToggleProps {
  buttonRef?: React.RefObject<HTMLButtonElement>;
}

export const PageChromeMobileToggle: React.FC<PageChromeMobileToggleProps> = ({ buttonRef }) => {
  const { mobileMenuOpen, toggleMobileMenu } = usePageHeader();

  return (
    <button
      ref={buttonRef}
      type="button"
      className="shell-mobile-toggle operator-mobile-toggle"
      onClick={toggleMobileMenu}
      aria-label={mobileMenuOpen ? 'Navigation schließen' : 'Navigation öffnen'}
      aria-expanded={mobileMenuOpen}
      aria-controls="operator-sidebar"
    >
      <span style={{ fontSize: 20, lineHeight: 1 }}>
        {mobileMenuOpen ? '\u2715' : '\u2630'}
      </span>
    </button>
  );
};

export const PageChromeUtilityMenu: React.FC = () => {
  const {
    densityMode,
    setDensityMode,
    theme,
    toggleTheme,
    handleLogout,
  } = usePageHeader();
  const location = useLocation();
  const [utilityMenuOpen, setUtilityMenuOpen] = useState(false);
  const utilityMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!utilityMenuOpen) {
      return undefined;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!utilityMenuRef.current?.contains(event.target as Node)) {
        setUtilityMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setUtilityMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [utilityMenuOpen]);

  useEffect(() => {
    setUtilityMenuOpen(false);
  }, [location.pathname]);

  return (
    <div className="operator-utility" ref={utilityMenuRef}>
      <button
        type="button"
        className="operator-utility-toggle"
        aria-label={utilityMenuOpen ? 'Schnellmenü schließen' : 'Schnellmenü öffnen'}
        aria-haspopup="menu"
        aria-expanded={utilityMenuOpen}
        onClick={() => setUtilityMenuOpen((open) => !open)}
      >
        <span className="material-symbols-outlined" aria-hidden="true">tune</span>
      </button>

      {utilityMenuOpen ? (
        <div className="operator-utility-panel" role="menu" aria-label="Schnellmenü">
          <div className="operator-utility-panel__section">
            <span className="operator-utility-panel__label">Ansicht</span>
            <div className="operator-density-toggle" role="group" aria-label="Ansichtsmodus">
              <button
                type="button"
                className={`operator-density-toggle__button ${densityMode === 'guided' ? 'active' : ''}`}
                aria-pressed={densityMode === 'guided'}
                onClick={() => setDensityMode('guided')}
              >
                Guided
              </button>
              <button
                type="button"
                className={`operator-density-toggle__button ${densityMode === 'dense' ? 'active' : ''}`}
                aria-pressed={densityMode === 'dense'}
                onClick={() => setDensityMode('dense')}
              >
                Dense
              </button>
            </div>
          </div>

          <div className="operator-utility-panel__section">
            <button
              type="button"
              role="menuitem"
              className="operator-utility-item"
              onClick={() => {
                toggleTheme();
                setUtilityMenuOpen(false);
              }}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                {theme === 'dark' ? 'light_mode' : 'dark_mode'}
              </span>
              <span>{theme === 'dark' ? 'Helles Design aktivieren' : 'Dunkles Design aktivieren'}</span>
            </button>
            <button
              type="button"
              role="menuitem"
              className="operator-utility-item"
              onClick={() => {
                handleLogout();
                setUtilityMenuOpen(false);
              }}
            >
              <span className="material-symbols-outlined" aria-hidden="true">logout</span>
              <span>Abmelden</span>
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
};

const AppLayout: React.FC<Props> = ({ children }) => {
  const { theme, toggle } = useTheme();
  const { handleLogout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [pdfLoading, setPdfLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [pageHeader, setPageHeaderState] = useState<PageHeaderConfig | null>(null);
  const [densityMode, setDensityMode] = useState<DensityMode>(() => {
    if (typeof window === 'undefined') {
      return 'guided';
    }
    return window.localStorage.getItem(DENSITY_STORAGE_KEY) === 'dense' ? 'dense' : 'guided';
  });
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const firstNavItemRef = useRef<HTMLButtonElement>(null);

  const isActive = (path: string) => location.pathname.startsWith(path);
  const currentSection = SECTION_META.find(({ path }) => location.pathname.startsWith(path)) || {
    kicker: 'Arbeitsbereich',
    title: 'Arbeitsansicht',
    description: 'Hier bleibt der aktuelle Stand an einem Ort.',
    signal: 'PEIX x GELO',
    note: 'Gilt auf Bundesland-Ebene, nicht für einzelne Städte.',
  };

  const handlePdfDownload = useCallback(async () => {
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
  }, []);

  const setPageHeader = useCallback((config: PageHeaderConfig | null) => {
    setPageHeaderState(config);
  }, []);

  const clearPageHeader = useCallback(() => {
    setPageHeaderState(null);
  }, []);

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

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(DENSITY_STORAGE_KEY, densityMode);
    }
  }, [densityMode]);

  const pageHeaderContext = useMemo<PageHeaderContextValue>(() => ({
    setPageHeader,
    clearPageHeader,
    exportWeeklyReport: handlePdfDownload,
    pdfLoading,
    densityMode,
    setDensityMode,
    theme,
    toggleTheme: toggle,
    handleLogout,
    mobileMenuOpen,
    toggleMobileMenu: () => setMobileMenuOpen((open) => !open),
  }), [clearPageHeader, densityMode, handleLogout, handlePdfDownload, mobileMenuOpen, pdfLoading, setPageHeader, theme, toggle]);

  const chromeMode = pageHeader?.chromeMode || 'full';
  const showHeader = chromeMode !== 'hidden';

  const renderPageAction = (
    action: PageHeaderAction | null | undefined,
    variant: 'primary' | 'secondary',
  ) => {
    if (!action) return null;

    return (
      <button
        type="button"
        className={`operator-page-action operator-page-action--${variant}`}
        onClick={action.onClick}
        disabled={action.disabled}
      >
        {action.label}
      </button>
    );
  };

  return (
    <PageHeaderContext.Provider value={pageHeaderContext}>
      <div className="app-shell app-shell--operator" data-density={densityMode}>
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
                  <span className="operator-brand-lockup__subline">Wochensteuerung</span>
                </span>
              </Link>
            </div>

            <div className="operator-sidebar__brand-block">
              <p className="operator-sidebar__brand-copy">PEIX x GELO</p>
              <p className="operator-sidebar__brand-note">Bundesland-Ebene, nicht Stadt-Ebene.</p>
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
                    <span className="operator-nav-item__headline">
                      <span className="material-symbols-outlined operator-nav-item__icon" aria-hidden="true">{icon}</span>
                      <span className="operator-nav-item__label">{label}</span>
                    </span>
                    <span className="operator-nav-item__helper">{helper}</span>
                  </button>
                );
              })}
            </nav>

            <div className="operator-sidebar__rail">
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
            {showHeader ? (
              <header className="operator-header surface-header">
                <div className="operator-header__topbar">
                  <div className="operator-header__context">
                    <div className="operator-header__search-row">
                      <PageChromeMobileToggle buttonRef={mobileToggleRef} />

                      <div className="operator-header__suite-group">
                        <span className="operator-header__suite">ViralFlux</span>
                        <span className="operator-header__suite-separator" aria-hidden="true">/</span>
                        <span className="operator-header__section-context">{currentSection.kicker}</span>
                      </div>
                    </div>

                    <div className="operator-header__hero-meta">
                      <span className="operator-header__signal operator-header__signal--go">
                        {currentSection.signal}
                      </span>
                    </div>

                    <div className="operator-header__copy-block">
                      <h1 id="operator-page-title" className="operator-header__title">{currentSection.title}</h1>
                      <p className="operator-header__copy">{currentSection.description}</p>
                      <div className="operator-header__summary-line">
                        <span>{pageHeader?.contextNote || currentSection.note}</span>
                        <span>Gilt auf Bundesland-Ebene</span>
                      </div>
                    </div>
                  </div>

                  <div className="operator-header__actions">
                    <div className="operator-page-actions" aria-label="Seitenaktionen">
                      {renderPageAction(pageHeader?.secondaryAction, 'secondary')}
                      {renderPageAction(pageHeader?.primaryAction, 'primary')}
                    </div>
                    <PageChromeUtilityMenu />
                  </div>
                </div>
              </header>
            ) : null}

            <main
              className="shell-main operator-main"
              id="main-content"
              tabIndex={-1}
              aria-labelledby={showHeader ? 'operator-page-title' : undefined}
              aria-label={showHeader ? undefined : currentSection.title}
            >
              <div className="shell-main-inner operator-main-inner">
                {children}
              </div>
            </main>
          </div>
        </div>
      </div>
    </PageHeaderContext.Provider>
  );
};

export default AppLayout;
