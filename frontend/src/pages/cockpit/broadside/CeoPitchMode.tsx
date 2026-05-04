import React, { useMemo, useState } from 'react';
import type { CockpitSnapshot } from '../types';
import {
  fmtPctOrDash,
  fmtSignedPct,
  fmtSignalStrength,
} from '../format';
import AtlasChoropleth from './AtlasChoropleth';
import MediaPlanUploadModal from './MediaPlanUploadModal';
import { canChangeBudget, isDiagnosticOnly, sellOutWeeks, signalRiserCount } from './snapshotAccessors';

interface Props {
  snapshot: CockpitSnapshot;
  supportedViruses?: readonly string[];
  onReload?: () => void;
}

type TrustTone = 'go' | 'caution' | 'stop';

const STRONG_RISER_THRESHOLD = 0.15;

function formatLag(days: number | null | undefined): string {
  if (typeof days !== 'number' || !Number.isFinite(days)) return '—';
  return `${Math.abs(days)} Tage`;
}

function trustFromSnapshot(snapshot: CockpitSnapshot): {
  tone: TrustTone;
  label: string;
  note: string;
} {
  const readiness = snapshot.modelStatus?.forecastReadiness ?? 'UNKNOWN';
  const lagDays = snapshot.modelStatus?.forecastFreshness?.featureLagDays;
  const hasFeatureLag = typeof lagDays === 'number' && lagDays > 7;
  const scienceStatus =
    snapshot.systemStatus?.science_status ?? snapshot.systemStatus?.scienceStatus ?? null;

  if (isDiagnosticOnly(snapshot)) {
    return {
      tone: 'caution',
      label: 'Kalibrierungsfenster',
      note: 'Funktioniert. Wartet auf eure Daten, bevor wir Budget bewegen.',
    };
  }

  if (scienceStatus === 'review') {
    return {
      tone: 'caution',
      label: 'Review-Modus',
      note: 'Science-Layer ist noch im Review. Signal lesen, aber nicht als automatische Freigabe behandeln.',
    };
  }

  if (readiness === 'DATA_STALE' || readiness === 'DRIFT_WARN') {
    return {
      tone: 'stop',
      label: 'Nicht als Budget-Automatik nutzen',
      note:
        readiness === 'DATA_STALE'
          ? 'Forecast-Daten sind zu alt. Erst Pipeline aktualisieren.'
          : 'Drift-Monitor warnt. Ranking nur als Analyse lesen.',
    };
  }

  if (readiness === 'WATCH' || readiness === 'LEAD_ONLY' || readiness === 'SEASON_OFF') {
    return {
      tone: 'caution',
      label: 'Beobachten',
      note: 'Signal ist sichtbar, aber nicht stark genug für eine harte Budget-Automatik.',
    };
  }

  if (hasFeatureLag) {
    return {
      tone: 'caution',
      label: 'Signal nutzbar mit Vorsicht',
      note: `AMELAG-Feature-Stand ist ${formatLag(lagDays)} alt. Empfehlung pitchen, aber Risiko offen zeigen.`,
    };
  }

  return {
    tone: 'go',
    label: 'Budget-Gate offen',
    note: 'Budget-Gates erlauben eine operative Übergabe. Dies sollte nur nach separater Freigabe sichtbar sein.',
  };
}

export const CeoPitchMode: React.FC<Props> = ({
  snapshot,
  supportedViruses,
  onReload,
}) => {
  const [mediaPlanModalOpen, setMediaPlanModalOpen] = useState(false);

  const rankedRegions = useMemo(() => {
    return [...snapshot.regions]
      .filter((r) => typeof r.delta7d === 'number' && r.decisionLabel !== 'TrainingPending')
      .sort((a, b) => (b.delta7d ?? 0) - (a.delta7d ?? 0));
  }, [snapshot.regions]);

  const topRiser = rankedRegions[0] ?? null;
  const topFaller = rankedRegions[rankedRegions.length - 1] ?? null;
  const rec = snapshot.primaryRecommendation;
  const trust = trustFromSnapshot(snapshot);
  const mediaConnected = snapshot.mediaPlan?.connected === true;

  const toName = rec?.toName ?? topRiser?.name ?? 'Top-Region';
  const toCode = rec?.toCode ?? topRiser?.code ?? '—';
  const fromCode = rec?.fromCode ?? topFaller?.code ?? '—';
  const toDelta = topRiser?.delta7d ?? null;
  const hasStrongSignal =
    typeof toDelta === 'number' && toDelta > STRONG_RISER_THRESHOLD && topRiser !== null;

  const activeRegions = snapshot.regions.filter(
    (r) => r.decisionLabel !== 'TrainingPending',
  ).length;
  const pendingRegions = Math.max(0, 16 - activeRegions);
  const virusCount = supportedViruses?.length ?? 0;
  const signalScore = rec?.signalScore ?? rec?.confidence ?? null;
  const featureLagDays = snapshot.modelStatus?.forecastFreshness?.featureLagDays;
  const ranking = snapshot.modelStatus?.ranking;
  const lead = snapshot.modelStatus?.lead;
  const budgetDisabled = !canChangeBudget(snapshot);
  const salesProofLabel = 'Sales-Validierung offen';
  const dataWeeks = sellOutWeeks(snapshot);
  const riserCount = signalRiserCount(snapshot);
  const signalPct =
    typeof signalScore === 'number' && Number.isFinite(signalScore)
      ? `${Math.round(signalScore * 100)} %`
      : '—';

  const signalStatus =
    hasStrongSignal
      ? 'signal_present'
      : dataWeeks < 12
        ? 'insufficient_data'
        : 'stable';
  const headline =
    signalStatus === 'signal_present' ? (
      <>
        Atemwegsdruck steigt in <span>{toName}.</span>{' '}
        <small>Prüfen, ob ein Media-Shift sich lohnt.</small>
      </>
    ) : signalStatus === 'stable' ? (
      <>Signallage stabil. Beobachten genügt diese Woche.</>
    ) : (
      <>Datenlage zu eng für eine Empfehlung. System sammelt weiter.</>
    );
  const primaryCta =
    signalStatus === 'signal_present'
      ? 'Signal-Evidenz öffnen'
      : signalStatus === 'stable'
        ? 'Forecast ansehen'
        : 'Erste GELO-CSV hochladen';
  const primaryHref =
    signalStatus === 'signal_present'
      ? '#sec-evidence'
      : signalStatus === 'stable'
        ? '#sec-forecast'
        : '/cockpit/data';
  const nextStep =
    dataWeeks <= 0
      ? 'GELO-CSV anschließen'
      : dataWeeks < 12
        ? 'Sales-Historie erweitern'
        : hasStrongSignal
          ? 'Forecast neu rechnen'
          : 'Beobachten';

  return (
    <section className="ceo-pitch" id="sec-ceo-pitch" aria-labelledby="ceo-pitch-title">
      <div className="ceo-pitch-layout">
        <div className="ceo-pitch-copy">
          <div className="ceo-eyebrow">
            Evidence Summary · {snapshot.client} Pilot · {snapshot.isoWeek}
          </div>
          <h1 id="ceo-pitch-title">
            {headline}
          </h1>
          <p className="ceo-lede">
            Frühsignal aus Abwasser und Notaufnahmen. Eine Budget-Empfehlung
            gibt es erst, wenn euer Sell-Out drei Monate angeschlossen ist
            und das Modell auf eure Sortimente kalibriert ist.
          </p>

          <div className="ceo-action-row" aria-label="Pitch-Aktionen">
            <a className="ceo-primary-link" href={primaryHref}>
              {primaryCta}
            </a>
            <a className="ceo-secondary-link" href="#sec-backtest">
              Methodik
            </a>
            <button
              type="button"
              className="ceo-secondary-link ceo-plan-button"
              onClick={() => setMediaPlanModalOpen(true)}
            >
              {mediaConnected ? 'Plan bearbeiten' : 'Media-Plan anbinden'}
            </button>
          </div>
        </div>

        <div className="ceo-map-stage" aria-label="Deutschlandkarte mit regionalem Wellen-Signal">
          <AtlasChoropleth snapshot={snapshot} />
          <div className="ceo-map-caption">
            <span>{fromCode} → {toCode}</span>
            <b>{fmtSignedPct(toDelta)} in {toName}</b>
          </div>
        </div>
      </div>

      <div className="ceo-readout ceo-readout-primary" aria-label="Cockpit-Kennzahlen">
        <div title="Bundesländer mit signifikantem Anstieg über die eigene Baseline.">
          <span>Signal-Status</span>
          <b>{riserCount === 1 ? '1 Region riser' : riserCount > 1 ? `${riserCount} Regionen riser` : 'keine Riser'}</b>
          <small>{hasStrongSignal ? `${toName} führt die Liste an.` : 'Keine Region über Trigger-Schwelle.'}</small>
        </div>
        <div title="Wochen verknüpfter GELO-Sales-Daten. Ab 12 Wochen empfehlungsfähig.">
          <span>Daten-Reife</span>
          <b>{dataWeeks} / 12 Wochen Sell-Out</b>
          <small>{dataWeeks >= 12 ? 'Sales-Anker vorhanden' : 'Kalibrierungsfenster läuft'}</small>
        </div>
        <div title="Der nächste operative Schritt aus Signal, Datenreife und Gate-Status.">
          <span>Nächster Schritt</span>
          <b>{nextStep}</b>
          <small>{budgetDisabled ? 'Budget-Gate geschlossen' : 'Budget-Gate offen'}</small>
        </div>
      </div>

      <details className="ceo-metrics-expander">
        <summary>Alle Metriken anzeigen</summary>
        <div className="ceo-readout ceo-readout-detail" aria-label="Cockpit-Detailkennzahlen">
        <div className={`ceo-trust ceo-trust-${trust.tone}`}>
          <span>Prüfstatus</span>
          <b>{trust.label}</b>
          <small>{trust.note}</small>
        </div>
        <div>
          <span>Budget-Gate</span>
          <b>{budgetDisabled ? 'Budget-Gate geschlossen' : 'Budget-Gate offen'}</b>
          <small>{budgetDisabled ? 'can_change_budget=false' : 'separate Freigabe aktiv'}</small>
        </div>
        <div>
          <span>Signal</span>
          <b>{fmtSignalStrength(signalScore)}</b>
          <small>Wir sind uns zu {signalPct} sicher. Mit euren Daten sehen wir, ob das stimmt.</small>
        </div>
        <div>
          <span>Coverage</span>
          <b>{activeRegions}/16 BL</b>
          <small>{pendingRegions > 0 ? `${pendingRegions} Training pending` : 'alle Regionen trainiert'}</small>
        </div>
        <div>
          <span>Lead-Time</span>
          <b>
            {lead?.bestLagDays !== null && typeof lead?.bestLagDays === 'number'
              ? `${lead.bestLagDays >= 0 ? '+' : ''}${lead.bestLagDays} d`
              : '—'}
          </b>
          <small>gegen {lead?.targetLabel ?? 'Meldewesen'}</small>
        </div>
        <div>
          <span>Regionaler Modelltest</span>
          <b>{fmtPctOrDash(ranking?.precisionAtTop3, 1)}</b>
          <small>Precision @ Top-3 · PR-AUC {ranking?.prAuc?.toFixed(3) ?? '—'}</small>
        </div>
        <div>
          <span>Sales-Prüfung</span>
          <b>{salesProofLabel}</b>
          <small>{mediaConnected ? 'Media-Plan verbunden' : 'Media-Plan wartet'} · echte GELO-Salesdaten sind der nächste Prüfstein</small>
        </div>
        <div>
          <span>5-Tage-Ziel</span>
          <b>Produktziel</b>
          <small>UI zeigt den aktiven {snapshot.modelStatus?.horizonDays ?? '—'}d-Horizont transparent; h5 ist der GELO-Pilotpfad</small>
        </div>
        <div>
          <span>Datenalter</span>
          <b>{formatLag(featureLagDays)}</b>
          <small>AMELAG-Feature-Lag</small>
        </div>
        <div>
          <span>Viren</span>
          <b>{virusCount || '—'}/4</b>
          <small>{snapshot.virusLabel || snapshot.virusTyp}</small>
        </div>
        </div>
      </details>

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

export default CeoPitchMode;
