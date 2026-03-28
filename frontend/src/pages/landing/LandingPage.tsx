import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import packageJson from '../../../package.json';

import { useTheme } from '../../App';
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
  { label: 'Jetzt', path: '/jetzt' },
  { label: 'Regionen', path: '/regionen' },
  { label: 'Kampagnen', path: '/kampagnen' },
  { label: 'Qualität', path: '/evidenz' },
] as const;

const DOCS_URL = 'https://github.com/Fliegenbart/ViralFlux-Media-Intelligence/blob/main/docs/OPERATORS_GUIDE.md';

const FEATURE_CARDS = [
  {
    label: 'Frühwarnung',
    value: '3 bis 7 Tage voraus',
    meta: 'Forecast auf Bundesland-Ebene, bevor die Lage in der Rückschau klar sichtbar wird.',
    tone: 'accent' as const,
  },
  {
    label: 'Entscheidungshilfe',
    value: 'Signal vor Bauchgefühl',
    meta: 'Regionen werden nach Signal, Dynamik und operativer Relevanz geordnet.',
    tone: 'muted' as const,
  },
  {
    label: 'Freigabe-Gate',
    value: 'Signal ist nicht gleich Freigabe',
    meta: 'Epidemiologie und Budget-Freigabe bleiben bewusst getrennt sichtbar.',
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

const LandingPage: React.FC = () => {
  const { theme, toggle: toggleTheme } = useTheme();
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

  const openCockpit = () => navigate('/jetzt');
  const liveStatusLabel = apiLive ? 'Live-Daten verbunden' : 'Wird geladen';
  const topRegion = topRegions[0];

  return (
    <div className="app-shell landing-page">
      <header className="shell-header media-header surface-header" style={{ zIndex: 10 }}>
        <div className="shell-header-inner">
          <Link to="/welcome" className="shell-brand product-brand-lockup">
            <span className="shell-logo-mark product-brand-mark">VF</span>
            <span className="shell-logo-copy product-brand-copy">ViralFlux</span>
          </Link>

          <nav className="shell-nav" aria-label="Hauptnavigation">
            {NAV_ITEMS.map(({ label, path }) => (
              <button key={path} type="button" onClick={() => navigate(path)} className="shell-nav-item">
                {label}
              </button>
            ))}
          </nav>

          <div className="shell-header-spacer" />

          <div className="lp-nav-actions">
            <button type="button" onClick={openCockpit} className="media-button">
              Zum Dashboard
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
            <section className="operator-section-shell operator-section-shell--accent landing-hero-shell">
              <div className="landing-hero-grid">
                <div className="landing-hero-copy">
                  <span className="landing-hero-kicker">PEIX x GELO</span>

                  <h1 className="landing-hero-title">
                    Regionale Virus-Frühwarnung für Media-Entscheidungen
                  </h1>

                  <p className="operator-section-shell__copy landing-hero-copytext">
                    ViralFlux zeigt, wo sich Viruswellen aufbauen und was das für Kampagnen,
                    Priorisierung und Freigabe bedeutet.
                  </p>

                  <div className="landing-action-row">
                    <button type="button" onClick={openCockpit} className="media-button">
                      Zum Dashboard &#8594;
                    </button>
                  </div>
                </div>

                <OperatorPanel
                  eyebrow="Heute sichtbar"
                  title={topRegion ? `${topRegion.name} zuerst prüfen` : 'Lage im Überblick'}
                  description="Die Karte zeigt, wo sich Dynamik zuerst aufbaut. Die genaue Einordnung übernimmt danach das Dashboard."
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
            <OperatorSection
              kicker="Im Überblick"
              title="Was hier sichtbar wird"
              description="Die Startseite zeigt nur die Grundlogik. Alles Weitere liegt im Dashboard und in der Evidenz."
            >
              <div className="operator-stat-grid">
                {FEATURE_CARDS.map((feature) => (
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
          </RevealSection>
        </div>
      </main>

      <footer className="shell-footer">
        <div className="shell-footer-inner landing-footer-inner">
          <span className="shell-footer-note">{formatDataStatus(generatedAt)}</span>
          <div className="landing-footer-meta">
            <span className="landing-footer-version">Version {packageJson.version}</span>
            <a href={DOCS_URL} target="_blank" rel="noreferrer" className="landing-footer-link">
              Docs
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
