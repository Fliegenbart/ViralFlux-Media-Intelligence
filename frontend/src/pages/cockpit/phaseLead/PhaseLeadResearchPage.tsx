import React, { useState } from 'react';
import { CircleHelp } from 'lucide-react';
import { Link } from 'react-router-dom';

import '../../../styles/peix.css';
import '../../../styles/peix-gate.css';
import './phase-lead.css';

import CockpitGate from '../CockpitGate';
import { usePhaseLeadSnapshot } from './usePhaseLeadSnapshot';
import type { PhaseLeadRegion, PhaseLeadSnapshot } from './types';

const sourceLabels: Record<string, string> = {
  wastewater: 'AMELAG',
  survstat: 'SurvStat',
  are: 'ARE',
  notaufnahme: 'Notaufnahme',
};

const sourceHelp: Record<string, string> = {
  wastewater: 'AMELAG ist das Abwassermonitoring. Es kann Atemwegswellen oft früher sichtbar machen als klassische Meldedaten.',
  survstat: 'SurvStat sind gemeldete Infektionsdaten. Sie sind belastbar, kommen aber mit Meldeverzug.',
  are: 'ARE steht für akute respiratorische Erkrankungen. Die Quelle zeigt, wie stark Erkältungs- und Atemwegsaktivität allgemein zunimmt.',
  notaufnahme: 'Notaufnahme-Daten geben Hinweise auf akuten Versorgungsdruck. Sie sind hier ein ergänzendes Signal, nicht die alleinige Wahrheit.',
};

const availableViruses = ['Gesamt', 'Influenza A', 'Influenza B', 'RSV A', 'SARS-CoV-2'] as const;

type PhaseLeadAudience = 'product' | 'limbach';

export interface PhaseLeadResearchPageProps {
  audience?: PhaseLeadAudience;
}

function Explain({
  label,
  title,
  children,
  placement = 'top',
}: {
  label: string;
  title: string;
  children: React.ReactNode;
  placement?: 'top' | 'left' | 'right';
}) {
  return (
    <span className={`phase-lead-help phase-lead-help--${placement}`}>
      <button type="button" className="phase-lead-help__button" aria-label={label}>
        <CircleHelp size={14} strokeWidth={2.3} aria-hidden="true" />
      </button>
      <span className="phase-lead-help__bubble" role="tooltip" aria-hidden="true">
        <b>{title}</b>
        <span>{children}</span>
      </span>
    </span>
  );
}

function HelpLabel({
  children,
  label,
  title,
  body,
  placement,
}: {
  children: React.ReactNode;
  label: string;
  title: string;
  body: React.ReactNode;
  placement?: 'top' | 'left' | 'right';
}) {
  const tooltipTitle =
    typeof children === 'string' && children.replace(/\.$/, '') === title
      ? 'Kurz erklärt'
      : title;

  return (
    <span className="phase-lead-help-label">
      <span>{children}</span>
      <Explain label={label} title={tooltipTitle} placement={placement}>
        {body}
      </Explain>
    </span>
  );
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString('de-DE');
}

function parseDateOnly(value: string | null | undefined): Date | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (match) {
    return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function formatDateObject(date: Date | null): string {
  return date ? date.toLocaleDateString('de-DE') : '-';
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return `${Math.round(value * 100)}%`;
}

function formatSigned(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
}

function formatOne(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return value.toFixed(1);
}

function actionForRegion(
  region: PhaseLeadRegion | undefined,
  audience: PhaseLeadAudience = 'product',
): {
  label: string;
  tone: 'prepare' | 'watch' | 'hold';
  explanation: string;
} {
  if (!region) {
    return {
      label: 'Keine Region',
      tone: 'hold',
      explanation: 'Noch kein regionales Signal vorhanden.',
    };
  }
  if (audience === 'limbach') {
    if (region.p_surge_h7 >= 0.35 || region.p_up_h7 >= 0.55) {
      return {
        label: `${region.region} disponieren`,
        tone: region.p_surge_h7 >= 0.35 || region.p_up_h7 >= 0.75 ? 'prepare' : 'watch',
        explanation:
          'Probenlogistik, Abholfenster, Entnahmematerial und respiratorische Diagnostik-Kapazität regional vorbereiten.',
      };
    }
    return {
      label: `${region.region} beobachten`,
      tone: 'hold',
      explanation: 'Region weiter monitoren; noch keine operative Labor-Disposition nötig.',
    };
  }
  if (region.p_surge_h7 >= 0.35 || region.p_up_h7 >= 0.75) {
    return {
      label: `${region.region} vorbereiten`,
      tone: 'prepare',
      explanation: 'Creative, regionale Gebote und Apothekenabdeckung vorbereiten. Budget bleibt shadow-only.',
    };
  }
  if (region.p_up_h7 >= 0.55) {
    return {
      label: `${region.region} beobachten`,
      tone: 'watch',
      explanation: 'Region eng beobachten und Aktivierungspaket bereithalten.',
    };
  }
  return {
    label: `${region.region} halten`,
    tone: 'hold',
    explanation: 'Keine operative Vorbereitungsaktion nötig.',
  };
}

function confidenceLabel(snapshot: PhaseLeadSnapshot): string {
  if (snapshot.summary.converged && snapshot.summary.warning_count === 0) return 'hoch';
  if (snapshot.summary.fit_mode === 'map_optimization') return 'mittel';
  return 'vorläufig';
}

function latestSourceDate(snapshot: PhaseLeadSnapshot): string | null {
  const latestDates = Object.values(snapshot.sources)
    .map((source) => source.latest_event_date)
    .filter(Boolean)
    .sort();
  return latestDates[latestDates.length - 1] ?? null;
}

function reportingLagDays(snapshot: PhaseLeadSnapshot): number | null {
  const latest = latestSourceDate(snapshot);
  if (!latest || !snapshot.as_of) return null;
  const latestDate = new Date(latest);
  const asOfDate = new Date(snapshot.as_of);
  if (Number.isNaN(latestDate.getTime()) || Number.isNaN(asOfDate.getTime())) return null;
  return Math.max(0, Math.round((asOfDate.getTime() - latestDate.getTime()) / 86_400_000));
}

function sourceFreshnessLabel(snapshot: PhaseLeadSnapshot): string {
  const latest = latestSourceDate(snapshot);
  const lagDays = reportingLagDays(snapshot);
  if (!latest) return 'Neueste Meldung: -';
  const lagLabel = lagDays === null ? '' : ` · ${lagDays} Tage Meldeverzug`;
  return `Neueste Meldung: ${formatDate(latest)}${lagLabel}`;
}

function topRegionHeadline(topRegion: PhaseLeadRegion | undefined, audience: PhaseLeadAudience = 'product'): string {
  if (!topRegion) return 'Kein regionaler Kandidat';
  if (audience === 'limbach') return `${topRegion.region} disponieren`;
  return `${topRegion.region} zuerst vorbereiten`;
}

function aggregateDrivers(snapshot: PhaseLeadSnapshot, regionCode: string): string {
  const drivers = snapshot.aggregate?.drivers_by_region[regionCode] ?? [];
  if (!drivers.length) return '-';
  return drivers
    .slice(0, 2)
    .map((driver) => driver.virus_typ)
    .join(' + ');
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function chartPath(points: Array<{ x: number; y: number }>): string {
  return points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(' ');
}

function buildSignalCurve(region: PhaseLeadRegion | undefined): {
  historyPath: string;
  forecastPath: string;
  currentLabel: string;
  forecastLabel: string;
} {
  if (!region) {
    return {
      historyPath: '',
      forecastPath: '',
      currentLabel: '-',
      forecastLabel: '-',
    };
  }

  const left = 34;
  const right = 646;
  const todayX = 420;
  const bottom = 220;
  const top = 34;
  const level = Math.max(0.1, region.current_level);
  const growth = clamp(region.current_growth, -0.35, 0.45);
  const pressure = clamp(0.55 * region.p_up_h7 + 0.35 * region.p_surge_h7 + 0.1 * region.p_front, 0, 1);

  const historyValues = Array.from({ length: 8 }, (_, index) => {
    const distance = 7 - index;
    const wave = Math.sin(index * 0.95) * 0.08 * level;
    return Math.max(0.02, level * Math.exp(-growth * distance * 0.45) + wave);
  });
  const forecastValues = Array.from({ length: 5 }, (_, index) => {
    const step = index + 1;
    const momentum = 1 + growth * step * 0.75 + pressure * step * 0.13;
    return Math.max(0.02, level * momentum);
  });
  const allValues = [...historyValues, ...forecastValues];
  const minValue = Math.min(...allValues);
  const maxValue = Math.max(...allValues);
  const spread = Math.max(0.01, maxValue - minValue);
  const yFor = (value: number) => bottom - ((value - minValue) / spread) * (bottom - top);

  const historyPoints = historyValues.map((value, index) => ({
    x: left + (todayX - left) * (index / (historyValues.length - 1)),
    y: yFor(value),
  }));
  const forecastPoints = [historyValues[historyValues.length - 1], ...forecastValues].map((value, index) => ({
    x: todayX + (right - todayX) * (index / forecastValues.length),
    y: yFor(value),
  }));

  return {
    historyPath: chartPath(historyPoints),
    forecastPath: chartPath(forecastPoints),
    currentLabel: formatOne(level),
    forecastLabel: formatOne(forecastValues[forecastValues.length - 1]),
  };
}

function buildCurveTimeline(snapshot: PhaseLeadSnapshot): {
  historyStartLabel: string;
  todayLabel: string;
  forecastEndLabel: string;
  dataCutoffLabel: string;
} {
  const asOfDate = parseDateOnly(snapshot.as_of);
  const horizonDays = snapshot.horizons.length > 0 ? Math.max(...snapshot.horizons) : 14;

  return {
    historyStartLabel: formatDateObject(asOfDate ? addDays(asOfDate, -7) : null),
    todayLabel: formatDateObject(asOfDate),
    forecastEndLabel: formatDateObject(asOfDate ? addDays(asOfDate, horizonDays) : null),
    dataCutoffLabel: formatDate(latestSourceDate(snapshot)),
  };
}

export const PhaseLeadResearchPage: React.FC<PhaseLeadResearchPageProps> = ({ audience = 'product' }) => {
  const [selectedVirus, setSelectedVirus] = useState<(typeof availableViruses)[number]>('Gesamt');
  const { snapshot, loading, error, reload } = usePhaseLeadSnapshot({
    virusTyp: selectedVirus,
  });
  const isAuth401 =
    error &&
    (((error as Error & { status?: number }).status === 401) ||
      /HTTP 401/.test(error.message));

  if (isAuth401 && !snapshot) {
    return <CockpitGate onUnlocked={reload} />;
  }

  if (loading && !snapshot) {
    return (
      <div className="peix phase-lead-page">
        <main className="phase-lead-shell">
          <div className="phase-lead-loading" role="status">
            <span aria-hidden="true" />
            Regional Media Watch lädt...
          </div>
        </main>
      </div>
    );
  }

  if (error && !snapshot) {
    return (
      <div className="peix phase-lead-page">
        <main className="phase-lead-shell">
          <Link to="/cockpit" className="phase-lead-back">
            Zurück ins Cockpit
          </Link>
          <section className="phase-lead-panel phase-lead-error" role="alert">
            <div className="phase-lead-kicker">Signal nicht verfügbar</div>
            <h1>Regional Media Watch konnte nicht geladen werden.</h1>
            <p>{error.message}</p>
            <button type="button" onClick={reload}>
              Erneut laden
            </button>
          </section>
        </main>
      </div>
    );
  }

  if (!snapshot) return null;

  const topRegions = snapshot.regions.slice(0, 8);
  const topRegion = snapshot.regions[0];
  const isLimbach = audience === 'limbach';
  const primaryAction = actionForRegion(topRegion, audience);
  const connectedSources = Object.keys(snapshot.sources).length;
  const sourceFreshness = sourceFreshnessLabel(snapshot);
  const modelConfidence = confidenceLabel(snapshot);
  const isMapOptimized = snapshot.summary.fit_mode === 'map_optimization';
  const isAggregate = snapshot.virus_typ === 'Gesamt' || Boolean(snapshot.aggregate);
  const heroHeadline = isLimbach ? 'Labor-Demand-Radar' : topRegion ? `${topRegion.region_code} zuerst.` : 'Region zuerst.';
  const topDriverLabel = topRegion ? aggregateDrivers(snapshot, topRegion.region_code) : '-';
  const heroScoreLabel = isAggregate ? 'Gesamt-Score' : 'GEGB';
  const signalCurve = buildSignalCurve(topRegion);
  const signalTimeline = buildCurveTimeline(snapshot);

  return (
    <div className="peix phase-lead-page">
      <main className="phase-lead-shell">
        <header className="phase-lead-hero phase-lead-hero--product">
          <div className="phase-lead-brandline">
            <Link to="/cockpit" className="phase-lead-back">
              Zurück ins Cockpit
            </Link>
            <span className="phase-lead-orbit-mark" aria-hidden="true" />
            <span>{isLimbach ? 'FluxEngine für Limbach' : 'Regional Media Watch'}</span>
          </div>
          <nav className="phase-lead-virus-switcher" aria-label="Virus auswählen">
            {availableViruses.map((virus) => (
              <button
                key={virus}
                type="button"
                className="phase-lead-virus-switcher__button"
                aria-pressed={selectedVirus === virus}
                onClick={() => setSelectedVirus(virus)}
              >
                {virus}
              </button>
            ))}
          </nav>
          <div className="phase-lead-hero__copy">
            <div className="phase-lead-kicker">
              <span className="phase-lead-live-dot" aria-hidden="true" />
              {isLimbach ? 'Limbach Pitch' : 'Media-Fokus'}
            </div>
            <h1>{heroHeadline}</h1>
            <p>
              {isLimbach
                ? 'Früh sehen, wo Atemwegsdiagnostik regional anzieht: dieselben Phase-Lead-Werte werden hier in Laborlogistik, Materialplanung und Arztkommunikation übersetzt.'
                : 'Regional Media Watch übersetzt Atemwegsdaten in eine klare Vorbereitungsempfehlung: welches Bundesland zuerst Aufmerksamkeit braucht, welcher Score dahintersteht und ob Budget noch gesperrt bleibt.'}
            </p>
            <div className="phase-lead-hero__cta-row">
              <div className={`phase-lead-primary-command phase-lead-primary-command--${primaryAction.tone}`}>
                <span aria-hidden="true">→</span>
                {primaryAction.label}
              </div>
              <div className="phase-lead-hero__fineprint">
                {isLimbach
                  ? 'Gleiche Daten, andere Entscheidung: Nachfrage früher disponieren.'
                  : 'Budget bleibt gesperrt, bis GELO-Sales angebunden sind.'}
              </div>
            </div>
          </div>

          <aside className="phase-lead-hero__visual" aria-label="Signalstatus">
            <div className="phase-lead-signal-card">
              <span>
                <HelpLabel
                  label={`${heroScoreLabel} erklären`}
                  title={heroScoreLabel}
                  body={
                    isAggregate
                      ? 'Verdichtet die Signale der verfügbaren Atemwegsviren zu einem regionalen Atemwegsdruck-Score. Er ist ein Priorisierungssignal, keine Umsatzprognose und keine medizinische Diagnose.'
                      : 'GEGB ist der growth-weighted burden score: aktueller Druck plus erwartetes Wachstum. Er zeigt, welche Region zuerst vorbereitet werden sollte.'
                  }
                >
                  {heroScoreLabel}
                </HelpLabel>
              </span>
              <strong>{formatOne(topRegion?.gegb)}</strong>
              <p>
                {isAggregate && topDriverLabel !== '-'
                  ? (
                    <>
                      {topDriverLabel} treiben das Signal am stärksten.
                      <Explain
                        label="Haupttreiber erklären"
                        title="Haupttreiber"
                        placement="left"
                      >
                        Die Haupttreiber zeigen, welche Viren in dieser Region den größten Beitrag zum Gesamt-Score leisten. Das hilft im Pitch zu erklären, warum eine Region vorne liegt.
                      </Explain>
                    </>
                  )
                  : `${snapshot.virus_typ} treibt das regionale Signal.`}
              </p>
            </div>
            <div className="phase-lead-signal-strip" aria-label="Top-Signale">
              <div>
                <span>
                  <HelpLabel
                    label="p(up) 7 Tage erklären"
                    title="p(up) 7 Tage"
                    body="Wahrscheinlichkeit, dass das regionale Signal in den nächsten 7 Tagen steigt. Hohe Werte heißen: jetzt vorbereiten, nicht automatisch Budget verschieben."
                  >
                    p(up) 7 Tage
                  </HelpLabel>
                </span>
                <strong>{formatPercent(topRegion?.p_up_h7)}</strong>
              </div>
              <div>
                <span>
                  <HelpLabel
                    label="Surge erklären"
                    title="Surge"
                    body="Surge meint ein stärkeres, kurzfristiges Anstiegsrisiko. Für GELO ist das ein Frühhinweis für Kampagnen- und Außendienstvorbereitung."
                  >
                    Surge
                  </HelpLabel>
                </span>
                <strong>{formatPercent(topRegion?.p_surge_h7)}</strong>
              </div>
              <div>
                <span>
                  <HelpLabel
                    label={isLimbach ? 'Logistikstatus erklären' : 'Budgetstatus erklären'}
                    title={isLimbach ? 'Logistik' : 'Budget'}
                    body={
                      isLimbach
                        ? 'Für Labor-Use-Cases bedeutet das: Kapazität, Material und Kurierlogik vorbereiten.'
                        : 'Budget ist bewusst gesperrt. Das Tool zeigt, wo Vorbereitung sinnvoll ist. Für echte Budgetfreigabe fehlen noch GELO-Sales- und Outcome-Daten.'
                    }
                    placement="left"
                  >
                    {isLimbach ? 'Logistik' : 'Budget'}
                  </HelpLabel>
                </span>
                <strong>{isLimbach ? 'planen' : 'gesperrt'}</strong>
              </div>
            </div>
          </aside>

          <aside className="phase-lead-hero__meta" aria-label="Signalstatus">
            <span>
              <HelpLabel
                label="Virus-Auswahl erklären"
                title="Virus-Auswahl"
                body="Gesamt fasst die Atemwegsviren zusammen. Die Einzelansichten bleiben wichtig, wenn Anna oder Johannes wissen wollen, welcher Erreger das Signal treibt."
              >
                {snapshot.virus_typ}
              </HelpLabel>
            </span>
            <span>
              <HelpLabel
                label="Berechnungsdatum erklären"
                title="Berechnungsdatum"
                body="Das ist der Stand der Berechnung. Der Datenstand kann etwas älter sein, weil öffentliche Quellen mit Meldeverzug eintreffen."
              >
                {formatDate(snapshot.as_of)}
              </HelpLabel>
            </span>
            <span>
              <HelpLabel
                label="Prognosehorizont erklären"
                title="Prognosehorizont"
                body="Die Seite bewertet mehrere Horizonte. Für den Pitch ist vor allem 7 Tage interessant: genug früh für Vorbereitung, nah genug für operative Entscheidungen."
              >
                {snapshot.horizons.join('/')} Tage Horizont
              </HelpLabel>
            </span>
            <span>
              <HelpLabel
                label="MAP-Optimierung erklären"
                title={isMapOptimized ? 'MAP optimiert' : 'Schnellmodus'}
                body={
                  isMapOptimized
                    ? 'MAP optimiert heißt: Die schwere Berechnung wurde aus den echten Quellen vorab berechnet und gespeichert. Die Seite zeigt also keinen schnellen Demo-Fallback.'
                    : 'Schnellmodus heißt: Das System kann eine Ansicht liefern, auch wenn noch kein gespeichertes schweres Ergebnis vorliegt.'
                }
                placement="left"
              >
                {isMapOptimized ? 'MAP optimiert' : 'Schnellmodus'}
              </HelpLabel>
            </span>
          </aside>
        </header>

        <section className={`phase-lead-panel phase-lead-action phase-lead-action--${primaryAction.tone}`}>
          <div>
            <div className="phase-lead-kicker">
              <HelpLabel
                label="Nächste Aktion erklären"
                title="Nächste Aktion"
                body={
                  isLimbach
                    ? 'Die Aktion übersetzt das Frühwarnsignal in Laborplanung: disponieren, beobachten oder halten.'
                    : 'Die Aktion ist ein Vorbereitungshinweis. Sie sagt, wo GELO jetzt Creatives, Apothekenlisten und regionale Pakete prüfen sollte.'
                }
              >
                Nächste Aktion
              </HelpLabel>
            </div>
            <h2>{topRegionHeadline(topRegion, audience)}</h2>
            <p>{primaryAction.explanation}</p>
          </div>
          <div className="phase-lead-action__command">{primaryAction.label}</div>
        </section>

        <section className="phase-lead-live-grid phase-lead-live-grid--product" aria-label="Signal metrics">
          <div className="phase-lead-live-metric">
            <span>
              <HelpLabel
                label="p(up) Kennzahl erklären"
                title="p(up) 7 Tage"
                body="Das ist die Anstiegswahrscheinlichkeit für die Top-Region. Hohe Werte bedeuten: Früh handeln, weil die Welle wahrscheinlich noch stärker wird."
              >
                p(up) 7 Tage
              </HelpLabel>
            </span>
            <strong>{formatPercent(topRegion?.p_up_h7)}</strong>
            <small>{topRegion?.region ?? 'Keine Region'}</small>
          </div>
          <div className="phase-lead-live-metric">
            <span>
              <HelpLabel
                label="Surge-Risiko erklären"
                title="Surge-Risiko"
                body="Surge meint einen stärkeren Sprung nach oben. Für den Pitch ist das der Hinweis: Nicht nur Wachstum, sondern mögliches Beschleunigen."
              >
                Surge-Risiko
              </HelpLabel>
            </span>
            <strong>{formatPercent(topRegion?.p_surge_h7)}</strong>
            <small>Schwelle für Vorbereitung</small>
          </div>
          <div className="phase-lead-live-metric">
            <span>
              <HelpLabel
                label="Modellvertrauen erklären"
                title="Modellvertrauen"
                body="Das Vertrauen fasst zusammen, ob die schwere Optimierung sauber lief und ob Warnungen vorliegen. Es ersetzt keine fachliche Prüfung."
              >
                Modellvertrauen
              </HelpLabel>
            </span>
            <strong>{modelConfidence}</strong>
            <small>{snapshot.summary.warning_count} Warnungen</small>
          </div>
          <div className="phase-lead-live-metric">
            <span>
              <HelpLabel
                label="Datenstand erklären"
                title="Datenstand"
                body="Die Zahl zeigt, wie viele öffentliche Quellen verbunden sind. Das Datum darunter zeigt den neuesten Eingang und den Meldeverzug."
              >
                Datenstand
              </HelpLabel>
            </span>
            <strong>{connectedSources} Quellen</strong>
            <small>{sourceFreshness}</small>
          </div>
        </section>

        <section className="phase-lead-panel phase-lead-sales-gate" aria-labelledby="phase-lead-sales-gate-title">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">
                <HelpLabel
                  label="Budget-Gate erklären"
                  title={isLimbach ? 'Laborbedarf' : 'Budget-Gate'}
                  body={
                    isLimbach
                      ? 'Das Tool empfiehlt operative Vorbereitung für Laborbedarf, aber keine medizinische Einzelfallentscheidung.'
                      : 'Das Tool empfiehlt Vorbereitung, aber keine automatische Media-Budgetverschiebung. Dafür fehlen noch GELO-Sales- und Outcome-Daten.'
                  }
                >
                  {isLimbach ? 'Laborbedarf' : 'Budget-Gate'}
                </HelpLabel>
              </div>
              <h2 id="phase-lead-sales-gate-title">
                {isLimbach
                  ? 'Von Frühwarnsignal zu Laborplanung.'
                  : 'Budget bleibt shadow-only bis GELO-Sales angebunden sind.'}
              </h2>
            </div>
            <p>
              {isLimbach
                ? 'Die Limbach Gruppe könnte externe Atemwegs-Frühsignale nutzen, um Probenlogistik, Praxisbedarf und regionale Kommunikation früher zu planen.'
                : 'Das Signal priorisiert Vorbereitung, nicht automatische Umschichtung. Sales- und Outcome-Daten fehlen noch für echte Budgetfreigabe.'}
              {!isLimbach ? (
                <Explain
                  label="Warum jetzt GELO zeigen erklären"
                  title="Warum jetzt GELO zeigen?"
                  placement="left"
                >
                  Es ist jetzt sinnvoll für GELO, weil der Nutzen ohne Salesdaten schon sichtbar ist: Regionen priorisieren, Vorbereitung auslösen und Grenzen transparent machen. Mit GELO-Salesdaten wird daraus später ein Budget-Gate.
                </Explain>
              ) : null}
            </p>
          </div>
          <div className="phase-lead-decision-grid">
            <article>
              <span>
                <HelpLabel
                  label={isLimbach ? 'Operations erklären' : 'Heute erlaubt erklären'}
                  title={isLimbach ? 'Operations' : 'Heute erlaubt'}
                  body={
                    isLimbach
                      ? 'Hier wird das Signal in konkrete Laborvorbereitung übersetzt.'
                      : 'Diese Maßnahmen kann GELO schon nutzen, ohne Budget automatisch zu verschieben.'
                  }
                >
                  {isLimbach ? 'Operations' : 'Heute erlaubt'}
                </HelpLabel>
              </span>
              <b>
                <HelpLabel
                  label={isLimbach ? 'Probenlogistik vorbereiten erklären' : 'Vorbereiten erklären'}
                  title={isLimbach ? 'Probenlogistik vorbereiten' : 'Vorbereiten'}
                  body={
                    isLimbach
                      ? 'Kurierfenster, regionale Last und Materialflüsse früher planen.'
                      : 'Regionale Creatives, Zielgruppen, Inventar und Außendiensthinweise bereitlegen.'
                  }
                >
                  {isLimbach ? 'Probenlogistik vorbereiten' : 'Vorbereiten'}
                </HelpLabel>
              </b>
              <p>{isLimbach ? 'Regionale Kurierfenster, Abholspitzen und Laborstandorte frühzeitig einplanen.' : 'Regionale Creatives, Inventar, Zielgruppen und Apothekenlisten prüfen.'}</p>
            </article>
            <article>
              <span>
                <HelpLabel
                  label={isLimbach ? 'Versorgung erklären' : 'Noch blockiert erklären'}
                  title={isLimbach ? 'Versorgung' : 'Noch blockiert'}
                  body={
                    isLimbach
                      ? 'Das Frühwarnsignal kann helfen, Engpässe bei Material und Testkapazität früher zu vermeiden.'
                      : 'Automatische Budgetverschiebung bleibt blockiert, bis echte GELO-Nachfrage- und Ergebnisdaten angebunden sind.'
                  }
                >
                  {isLimbach ? 'Versorgung' : 'Noch blockiert'}
                </HelpLabel>
              </span>
              <b>
                <HelpLabel
                  label={isLimbach ? 'Reagenzien und Entnahmematerial erklären' : 'Budget verschieben erklären'}
                  title={isLimbach ? 'Reagenzien und Entnahmematerial' : 'Budget verschieben'}
                  body={
                    isLimbach
                      ? 'Material muss oft früher disponiert werden als die sichtbare Nachfrage steigt.'
                      : 'Das Tool kann eine starke Empfehlung geben. Die eigentliche Budgetentscheidung soll erst mit Sales-Validierung automatisiert werden.'
                  }
                >
                  {isLimbach ? 'Reagenzien und Entnahmematerial' : 'Budget verschieben'}
                </HelpLabel>
              </b>
              <p>{isLimbach ? 'Respiratorische Tests, Abstrichmaterial und Verbrauchsgüter entlang regionaler Wellen vorbereiten.' : 'Ohne GELO-Sales bleibt jede Aktivierung eine manuelle Business-Entscheidung.'}</p>
            </article>
            <article>
              <span>
                <HelpLabel
                  label={isLimbach ? 'Partnernetz erklären' : 'Nächster Datenhebel erklären'}
                  title={isLimbach ? 'Partnernetz' : 'Nächster Datenhebel'}
                  body={
                    isLimbach
                      ? 'Der Nutzen entsteht, wenn Labore Praxen und Kliniken vor der Spitze informieren können.'
                      : 'Der nächste große Schritt ist die Verbindung mit GELO-Sales, damit aus Signalqualität Business-Wirkung wird.'
                  }
                >
                  {isLimbach ? 'Partnernetz' : 'Nächster Datenhebel'}
                </HelpLabel>
              </span>
              <b>
                <HelpLabel
                  label={isLimbach ? 'Arztkommunikation timen erklären' : 'Sales anschließen erklären'}
                  title={isLimbach ? 'Arztkommunikation timen' : 'Sales anschließen'}
                  body={
                    isLimbach
                      ? 'Regionale Kommunikation kann starten, bevor Diagnostiknachfrage in den eigenen Zahlen voll sichtbar ist.'
                      : 'Mit GELO-Salesdaten lässt sich prüfen, ob Frühwarnsignale wirklich Absatz, Verfügbarkeit oder Kampagnenwirkung verbessern.'
                  }
                  placement="left"
                >
                  {isLimbach ? 'Arztkommunikation timen' : 'Sales anschließen'}
                </HelpLabel>
              </b>
              <p>{isLimbach ? 'Praxen, MVZ und Kliniken regional informieren, bevor die Diagnostiknachfrage sichtbar steigt.' : 'Danach kann das Signal gegen Nachfrage und Kampagnenwirkung kalibriert werden.'}</p>
            </article>
          </div>
        </section>

        <section className="phase-lead-panel" aria-labelledby="phase-lead-region-title">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">Regionale Priorisierung</div>
              <h2 id="phase-lead-region-title">
                {isLimbach
                  ? 'Welche Regionen Laborbedarf früher anzeigen.'
                  : 'Welche Bundesländer jetzt Aufmerksamkeit brauchen.'}
              </h2>
            </div>
            <p>
              {isLimbach
                ? 'Sortiert nach Gesamt-Score: hohe Werte markieren Regionen, in denen Atemwegsdiagnostik, Probenlogistik und Praxisbedarf früher geplant werden sollten.'
                : 'Sortiert nach GEGB: ein growth-weighted burden score für Media-Priorisierung. Höher bedeutet: mehr erwartete Last bei positivem Wachstum.'}
            </p>
          </div>
          <div className="phase-lead-table-wrap">
            <table className="phase-lead-table">
              <thead>
                <tr>
                  <th>
                    <HelpLabel
                      label="Region Tabellenspalte erklären"
                      title="Region"
                      body="Bundesland, für das das Signal berechnet wird."
                    >
                      Region
                    </HelpLabel>
                  </th>
                  <th>
                    <HelpLabel
                      label={isLimbach ? 'Laboraktion Tabellenspalte erklären' : 'Empfehlung Tabellenspalte erklären'}
                      title={isLimbach ? 'Laboraktion' : 'Empfehlung'}
                      body={
                        isLimbach
                          ? 'Kurzfassung der empfohlenen Laborvorbereitung pro Region.'
                          : 'Kurzfassung der empfohlenen Media- oder Vorbereitungsaktion pro Region.'
                      }
                    >
                      {isLimbach ? 'Laboraktion' : 'Empfehlung'}
                    </HelpLabel>
                  </th>
                  {isAggregate ? (
                    <th>
                      <HelpLabel
                        label="Haupttreiber Tabellenspalte erklären"
                        title="Haupttreiber"
                        body="Die zwei Viren, die in der jeweiligen Region am stärksten zum Gesamt-Score beitragen."
                      >
                        Haupttreiber
                      </HelpLabel>
                    </th>
                  ) : null}
                  <th>
                    <HelpLabel
                      label="p(up) h7 Tabellenspalte erklären"
                      title="p(up) h7"
                      body="Wahrscheinlichkeit für steigendes Signal über den 7-Tage-Horizont."
                    >
                      p(up) h7
                    </HelpLabel>
                  </th>
                  <th>
                    <HelpLabel
                      label="Surge h7 Tabellenspalte erklären"
                      title="Surge h7"
                      body="Risiko für einen stärkeren kurzfristigen Anstieg in den nächsten 7 Tagen."
                    >
                      Surge h7
                    </HelpLabel>
                  </th>
                  <th>
                    <HelpLabel
                      label="Wachstum Tabellenspalte erklären"
                      title="Wachstum"
                      body="Aktuelle Wachstumsrichtung des regionalen Signals. Plus bedeutet steigende Aktivität."
                    >
                      Wachstum
                    </HelpLabel>
                  </th>
                  <th>
                    <HelpLabel
                      label={`${isAggregate ? 'Gesamt-Score' : 'GEGB'} Tabellenspalte erklären`}
                      title={isAggregate ? 'Gesamt-Score' : 'GEGB'}
                      body={
                        isAggregate
                          ? 'Der Gesamt-Score verdichtet mehrere Atemwegsviren zu einem regionalen Prioritätswert.'
                          : 'GEGB gewichtet aktuelle Last und erwartetes Wachstum für dieses einzelne Virus.'
                      }
                      placement="left"
                    >
                      {isAggregate ? 'Gesamt-Score' : 'GEGB'}
                    </HelpLabel>
                  </th>
                </tr>
              </thead>
              <tbody>
                {topRegions.map((region) => {
                  const action = actionForRegion(region, audience);
                  return (
                    <tr key={region.region_code}>
                      <td>{region.region_code} - {region.region}</td>
                      <td>
                        <span className={`phase-lead-badge phase-lead-badge--${action.tone}`}>
                          {action.label}
                        </span>
                      </td>
                      {isAggregate ? (
                        <td>
                          <span className="phase-lead-driver">
                            {aggregateDrivers(snapshot, region.region_code)}
                          </span>
                        </td>
                      ) : null}
                      <td>{formatPercent(region.p_up_h7)}</td>
                      <td>{formatPercent(region.p_surge_h7)}</td>
                      <td>{formatSigned(region.current_growth)}</td>
                      <td>{formatOne(region.gegb)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="phase-lead-grid phase-lead-grid--two" aria-label="Operativer Kontext">
          <article className="phase-lead-panel phase-lead-output">
            <div className="phase-lead-kicker">
              <HelpLabel
                label="Datenbasis erklären"
                title="Datenbasis"
                body="Die Seite nutzt reale öffentliche Quellen. Die Quellen erklären, warum das Signal früher sein kann als reine Salesdaten."
              >
                Datenbasis
              </HelpLabel>
            </div>
            <h2>{isLimbach ? 'Öffentliche Frühsignale sind verbunden.' : 'Live-Quellen sind verbunden.'}</h2>
            <div className="phase-lead-source-list">
              {Object.entries(snapshot.sources).map(([source, status]) => (
                <div key={source} className="phase-lead-source-pill">
                  <b>
                    <HelpLabel
                      label={`${sourceLabels[source] ?? source} erklären`}
                      title={sourceLabels[source] ?? source}
                      body={sourceHelp[source] ?? 'Diese Quelle liefert ein ergänzendes regionales Signal für die Berechnung.'}
                    >
                      {sourceLabels[source] ?? source}
                    </HelpLabel>
                  </b>
                  <span>{status.rows} Zeilen</span>
                  <small>{formatDate(status.latest_event_date)} · {status.units.length} Einheiten</small>
                </div>
              ))}
            </div>
          </article>
          <article className="phase-lead-panel phase-lead-output">
            <div className="phase-lead-kicker">
              <HelpLabel
                label="Modellstatus erklären"
                title="Modellstatus"
                body="Hier sieht man, ob die Berechnung sauber lief, wie groß das Datenfenster ist und ob Warnungen vorliegen."
              >
                Modellstatus
              </HelpLabel>
            </div>
            <h2>{snapshot.summary.converged ? 'Optimierung konvergiert.' : 'Optimierung prüfen.'}</h2>
            <p>
              {isLimbach
                ? 'Für Limbach wäre der nächste Schritt, diese Frühindikatoren mit eigenen anonymisierten Testvolumina, Standortlogistik und Materialverbrauch zu kalibrieren.'
                : isMapOptimized
                  ? 'Das Cockpit nutzt das gespeicherte MAP-Ergebnis aus dem Nachtlauf.'
                  : 'Das Cockpit nutzt gerade den schnellen Fallback, bis ein MAP-Ergebnis vorliegt.'}
            </p>
            <div className="phase-lead-model-meta">
              <span>
                <HelpLabel
                  label="Beobachtungen erklären"
                  title="Beobachtungen"
                  body="Anzahl der Datenpunkte, die für die Berechnung verwendet wurden."
                >
                  Beobachtungen: {snapshot.summary.observation_count}
                </HelpLabel>
              </span>
              <span>
                <HelpLabel
                  label="Modellfenster erklären"
                  title="Fenster"
                  body="Zeitraum, aus dem das Modell gelernt hat. Die öffentlichen Daten laufen mit Meldeverzug ein."
                >
                  Fenster: {formatDate(snapshot.summary.window_start)} – {formatDate(snapshot.summary.window_end)}
                </HelpLabel>
              </span>
              <span>
                <HelpLabel
                  label="Zielwert erklären"
                  title="Zielwert"
                  body="Technischer Optimierungswert des Modells. Wichtig für Debugging, nicht als Business-Kennzahl."
                  placement="left"
                >
                  Zielwert: {formatOne(snapshot.summary.objective_value)}
                </HelpLabel>
              </span>
            </div>
          </article>
        </section>

        {snapshot.warnings.length > 0 ? (
          <section className="phase-lead-panel" aria-label="Modellhinweise">
            <div className="phase-lead-kicker">Modellhinweise</div>
            <ul className="phase-lead-warning-list">
              {snapshot.warnings.slice(0, 4).map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="phase-lead-panel phase-lead-curve-panel" aria-labelledby="phase-lead-curve-title">
          <div className="phase-lead-section-head">
            <div>
              <div className="phase-lead-kicker">Verlauf</div>
              <h2 id="phase-lead-curve-title">
                <HelpLabel
                  label="Bisherige Kurve und Prognose erklären"
                  title="Bisherige Kurve und Prognose"
                  body="Links steht der modellierte Verlauf bis zum Berechnungsdatum. Rechts zeigt die gestrichelte Linie die Prognose. Die Datumsfelder darunter zeigen, auf welchen Zeitraum sich die Kurve bezieht."
                >
                  Bisherige Kurve und Prognose.
                </HelpLabel>
              </h2>
            </div>
            <p>
              Die Linie zeigt das aktuelle Top-Signal: links der bisherige Verlauf,
              rechts die Modellprojektion für die nächsten Tage.
              <Explain
                label="Datumsachse erklären"
                title="Datumsachse"
                placement="left"
              >
                Die Prognose startet am Berechnungsdatum. Die Wahrheit endet beim neuesten Datenstand, weil Meldedaten erst verzögert eintreffen.
              </Explain>
            </p>
          </div>
          <div className="phase-lead-curve-layout">
            <div className="phase-lead-curve-card">
              <svg
                className="phase-lead-curve"
                viewBox="0 0 680 260"
                role="img"
                aria-label="Signalverlauf und Prognose"
                preserveAspectRatio="none"
              >
                <defs>
                  <linearGradient id="phaseLeadHistoryGradient" x1="0" x2="1" y1="0" y2="0">
                    <stop offset="0%" stopColor="#00d6ff" />
                    <stop offset="100%" stopColor="#ff2a59" />
                  </linearGradient>
                </defs>
                <rect x="0" y="0" width="680" height="260" rx="8" />
                <path className="phase-lead-curve-grid" d="M 34 74 H 646 M 34 128 H 646 M 34 182 H 646" />
                <path className="phase-lead-curve-area" d={`${signalCurve.historyPath} L 420 220 L 34 220 Z`} />
                <path className="phase-lead-curve-history" d={signalCurve.historyPath} />
                <path className="phase-lead-curve-forecast" d={signalCurve.forecastPath} />
                <line className="phase-lead-curve-today" x1="420" x2="420" y1="28" y2="226" />
              </svg>
              <div className="phase-lead-curve-label phase-lead-curve-label--history">Bisher</div>
              <div className="phase-lead-curve-label phase-lead-curve-label--today">Heute</div>
              <div className="phase-lead-curve-label phase-lead-curve-label--forecast">Prognose</div>
              <div className="phase-lead-curve-date-row" aria-label="Datumsachse Signalverlauf">
                <div>
                  <span>Verlauf ab</span>
                  <strong>{signalTimeline.historyStartLabel}</strong>
                </div>
                <div>
                  <span>Berechnet</span>
                  <strong>{signalTimeline.todayLabel}</strong>
                </div>
                <div>
                  <span>Prognose bis</span>
                  <strong>{signalTimeline.forecastEndLabel}</strong>
                </div>
              </div>
            </div>
            <div className="phase-lead-curve-copy">
              <div>
                <span>Region</span>
                <strong>{topRegion?.region ?? '-'}</strong>
              </div>
              <div>
                <span>Aktuell</span>
                <strong>{signalCurve.currentLabel}</strong>
              </div>
              <div>
                <span>Prognose-Ende</span>
                <strong>{signalCurve.forecastLabel}</strong>
              </div>
              <div>
                <span>Wahrheit</span>
                <strong>Datenstand {signalTimeline.dataCutoffLabel}</strong>
              </div>
            </div>
          </div>
        </section>

        <footer className="phase-lead-footer">
          <div>
            <b>Produktstatus</b>
            <p>
              {isLimbach
                ? 'Pitch-Version für die Limbach Gruppe: gleiche Phase-Lead-Werte, übersetzt in Labor-Demand, Probenlogistik und Praxispartner-Kommunikation.'
                : 'Live-Frühwarnsignal für Vorbereitung. Budgetfreigabe bleibt blockiert, bis GELO-Sales und Outcome-Validierung angeschlossen sind.'}
            </p>
          </div>
          <Link to="/cockpit" className="phase-lead-footer__link">
            Zurück ins Cockpit
          </Link>
        </footer>
      </main>
    </div>
  );
};

export default PhaseLeadResearchPage;
