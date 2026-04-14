import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useLocation, Link } from 'react-router-dom';
import { useTheme, useAuth } from '../App';
import { apiFetch } from '../lib/api';
import {
  Activity,
  Zap,
  TrendingUp,
  MapPin,
  Sparkles,
  ShieldCheck,
  MoreHorizontal,
  Sun,
  Moon,
  LogOut,
} from 'lucide-react';

interface Props {
  children: React.ReactNode;
}

export interface PageHeaderAction {
  label: string;
  onClick?: () => void | Promise<void>;
  to?: string;
  href?: string;
  disabled?: boolean;
}

export interface PageHeaderConfig {
  primaryAction?: PageHeaderAction | null;
  secondaryAction?: PageHeaderAction | null;
}

interface PageHeaderContextValue {
  setPageHeader: (config: PageHeaderConfig | null) => void;
  clearPageHeader: () => void;
  exportBriefingPdf: () => Promise<void>;
  pdfLoading: boolean;
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  handleLogout: () => void;
  mobileMenuOpen: boolean;
  toggleMobileMenu: () => void;
}

const ICON_SIZE = 18;

const PRIMARY_NAV_ITEMS = [
  { label: 'Virus-Radar', path: '/virus-radar', helper: 'Alles für die Media-Entscheidung auf einer Seite', Icon: Activity },
  { label: 'Diese Woche', path: '/jetzt', helper: 'Die aktuelle Wochenentscheidung im Detail', Icon: Zap },
  { label: 'Zeitgraph', path: '/zeitgraph', helper: 'Nur Verlauf und 7-Tage-Ausblick', Icon: TrendingUp },
  { label: 'Regionen', path: '/regionen', helper: 'Wo sich diese Woche genaueres Hinsehen lohnt', Icon: MapPin },
  { label: 'Kampagnen', path: '/kampagnen', helper: 'Welcher Fall als Nächstes geprüft werden sollte', Icon: Sparkles },
  { label: 'Evidenz', path: '/evidenz', helper: 'Ob die Empfehlung für diese Woche trägt', Icon: ShieldCheck },
] as const;

const SECTION_META = [
  { path: '/virus-radar', kicker: 'Virus-Radar', title: 'Die zentrale Media-Entscheidungsseite' },
  { path: '/jetzt', kicker: 'Diese Woche', title: 'Die aktuelle Wochenentscheidung im Detail' },
  { path: '/zeitgraph', kicker: 'Zeitgraph', title: 'Nur Verlauf und 7-Tage-Ausblick' },
  { path: '/regionen', kicker: 'Regionen', title: 'Wo diese Woche genauer hingesehen werden sollte' },
  { path: '/kampagnen', kicker: 'Kampagnen', title: 'Welcher Fall als Nächstes geprüft werden sollte' },
  { path: '/evidenz', kicker: 'Evidenz', title: 'Ob die Empfehlung für diese Woche trägt' },
] as const;

const PageHeaderContext = createContext<PageHeaderContextValue>({
  setPageHeader: () => {},
  clearPageHeader: () => {},
  exportBriefingPdf: async () => {},
  pdfLoading: false,
  theme: 'light',
  toggleTheme: () => {},
  handleLogout: () => {},
  mobileMenuOpen: false,
  toggleMobileMenu: () => {},
});

export const usePageHeader = () => useContext(PageHeaderContext);

interface PageChromeMobileToggleProps {
  buttonRef?: React.RefObject<HTMLButtonElement | null>;
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
        <MoreHorizontal size={ICON_SIZE} aria-hidden="true" />
      </button>

      {utilityMenuOpen ? (
        <div className="operator-utility-panel" role="menu" aria-label="Schnellmenü">
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
              {theme === 'dark' ? <Sun size={ICON_SIZE} aria-hidden="true" /> : <Moon size={ICON_SIZE} aria-hidden="true" />}
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
              <LogOut size={ICON_SIZE} aria-hidden="true" />
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
  const [pdfLoading, setPdfLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [pageHeader, setPageHeaderState] = useState<PageHeaderConfig | null>(null);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const firstNavItemRef = useRef<HTMLAnchorElement>(null);

  const isActive = (path: string) => location.pathname.startsWith(path);
  const currentSection = SECTION_META.find(({ path }) => location.pathname.startsWith(path)) || {
    kicker: 'Arbeitsbereich',
    title: 'Arbeitsansicht',
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
      a.download = 'ViralFlux_Wochenbericht.pdf';
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

  const pageHeaderContext = useMemo<PageHeaderContextValue>(() => ({
    setPageHeader,
    clearPageHeader,
    exportBriefingPdf: handlePdfDownload,
    pdfLoading,
    theme,
    toggleTheme: toggle,
    handleLogout,
    mobileMenuOpen,
    toggleMobileMenu: () => setMobileMenuOpen((open) => !open),
  }), [clearPageHeader, handleLogout, handlePdfDownload, mobileMenuOpen, pdfLoading, setPageHeader, theme, toggle]);

  const renderPageAction = (
    action: PageHeaderAction | null | undefined,
    variant: 'primary' | 'secondary',
  ) => {
    if (!action) return null;

    const className = `operator-page-action operator-page-action--${variant}`;

    if (action.disabled && (action.to || action.href)) {
      return (
        <button type="button" className={className} disabled>
          {action.label}
        </button>
      );
    }

    if (action.to) {
      return (
        <Link
          to={action.to}
          className={className}
          onClick={action.onClick}
        >
          {action.label}
        </Link>
      );
    }

    if (action.href) {
      return (
        <a
          href={action.href}
          className={className}
          onClick={action.onClick}
        >
          {action.label}
        </a>
      );
    }

    return (
      <button
        type="button"
        className={className}
        onClick={action.onClick}
        disabled={action.disabled}
      >
        {action.label}
      </button>
    );
  };

  const hasPageActions = Boolean(pageHeader?.secondaryAction || pageHeader?.primaryAction);

  return (
    <PageHeaderContext.Provider value={pageHeaderContext}>
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
                </span>
              </Link>
            </div>

            <nav className="operator-nav" role="navigation" aria-label="Arbeitsbereiche">
              {PRIMARY_NAV_ITEMS.map(({ label, path, helper, Icon }) => {
                const active = isActive(path);
                return (
                  <Link
                    key={path}
                    ref={path === PRIMARY_NAV_ITEMS[0].path ? firstNavItemRef : undefined}
                    to={path}
                    onClick={() => setMobileMenuOpen(false)}
                    className={`operator-nav-item ${active ? 'active' : ''}`}
                    aria-current={active ? 'page' : undefined}
                    title={helper}
                  >
                    <span className="operator-nav-item__headline">
                      <Icon size={ICON_SIZE} className="operator-nav-item__icon" aria-hidden="true" />
                      <span className="operator-nav-item__label">{label}</span>
                    </span>
                  </Link>
                );
              })}
            </nav>

          </aside>

          <div className="operator-stage">
              <header className="operator-header operator-header--slim">
                <div className="operator-header__topbar">
                  <div className="operator-header__search-row">
                    <PageChromeMobileToggle buttonRef={mobileToggleRef} />

                    <div className="operator-header__section-frame" aria-label="Aktueller Bereich">
                      <div className="operator-header__section-meta">
                        <span className="operator-header__suite">ViralFlux</span>
                        <span className="operator-header__suite-separator" aria-hidden="true">/</span>
                        <span className="operator-header__section-context">{currentSection.kicker}</span>
                      </div>
                      <h1 id="operator-page-title" className="operator-header__section-title">{currentSection.title}</h1>
                    </div>
                  </div>

                  <div className="operator-header__actions">
                    {hasPageActions ? (
                      <div className="operator-page-actions" aria-label="Seitenaktionen">
                        {renderPageAction(pageHeader?.secondaryAction, 'secondary')}
                        {renderPageAction(pageHeader?.primaryAction, 'primary')}
                      </div>
                    ) : null}
                    <PageChromeUtilityMenu />
                  </div>
                </div>
              </header>

            <main
              className="shell-main operator-main"
              id="main-content"
              tabIndex={-1}
              aria-labelledby="operator-page-title"
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
