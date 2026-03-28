import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useTheme, useAuth } from '../App';
import { apiFetch } from '../lib/api';
import { usePilotSurfaceData } from '../features/media/usePilotSurfaceData';
import { useMediaWorkflow } from '../features/media/workflowContext';
import { PilotReadoutResponse, PilotReadoutStatus, PilotReadoutRegion, StructuredReasonItem } from '../types/media';
import { formatDateTime } from './cockpit/cockpitUtils';
import { explainInPlainGerman } from '../lib/plainLanguage';

interface Props {
  children: React.ReactNode;
}

const PRIMARY_NAV_ITEMS = [
  { label: 'Wochenplan', path: '/jetzt', helper: 'Die operative Hauptentscheidung für diese Woche', icon: 'bolt' },
  { label: 'Regionen', path: '/regionen', helper: 'Welche Bundesländer gerade vorne liegen', icon: 'location_on' },
  { label: 'Kampagnen', path: '/kampagnen', helper: 'Welcher Vorschlag als Nächstes geprüft werden sollte', icon: 'auto_awesome' },
  { label: 'Evidenz', path: '/evidenz', helper: 'Was schon belegt ist und was noch fehlt', icon: 'verified' },
] as const;

const SECTION_META = [
  {
    path: '/jetzt',
    kicker: 'Wochenplan',
    title: 'Regionale Dynamiken früher sehen',
    description: 'Verdichtet respiratorische Signale, Evidenz und Priorisierung zu einer operativen Wochenlage.',
  },
  {
    path: '/regionen',
    kicker: 'Regionen',
    title: 'Regionale Priorisierung',
    description: 'Zeigt, welche Bundesländer aktuell Relevanz gewinnen und wie sich ihre Priorität einordnen lässt.',
  },
  {
    path: '/kampagnen',
    kicker: 'Kampagnen',
    title: 'Operative Maßnahmen',
    description: 'Zeigt, welcher Vorschlag aktuell prüfbar ist, was ihn trägt und welche Fälle danach folgen.',
  },
  {
    path: '/evidenz',
    kicker: 'Evidenz',
    title: 'Belastbarkeit und Belege',
    description: 'Zeigt, was Empfehlungen bereits trägt, was noch fehlt und wo Daten oder Freigabe noch nicht ausreichen.',
  },
] as const;

const AppLayout: React.FC<Props> = ({ children }) => {
  const { theme, toggle } = useTheme();
  const { handleLogout } = useAuth();
  const { virus, brand, weeklyBudget, dataVersion } = useMediaWorkflow();
  const location = useLocation();
  const navigate = useNavigate();
  const [pdfLoading, setPdfLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const firstNavItemRef = useRef<HTMLButtonElement>(null);
  const { pilotReadout, loading: readoutLoading } = usePilotSurfaceData({
    brand,
    virus,
    horizonDays: 7,
    weeklyBudget,
    dataVersion,
  });

  const isActive = (path: string) => location.pathname.startsWith(path);
  const currentSection = SECTION_META.find(({ path }) => location.pathname.startsWith(path)) || {
    kicker: 'Arbeitsbereich',
    title: 'Arbeitsansicht',
    description: 'Hier bleibt der aktuelle Stand an einem Ort.',
  };
  const exportLabel = 'Wochenbericht exportieren';
  const readoutSummary = buildWeeklyReadoutSummary(pilotReadout, readoutLoading);

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
            <p className="operator-sidebar__brand-note">Gilt fürs Bundesland, keine Stadt-Prognose.</p>
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
                  {pdfLoading ? 'Wird erstellt...' : exportLabel}
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
              <div className="operator-header__hero-meta">
                <span className="operator-header__status-pill">{currentSection.kicker}</span>
                <span className={`operator-header__signal operator-header__signal--${readoutSummary.tone}`}>
                  {readoutSummary.status}
                </span>
              </div>
              <div className="operator-header__copy-block">
                <div className="operator-header__title-row">
                  <h1 id="operator-page-title" className="operator-header__title">{currentSection.title}</h1>
                </div>
                <p className="operator-header__copy">{currentSection.description}</p>
                <div className="operator-header__summary-line">
                  <span>{readoutSummary.focusRegions}</span>
                  <span>{readoutSummary.nextReview}</span>
                </div>
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

type WeeklyReadoutTone = 'go' | 'watch' | 'no-go';

interface WeeklyReadoutSummary {
  tone: WeeklyReadoutTone;
  status: string;
  title: string;
  summary: string;
  focusRegions: string;
  nextReview: string;
  reliability: string;
  dataReadiness: string;
  openGap: string;
  stripHeadline: string;
  stripGap: string;
  updatedAt: string;
}

function buildWeeklyReadoutSummary(
  pilotReadout: PilotReadoutResponse | null,
  loading: boolean,
): WeeklyReadoutSummary {
  if (loading) {
    return {
      tone: 'watch',
      status: 'Wochenlage wird geladen',
      title: 'Wochenlage wird vorbereitet',
      summary: 'Die Plattform verdichtet gerade Regionen, Kampagnen und Evidenz zu einer operativen Einordnung.',
      focusRegions: 'Wird geladen',
      nextReview: 'Wird geladen',
      reliability: 'Wird geladen',
      dataReadiness: 'Wird geladen',
      openGap: 'Noch keine Einschätzung',
      stripHeadline: 'Wochenlage wird vorbereitet',
      stripGap: 'Wird geladen',
      updatedAt: '-',
    };
  }

  if (!pilotReadout) {
    return {
      tone: 'watch',
      status: 'Wochenlage fehlt gerade',
      title: 'Wochenlage gerade nicht verfügbar',
      summary: 'Die verdichtete Wochenlage konnte gerade nicht geladen werden. Der Export bleibt verfügbar.',
      focusRegions: 'Noch offen',
      nextReview: 'Wochenplan erneut öffnen',
      reliability: 'Noch keine klare Einschätzung',
      dataReadiness: 'Datenlage noch offen',
      openGap: 'Daten für die Wochenlage fehlen',
      stripHeadline: 'Wochenlage fehlt',
      stripGap: 'Daten fehlen',
      updatedAt: '-',
    };
  }

  const executive = pilotReadout.executive_summary;
  const runContext = pilotReadout.run_context;
  const gate = runContext?.gate_snapshot;
  const operationalSummary = pilotReadout.operational_recommendations?.summary;
  const allRegions = pilotReadout.operational_recommendations?.regions || [];
  const topRegions = executive?.top_regions?.length ? executive.top_regions : allRegions.slice(0, 3);
  const leadRegion = topRegions[0] || allRegions[0] || null;
  const scopeReadiness = runContext?.scope_readiness || executive?.scope_readiness || 'NO_GO';
  const forecastReadiness = runContext?.forecast_readiness || gate?.forecast_readiness || 'NO_GO';
  const commercialValidation = runContext?.commercial_validation_status || gate?.commercial_validation_status || gate?.commercial_data_status || 'NO_GO';
  const focusRegions = topRegions.map((item) => regionIdentity(item)).filter(Boolean).slice(0, 3);
  const reasonTrace = firstMeaningful([
    executive?.headline,
    executive?.what_should_we_do_now,
    explainReason(executive?.uncertainty_summary_detail),
    executive?.uncertainty_summary,
    operationalSummary?.headline,
  ], 'Die Wochenübersicht bündelt den aktuellen Stand aus Regionen, Kampagnen und Evidenz.');
  const leadFocus = firstMeaningful([
    [regionIdentity(leadRegion), leadRegion?.recommended_product].filter(Boolean).join(' · '),
    [regionIdentity(leadRegion), leadRegion?.campaign_recommendation].filter(Boolean).join(' · '),
    executive?.what_should_we_do_now,
  ], 'Noch kein klarer Review-Fall sichtbar');
  const openGap = firstMeaningful([
    gate?.missing_requirements?.[0],
    executive?.budget_recommendation?.blocked_reasons?.[0],
    pilotReadout.empty_state?.body,
    executive?.validation_disclaimer,
    explainReason(leadRegion?.uncertainty_summary_detail),
    leadRegion?.uncertainty_summary,
  ], 'Keine akute Lücke sichtbar, aber weiter auf Datenfrische und Freigabestatus achten.');
  const coverageWeeks = gate?.coverage_weeks;
  const dataReadiness = coverageWeeks
    ? `${coverageWeeks} Wochen GELO-Daten verbunden`
    : commercialValidation === 'GO'
      ? 'GELO-Datenlage: ausreichend'
      : commercialValidation === 'WATCH'
        ? 'GELO-Datenlage: mit Vorsicht'
        : 'GELO-Datenlage: im Aufbau';
  const reliability = forecastReadiness === 'GO'
    ? (commercialValidation === 'GO' ? 'Sicherheit: gut genug' : 'Sicherheit: ok, Evidenz noch mit Vorsicht')
    : forecastReadiness === 'WATCH'
      ? 'Mit Vorsicht: noch nicht überall sicher genug'
      : 'Noch nicht sicher genug';
  const tone = readinessTone(scopeReadiness);
  const status = statusLabel(scopeReadiness);
  const updatedAt = formatDateTime(runContext?.generated_at || pilotReadout.generated_at || null);
  const stripHeadline = firstMeaningful([
    operationalSummary?.headline,
    executive?.what_should_we_do_now,
  ], 'Wochenlage wird weiter aufgebaut');
  const stripGap = shortText(openGap, 58);

  return {
    tone,
    status,
    title: executive?.what_should_we_do_now || 'Was GELO diese Woche zuerst prüfen sollte',
    summary: reasonTrace,
    focusRegions: focusRegions.length ? focusRegions.join(', ') : 'Noch keine Fokus-Bundesländer',
    nextReview: leadFocus,
    reliability,
    dataReadiness,
    openGap,
    stripHeadline,
    stripGap,
    updatedAt,
  };
}

function readinessTone(value?: PilotReadoutStatus | null): WeeklyReadoutTone {
  if (value === 'GO') return 'go';
  if (value === 'WATCH') return 'watch';
  return 'no-go';
}

function statusLabel(value?: PilotReadoutStatus | null): string {
  if (value === 'GO') return 'Bereit';
  if (value === 'WATCH') return 'Mit Vorsicht';
  return 'Noch unsicher';
}

function regionIdentity(region?: PilotReadoutRegion | null): string {
  return region?.region_name || region?.region_code || '';
}

function explainReason(value?: StructuredReasonItem | null): string {
  const explained = explainInPlainGerman(value || null);
  return explained || '';
}

function firstMeaningful(values: Array<string | null | undefined>, fallback: string): string {
  return values.find((value) => typeof value === 'string' && value.trim().length > 0)?.trim() || fallback;
}

function shortText(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1).trimEnd()}…`;
}
