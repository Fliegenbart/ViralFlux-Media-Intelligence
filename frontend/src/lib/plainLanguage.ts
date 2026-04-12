import { PredictionNarrative, StructuredReasonItem } from '../types/media';
import { OPERATOR_LABELS } from '../constants/operatorLabels';
import { COCKPIT_SEMANTICS, UI_COPY, evidenceStatusLabel } from './copy';

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
  [/\bActionability\b/g, 'Handlungsreife'],
  [/\bAktivierbarkeit\b/g, 'Handlungsreife'],
  [/\bBrand\b/g, 'Marke'],
  [/\bFlight\b/g, 'Startfenster'],
  [/\bLearning-State\b/g, 'Lernstand'],
  [/\bOutcome-Learnings\b/g, 'Wirkungs-Hinweise (Kundendaten)'],
  [/\bOutcome-Learning\b/g, 'Wirkungs-Hinweis (Kundendaten)'],
  [/\bOutcome-Score\b/g, 'Wirkungshinweis (Kundendaten)'],
  [/\bOutcome-Metrik\b/g, 'Wirkungskennzahl'],
  [/\bOutcome-Daten\b/g, 'Kundendaten'],
  [/\bOutcome\b/g, 'Wirkung'],
  [/\bTruth-Historie\b/g, 'Kundendatenhistorie'],
  [/\bTruth-Gate\b/g, 'Freigabe-Status Kundendaten'],
  [/\bTruth-Layer\b/g, 'Kundendatenbasis'],
  [/\bTruth\b/g, 'Kundendaten'],
  [/\bBusiness-Gate\b/g, 'Freigabe-Status'],
  [/\bHoldout-Validierung\b/g, 'Validierung mit Vergleichsgruppe'],
  [/\bHoldout-Design\b/g, 'Vergleichsgruppendesign'],
  [/\bHoldout-Test\b/g, 'Vergleichsgruppentest'],
  [/\bHoldout\b/g, 'Vergleichsgruppe'],
  [/\bLift-Metriken\b/g, 'Zusatz-Effekt Kennzahlen'],
  [/\bLift\b/g, 'Zusatz-Effekt'],
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
  [/\bSignal-Score\b/g, UI_COPY.signalScore],
  [/\bSignalscore\b/g, UI_COPY.signalScore],
  [/\bPriority-Score\b/g, UI_COPY.decisionPriority],
  [/\bLearning-Konfidenz\b/g, 'Sicherheitsgrad (Kundendaten)'],
  [/\bSearch Lift\b/g, 'Suchanstieg'],
  [/\bSales\b/g, 'Verkäufe'],
  [/\bOrders\b/g, 'Bestellungen'],
  [/\bRevenue\b/g, 'Umsatz'],
  [/\bImpressions\b/g, 'Impressionen'],
  [/\bClicks\b/g, 'Klicks'],
  [/\bShift\b/g, 'Änderung'],
  [/\bForecast-Accuracy\b/g, 'Vorhersagegenauigkeit'],
  [/\bForecast-Monitoring\b/g, 'Prüfung der Vorhersage'],
  [/\bForecast-Frische\b/g, 'Frische der Vorhersage'],
  [/\bForecast-Richtung\b/g, 'Richtung der Vorhersage'],
  [/\bML-Prognose\b/g, 'Modellvorhersage'],
  [/\bForecast\b/g, 'Vorhersage'],
  [/\bHorizon\b/g, 'Zeitraum'],
  [/\bEpi-Welle\b/g, 'Atemwegswelle'],
  [/\bActive\b/g, 'Aktiv'],
];

function localizedNumber(value: number, digits = 1): string {
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function percentFromModelValue(raw: string): string {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  const percentage = parsed <= 1 ? parsed * 100 : parsed;
  const digits = percentage >= 10 ? 0 : 1;
  return `${localizedNumber(percentage, digits)} %`;
}

function percentLabel(raw: string): string {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  const digits = parsed >= 10 ? 0 : 1;
  return `${localizedNumber(parsed, digits)} %`;
}

function currencyLabel(raw: string): string {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  return `${new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 }).format(parsed)} EUR`;
}

function stageLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'activate') return 'Aktivieren';
  if (normalized === 'prepare') return 'Vorbereiten';
  if (normalized === 'watch') return 'Beobachten';
  return normalizeGermanText(value);
}

function stageSentence(region: string, stage: string): string {
  const normalized = String(stage || '').trim().toLowerCase();
  if (normalized === 'activate') return `Empfehlung für ${region}: Aktivieren`;
  if (normalized === 'prepare') return `Empfehlung für ${region}: Vorbereiten`;
  return `Empfehlung für ${region}: Beobachten`;
}

function directionLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'up') return 'nach oben';
  if (normalized === 'down') return 'nach unten';
  return 'seitwärts';
}

function evidenceClassLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'truth_backed') return evidenceStatusLabel('truth_backed');
  if (normalized === 'epidemiological_only') return evidenceStatusLabel('epidemiological_only');
  if (normalized === 'no_truth') return UI_COPY.insufficientTruth;
  return normalizeGermanText(String(value || '').replace(/_/g, ' '));
}

function agreementLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'no_signal') return 'noch ohne belastbaren Abgleich';
  if (normalized === 'weak') return 'nur schwach gestützt';
  if (normalized === 'supported') return 'durch Kundendaten gestützt';
  return normalizeGermanText(String(value || '').replace(/_/g, ' '));
}

function compactListLabel(raw: string): string {
  return raw
    .replace(/^\[/, '')
    .replace(/\]$/, '')
    .replace(/['"]/g, '')
    .trim();
}

function joinList(items: string[]): string {
  if (items.length === 0) return '';
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} und ${items[1]}`;
  return `${items.slice(0, -1).join(', ')} und ${items[items.length - 1]}`;
}

function isStructuredReasonItem(value: unknown): value is StructuredReasonItem {
  return Boolean(
    value
    && typeof value === 'object'
    && typeof (value as StructuredReasonItem).code === 'string'
    && typeof (value as StructuredReasonItem).message === 'string',
  );
}

function reasonParam(item: StructuredReasonItem, key: string): unknown {
  return item.params?.[key];
}

function reasonNumber(item: StructuredReasonItem, key: string): number | null {
  const raw = reasonParam(item, key);
  const candidate = Array.isArray(raw) ? raw[0] : raw;
  const parsed = Number(candidate);
  return Number.isFinite(parsed) ? parsed : null;
}

function reasonString(item: StructuredReasonItem, key: string): string {
  const raw = reasonParam(item, key);
  const candidate = Array.isArray(raw) ? raw[0] : raw;
  return String(candidate || '').trim();
}

function reasonStringList(item: StructuredReasonItem, key: string): string[] {
  const raw = reasonParam(item, key);
  if (Array.isArray(raw)) {
    return raw.map((entry) => String(entry || '').trim()).filter(Boolean);
  }
  const single = String(raw || '').trim();
  return single ? [single] : [];
}

function uncertaintyPartLabel(code: string, item: StructuredReasonItem): string {
  if (code === 'revision_risk') {
    const revisionRisk = reasonNumber(item, 'revision_risk');
    return revisionRisk == null
      ? 'Zahlen, die sich noch ändern können'
      : `Zahlen, die sich noch ändern können (${percentFromModelValue(String(revisionRisk))})`;
  }
  if (code === 'freshness_score') {
    const freshnessScore = reasonNumber(item, 'freshness_score');
    return freshnessScore == null
      ? 'Datenstand, der noch nicht aktuell ist'
      : `Datenstand noch nicht aktuell (${percentFromModelValue(String(freshnessScore))})`;
  }
  if (code === 'thin_agreement_evidence') return 'zu wenig übereinstimmenden Quellen';
  if (code === 'no_positive_cross_source_agreement') return 'keinem klaren Abgleich über mehrere Quellen';
  if (code === 'quality_gate_not_passed') return 'einem Qualitätscheck, der noch nicht bestanden ist';
  return normalizeGermanText(code.replace(/_/g, ' '));
}

function translateStructuredReason(item: StructuredReasonItem): string | null {
  switch (item.code) {
    case 'decision_summary': {
      const region = normalizeGermanText(reasonString(item, 'bundesland_name') || 'Die Region');
      const stage = reasonString(item, 'stage') || 'watch';
      const eventProbability = reasonNumber(item, 'event_probability');
      const signalSupport = reasonNumber(item, 'signal_support_score') ?? reasonNumber(item, 'forecast_confidence');
      const agreementDirection = reasonString(item, 'agreement_direction');
      const details: string[] = [];
      if (eventProbability != null) details.push(`${OPERATOR_LABELS.forecast_event_probability} ${percentFromModelValue(String(eventProbability))}`);
      if (signalSupport != null) details.push(`${OPERATOR_LABELS.signal_confidence} ${percentFromModelValue(String(signalSupport))}`);
      if (agreementDirection) details.push(`Quellen eher ${directionLabel(agreementDirection)}`);
      const detailText = details.length > 0 ? ` (${details.join(', ')})` : '';
      return `${stageSentence(region, stage)}${detailText}.`;
    }
    case 'uncertainty_summary': {
      const parts = reasonStringList(item, 'parts');
      if (parts.length === 0) return 'Aktuell gibt es nur wenige Warnhinweise.';
      return `Noch offen: ${joinList(parts.map((part) => uncertaintyPartLabel(part, item)))}.`;
    }
    case 'event_probability_activate_threshold':
      return `${OPERATOR_LABELS.forecast_event_probability}: ${percentFromModelValue(String(reasonNumber(item, 'event_probability') ?? 0))}. Das passt zu Aktivieren.`;
    case 'event_probability_prepare_threshold':
      return `${OPERATOR_LABELS.forecast_event_probability}: ${percentFromModelValue(String(reasonNumber(item, 'event_probability') ?? 0))}. Das passt zu Vorbereiten (noch nicht Aktivieren).`;
    case 'event_probability_below_prepare_threshold':
      return `${OPERATOR_LABELS.forecast_event_probability}: ${percentFromModelValue(String(reasonNumber(item, 'event_probability') ?? 0))}. Noch zu früh für Vorbereiten oder Aktivieren.`;
    case 'forecast_confidence_strong':
      return `Das Signal wirkt stabil (${percentFromModelValue(String(reasonNumber(item, 'signal_support_score') ?? reasonNumber(item, 'forecast_confidence') ?? 0))}).`;
    case 'forecast_confidence_usable':
      return `Das Signal wirkt brauchbar (${percentFromModelValue(String(reasonNumber(item, 'signal_support_score') ?? reasonNumber(item, 'forecast_confidence') ?? 0))}).`;
    case 'forecast_confidence_low':
      return `Das Signal ist noch unsicher (${percentFromModelValue(String(reasonNumber(item, 'signal_support_score') ?? reasonNumber(item, 'forecast_confidence') ?? 0))}).`;
    case 'primary_sources_fresh':
      return `Die wichtigsten Quellen sind aktuell (Ø ${localizedNumber(reasonNumber(item, 'freshness_days') ?? 0, 1)} Tage).`;
    case 'primary_sources_stale':
      return `Die wichtigsten Quellen sind etwas älter (Ø ${localizedNumber(reasonNumber(item, 'freshness_days') ?? 0, 1)} Tage).`;
    case 'revision_risk_high':
      return `Die Zahlen können sich noch deutlich ändern (${percentFromModelValue(String(reasonNumber(item, 'revision_risk') ?? 0))}).`;
    case 'revision_risk_material':
    case 'uncertainty_revision_risk_material':
      return `Die Zahlen können sich noch ändern (${percentFromModelValue(String(reasonNumber(item, 'revision_risk') ?? 0))}).`;
    case 'trend_acceleration_supportive':
      return 'Die letzten Tage stützen diese Richtung.';
    case 'trend_acceleration_not_convincing':
      return 'Die Dynamik reicht noch nicht für einen klaren nächsten Schritt.';
    case 'cross_source_agreement_low_evidence': {
      const signalCount = reasonNumber(item, 'signal_count');
      return signalCount != null && signalCount > 0
        ? `Aktuell zeigen nur ${localizedNumber(signalCount, 0)} Quellen klar in eine Richtung.`
        : 'Aktuell zeigen zu wenige Quellen klar in eine Richtung.';
    }
    case 'cross_source_agreement_upward': {
      const signalCount = reasonNumber(item, 'signal_count');
      return signalCount != null && signalCount > 0
        ? `${localizedNumber(signalCount, 0)} Quellen zeigen aktuell nach oben.`
        : 'Mehrere Quellen zeigen aktuell nach oben.';
    }
    case 'cross_source_agreement_not_upward':
      return 'Die Quellen zeigen noch nicht klar nach oben.';
    case 'quality_gate_not_passed':
      return 'Für eine Freigabe reicht die Datenlage noch nicht aus.';
    case 'final_stage_policy_overlay':
      return `Eine Freigaberegel setzt die Region auf ${stageLabel(reasonString(item, 'final_stage'))} (Ausgangssignal: ${stageLabel(reasonString(item, 'signal_stage'))}).`;
    case 'policy_override_watch_only':
      return 'Eine Regel setzt die Region bewusst auf Beobachten, auch wenn das Rohsignal stärker wirkt.';
    case 'policy_override_quality_gate':
      return 'Ein Qualitätscheck verhindert aktuell eine höhere Stufe.';
    case 'policy_override':
      return 'Eine zusätzliche Regel verändert die endgültige Stufe.';
    case 'decision_stage_base':
      return `Grundstufe: ${stageLabel(reasonString(item, 'stage'))}.`;
    case 'ranking_priority_and_probability':
      return `${COCKPIT_SEMANTICS.decisionPriority.label} und ${COCKPIT_SEMANTICS.eventProbability.label} bestimmen hier die Reihenfolge.`;
    case 'budget_driver_activate_multiplier':
      return 'Bei Aktivieren wird Budget stärker konzentriert.';
    case 'budget_driver_prepare_weighting':
      return 'Vorbereiten bleibt möglich, wird aber niedriger gewichtet.';
    case 'budget_driver_watch_observe_only':
      return 'Beobachten bleibt vorerst prüfend und bekommt meist kein zusätzliches Budget.';
    case 'budget_driver_confidence_low_penalty':
      return `Hohe ${OPERATOR_LABELS.signal_confidence} (${percentFromModelValue(String(reasonNumber(item, 'allocation_support_score') ?? reasonNumber(item, 'confidence') ?? 0))}): Budget wird nur leicht reduziert.`;
    case 'budget_driver_confidence_moderate_penalty':
      return `Mittlere ${OPERATOR_LABELS.signal_confidence} (${percentFromModelValue(String(reasonNumber(item, 'allocation_support_score') ?? reasonNumber(item, 'confidence') ?? 0))}): Budget wird moderat reduziert.`;
    case 'budget_driver_confidence_high_penalty':
      return `Geringe ${OPERATOR_LABELS.signal_confidence} (${percentFromModelValue(String(reasonNumber(item, 'allocation_support_score') ?? reasonNumber(item, 'confidence') ?? 0))}): Budget wird deutlich reduziert.`;
    case 'budget_driver_population_weight':
      return 'Die Reichweite der Region stärkt den Vorschlag.';
    case 'budget_driver_region_weight_boost':
      return 'Die hinterlegte Regionsgewichtung erhöht den Vorschlag.';
    case 'budget_driver_region_weight_reduce':
      return 'Die hinterlegte Regionsgewichtung senkt den Vorschlag etwas.';
    case 'budget_driver_source_freshness_penalty':
      return 'Datenstand eher alt: Budget wird vorsichtiger verteilt.';
    case 'budget_driver_revision_risk_penalty':
      return 'Zahlen können sich noch ändern: Budget wird vorsichtiger verteilt.';
    case 'budget_driver_suggested_share':
      return `Vorgeschlagener Budgetanteil: ${percentFromModelValue(String(reasonNumber(item, 'suggested_budget_share') ?? 0))}.`;
    case 'uncertainty_source_freshness_soft':
      return `Datenstand noch nicht aktuell (${percentFromModelValue(String(reasonNumber(item, 'source_freshness') ?? 0))}).`;
    case 'budget_ineligible_region':
      return 'Die Region ist unter den aktuellen Regeln noch nicht für zusätzliches Budget freigegeben.';
    case 'campaign_stage_budget_share':
      return `${normalizeGermanText(reasonString(item, 'region_name') || 'Die Region')}: ${stageLabel(reasonString(item, 'stage'))} (Budgetanteil ${percentFromModelValue(String(reasonNumber(item, 'budget_share') ?? 0))}).`;
    case 'campaign_wave_plan_support':
      return `Die Region bleibt im Wochenplan, weil Signalstärke und Rang im Vergleich gut genug sind (Signalstärke ${percentFromModelValue(String(reasonNumber(item, 'allocation_support_score') ?? reasonNumber(item, 'confidence') ?? 0))}, Rang ${localizedNumber(reasonNumber(item, 'priority_rank') ?? 0, 0)}).`;
    case 'campaign_product_cluster_fit': {
      const cluster = normalizeGermanText(reasonString(item, 'cluster_label'));
      const fitScore = reasonNumber(item, 'fit_score');
      const products = joinList(reasonStringList(item, 'products').map((entry) => normalizeGermanText(entry)));
      const productText = products ? ` Produkte: ${products}.` : '';
      return `${cluster}: passt zum Produktset (Passung ${localizedNumber(fitScore ?? 0, 2)}).${productText}`;
    }
    case 'campaign_region_product_fit_boost':
      return 'Region und Produkt passen gut zusammen und stärken den Vorschlag.';
    case 'campaign_keyword_cluster_fit':
      return `${normalizeGermanText(reasonString(item, 'cluster_label'))} lässt sich gut in konkrete Suchanfragen übersetzen.`;
    case 'campaign_budget_amount':
      return `Budgetvorschlag: ${currencyLabel(String(reasonNumber(item, 'budget_amount') ?? 0))}.`;
    case 'campaign_budget_share':
      return `Budgetanteil: ${percentFromModelValue(String(reasonNumber(item, 'budget_share') ?? 0))}.`;
    case 'campaign_evidence_class':
      return `Evidenzstatus: ${evidenceClassLabel(reasonString(item, 'evidence_class'))}.`;
    case 'campaign_signal_outcome_agreement':
      return `Abgleich Signal und Kundendaten: ${agreementLabel(reasonString(item, 'status'))}.`;
    case 'campaign_guardrail_ready':
      return 'Budget-Regeln: ok. Nächster Schritt möglich.';
    case 'campaign_guardrail_bundle_neighbor':
      return 'Das Budget ist für eine einzelne Region noch zu klein; sinnvoll ist eine Bündelung mit einer Nachbarregion.';
    case 'campaign_guardrail_low_confidence_review':
      return 'Das Signal ist noch nicht sicher genug; vor dem nächsten Schritt ist eine manuelle Prüfung sinnvoll.';
    case 'campaign_guardrail_blocked':
      return 'Ein offener Freigabe-Punkt blockiert den nächsten Schritt noch.';
    case 'campaign_guardrail_discussion_only':
      return 'Der Vorschlag ist noch nicht freigabefähig; erst prüfen und einordnen.';
    default:
      return null;
  }
}

function uncertaintyItemLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  const revisionMatch = normalized.match(/^revision risk ([\d.]+)$/i);
  if (revisionMatch) {
    return `Zahlen können sich noch ändern (${percentFromModelValue(revisionMatch[1])})`;
  }
  const freshnessMatch = normalized.match(/^freshness score ([\d.]+)$/i);
  if (freshnessMatch) {
    return `Datenstand noch nicht aktuell (${percentFromModelValue(freshnessMatch[1])})`;
  }
  if (normalized === 'thin agreement evidence') return 'zu wenig übereinstimmende Quellen';
  if (normalized === 'no positive cross-source agreement') return 'kein klarer Abgleich über mehrere Quellen';
  if (normalized === 'quality gate not passed') return 'Qualitätscheck noch nicht bestanden';
  return normalizeGermanText(value);
}

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

export function explainInPlainGerman(value?: string | StructuredReasonItem | null): string {
  const structuredReason = isStructuredReasonItem(value) ? value : null;
  const raw = String(structuredReason?.message || value || '').trim();
  if (!raw) return '';

  if (structuredReason) {
    const translated = translateStructuredReason(structuredReason);
    if (translated) return translated;
  }

  const compactRaw = raw.replace(/\s+/g, ' ').trim();
  const normalized = normalizeGermanText(compactRaw);

  const leadRegionMatch = compactRaw.match(/^(.+?) is the current lead region\.$/i);
  if (leadRegionMatch) {
    return `${normalizeGermanText(leadRegionMatch[1])} ist aktuell die führende Region.`;
  }

  const leadsWaveMatch = compactRaw.match(/^(.+?) leads the current viral wave\.$/i);
  if (leadsWaveMatch) {
    return `${normalizeGermanText(leadsWaveMatch[1])} führt aktuell die virale Lage an.`;
  }

  const largestShareMatch = compactRaw.match(/^(.+?) receives the largest share\.$/i);
  if (largestShareMatch) {
    return `${normalizeGermanText(largestShareMatch[1])} erhält aktuell den größten Budgetanteil.`;
  }

  const watchModeMatch = compactRaw.match(/^(.+?) stays in watch mode\.$/i);
  if (watchModeMatch) {
    return `${normalizeGermanText(watchModeMatch[1])} bleibt vorerst im Beobachtungsmodus.`;
  }

  const belowActionMatch = compactRaw.match(/^(.+?) stays below the action threshold\.$/i);
  if (belowActionMatch) {
    return `${normalizeGermanText(belowActionMatch[1])} wirkt noch nicht stark genug für einen nächsten Schritt.`;
  }

  const stageShareMatch = compactRaw.match(/^(.+?) stays on (Activate|Prepare|Watch) with budget share ([\d.]+)%\.$/i);
  if (stageShareMatch) {
    return `${normalizeGermanText(stageShareMatch[1])}: ${stageLabel(stageShareMatch[2])} (Budgetanteil ${percentLabel(stageShareMatch[3])}).`;
  }

  const activationThresholdMatch = compactRaw.match(
    /^Event probability ([\d.]+) clears the Activate threshold ([\d.]+)\.$/i,
  );
  if (activationThresholdMatch) {
    return `${OPERATOR_LABELS.forecast_event_probability}: ${percentFromModelValue(activationThresholdMatch[1])}. Das passt zu Aktivieren.`;
  }

  const prepareThresholdMatch = compactRaw.match(
    /^Event probability ([\d.]+) clears the Prepare threshold ([\d.]+), but not all Activate conditions are met\.$/i,
  );
  if (prepareThresholdMatch) {
    return `${OPERATOR_LABELS.forecast_event_probability}: ${percentFromModelValue(prepareThresholdMatch[1])}. Das passt zu Vorbereiten (noch nicht Aktivieren).`;
  }

  const belowThresholdMatch = compactRaw.match(
    /^Event probability ([\d.]+) stays below the rule set needed for Prepare\/Activate\.$/i,
  );
  if (belowThresholdMatch) {
    return `${OPERATOR_LABELS.forecast_event_probability}: ${percentFromModelValue(belowThresholdMatch[1])}. Noch zu früh für Vorbereiten oder Aktivieren.`;
  }

  const explanationMatch = compactRaw.match(
    /^(.+?): (Activate|Prepare|Watch) because event probability is ([\d.]+), (?:signal support|forecast confidence) is ([\d.]+), trend acceleration is ([-\d.]+), and cross-source direction is (up|down|flat)\.$/i,
  );
  if (explanationMatch) {
    const region = normalizeGermanText(explanationMatch[1]);
    const details = [
      `${OPERATOR_LABELS.forecast_event_probability} ${percentFromModelValue(explanationMatch[3])}`,
      `${OPERATOR_LABELS.signal_confidence} ${percentFromModelValue(explanationMatch[4])}`,
      `Quellen eher ${directionLabel(explanationMatch[6])}`,
    ];
    return `${stageSentence(region, explanationMatch[2])} (${details.join(', ')}).`;
  }

  const legacyActivateMatch = compactRaw.match(
    /^(.+?): Activate because event probability is ([\d.]+) and source alignment stays supportive\.$/i,
  );
  if (legacyActivateMatch) {
    const region = normalizeGermanText(legacyActivateMatch[1]);
    return `${stageSentence(region, 'activate')} (${OPERATOR_LABELS.forecast_event_probability} ${percentFromModelValue(legacyActivateMatch[2])}, Quellenlage stützt das Signal).`;
  }

  const legacyWatchMatch = compactRaw.match(
    /^(.+?): Watch because probability and trend stay below the current action thresholds\.$/i,
  );
  if (legacyWatchMatch) {
    const region = normalizeGermanText(legacyWatchMatch[1]);
    return `${stageSentence(region, 'watch')} (${OPERATOR_LABELS.forecast_event_probability} und Dynamik reichen noch nicht aus).`;
  }

  const strongConfidenceMatch = compactRaw.match(/^(?:Signal support|Forecast confidence) is strong at ([\d.]+)\.$/i);
  if (strongConfidenceMatch) {
    return `Das Signal wirkt stabil (${percentFromModelValue(strongConfidenceMatch[1])}).`;
  }

  const usableConfidenceMatch = compactRaw.match(/^(?:Signal support|Forecast confidence) is usable at ([\d.]+)\.$/i);
  if (usableConfidenceMatch) {
    return `Das Signal wirkt brauchbar (${percentFromModelValue(usableConfidenceMatch[1])}).`;
  }

  const weakConfidenceMatch = compactRaw.match(/^(?:Signal support|Forecast confidence) is only ([\d.]+)\.$/i);
  if (weakConfidenceMatch) {
    return `Das Signal ist noch unsicher (${percentFromModelValue(weakConfidenceMatch[1])}).`;
  }

  const revisionHighMatch = compactRaw.match(/^Revision risk is high at ([\d.]+)\.$/i);
  if (revisionHighMatch) {
    return `Die Zahlen können sich noch deutlich ändern (${percentFromModelValue(revisionHighMatch[1])}).`;
  }

  const revisionMaterialMatch = compactRaw.match(/^Revision risk is still material at ([\d.]+)\.$/i);
  if (revisionMaterialMatch) {
    return `Die Zahlen können sich noch ändern (${percentFromModelValue(revisionMaterialMatch[1])}).`;
  }

  if (/^Revision risk remains visible\.$/i.test(compactRaw)) {
    return 'Die Zahlen können sich noch ändern (z.B. durch Nachmeldungen).';
  }

  if (/^Residual uncertainty is currently limited\.$/i.test(compactRaw)) {
    return 'Aktuell gibt es nur wenige Warnhinweise.';
  }

  const remainingUncertaintyMatch = compactRaw.match(/^Remaining uncertainty: (.+)\.$/i);
  if (remainingUncertaintyMatch) {
    const parts = remainingUncertaintyMatch[1]
      .split(',')
      .map((item) => uncertaintyItemLabel(item))
      .filter(Boolean);
    return `Noch offen: ${joinList(parts)}.`;
  }

  const sourceFreshnessMatch = compactRaw.match(/^Primary sources are fresh on average \(([\d.]+) days old\)\.$/i);
  if (sourceFreshnessMatch) {
    return `Die wichtigsten Quellen sind aktuell (Ø ${localizedNumber(Number(sourceFreshnessMatch[1]), 1)} Tage).`;
  }

  const trendSupportMatch = compactRaw.match(/^Recent trend acceleration is supportive \(([-\d.]+)\)\.$/i);
  if (trendSupportMatch) {
    return 'Die letzten Tage stützen diese Richtung.';
  }

  if (/^Trend acceleration is not yet convincing \([-\d.]+\)\.$/i.test(compactRaw)) {
    return 'Die Dynamik reicht noch nicht für einen klaren nächsten Schritt.';
  }

  if (/^Cross-source agreement does not clearly confirm an upward move\.$/i.test(compactRaw)) {
    return 'Die Quellen zeigen noch nicht klar nach oben.';
  }

  if (/^Regional forecast quality gate is currently not passed\.$/i.test(compactRaw)) {
    return 'Die regionale Vorhersage ist aktuell noch nicht stark genug für eine Freigabe.';
  }

  const stageBaseMatch = compactRaw.match(/^(Activate|Prepare|Watch) from the decision engine sets the base activation level\.$/i);
  if (stageBaseMatch) {
    return `${stageLabel(stageBaseMatch[1])} ist hier die grundlegende Aktivierungsstufe.`;
  }

  const rankDriverMatch = compactRaw.match(/^Priority score ([\d.]+) and event probability ([\d.]+) drive the ranking\.$/i);
  if (rankDriverMatch) {
    return `${COCKPIT_SEMANTICS.decisionPriority.label} und ${COCKPIT_SEMANTICS.eventProbability.label} bestimmen hier die Reihenfolge.`;
  }

  if (/^Priority score and event probability drive the ranking\.$/i.test(compactRaw)) {
    return `${COCKPIT_SEMANTICS.decisionPriority.label} und ${COCKPIT_SEMANTICS.eventProbability.label} bestimmen hier die Reihenfolge.`;
  }

  if (/^Activate regions receive the strongest label multiplier\.$/i.test(compactRaw)) {
    return 'Bei Aktivieren wird Budget stärker konzentriert.';
  }

  if (/^Prepare regions stay eligible, but below Activate in weighting\.$/i.test(compactRaw)) {
    return 'Vorbereiten bleibt möglich, wird aber niedriger gewichtet.';
  }

  if (/^Watch regions are observation-first and usually receive no spend\.$/i.test(compactRaw)) {
    return 'Beobachten bleibt vorerst prüfend und bekommt meist kein zusätzliches Budget.';
  }

  const confidenceLowPenaltyMatch = compactRaw.match(/^(?:Allocation support score|Confidence) ([\d.]+) keeps the allocation penalty low\.$/i);
  if (confidenceLowPenaltyMatch) {
    return `Hohe ${OPERATOR_LABELS.signal_confidence} (${percentFromModelValue(confidenceLowPenaltyMatch[1])}): Budget wird nur leicht reduziert.`;
  }

  const confidenceModeratePenaltyMatch = compactRaw.match(/^(?:Allocation support score|Confidence) ([\d.]+) leads to a moderate spend penalty\.$/i);
  if (confidenceModeratePenaltyMatch) {
    return `Mittlere ${OPERATOR_LABELS.signal_confidence} (${percentFromModelValue(confidenceModeratePenaltyMatch[1])}): Budget wird moderat reduziert.`;
  }

  const lowConfidenceMatch = compactRaw.match(/^Low (?:allocation support score|confidence) ([\d.]+) sharply reduces allocation\.$/i);
  if (lowConfidenceMatch) {
    return `Geringe ${OPERATOR_LABELS.signal_confidence} (${percentFromModelValue(lowConfidenceMatch[1])}): Budget wird deutlich reduziert.`;
  }

  const populationWeightMatch = compactRaw.match(/^Population weighting contributes ([\d.]+) to addressable reach\.$/i);
  if (populationWeightMatch) {
    return 'Die Reichweite der Region stärkt den Vorschlag.';
  }

  const regionBoostMatch = compactRaw.match(/^Configured region weight ([\d.]+) boosts the allocation score\.$/i);
  if (regionBoostMatch) {
    return `Die hinterlegte Regionsgewichtung erhöht den Vorschlag.`;
  }

  const regionReduceMatch = compactRaw.match(/^Configured region weight ([\d.]+) reduces the allocation score\.$/i);
  if (regionReduceMatch) {
    return `Die hinterlegte Regionsgewichtung senkt den Vorschlag etwas.`;
  }

  if (/^Low source freshness adds an extra allocation penalty\.$/i.test(compactRaw)) {
    return 'Datenstand eher alt: Budget wird vorsichtiger verteilt.';
  }

  if (/^High revision risk adds an extra allocation penalty\.$/i.test(compactRaw)) {
    return 'Zahlen können sich noch ändern: Budget wird vorsichtiger verteilt.';
  }

  const suggestedShareMatch = compactRaw.match(/^Suggested budget share is ([\d.]+)%\.$/i);
  if (suggestedShareMatch) {
    return `Vorgeschlagener Budgetanteil: ${percentLabel(suggestedShareMatch[1])}.`;
  }

  const revisionShareMatch = compactRaw.match(/^Revision risk slightly reduces share\.$/i);
  if (revisionShareMatch) {
    return 'Zahlen können sich noch ändern: Budgetanteil wird leicht reduziert.';
  }

  const sourceSoftMatch = compactRaw.match(/^Source freshness is soft at ([\d.]+)\.$/i);
  if (sourceSoftMatch) {
    return `Datenstand noch nicht aktuell (${percentFromModelValue(sourceSoftMatch[1])}).`;
  }

  const allocationConfidenceMatch = compactRaw.match(
    /^Allocation (?:support score|confidence) ([\d.]+) and priority rank (\d+) keep the region in the current wave plan\.$/i,
  );
  if (allocationConfidenceMatch) {
    return `Die Region bleibt im Wochenplan (Signalstärke ${percentFromModelValue(allocationConfidenceMatch[1])}, Rang ${allocationConfidenceMatch[2]}).`;
  }

  const productFitMatch = compactRaw.match(/^(.+?) scores ([\d.]+) for the available product set (.+)\.$/i);
  if (productFitMatch) {
    const productList = compactListLabel(productFitMatch[3]);
    return `${normalizeGermanText(productFitMatch[1])}: passt zum Produktset (Passung ${localizedNumber(Number(productFitMatch[2]), 2)}).${productList ? ` Produkte: ${normalizeGermanText(productList)}.` : ''}`;
  }

  const regionProductBoostMatch = compactRaw.match(/^Region\/product fit boosts this cluster by ([\d.]+)\.$/i);
  if (regionProductBoostMatch) {
    return 'Region und Produkt passen gut zusammen und stärken den Vorschlag.';
  }

  const keywordFitMatch = compactRaw.match(/^(.+?) translates the product cluster into concrete search intent with fit ([\d.]+)\.$/i);
  if (keywordFitMatch) {
    return `${normalizeGermanText(keywordFitMatch[1])} lässt sich gut in konkrete Suchanfragen übersetzen.`;
  }

  const budgetAmountMatch = compactRaw.match(/^Suggested campaign budget is ([\d.]+) EUR\.$/i);
  if (budgetAmountMatch) {
    return `Budgetvorschlag: ${currencyLabel(budgetAmountMatch[1])}.`;
  }

  const budgetShareContributionMatch = compactRaw.match(/^Budget share contribution is ([\d.]+)%\.$/i);
  if (budgetShareContributionMatch) {
    return `Budgetanteil: ${percentLabel(budgetShareContributionMatch[1])}.`;
  }

  const evidenceClassMatch = compactRaw.match(/^Evidence class is (.+)\.$/i);
  if (evidenceClassMatch) {
    return `Evidenzstatus: ${evidenceClassLabel(evidenceClassMatch[1])}.`;
  }

  const signalOutcomeMatch = compactRaw.match(/^Signal\/outcome agreement is (.+)\.$/i);
  if (signalOutcomeMatch) {
    return `Abgleich Signal und Kundendaten: ${agreementLabel(signalOutcomeMatch[1])}.`;
  }

  if (/^Spend guardrails are currently satisfied\.$/i.test(compactRaw)) {
    return 'Budget-Regeln: ok. Nächster Schritt möglich.';
  }

  if (/^Budget is below the standalone threshold and should be bundled with a neighboring region or shared flight\.$/i.test(compactRaw)) {
    return 'Das Budget ist für eine einzelne Region noch zu klein; sinnvoll ist eine Bündelung mit einer Nachbarregion.';
  }

  if (/^(?:Allocation support score|Confidence) is below the stage-specific guardrail, so the recommendation needs manual review\.$/i.test(compactRaw)) {
    return 'Das Signal ist noch nicht sicher genug; vor dem nächsten Schritt ist eine manuelle Prüfung sinnvoll.';
  }

  if (/^Operational or commercial spend gate is still blocking execution\.$/i.test(compactRaw)) {
    return 'Ein offener Freigabe-Punkt blockiert den nächsten Schritt noch.';
  }

  if (/^Recommendation stays discussion-only for now\.$/i.test(compactRaw)) {
    return 'Der Vorschlag ist noch nicht freigabefähig; erst prüfen und einordnen.';
  }

  if (/^Demand remains soft\.$/i.test(compactRaw)) {
    return 'Die Nachfrage bleibt noch verhalten.';
  }

  if (/^Region is not currently eligible for spend under the configured label rules\.$/i.test(compactRaw)) {
    return 'Die Region ist unter den aktuellen Regeln noch nicht für zusätzliches Budget freigegeben.';
  }

  return normalized
    .replace(/\s+—\s+/g, ' — ')
    .replace(/\s+\./g, '.');
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
      headline: `Die Prognose zeigt im ${horizonDays}-Tage-Fenster die größte Dynamik aktuell in ${cleanedRegion}.`,
      supportingText: 'Damit ist früh sichtbar, wo als Nächstes priorisiert werden sollte und wo Budget gezielt eingesetzt werden kann.',
      proofPoints: visibleProofPoints,
      cautionText: 'Die Richtung ist nachvollziehbar, aber keine Vorhersage ist eine Garantie.',
      assertive: true,
    };
  }

  return {
    headline: `Im ${horizonDays}-Tage-Fenster deuten die Daten aktuell auf die größte Dynamik in ${cleanedRegion} hin.`,
    supportingText: 'Dort lohnt sich ein erster Blick. Vor einer Freigabe werden Datenlage und Stabilität noch geprüft.',
    proofPoints: visibleProofPoints,
    cautionText: 'Die Richtung ist erkennbar, aber Warnhinweise bleiben sichtbar und werden vor einer Freigabe geprüft.',
    assertive: false,
  };
}
