import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { useTheme } from '../../App';
import { UI_COPY } from '../../lib/copy';
import {
  OperatorChipRail,
  OperatorPanel,
  OperatorSection,
  OperatorStat,
} from '../../components/cockpit/operator/OperatorPrimitives';
import {
  MiniGermanyMap,
  RevealSection,
  ScoreGauge,
  VirusBars,
  createThemePalette,
} from './LandingWidgets';

const MAILTO = (() => {
  const subject = 'Beratungsgespraech: PEIX x GELO Fruehwarnung';
  const body = [
    'Hallo PEIX Team,',
    '',
    'wir möchten ein kurzes Beratungsgespräch zu PEIX x GELO vereinbaren.',
    '',
    'Marke/Produkt:',
    'Regionen:',
    'Gewünschter Termin:',
    '',
    'Viele Grüße',
  ].join('\n');

  return `mailto:sales@peix.de?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
})();

const NAV_ITEMS = [
  { label: 'Jetzt', path: '/jetzt' },
  { label: 'Regionen', path: '/regionen' },
  { label: 'Kampagnen', path: '/kampagnen' },
  { label: 'Qualität', path: '/evidenz' },
] as const;

const HERO_STATS = ['16 Bundesländer', '4 Virustypen', '3 / 5 / 7 Tage Vorlauf'];

const FEATURE_STATS = [
  {
    label: 'Vorlauf',
    value: '3 bis 7 Tage',
    meta: 'Abwasser, ARE, Versorgung und weitere Signale werden verbunden, damit frühe Veränderungen sichtbar werden.',
    tone: 'accent' as const,
  },
  {
    label: 'Ort',
    value: 'Bundeslandgenau',
    meta: 'Wir zeigen, in welcher Region die Nachfrage als Nächstes anzieht.',
    tone: 'default' as const,
  },
  {
    label: 'Transparenz',
    value: 'Mit Begründung',
    meta: 'Vorhersage, Quellenstand und Prüfstatus bleiben sichtbar und prüfbar.',
    tone: 'muted' as const,
  },
] as const;

const FLOW_STEPS = [
  {
    label: 'Frühe Hinweise',
    value: '01',
    meta: 'Frühe Hinweise aus Abwasser, Wetter, Nachfrage und Versorgung erfassen.',
    tone: 'default' as const,
  },
  {
    label: 'Vorhersage',
    value: '02',
    meta: `3-, 5- oder 7-Tage-Vorhersage pro Bundesland in einen klaren ${UI_COPY.signalScore} verdichten.`,
    tone: 'default' as const,
  },
  {
    label: 'Region',
    value: '03',
    meta: 'Die Region mit der größten Dynamik und dem passenden Produktfokus sichtbar machen.',
    tone: 'default' as const,
  },
  {
    label: 'Nächster Schritt',
    value: '04',
    meta: 'Vorschlag prüfen, freigeben und die Kampagne gezielt vorbereiten oder starten.',
    tone: 'accent' as const,
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

interface VirusItem {
  label: string;
  pct: number;
  color: string;
}

const DEFAULT_VIRUS_DATA: VirusItem[] = [
  { label: 'Influenza A', pct: 0, color: '#dc2626' },
  { label: 'SARS-CoV-2', pct: 0, color: '#2563eb' },
  { label: 'RSV', pct: 0, color: '#d97706' },
];

const DEFAULT_REGIONS: RegionItem[] = [
  { bl: '—', name: 'Lade Regionaldaten...', score: 0, trend: 'stabil', col: '#94a3b8' },
];

const readVirusScore = (virusScores: Record<string, any>, keys: string[]) => {
  for (const key of keys) {
    const entry = virusScores[key];
    if (entry && typeof entry.epi_score === 'number') {
      return entry.epi_score;
    }
  }
  return 0;
};

const buildVirusData = (virusScores: Record<string, any> | null | undefined): VirusItem[] => {
  if (!virusScores || typeof virusScores !== 'object') {
    return DEFAULT_VIRUS_DATA;
  }

  return [
    {
      label: 'Influenza A',
      pct: Math.round(readVirusScore(virusScores, ['influenza', 'Influenza']) * 100),
      color: '#dc2626',
    },
    {
      label: 'SARS-CoV-2',
      pct: Math.round(readVirusScore(virusScores, ['covid', 'COVID-19', 'sars-cov-2']) * 100),
      color: '#2563eb',
    },
    {
      label: 'RSV',
      pct: Math.round(readVirusScore(virusScores, ['rsv', 'RSV']) * 100),
      color: '#d97706',
    },
  ];
};

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

const LandingPage: React.FC = () => {
  const { theme, toggle: toggleTheme } = useTheme();
  const palette = createThemePalette(theme);
  const navigate = useNavigate();
  const [peixScore, setPeixScore] = useState(0);
  const [virusData, setVirusData] = useState<VirusItem[]>(DEFAULT_VIRUS_DATA);
  const [topRegions, setTopRegions] = useState<RegionItem[]>(DEFAULT_REGIONS);
  const [recText, setRecText] = useState('');
  const [apiLive, setApiLive] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    fetch('/api/v1/outbreak-score/peix-score', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!active || !data) return;

        setApiLive(true);

        const nationalScore = data.national_score ?? data.score;
        if (typeof nationalScore === 'number') {
          setPeixScore(nationalScore / 100);
        }

        setVirusData(buildVirusData(data.virus_scores));

        const regions = buildTopRegions(data.regions);
        if (regions.length > 0) {
          setTopRegions(regions);
          setRecText(`Die stärkste Dynamik sehen wir aktuell in ${regions.map((region) => region.name).join(', ')}.`);
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
  const openCampaigns = () => navigate('/kampagnen');

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
            <a
              href={MAILTO}
              className="media-button secondary"
              style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
            >
              Kontakt
            </a>
            <button type="button" onClick={openCockpit} className="media-button">
              Zum Cockpit
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
                  <OperatorChipRail className="landing-hero-chip-rail">
                    <span className="landing-hero-chip landing-hero-chip--status">
                      <span className="landing-hero-chip__dot" aria-hidden="true" />
                      PEIX x GELO Frühwarnung
                    </span>
                    <span className="landing-hero-chip">Vom Signal bis zur Wochenlage</span>
                  </OperatorChipRail>

                  <h1 className="landing-hero-title">
                    Regionale Krankheitswellen früher erkennen und Budgets gezielter einsetzen.
                  </h1>

                  <p className="operator-section-shell__copy landing-hero-copytext">
                    Unsere Frühwarnung zeigt 3 bis 7 Tage im Voraus, wo Atemwegserkrankungen ansteigen.
                    So kannst du Regionen früher priorisieren, Streuverluste senken und dein Mediabudget gezielter einsetzen.
                  </p>

                  <div className="landing-action-row">
                    <button type="button" onClick={openCockpit} className="media-button">
                      Wochenlage prüfen
                    </button>
                    <button type="button" onClick={openCampaigns} className="media-button secondary">
                      Kampagnen ansehen
                    </button>
                  </div>

                  <OperatorChipRail className="landing-hero-metrics">
                    {HERO_STATS.map((stat) => (
                      <span key={stat} className="landing-hero-metric">
                        {stat}
                      </span>
                    ))}
                  </OperatorChipRail>
                </div>

                <OperatorPanel
                  eyebrow="Live-Übersicht"
                  title={UI_COPY.signalScore}
                  description="Deutschlandweite Einordnung der aktuellen Lage"
                  tone="accent"
                  className="landing-live-panel"
                >
                  <div className="landing-live-topline">
                    <span className={`landing-live-badge ${apiLive ? 'landing-live-badge--live' : 'landing-live-badge--idle'}`}>
                      {apiLive ? 'LIVE' : '...'}
                    </span>
                    <span className="landing-live-caption">
                      {apiLive ? 'Aktuelle Werte' : 'Wird geladen'}
                    </span>
                  </div>

                  <ScoreGauge score={peixScore} label={UI_COPY.signalScore} palette={palette} />

                  <div className="landing-live-divider" />

                  <div className="landing-live-rail">
                    <span className="landing-live-subtitle">Aktuelle Entwicklung</span>
                    <VirusBars data={virusData} palette={palette} />
                  </div>

                  <div className="landing-recommendation">
                    <strong>Empfehlung:</strong> {recText || 'Daten werden geladen...'}
                  </div>
                </OperatorPanel>
              </div>
            </section>
          </RevealSection>

          <RevealSection delay={0.04}>
            <OperatorSection
              kicker="01"
              title="Was macht ViralFlux anders"
              description="ViralFlux hilft dir, Nachfrage früher zu erkennen und daraus direkt einen sinnvollen nächsten Schritt abzuleiten."
            >
              <div className="operator-stat-grid">
                {FEATURE_STATS.map((feature) => (
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

          <RevealSection delay={0.08}>
            <OperatorSection
              kicker="02"
              title="Von frühen Hinweisen zur klaren Wochenlage"
              description="Aus vielen Datenquellen wird eine einfache Reihenfolge: Lage verstehen, Region priorisieren, nächsten Schritt festlegen."
              tone="muted"
            >
              <div className="landing-flow-grid">
                {FLOW_STEPS.map((step) => (
                  <OperatorStat
                    key={step.value}
                    label={step.label}
                    value={step.value}
                    meta={step.meta}
                    tone={step.tone}
                  />
                ))}
              </div>
            </OperatorSection>
          </RevealSection>

          <RevealSection delay={0.12}>
            <OperatorSection
              kicker="03"
              title="Wo die Welle zuerst beginnt"
              description="Die Karte zeigt, wo die größte Dynamik gerade entsteht. Rechts daneben siehst du die drei wichtigsten Regionen im Überblick."
            >
              <div className="landing-preview-grid">
                <MiniGermanyMap palette={palette} />

                <OperatorPanel
                  eyebrow="Cockpit-Vorschau"
                  title="So sieht die Wochenlage aus"
                  description="Die Deutschlandkarte zeigt, wo du jetzt zuerst hinschauen solltest."
                  tone="muted"
                >
                  <div className="landing-region-list">
                    {topRegions.map((region) => (
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
                </OperatorPanel>
              </div>
            </OperatorSection>
          </RevealSection>

          <RevealSection delay={0.16}>
            <OperatorSection
              kicker="Nächster Schritt"
              title="3 bis 7 Tage früher erkennen, wo Nachfrage anzieht."
              description="Starte direkt in der Wochenlage und sieh sofort, welche Region wichtig wird und welcher nächste Schritt sinnvoll ist."
              tone="accent"
              className="landing-cta-section"
            >
              <div className="landing-cta-body">
                <div className="landing-action-row landing-action-row--center">
                  <button type="button" onClick={openCockpit} className="media-button">
                    Wochenlage prüfen
                  </button>
                  <a
                    href={MAILTO}
                    className="media-button secondary"
                    style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
                  >
                    Beratung anfragen
                  </a>
                </div>
              </div>
            </OperatorSection>
          </RevealSection>
        </div>
      </main>

      <footer className="shell-footer">
        <div className="shell-footer-inner landing-footer-inner">
          <span className="shell-footer-note">PEIX x GELO Frühwarnung für regionale Nachfrage</span>

          <div className="landing-footer-actions">
            <a
              href={MAILTO}
              className="media-button secondary"
              style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
            >
              Beratung anfragen
            </a>
            <button type="button" onClick={openCockpit} className="media-button">
              Wochenlage öffnen
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
