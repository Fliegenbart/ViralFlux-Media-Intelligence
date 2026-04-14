import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import packageJson from '../../../package.json';

import { useAuth, useTheme } from '../../App';
import {
  OperatorPanel,
  OperatorSection,
  OperatorStat,
} from '../../components/cockpit/operator/OperatorPrimitives';
import {
  MiniGermanyMap,
  RevealSection,
  createThemePalette,
} from './LandingWidgets';

const NAV_ITEMS = [
  { label: 'Nutzen', sectionId: 'landing-value' },
  { label: 'Produktkern', sectionId: 'landing-surface' },
  { label: 'Einsatzgrenzen', sectionId: 'landing-scope' },
] as const;

const PRODUCT_SCOPE_URL = 'https://github.com/Fliegenbart/ViralFlux-Media-Intelligence/blob/main/docs/current_product_scope.md';

const VALUE_CARDS = [
  {
    label: 'Regionen schneller priorisieren',
    value: 'Welche Regionen jetzt zuerst geprüft werden sollten',
    meta: 'ViralFlux zeigt nicht nur Rohdaten, sondern macht sichtbar, wo zuerst hingeschaut werden sollte.',
    tone: 'accent' as const,
  },
  {
    label: 'Forecast, Lage und Empfehlung getrennt sehen',
    value: 'Vergangenheit, Forecast und Empfehlung bleiben unterscheidbar',
    meta: 'Dadurch wird klarer, was schon beobachtet wurde und was nur als Entscheidungshilfe dient.',
    tone: 'muted' as const,
  },
  {
    label: 'Im Wochenrhythmus arbeiten',
    value: 'Regelmäßige Steuerung statt punktueller Einzelauswertung',
    meta: 'Der Produktkern ist für wiederholbare Reviews und Priorisierung gedacht, nicht nur für einen einzelnen Blick auf Daten.',
    tone: 'default' as const,
  },
] as const;

const SCOPE_CARDS = [
  {
    label: 'Bewusst klar begrenzt',
    value: 'Nicht jede sichtbare Kombination wird automatisch als produktionsreif behauptet',
    meta: 'Der fachliche Scope wird vorab definiert und bleibt im aktuellen Stand bewusst eng geführt.',
    tone: 'muted' as const,
  },
  {
    label: 'Menschliche Freigabe bleibt',
    value: 'Empfehlungen ersetzen keine finale Entscheidung',
    meta: 'Forecasts bleiben Entscheidungshilfen. Freigaben und operative Schritte werden weiterhin bewusst geprüft.',
    tone: 'accent' as const,
  },
  {
    label: 'Technisch überprüfbar',
    value: 'Readiness- und Release-Prüfungen sichern den laufenden Kernbetrieb',
    meta: 'Damit lässt sich nicht nur eine Oberfläche zeigen, sondern ein nachvollziehbarer Live-Stand.',
    tone: 'default' as const,
  },
] as const;

const BL_NAMES: Record<string, string> = {
  BW: 'Baden-Württemberg',
  BY: 'Bayern',
  BE: 'Berlin',
  BB: 'Brandenburg',
  HB: 'Bremen',
  HH: 'Hamburg',
  HE: 'Hessen',
  MV: 'Mecklenburg-Vorpommern',
  NI: 'Niedersachsen',
  NW: 'Nordrhein-Westfalen',
  RP: 'Rheinland-Pfalz',
  SL: 'Saarland',
  SN: 'Sachsen',
  ST: 'Sachsen-Anhalt',
  SH: 'Schleswig-Holstein',
  TH: 'Thüringen',
};

interface RegionItem {
  bl: string;
  name: string;
  score: number;
  trend: string;
  col: string;
}

const DEFAULT_REGIONS: RegionItem[] = [
  { bl: '—', name: 'Lade Regionaldaten...', score: 0, trend: 'stabil', col: '#94a3b8' },
];

const buildTopRegions = (regions: unknown): RegionItem[] => {
  if (!regions || typeof regions !== 'object') {
    return DEFAULT_REGIONS;
  }

  return Object.entries(regions as Record<string, any>)
    .map(([code, value]) => {
      const scoreRaw = Number(value?.score_0_100 ?? 0);
      return {
        bl: code,
        name: value?.region_name || BL_NAMES[code] || code,
        score: scoreRaw / 100,
        trend: value?.trend || 'stabil',
        col: scoreRaw >= 70 ? '#dc2626' : scoreRaw >= 40 ? '#d97706' : '#059669',
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);
};

const formatTrend = (trend: string) => {
  if (trend === 'steigend') return '↑ steigend';
  if (trend === 'fallend') return '↓ fallend';
  return '→ stabil';
};

const formatDataStatus = (value?: string | null) => {
  if (!value) return 'Datenstatus: letzte Aktualisierung derzeit nicht verfügbar';

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return 'Datenstatus: letzte Aktualisierung derzeit nicht verfügbar';
  }

  return `Datenstatus: ${new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)}`;
};

const scrollToSection = (sectionId: string) => {
  const element = document.getElementById(sectionId);
  if (element && typeof element.scrollIntoView === 'function') {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
};

const LandingPage: React.FC = () => {
  const { theme, toggle: toggleTheme } = useTheme();
  const { authenticated } = useAuth();
  const palette = createThemePalette(theme);
  const navigate = useNavigate();
  const [topRegions, setTopRegions] = useState<RegionItem[]>(DEFAULT_REGIONS);
  const [apiLive, setApiLive] = useState(false);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    fetch('/api/v1/outbreak-score/peix-score', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!active || !data) return;

        setApiLive(true);
        setGeneratedAt(typeof data.generated_at === 'string' ? data.generated_at : null);

        const regions = buildTopRegions(data.regions);
        if (regions.length > 0) {
          setTopRegions(regions);
        }
      })
      .catch((error) => {
        if (active && !controller.signal.aborted) {
          console.warn('Landing page data fetch failed', error);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  const openProductCore = () => navigate(authenticated ? '/virus-radar' : '/login');
  const liveStatusLabel = apiLive ? 'Live-Daten verbunden' : 'Wird geladen';
  const topRegion = topRegions[0];

  return (
    <div className="app-shell landing-page">
      <header className="shell-header media-header surface-header" style={{ zIndex: 10 }}>
        <div className="shell-header-inner">
          <Link to="/" className="shell-brand product-brand-lockup">
            <span className="shell-logo-mark product-brand-mark">VF</span>
            <span className="shell-logo-copy product-brand-copy">ViralFlux</span>
          </Link>

          <nav className="shell-nav" aria-label="Hauptnavigation">
            {NAV_ITEMS.map(({ label, sectionId }) => (
              <button key={sectionId} type="button" onClick={() => scrollToSection(sectionId)} className="shell-nav-item">
                {label}
              </button>
            ))}
          </nav>

          <div className="shell-header-spacer" />

          <div className="lp-nav-actions">
            <button type="button" onClick={openProductCore} className="media-button">
              Produktkern ansehen
            </button>
            <button
              type="button"
              onClick={toggleTheme}
              className="theme-toggle"
              title={theme === 'dark' ? 'Heller Modus' : 'Dunkler Modus'}
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
          </div>
        </div>
      </header>

      <main className="shell-main landing-main" style={{ zIndex: 5 }}>
        <div className="shell-main-inner landing-main-inner">
          <RevealSection>
            <section
              className="operator-section-shell operator-section-shell--accent landing-hero-shell"
              aria-label="Produktkern Einstieg"
            >
              <div className="landing-hero-grid">
                <div className="landing-hero-copy">
                  <span className="landing-hero-kicker">Regionale Frühwarnung</span>

                  <h1 className="landing-hero-title">
                    Erkennen, welche Regionen jetzt zuerst geprüft werden sollten
                  </h1>

                  <p className="operator-section-shell__copy landing-hero-copytext">
                    ViralFlux hilft Teams dabei, regionale Virus-Signale früher zu erkennen,
                    die Lage für die nächsten Tage besser einzuordnen und daraus eine verständliche
                    Wochensteuerung abzuleiten.
                  </p>

                  <div className="landing-action-row">
                    <button type="button" onClick={openProductCore} className="media-button">
                      Produktkern ansehen
                    </button>
                    <a href={PRODUCT_SCOPE_URL} target="_blank" rel="noreferrer" className="media-button secondary">
                      Aktuellen Produktumfang lesen
                    </a>
                  </div>
                </div>

                <OperatorPanel
                  eyebrow="Heute sichtbar"
                  title={topRegion ? `${topRegion.name} jetzt zuerst prüfen` : 'Regionale Lage im Überblick'}
                  description="Der Produktkern macht sichtbar, wo zuerst hingeschaut werden sollte und wie belastbar die aktuelle Einordnung wirkt."
                  tone="accent"
                  className="landing-live-panel"
                >
                  <div className="landing-live-topline">
                    <span className={`landing-live-badge ${apiLive ? 'landing-live-badge--live' : 'landing-live-badge--idle'}`}>
                      {apiLive ? 'LIVE' : 'OFFEN'}
                    </span>
                    <span className="landing-live-caption">
                      {liveStatusLabel}
                    </span>
                  </div>

                  <div className="landing-preview-grid landing-preview-grid--hero">
                    <MiniGermanyMap palette={palette} />

                    <div className="landing-region-list">
                      {(topRegions.length ? topRegions : DEFAULT_REGIONS).map((region) => (
                        <div key={region.bl} className="landing-region-row">
                          <span
                            className="landing-region-row__code"
                            style={{ background: `${region.col}15`, color: region.col }}
                          >
                            {region.bl}
                          </span>
                          <div className="landing-region-row__body">
                            <strong className="landing-region-row__name">{region.name}</strong>
                            <span className="landing-region-row__trend">{formatTrend(region.trend)}</span>
                          </div>
                          <span className="landing-region-row__score" style={{ color: region.col }}>
                            {region.score.toFixed(2)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </OperatorPanel>
              </div>
            </section>
          </RevealSection>

          <RevealSection delay={0.04}>
            <div id="landing-value">
              <OperatorSection
                kicker="Was der Produktkern heute schon leistet"
                title="Klare Priorisierung statt verstreuter Einzelsignale"
                description="ViralFlux macht aus Gesundheits- und Kontextsignalen eine lesbare Arbeitsgrundlage für die nächste Entscheidung."
              >
                <div className="operator-stat-grid">
                  {VALUE_CARDS.map((feature) => (
                    <OperatorStat
                      key={feature.label}
                      label={feature.label}
                      value={feature.value}
                      meta={feature.meta}
                      tone={feature.tone}
                    />
                  ))}
                </div>
              </OperatorSection>
            </div>
          </RevealSection>

          <RevealSection delay={0.08}>
            <div id="landing-surface">
              <OperatorSection
                kicker="Produktkern"
                title="Bewusst klar begrenzt statt zu viel versprochen"
                description="Der aktuelle Einsatz ist als eng geführter operativer Kern gedacht: mit definiertem Scope, menschlicher Freigabe und nachvollziehbarem Betriebsstand."
                tone="muted"
              >
                <div id="landing-scope" className="operator-stat-grid">
                  {SCOPE_CARDS.map((feature) => (
                    <OperatorStat
                      key={feature.label}
                      label={feature.label}
                      value={feature.value}
                      meta={feature.meta}
                      tone={feature.tone}
                    />
                  ))}
                </div>
              </OperatorSection>
            </div>
          </RevealSection>
        </div>
      </main>

      <footer className="shell-footer">
        <div className="shell-footer-inner landing-footer-inner">
          <span className="shell-footer-note">{formatDataStatus(generatedAt)}</span>
          <div className="landing-footer-meta">
            <span className="landing-footer-version">Version {packageJson.version}</span>
            <a href={PRODUCT_SCOPE_URL} target="_blank" rel="noreferrer" className="landing-footer-link">
              Produktumfang
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
