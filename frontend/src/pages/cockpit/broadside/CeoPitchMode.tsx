import React, { useMemo, useState } from 'react';
import type { CockpitSnapshot } from '../types';
import {
  fmtPctOrDash,
  fmtSignedPct,
  fmtSignalStrength,
} from '../format';
import AtlasChoropleth from './AtlasChoropleth';
import MediaPlanUploadModal from './MediaPlanUploadModal';
import { canChangeBudget, isDiagnosticOnly } from './snapshotAccessors';

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
      label: 'Diagnose nutzbar',
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
    label: 'Budgetfreigabe aktiv',
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
  const fromName = rec?.fromName ?? topFaller?.name ?? 'Spar-Region';
  const toCode = rec?.toCode ?? topRiser?.code ?? '—';
  const fromCode = rec?.fromCode ?? topFaller?.code ?? '—';
  const toDelta = topRiser?.delta7d ?? null;
  const fromDelta = topFaller?.delta7d ?? null;
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
  const signalPct =
    typeof signalScore === 'number' && Number.isFinite(signalScore)
      ? `${Math.round(signalScore * 100)} %`
      : '—';

  const headline = hasStrongSignal
    ? `${toName} zeigt ein Frühsignal.`
    : 'Kein Budgettrigger diese Woche';

  return (
    <section className="ceo-pitch" id="sec-ceo-pitch" aria-labelledby="ceo-pitch-title">
      <div className="ceo-pitch-layout">
        <div className="ceo-pitch-copy">
          <div className="ceo-eyebrow">
            Evidence Summary · {snapshot.client} Pilot · {snapshot.isoWeek}
          </div>
          <h1 id="ceo-pitch-title">
            {headline}{' '}
            {hasStrongSignal && (
              <span>Was wir noch nicht wissen: ob es sich in Sales übersetzt.</span>
            )}
          </h1>
          <p className="ceo-lede">
            {hasStrongSignal ? (
              <>
                {toName} zeigt Atemwegsdruck ({fmtSignedPct(toDelta)}),{' '}
                {fromName} entspannt ({fmtSignedPct(fromDelta)}). Ob daraus
                GELO-Sales werden, zeigen erst Media-Plan und Sales-Daten;{' '}
                <b>
                  {budgetDisabled
                    ? 'keine automatische Budgetänderung.'
                    : 'Budget-Gate aktiv.'}
                </b>
              </>
            ) : (
              <>
                Kein sauberer regionaler Trigger.{' '}
                <b>
                  {budgetDisabled
                    ? 'Budget bleibt gesperrt, bis die nächste Datenwelle klarer ist.'
                    : 'Budget-Gate aktiv.'}
                </b>
              </>
            )}
          </p>

          <div className="ceo-action-row" aria-label="Pitch-Aktionen">
            <a className="ceo-primary-link" href="#sec-evidence">
              Signal-Evidenz ansehen
            </a>
            <a className="ceo-secondary-link" href="#sec-impact">
              Sales-Validierung prüfen
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

      <div className="ceo-readout" aria-label="Cockpit-Kennzahlen">
        <div className={`ceo-trust ceo-trust-${trust.tone}`}>
          <span>Prüfstatus</span>
          <b>{trust.label}</b>
          <small>{trust.note}</small>
        </div>
        <div>
          <span>Budget-Gate</span>
          <b>{budgetDisabled ? 'Budget-Automation deaktiviert' : 'Budget-Gate aktiv'}</b>
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
