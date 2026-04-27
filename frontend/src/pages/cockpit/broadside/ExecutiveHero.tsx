import React, { useMemo, useState } from 'react';
import type { CockpitSnapshot } from '../types';
import MediaPlanUploadModal from './MediaPlanUploadModal';

/**
 * ExecutiveHero — 30-Sekunden-Überblick ganz oben, zwischen Status-Strip
 * und § I. Drei Kacheln, die ein GELO-Marketing-Manager ohne ML-Background
 * sofort versteht: wo sind wir in der Saison, was sagt der Atlas gerade,
 * wie würde ein Euro-Shift aussehen.
 *
 * Kein Fake-Budget: die Demo-Zahl kommt aus einer klar als "Demo"
 * markierten Formel auf Basis der echten Top-Risers. Sobald der
 * Media-Plan verbunden ist (2026-04-21 CSV-Upload-Bridge), ersetzen
 * echte EUR-Werte aus ``snapshot.mediaPlan`` + ``primaryRecommendation
 * .amountEur`` die Demo-Zahlen und der "Demo"-Tag verschwindet.
 */

interface Props {
  snapshot: CockpitSnapshot;
  supportedViruses?: readonly string[];
  onReload?: () => void;
}

const STRONG_RISER_THRESHOLD = 0.15;
const DEMO_ASSUMED_WEEKLY_BUDGET = 100_000;

// Season phase heuristic: ISO-Week ranges — DE-spezifisch, ja.
function detectSeasonPhase(isoWeek: string): {
  label: string;
  tone: 'peak' | 'shoulder' | 'off';
  note: string;
} {
  const m = isoWeek.match(/\d+/);
  const kw = m ? parseInt(m[0], 10) : 0;
  if (kw >= 40 || kw <= 10) {
    return {
      label: 'Peak-Saison',
      tone: 'peak',
      note: 'Wellen-Fenster aktiv. Empfehlungen haben größten Hebel.',
    };
  }
  if ((kw >= 11 && kw <= 17) || (kw >= 36 && kw <= 39)) {
    return {
      label: 'Übergangs-Saison',
      tone: 'shoulder',
      note: 'Welle baut ab oder auf. Signal vorhanden, aber Trigger vorsichtig.',
    };
  }
  return {
    label: 'Post-Saison · Sparmodus',
    tone: 'off',
    note:
      'Aktuell keine Welle. Das Tool ruht bewusst: keine Empfehlung, kein Budget-Shift — das ist Kostendisziplin, kein Stillstand.',
  };
}

export const ExecutiveHero: React.FC<Props> = ({ snapshot, supportedViruses, onReload }) => {
  const [mediaPlanModalOpen, setMediaPlanModalOpen] = useState(false);
  const phase = useMemo(() => detectSeasonPhase(snapshot.isoWeek), [snapshot.isoWeek]);

  const topRiser = useMemo(() => {
    return [...snapshot.regions]
      .filter(
        (r) =>
          typeof r.delta7d === 'number' &&
          r.decisionLabel !== 'TrainingPending',
      )
      .sort((a, b) => (b.delta7d ?? 0) - (a.delta7d ?? 0))[0];
  }, [snapshot.regions]);

  const topFaller = useMemo(() => {
    return [...snapshot.regions]
      .filter(
        (r) =>
          typeof r.delta7d === 'number' &&
          r.decisionLabel !== 'TrainingPending',
      )
      .sort((a, b) => (a.delta7d ?? 0) - (b.delta7d ?? 0))[0];
  }, [snapshot.regions]);

  const hasStrongSignal =
    topRiser && typeof topRiser.delta7d === 'number' && topRiser.delta7d > STRONG_RISER_THRESHOLD;

  const mediaConnected = snapshot.mediaPlan?.connected === true;
  const liveTotalEur =
    typeof snapshot.mediaPlan?.totalWeeklySpendEur === 'number'
      ? snapshot.mediaPlan.totalWeeklySpendEur
      : null;
  const liveShiftEur =
    typeof snapshot.primaryRecommendation?.amountEur === 'number'
      ? snapshot.primaryRecommendation.amountEur
      : null;

  const demoShiftEur =
    topRiser && topFaller && typeof topRiser.delta7d === 'number'
      ? Math.round((DEMO_ASSUMED_WEEKLY_BUDGET * Math.min(0.35, topRiser.delta7d * 0.4)) / 1_000) * 1_000
      : null;
  // 2026-04-21 Media-Plan-Integration: wenn ein echter Plan hochgeladen
  // wurde, nehmen wir die amountEur aus primaryRecommendation; fallback
  // bleibt der Demo-Wert.
  const shiftEur = mediaConnected ? liveShiftEur : demoShiftEur;

  const virusLabel = snapshot.virusLabel || snapshot.virusTyp;

  // 2026-04-21 Integrity-Fix: dedicated health banner at the top of the hero
  // whenever the backend reports DATA_STALE or DRIFT_WARN. Mirrors the
  // `modelStatus.note` copy so the user sees *why* the banner tripped.
  const readiness = snapshot.modelStatus?.forecastReadiness ?? 'UNKNOWN';
  const freshness = snapshot.modelStatus?.forecastFreshness ?? null;
  const accuracy = snapshot.modelStatus?.accuracyLatest ?? null;
  const calibration = snapshot.modelStatus?.scaleCalibration ?? null;
  const integrityWarning = (() => {
    if (readiness === 'DATA_STALE') {
      const latest = freshness?.latestForecastDate ?? '—';
      const days = freshness?.daysFromToday;
      const daysBack =
        typeof days === 'number' && days < 0 ? `${Math.abs(days)} Tage` : '—';
      return {
        tone: 'stale' as const,
        title: 'Forecast ist retrospektiv — keine Zukunft',
        body: `Letzter Forecast-Punkt ${latest} (${daysBack} in der Vergangenheit). Der Fan-Chart ist ein Rückblick, keine Prognose. Daten-Pipeline oder täglicher Forecast-Cron stehen.`,
      };
    }
    if (readiness === 'SEASON_OFF') {
      // 2026-04-21 Pfad-C: Post-Saison-Pause. Bewusst sanfter Ton — das Tool
      // ruht narrativ, die Zahlen sollen den Nutzer nicht alarmieren.
      const postSamples = accuracy?.post?.samples ?? 0;
      return {
        tone: 'off' as const,
        title: 'Post-Saison · Drift-Monitor pausiert',
        body: `Aktuelle Woche liegt in KW 11–39. Auf flachem Signal ist Accuracy-Rauschen kein belastbares Drift-Indiz — der Monitor ruht bewusst (${postSamples} Post-Saison-Paare zur Einsicht). Das Gate springt wieder scharf, sobald Peak-Saison ab KW 40 neue Datenpunkte liefert.`,
      };
    }
    if (readiness === 'DRIFT_WARN') {
      // 2026-04-21 Pfad-C: bevorzugt Peak-Bucket anzeigen wenn vorhanden,
      // sonst overall. Sample-Size dazu, damit Nutzer die Aussagekraft
      // einschätzen können.
      const peak = accuracy?.peak;
      const usePeak = (peak?.samples ?? 0) > 0;
      const src = usePeak ? peak : accuracy;
      const scope = usePeak ? 'Peak-Saison' : 'Gesamt-Fenster';
      const samples = src?.samples ?? 0;
      const parts: string[] = [];
      if (
        typeof src?.correlation === 'number' &&
        src.correlation < 0.3 &&
        samples >= 20
      ) {
        parts.push(`Korrelation ${src.correlation.toFixed(2)}`);
      }
      if (src?.driftDetected) parts.push('Drift-Detector aktiv');
      return {
        tone: 'drift' as const,
        title: 'Modell driftet — Ranking nicht handlungsrelevant',
        body: `Live-Monitor (${scope}, N=${samples}): ${parts.join(' · ') || 'Accuracy-Signal unter Threshold'}. Die Bundesländer-Empfehlungen sind in dieser Phase nicht als Grundlage für Budget-Shifts geeignet.`,
      };
    }
    // 2026-04-21 A1 Root-Cause-Fix: soft note when forecast IS forward-
    // looking but AMELAG feature-cutoff is > 7 days behind today. Surface
    // the gap so readers see "the model's view-of-the-world is N days old"
    // without raising a red DATA_STALE banner.
    const lagDays = freshness?.featureLagDays;
    const featureAsOf = freshness?.featureAsOf;
    if (
      typeof lagDays === 'number' &&
      lagDays > 7 &&
      featureAsOf &&
      freshness?.isFuture
    ) {
      return {
        tone: 'lag' as const,
        title: 'Forecast läuft mit Feature-Lücke',
        body: `AMELAG-Cutoff ${featureAsOf} (${lagDays} Tage alt). Die Trajektorie ist zukunftsgerichtet, aber das Modell extrapoliert über die Lücke, bis die nächsten Abwasser-Messungen eintreffen.`,
      };
    }
    return null;
  })();

  // Status-Chip-Daten (ehemaliger StatusStrip)
  const isoMatch = snapshot.isoWeek.match(/(\d+)\D+(\d+)/);
  const dataKw = isoMatch ? Math.max(1, parseInt(isoMatch[1], 10) - 1) : null;
  const dataYear = isoMatch ? parseInt(isoMatch[2], 10) : null;
  const horizonDays = snapshot.modelStatus?.horizonDays ?? 14;
  const activeRegions = snapshot.regions.filter(
    (r) => r.decisionLabel !== 'TrainingPending',
  ).length;
  const virusCount = supportedViruses?.length ?? 0;

  // Confidence-Tag in Worten — ergänzt die Saison-Phase im Kicker.
  const confidenceTag = hasStrongSignal ? 'Trigger aktiv' : 'Ruhiges Signal';

  return (
    <section className="exec-hero" id="sec-exec-hero">
      <div className="exec-hero-main">
        <div className="exec-hero-headline">
          <div className="exec-hero-kicker">
            <span className={`exec-phase-tag exec-phase-${phase.tone}`}>{phase.label}</span>
            <span className={`exec-confidence-tag exec-confidence-${hasStrongSignal ? 'on' : 'off'}`}>{confidenceTag}</span>
          </div>
          <h1 className="exec-hero-title">
            {hasStrongSignal && topRiser ? (
              <>
                Welle vorn in <b>{topRiser.name}</b>
                <span className="exec-delta">
                  {' '}+{Math.round((topRiser.delta7d ?? 0) * 100)} % in 7 Tagen
                </span>
              </>
            ) : (
              <>Kein Wellen-Trigger diese Woche</>
            )}
          </h1>
          <p className="exec-hero-sub">
            {hasStrongSignal
              ? `${virusLabel}-Aktivität steigt hier merklich. ${phase.note}`
              : `Alle 16 Bundesländer unterhalb des Aktivierungs-Schwellwerts. ${phase.note}`}
          </p>
          <div className="exec-hero-shift">
            {shiftEur && hasStrongSignal ? (
              <>
                <span className="exec-shift-label">Shift-Kandidat</span>
                <span className="exec-shift-value">
                  {shiftEur.toLocaleString('de-DE')} €
                  <span className="exec-direction">
                    {' '}{topFaller?.code} → {topRiser?.code}
                  </span>
                </span>
                <span className="exec-shift-note">
                  {mediaConnected
                    ? `aus Media-Plan (${liveTotalEur ? `${liveTotalEur.toLocaleString('de-DE')} €` : '—'} Wochenbudget) · Signal ${snapshot.primaryRecommendation?.signalScore?.toFixed(2) ?? snapshot.primaryRecommendation?.confidence?.toFixed(2) ?? '—'} · Freigabe über Gates`
                    : 'Demo-Szene auf 100 k € Wochenbudget · keine automatische Freigabe'}
                </span>
                <button
                  type="button"
                  className="exec-upload-btn"
                  onClick={() => setMediaPlanModalOpen(true)}
                  title="Media-Plan via CSV hochladen"
                >
                  {mediaConnected ? 'Plan bearbeiten' : '⬆ CSV hochladen'}
                </button>
              </>
            ) : (
              <>
                <span className="exec-shift-label">Kein Shift</span>
                <span className="exec-shift-note">
                  {hasStrongSignal
                    ? 'Shift-Betrag wartet auf Media-Plan-Anbindung und Gate-Prüfung.'
                    : 'Keine Budgetfreigabe — Tool schont, bis ein sauberer Trigger kommt.'}
                </span>
                <button
                  type="button"
                  className="exec-upload-btn"
                  onClick={() => setMediaPlanModalOpen(true)}
                  title="Media-Plan via CSV hochladen"
                >
                  {mediaConnected ? 'Plan bearbeiten' : '⬆ CSV hochladen'}
                </button>
              </>
            )}
          </div>
        </div>
        {integrityWarning ? (
          <aside
            className={`exec-hero-integrity exec-integrity-${integrityWarning.tone}`}
            role="alert"
          >
            <div className="exec-integrity-title">{integrityWarning.title}</div>
            <div className="exec-integrity-body">{integrityWarning.body}</div>
          </aside>
        ) : null}
      </div>

      <div className="exec-hero-chips" aria-label="Tool-Status">
        <span className="exec-chip">
          <span className="exec-chip-label">Viren</span>
          <b>{virusCount}</b>
          <span className="exec-chip-sep">/</span>4
        </span>
        <span className="exec-chip">
          <span className="exec-chip-label">Bundesländer</span>
          <b>{activeRegions}</b>
          <span className="exec-chip-sep">/</span>16
        </span>
        <span className="exec-chip">
          <span className="exec-chip-label">Daten</span>
          KW <b>{dataKw ?? '—'}</b>
          {' / '}
          {dataYear ?? '—'}
        </span>
        <span className="exec-chip">
          <span className="exec-chip-label">Horizont</span>
          <b>{horizonDays}</b> d
        </span>
        <span className={`exec-chip ${mediaConnected ? 'exec-chip-ok' : 'exec-chip-wait'}`}>
          <span className="exec-chip-label">Outcome</span>
          <b>{mediaConnected ? 'verbunden' : 'wartet auf CSV'}</b>
        </span>
      </div>

      {/* Skalen-Kalibrator-Badge bleibt als schmale Mono-Zeile am unteren
          Rand des Hero — informativ, kein Alarm. */}
      {calibration?.applied ? (
        <div className="exec-calibrator-badge" role="note">
          <b>Skalen-Kalibrator aktiv</b>
          {' · '}
          β = {typeof calibration.beta === 'number' ? calibration.beta.toFixed(2) : '—'}
          {typeof calibration.alpha === 'number' ? `, α = ${calibration.alpha.toFixed(1)}` : ''}
          {typeof calibration.rmseImprovementPct === 'number'
            ? ` · RMSE ${calibration.rmseImprovementPct >= 0 ? '−' : '+'}${Math.abs(calibration.rmseImprovementPct).toFixed(0)} %`
            : ''}
          {typeof calibration.samples === 'number' ? ` · Fit auf N=${calibration.samples}` : ''}
          {accuracy?.calibrationImpact?.evaluated
            && typeof accuracy.calibrationImpact.rawMape === 'number'
            && typeof accuracy.calibrationImpact.calibratedMape === 'number' ? (
              <span className="exec-calibrator-projection">
                {' · '}
                MAPE {accuracy.calibrationImpact.rawMape.toFixed(0)} %
                {' → '}
                <b>{accuracy.calibrationImpact.calibratedMape.toFixed(0)} %</b>
                {' (erwartet ab KW+1)'}
              </span>
            ) : null}
        </div>
      ) : null}

      <MediaPlanUploadModal
        open={mediaPlanModalOpen}
        onClose={() => setMediaPlanModalOpen(false)}
        onCommitted={() => {
          setMediaPlanModalOpen(false);
          onReload?.();
        }}
        client={snapshot.client || 'GELO'}
      />
    </section>
  );
};

export default ExecutiveHero;
