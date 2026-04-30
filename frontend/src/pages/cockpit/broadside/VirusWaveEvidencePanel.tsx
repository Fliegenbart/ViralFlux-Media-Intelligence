import React from 'react';
import type { CockpitSnapshot, MediaSpendingTruthPayload, VirusWaveTruth } from '../types';
import SectionHeader from './SectionHeader';
import type { GateTone } from './SectionHeader';

interface Props {
  snapshot: CockpitSnapshot;
}

function firstText(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

function firstNumber(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

function phaseLabel(value: string | null | undefined): string {
  if (!value) return 'nicht bewertet';
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function scoreLabel(value: number | null): string {
  if (value === null) return '—';
  const pct = value <= 1 ? value * 100 : value;
  return `${Math.round(pct)} %`;
}

function weightLabel(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return `${Math.round(value * 100)} %`;
}

function waveTruthFrom(snapshot: CockpitSnapshot): VirusWaveTruth | null {
  const mediaTruth: MediaSpendingTruthPayload | null = snapshot.mediaSpendingTruth ?? null;
  return snapshot.virusWaveTruth ?? mediaTruth?.virusWaveTruth ?? null;
}

function evidenceSummary(waveTruth: VirusWaveTruth | null): string[] {
  if (!waveTruth || waveTruth.status === 'disabled') {
    return [
      'Die Wellen-Evidenz ist in diesem Snapshot noch nicht als eigener Block vorhanden.',
      'Budget-Gates bleiben deshalb unverändert und konservativ.',
    ];
  }

  const leadLag = firstNumber(
    waveTruth.alignment?.lead_lag_days,
    waveTruth.alignment?.leadLagDays,
  );
  const lines: string[] = [];
  if (leadLag !== null && leadLag < 0) {
    lines.push(`AMELAG sieht die Welle etwa ${Math.abs(leadLag)} Tage früher.`);
  } else if (leadLag !== null && leadLag > 0) {
    lines.push(`SurvStat liegt etwa ${leadLag} Tage vor AMELAG.`);
  } else {
    lines.push('AMELAG und SurvStat laufen aktuell ungefähr synchron.');
  }

  const alignment = firstNumber(
    waveTruth.alignment?.alignment_score,
    waveTruth.alignment?.alignmentScore,
  );
  const divergence = firstNumber(
    waveTruth.alignment?.divergence_score,
    waveTruth.alignment?.divergenceScore,
  );
  if (alignment !== null && alignment >= 0.65) {
    lines.push('Die Quellen passen gut zusammen.');
  } else if (divergence !== null && divergence >= 0.25) {
    lines.push('Die Quellen weichen sichtbar voneinander ab.');
  } else {
    lines.push('Die Quellenlage ist noch vorsichtig zu lesen.');
  }
  lines.push('AMELAG ist Early Signal, SurvStat ist die klinische Bestätigung.');
  return waveTruth.evidence?.summary?.length ? waveTruth.evidence.summary : lines;
}

export const VirusWaveEvidencePanel: React.FC<Props> = ({ snapshot }) => {
  const waveTruth = waveTruthFrom(snapshot);
  const weights = waveTruth?.evidence?.effective_weights ?? waveTruth?.evidence?.effectiveWeights ?? null;
  const confidenceMethod = firstText(
    waveTruth?.evidence?.confidence_method,
    waveTruth?.evidence?.confidenceMethod,
    waveTruth?.evidence?.method,
  );
  const confidence = firstNumber(
    waveTruth?.evidence?.confidence,
    waveTruth?.amelag?.confidence,
    waveTruth?.survstat?.confidence,
  );
  const alignment = firstNumber(
    waveTruth?.alignment?.alignment_score,
    waveTruth?.alignment?.alignmentScore,
  );
  const divergence = firstNumber(
    waveTruth?.alignment?.divergence_score,
    waveTruth?.alignment?.divergenceScore,
  );
  const leadLag = firstNumber(
    waveTruth?.alignment?.lead_lag_days,
    waveTruth?.alignment?.leadLagDays,
  );
  const gateTone: GateTone =
    waveTruth?.status === 'disabled'
      ? 'watch'
      : alignment !== null && alignment >= 0.65
        ? 'go'
        : waveTruth
          ? 'watch'
          : 'unknown';
  const gateLabel =
    waveTruth?.status === 'disabled'
      ? 'Evidence · disabled'
      : waveTruth
        ? 'Evidence · active'
        : 'Evidence · missing';

  return (
    <section className="instr-section evidence-first-section" id="sec-evidence">
      <SectionHeader
        numeral="I"
        title="Virus Wave Evidence"
        subtitle={
          <>
            Epidemiologische Evidenz vor Forecast und Budget
          </>
        }
        gate={{ label: gateLabel, tone: gateTone }}
        primer={
          <>
            Diese Ansicht beantwortet zuerst die fachliche Frage:
            <b> Was passiert epidemiologisch gerade?</b> AMELAG ist das
            frühe Abwasser-Signal, SurvStat ist die spätere klinische
            Bestätigung. Budget darf daraus erst entstehen, wenn die
            Gates danach ebenfalls tragen.
          </>
        }
      />

      <div className="wave-evidence-grid">
        <div className="wave-source early">
          <div className="wave-source-kicker">AMELAG · Early Signal</div>
          <div className="wave-source-phase">
            {phaseLabel(waveTruth?.amelag?.phase)}
          </div>
          <p>
            Abwasser sieht Bewegungen oft früher. Der Vergleich läuft gegen
            die lokale und nationale Evidenz, nicht gegen den letzten Einzelwert.
          </p>
        </div>
        <div className="wave-source confirmed">
          <div className="wave-source-kicker">SurvStat · Confirmed Signal</div>
          <div className="wave-source-phase">
            {phaseLabel(waveTruth?.survstat?.phase)}
          </div>
          <p>
            SurvStat bestätigt den klinischen Verlauf mit Meldeverzug. Es ist
            die Kontrollquelle, bevor Budget aktiv werden darf.
          </p>
        </div>
        <div className="wave-source verdict">
          <div className="wave-source-kicker">Lesbare Einschätzung</div>
          <ul>
            {evidenceSummary(waveTruth).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="wave-metrics">
        <div>
          <span className="metric-label">AMELAG lead days</span>
          <span className="metric-value">
            {leadLag !== null ? `${leadLag < 0 ? Math.abs(leadLag) : leadLag} d` : '—'}
          </span>
          <span className="metric-note">
            {leadLag !== null && leadLag < 0 ? 'AMELAG früher' : 'kein Vorsprung'}
          </span>
        </div>
        <div>
          <span className="metric-label">Alignment score</span>
          <span className="metric-value">{scoreLabel(alignment)}</span>
          <span className="metric-note">Passen die Quellen zusammen?</span>
        </div>
        <div>
          <span className="metric-label">Divergence score</span>
          <span className="metric-value">{scoreLabel(divergence)}</span>
          <span className="metric-note">Wie stark widersprechen sie sich?</span>
        </div>
        <div>
          <span className="metric-label">Confidence</span>
          <span className="metric-value">{scoreLabel(confidence)}</span>
          <span className="metric-note">
            {confidenceMethod === 'heuristic_v1'
              ? 'confidence_method=heuristic_v1'
              : confidenceMethod ?? 'Methode nicht angegeben'}
          </span>
        </div>
        <div>
          <span className="metric-label">Effective weights</span>
          <span className="metric-value">
            AMELAG {weightLabel(weights?.amelag)} · SurvStat {weightLabel(weights?.survstat)}
          </span>
          <span className="metric-note">Gewichtung der Evidenzquellen</span>
        </div>
      </div>
    </section>
  );
};

export default VirusWaveEvidencePanel;
