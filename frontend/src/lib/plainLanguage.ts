import { PredictionNarrative } from '../types/media';

const ASCII_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bFuehrt\b/g, 'Führt'],
  [/\bfuehrt\b/g, 'führt'],
  [/\bFuer\b/g, 'Für'],
  [/\bfuer\b/g, 'für'],
  [/\bUeber\b/g, 'Über'],
  [/\bueber\b/g, 'über'],
  [/\bNaechsten\b/g, 'Nächsten'],
  [/\bnaechsten\b/g, 'nächsten'],
  [/\bNaechste\b/g, 'Nächste'],
  [/\bnaechste\b/g, 'nächste'],
  [/\bNaechster\b/g, 'Nächster'],
  [/\bnaechster\b/g, 'nächster'],
  [/\bPruefung\b/g, 'Prüfung'],
  [/\bpruefung\b/g, 'prüfung'],
  [/\bPruefbar\b/g, 'Prüfbar'],
  [/\bpruefbar\b/g, 'prüfbar'],
  [/\bPruefbare\b/g, 'Prüfbare'],
  [/\bpruefbare\b/g, 'prüfbare'],
  [/\bVorschlaege\b/g, 'Vorschläge'],
  [/\bvorschlaege\b/g, 'vorschläge'],
  [/\bZukuenftige\b/g, 'Zukünftige'],
  [/\bzukuenftige\b/g, 'zukünftige'],
  [/\banschliesst\b/g, 'anschließt'],
  [/\bAnschliesst\b/g, 'Anschließt'],
  [/\bfreigabefaehig\b/g, 'freigabefähig'],
  [/\bfreigabefaehigen\b/g, 'freigabefähigen'],
  [/\bFaehig\b/g, 'Fähig'],
  [/\bfaehig\b/g, 'fähig'],
  [/\bKoennen\b/g, 'Können'],
  [/\bkoennen\b/g, 'können'],
  [/\bMoeglich\b/g, 'Möglich'],
  [/\bmoeglich\b/g, 'möglich'],
  [/\bOeffnen\b/g, 'Öffnen'],
  [/\boeffnen\b/g, 'öffnen'],
  [/\bUebergang\b/g, 'Übergang'],
  [/\buebergang\b/g, 'übergang'],
  [/\buebergegangen\b/g, 'übergegangen'],
];

const UI_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bMedia Intelligence Curator\b/g, 'Frühwarnung für regionale Nachfrage'],
  [/\bMedia Intelligence\b/g, 'Frühwarnung für regionale Nachfrage'],
  [/\bLive Intelligence Active\b/g, 'Live-Daten aktiv'],
  [/\bOperator-Raum\b/g, 'Arbeitsbereich'],
  [/\bOperator\b/g, 'Arbeitsbereich'],
  [/\bActionability\b/g, 'Umsetzbarkeit'],
  [/\bAktivierbarkeit\b/g, 'Umsetzbarkeit'],
  [/\bBrand\b/g, 'Marke'],
  [/\bFlight\b/g, 'Startfenster'],
  [/\bLearning-State\b/g, 'Lernstand'],
  [/\bOutcome-Learning\b/g, 'Wirkung aus Kundendaten'],
  [/\bOutcome-Score\b/g, 'Wirkungssignal'],
  [/\bOutcome-Daten\b/g, 'Kundendaten'],
  [/\bOutcome\b/g, 'Wirkungsdaten'],
  [/\bTruth-Gate\b/g, 'Freigabestatus Kundendaten'],
  [/\bTruth-Layer\b/g, 'Kundendatenbasis'],
  [/\bTruth\b/g, 'Kundendaten'],
  [/\bBusiness-Gate\b/g, 'Freigabestatus'],
  [/\bGate\b/g, 'Status'],
  [/\bSignal-Stack\b/g, 'Signalsystem'],
  [/\bStack\b/g, 'Datenbasis'],
  [/\bUpload-Detail\b/g, 'Import-Details'],
  [/\bUploads\b/g, 'Importe'],
  [/\bUpload\b/g, 'Import'],
  [/\bDashboard\b/g, 'Übersicht'],
  [/\bLegacy-Run\b/g, 'Früherer Lauf'],
  [/\bRun\b/g, 'Lauf'],
  [/\bDecision Support\b/g, 'Entscheidungshilfe'],
  [/\bMedia Spend\b/g, 'Mediabudget'],
  [/\bSignal-Score\b/g, 'Signalwert'],
  [/\bSignalscore\b/g, 'Signalwert'],
  [/\bPriority-Score\b/g, 'Priorität'],
  [/\bLearning-Konfidenz\b/g, 'Sicherheit aus Kundendaten'],
  [/\bShift\b/g, 'Änderung'],
  [/\bForecast-Monitoring\b/g, 'Prüfung der Vorhersage'],
  [/\bForecast-Frische\b/g, 'Frische der Vorhersage'],
  [/\bForecast-Richtung\b/g, 'Richtung der Vorhersage'],
  [/\bML-Prognose\b/g, 'Modellvorhersage'],
  [/\bForecast\b/g, 'Vorhersage'],
  [/\bHorizon\b/g, 'Zeitraum'],
  [/\bEpi-Welle\b/g, 'Atemwegswelle'],
  [/\bActive\b/g, 'Aktiv'],
];

export function normalizeGermanText(value?: string | null): string {
  let text = String(value || '').trim();
  if (!text) return '';

  for (const [pattern, replacement] of ASCII_REPLACEMENTS) {
    text = text.replace(pattern, replacement);
  }

  for (const [pattern, replacement] of UI_REPLACEMENTS) {
    text = text.replace(pattern, replacement);
  }

  return text
    .replace(/\bWirkungsdaten-Daten\b/g, 'Wirkungsdaten')
    .replace(/\bKundendaten-Daten\b/g, 'Kundendaten')
    .replace(/\bVorhersage-Promotion-Status\b/g, 'Freigabestatus der Vorhersage')
    .replace(/\s+/g, ' ')
    .trim();
}

export function buildPredictionNarrative({
  horizonDays,
  regionName,
  forecastStatus,
  proofPoints,
}: {
  horizonDays: number;
  regionName?: string | null;
  forecastStatus?: string | null;
  proofPoints?: Array<string | null | undefined>;
}): PredictionNarrative {
  const cleanedRegion = normalizeGermanText(regionName) || 'dieser Region';
  const cleanedStatus = normalizeGermanText(forecastStatus).toLowerCase();
  const assertive = cleanedStatus.includes('freigabe bereit') || cleanedStatus.includes('stabil');
  const visibleProofPoints = (proofPoints || [])
    .map((item) => normalizeGermanText(item))
    .filter(Boolean)
    .slice(0, 3);

  if (assertive) {
    return {
      headline: `Wir sehen im ${horizonDays}-Tage-Fenster das früheste relevante Signal aktuell in ${cleanedRegion}.`,
      supportingText: `Die Vorhersage spricht im Moment klar dafür, dass die nächste relevante Welle dort zuerst anzieht.`,
      proofPoints: visibleProofPoints,
      cautionText: 'Die Lage bleibt nachvollziehbar, aber keine Vorhersage ist eine Garantie.',
      assertive: true,
    };
  }

  return {
    headline: `Im ${horizonDays}-Tage-Fenster zeigt die Vorhersage das früheste relevante Signal aktuell in ${cleanedRegion}.`,
    supportingText: 'Der wahrscheinlichste frühe Start liegt derzeit dort. Vor einer Freigabe prüfen wir noch Modell- und Datenlage.',
    proofPoints: visibleProofPoints,
    cautionText: 'Die Richtung ist erkennbar, aber Warnhinweise bleiben sichtbar und werden vor einer Freigabe geprüft.',
    assertive: false,
  };
}
