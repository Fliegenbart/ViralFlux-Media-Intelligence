import { PredictionNarrative, StructuredReasonItem } from '../types/media';

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
  [/\bOutcome-Learnings\b/g, 'Erkenntnisse aus Kundendaten'],
  [/\bOutcome-Learning\b/g, 'Erkenntnis aus Kundendaten'],
  [/\bOutcome-Score\b/g, 'Wirkungssignal'],
  [/\bOutcome-Metrik\b/g, 'Wirkungszahl'],
  [/\bOutcome-Daten\b/g, 'Kundendaten'],
  [/\bOutcome\b/g, 'Wirkungsdaten'],
  [/\bTruth-Historie\b/g, 'Kundendatenhistorie'],
  [/\bTruth-Gate\b/g, 'Freigabestatus Kundendaten'],
  [/\bTruth-Layer\b/g, 'Kundendatenbasis'],
  [/\bTruth\b/g, 'Kundendaten'],
  [/\bBusiness-Gate\b/g, 'Freigabestatus'],
  [/\bHoldout-Validierung\b/g, 'Validierung mit Vergleichsgruppe'],
  [/\bHoldout-Design\b/g, 'Vergleichsgruppendesign'],
  [/\bHoldout-Test\b/g, 'Vergleichsgruppentest'],
  [/\bHoldout\b/g, 'Vergleichsgruppe'],
  [/\bLift-Metriken\b/g, 'Mehrwirkungswerte'],
  [/\bLift\b/g, 'Mehrwirkung'],
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
  if (normalized === 'activate') return `${region} sollte jetzt aktiviert werden`;
  if (normalized === 'prepare') return `${region} sollte jetzt vorbereitet werden`;
  return `${region} bleibt vorerst im Beobachtungsmodus`;
}

function directionLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'up') return 'aufwärts';
  if (normalized === 'down') return 'abwärts';
  return 'seitwärts';
}

function evidenceClassLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'truth_backed') return 'mit Kundendaten gestützt';
  if (normalized === 'epidemiological_only') return 'nur durch Forecast- und Marktdaten gestützt';
  if (normalized === 'no_truth') return 'ohne Kundendaten';
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
      ? 'sichtbarem Revisionsrisiko'
      : `Revisionsrisiko von ${percentFromModelValue(String(revisionRisk))}`;
  }
  if (code === 'freshness_score') {
    const freshnessScore = reasonNumber(item, 'freshness_score');
    return freshnessScore == null
      ? 'schwacher Datenfrische'
      : `Datenfrische von nur ${percentFromModelValue(String(freshnessScore))}`;
  }
  if (code === 'thin_agreement_evidence') return 'zu wenig übereinstimmenden Quellen';
  if (code === 'no_positive_cross_source_agreement') return 'keinem klar positiven Quellenabgleich';
  if (code === 'quality_gate_not_passed') return 'noch nicht bestandener Qualitätsprüfung';
  return normalizeGermanText(code.replace(/_/g, ' '));
}

function translateStructuredReason(item: StructuredReasonItem): string | null {
  switch (item.code) {
    case 'decision_summary': {
      const region = normalizeGermanText(reasonString(item, 'bundesland_name') || 'Die Region');
      const stage = reasonString(item, 'stage') || 'watch';
      const eventProbability = reasonNumber(item, 'event_probability');
      const forecastConfidence = reasonNumber(item, 'forecast_confidence');
      const agreementDirection = reasonString(item, 'agreement_direction');
      return `${stageSentence(region, stage)}, weil die Event-Wahrscheinlichkeit bei ${percentFromModelValue(String(eventProbability ?? 0))} liegt, die Forecast-Sicherheit bei ${percentFromModelValue(String(forecastConfidence ?? 0))} liegt und der Quellenabgleich aktuell eher ${directionLabel(agreementDirection)} zeigt.`;
    }
    case 'uncertainty_summary': {
      const parts = reasonStringList(item, 'parts');
      if (parts.length === 0) return 'Die verbleibende Unsicherheit ist aktuell gering.';
      return `Es bleibt Unsicherheit wegen ${joinList(parts.map((part) => uncertaintyPartLabel(part, item)))}.`;
    }
    case 'event_probability_activate_threshold':
      return `Die Vorhersage liegt mit ${percentFromModelValue(String(reasonNumber(item, 'event_probability') ?? 0))} über der Schwelle für eine Aktivierung.`;
    case 'event_probability_prepare_threshold':
      return `Die Vorhersage spricht mit ${percentFromModelValue(String(reasonNumber(item, 'event_probability') ?? 0))} für Vorbereitung, aber noch nicht für eine volle Aktivierung.`;
    case 'event_probability_below_prepare_threshold':
      return `Die Vorhersage reicht mit ${percentFromModelValue(String(reasonNumber(item, 'event_probability') ?? 0))} aktuell nicht für Vorbereitung oder Aktivierung.`;
    case 'forecast_confidence_strong':
      return `Die Vorhersage ist mit ${percentFromModelValue(String(reasonNumber(item, 'forecast_confidence') ?? 0))} Sicherheit stabil.`;
    case 'forecast_confidence_usable':
      return `Die Vorhersage ist mit ${percentFromModelValue(String(reasonNumber(item, 'forecast_confidence') ?? 0))} Sicherheit nutzbar.`;
    case 'forecast_confidence_low':
      return `Die Vorhersage ist mit ${percentFromModelValue(String(reasonNumber(item, 'forecast_confidence') ?? 0))} Sicherheit noch recht unsicher.`;
    case 'primary_sources_fresh':
      return `Die wichtigsten Quellen sind im Schnitt ${localizedNumber(reasonNumber(item, 'freshness_days') ?? 0, 1)} Tage alt und damit aktuell.`;
    case 'primary_sources_stale':
      return `Die wichtigsten Quellen sind mit durchschnittlich ${localizedNumber(reasonNumber(item, 'freshness_days') ?? 0, 1)} Tagen gerade eher veraltet.`;
    case 'revision_risk_high':
      return `Das Revisionsrisiko ist mit ${percentFromModelValue(String(reasonNumber(item, 'revision_risk') ?? 0))} aktuell hoch.`;
    case 'revision_risk_material':
    case 'uncertainty_revision_risk_material':
      return `Das Revisionsrisiko ist mit ${percentFromModelValue(String(reasonNumber(item, 'revision_risk') ?? 0))} weiter spürbar.`;
    case 'trend_acceleration_supportive':
      return 'Die jüngste Dynamik stützt die Einschätzung zusätzlich.';
    case 'trend_acceleration_not_convincing':
      return 'Die aktuelle Dynamik ist noch nicht stark genug für einen klaren nächsten Schritt.';
    case 'cross_source_agreement_low_evidence': {
      const signalCount = reasonNumber(item, 'signal_count');
      return signalCount != null && signalCount > 0
        ? `Es gibt aktuell nur ${localizedNumber(signalCount, 0)} belastbare Richtungssignale aus den Quellen.`
        : 'Es gibt aktuell zu wenig belastbare Richtungssignale aus den Quellen.';
    }
    case 'cross_source_agreement_upward': {
      const signalCount = reasonNumber(item, 'signal_count');
      return signalCount != null && signalCount > 0
        ? `${localizedNumber(signalCount, 0)} Quellen zeigen aktuell in dieselbe Aufwärtsrichtung.`
        : 'Mehrere Quellen zeigen aktuell in dieselbe Aufwärtsrichtung.';
    }
    case 'cross_source_agreement_not_upward':
      return 'Die Quellen bestätigen einen Aufwärtstrend noch nicht eindeutig.';
    case 'quality_gate_not_passed':
      return 'Die regionale Vorhersage ist aktuell noch nicht stark genug für eine Freigabe.';
    case 'final_stage_policy_overlay':
      return `Die Rohlogik sieht ${stageLabel(reasonString(item, 'signal_stage'))} vor, aber die Freigaberegeln halten die Region aktuell auf ${stageLabel(reasonString(item, 'final_stage'))}.`;
    case 'policy_override_watch_only':
      return 'Eine Regel hält die Region bewusst im Beobachtungsmodus, auch wenn das Rohsignal stärker aussieht.';
    case 'policy_override_quality_gate':
      return 'Die Qualitätsprüfung blockiert aktuell eine höhere Freigabestufe.';
    case 'policy_override':
      return 'Eine zusätzliche Freigaberegel verändert die endgültige Entscheidungsstufe.';
    case 'decision_stage_base':
      return `${stageLabel(reasonString(item, 'stage'))} ist hier die grundlegende Aktivierungsstufe.`;
    case 'ranking_priority_and_probability':
      return 'Prioritäts-Score und Event-Wahrscheinlichkeit treiben hier das Ranking.';
    case 'budget_driver_activate_multiplier':
      return 'Aktivierungsregionen erhalten in der Budgetlogik den stärksten Zuschlag.';
    case 'budget_driver_prepare_weighting':
      return 'Vorbereitungsregionen bleiben budgetfähig, liegen in der Gewichtung aber unter Aktivierungsregionen.';
    case 'budget_driver_watch_observe_only':
      return 'Beobachtungsregionen bleiben vorerst in der Prüfung und erhalten meist kein zusätzliches Budget.';
    case 'budget_driver_confidence_low_penalty':
      return `Die Signal-Sicherheit von ${percentFromModelValue(String(reasonNumber(item, 'confidence') ?? 0))} hält den Budgetabschlag gering.`;
    case 'budget_driver_confidence_moderate_penalty':
      return `Die Signal-Sicherheit von ${percentFromModelValue(String(reasonNumber(item, 'confidence') ?? 0))} führt zu einem moderaten Budgetabschlag.`;
    case 'budget_driver_confidence_high_penalty':
      return `Die geringe Signal-Sicherheit von ${percentFromModelValue(String(reasonNumber(item, 'confidence') ?? 0))} drückt die Budgetverteilung deutlich.`;
    case 'budget_driver_population_weight':
      return 'Die Reichweitenlogik spricht zusätzlich für die Region.';
    case 'budget_driver_region_weight_boost':
      return 'Die hinterlegte Regionsgewichtung stärkt den Allokationswert zusätzlich.';
    case 'budget_driver_region_weight_reduce':
      return 'Die hinterlegte Regionsgewichtung reduziert den Allokationswert etwas.';
    case 'budget_driver_source_freshness_penalty':
      return 'Die geringe Datenfrische führt zu einem zusätzlichen Budgetabschlag.';
    case 'budget_driver_revision_risk_penalty':
      return 'Das hohe Revisionsrisiko führt zu einem zusätzlichen Budgetabschlag.';
    case 'budget_driver_suggested_share':
      return `Der vorgeschlagene Budgetanteil liegt bei ${percentFromModelValue(String(reasonNumber(item, 'suggested_budget_share') ?? 0))}.`;
    case 'uncertainty_source_freshness_soft':
      return `Die Datenfrische ist mit ${percentFromModelValue(String(reasonNumber(item, 'source_freshness') ?? 0))} eher schwach.`;
    case 'budget_ineligible_region':
      return 'Die Region ist unter den aktuellen Regeln noch nicht für zusätzliches Budget freigegeben.';
    case 'campaign_stage_budget_share':
      return `${normalizeGermanText(reasonString(item, 'region_name') || 'Die Region')} bleibt aktuell auf ${stageLabel(reasonString(item, 'stage'))} mit ${percentFromModelValue(String(reasonNumber(item, 'budget_share') ?? 0))} Budgetanteil.`;
    case 'campaign_wave_plan_support':
      return `Die Allokations-Sicherheit von ${percentFromModelValue(String(reasonNumber(item, 'confidence') ?? 0))} und Rang ${localizedNumber(reasonNumber(item, 'priority_rank') ?? 0, 0)} halten die Region im aktuellen Wochenplan.`;
    case 'campaign_product_cluster_fit': {
      const cluster = normalizeGermanText(reasonString(item, 'cluster_label'));
      const fitScore = reasonNumber(item, 'fit_score');
      const products = joinList(reasonStringList(item, 'products').map((entry) => normalizeGermanText(entry)));
      return `${cluster} passt mit ${localizedNumber(fitScore ?? 0, 2)} gut zum verfügbaren Produktsortiment${products ? ` ${products}` : ''}.`;
    }
    case 'campaign_region_product_fit_boost':
      return 'Die Kombination aus Region und Produkt stärkt diesen Cluster zusätzlich.';
    case 'campaign_keyword_cluster_fit':
      return `${normalizeGermanText(reasonString(item, 'cluster_label'))} übersetzt den Produktfokus gut in konkrete Suchanfragen.`;
    case 'campaign_budget_amount':
      return `Das vorgeschlagene Kampagnenbudget liegt bei ${currencyLabel(String(reasonNumber(item, 'budget_amount') ?? 0))}.`;
    case 'campaign_budget_share':
      return `Der Kampagnenvorschlag erhält ${percentFromModelValue(String(reasonNumber(item, 'budget_share') ?? 0))} Budgetanteil.`;
    case 'campaign_evidence_class':
      return `Der Evidenzstatus ist ${evidenceClassLabel(reasonString(item, 'evidence_class'))}.`;
    case 'campaign_signal_outcome_agreement':
      return `Der Abgleich zwischen Signal und Kundendaten ist ${agreementLabel(reasonString(item, 'status'))}.`;
    case 'campaign_guardrail_ready':
      return 'Die Budget- und Freigabegrenzen sind aktuell erfüllt.';
    case 'campaign_guardrail_bundle_neighbor':
      return 'Das Budget ist für eine Einzelregion noch zu klein und sollte mit einer Nachbarregion gebündelt werden.';
    case 'campaign_guardrail_low_confidence_review':
      return 'Die Signal-Sicherheit liegt unter der Stufengrenze, deshalb braucht der Vorschlag noch eine manuelle Prüfung.';
    case 'campaign_guardrail_blocked':
      return 'Operative oder kommerzielle Freigaben blockieren die Ausführung noch.';
    case 'campaign_guardrail_discussion_only':
      return 'Die Empfehlung bleibt vorerst ein Diskussionsvorschlag.';
    default:
      return null;
  }
}

function uncertaintyItemLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  const revisionMatch = normalized.match(/^revision risk ([\d.]+)$/i);
  if (revisionMatch) {
    return `Revisionsrisiko von ${percentFromModelValue(revisionMatch[1])}`;
  }
  const freshnessMatch = normalized.match(/^freshness score ([\d.]+)$/i);
  if (freshnessMatch) {
    return `Datenfrische von nur ${percentFromModelValue(freshnessMatch[1])}`;
  }
  if (normalized === 'thin agreement evidence') return 'zu wenig übereinstimmende Quellen';
  if (normalized === 'no positive cross-source agreement') return 'kein klar positiver Quellenabgleich';
  if (normalized === 'quality gate not passed') return 'noch nicht bestandene Qualitätsprüfung';
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
    return `${normalizeGermanText(belowActionMatch[1])} bleibt aktuell unter der Handlungsschwelle.`;
  }

  const stageShareMatch = compactRaw.match(/^(.+?) stays on (Activate|Prepare|Watch) with budget share ([\d.]+)%\.$/i);
  if (stageShareMatch) {
    return `${normalizeGermanText(stageShareMatch[1])} bleibt aktuell auf ${stageLabel(stageShareMatch[2])} mit ${percentLabel(stageShareMatch[3])} Budgetanteil.`;
  }

  const activationThresholdMatch = compactRaw.match(
    /^Event probability ([\d.]+) clears the Activate threshold ([\d.]+)\.$/i,
  );
  if (activationThresholdMatch) {
    return `Die Vorhersage liegt mit ${percentFromModelValue(activationThresholdMatch[1])} über der Schwelle für eine Aktivierung.`;
  }

  const prepareThresholdMatch = compactRaw.match(
    /^Event probability ([\d.]+) clears the Prepare threshold ([\d.]+), but not all Activate conditions are met\.$/i,
  );
  if (prepareThresholdMatch) {
    return `Die Vorhersage spricht mit ${percentFromModelValue(prepareThresholdMatch[1])} für Vorbereitung, aber noch nicht für eine volle Aktivierung.`;
  }

  const belowThresholdMatch = compactRaw.match(
    /^Event probability ([\d.]+) stays below the rule set needed for Prepare\/Activate\.$/i,
  );
  if (belowThresholdMatch) {
    return `Die Vorhersage reicht mit ${percentFromModelValue(belowThresholdMatch[1])} aktuell nicht für Vorbereitung oder Aktivierung.`;
  }

  const explanationMatch = compactRaw.match(
    /^(.+?): (Activate|Prepare|Watch) because event probability is ([\d.]+), forecast confidence is ([\d.]+), trend acceleration is ([-\d.]+), and cross-source direction is (up|down|flat)\.$/i,
  );
  if (explanationMatch) {
    const region = normalizeGermanText(explanationMatch[1]);
    return `${stageSentence(region, explanationMatch[2])}, weil die Event-Wahrscheinlichkeit bei ${percentFromModelValue(explanationMatch[3])} liegt, die Forecast-Sicherheit bei ${percentFromModelValue(explanationMatch[4])} liegt und der Quellenabgleich aktuell eher ${directionLabel(explanationMatch[6])} zeigt.`;
  }

  const legacyActivateMatch = compactRaw.match(
    /^(.+?): Activate because event probability is ([\d.]+) and source alignment stays supportive\.$/i,
  );
  if (legacyActivateMatch) {
    const region = normalizeGermanText(legacyActivateMatch[1]);
    return `${region} sollte jetzt aktiviert werden, weil die Event-Wahrscheinlichkeit bei ${percentFromModelValue(legacyActivateMatch[2])} liegt und die Quellenlage das Signal stützt.`;
  }

  const legacyWatchMatch = compactRaw.match(
    /^(.+?): Watch because probability and trend stay below the current action thresholds\.$/i,
  );
  if (legacyWatchMatch) {
    return `${normalizeGermanText(legacyWatchMatch[1])} bleibt vorerst im Beobachtungsmodus, weil Wahrscheinlichkeit und Trend noch unter den aktuellen Handlungsschwellen liegen.`;
  }

  const strongConfidenceMatch = compactRaw.match(/^Forecast confidence is strong at ([\d.]+)\.$/i);
  if (strongConfidenceMatch) {
    return `Die Vorhersage ist mit ${percentFromModelValue(strongConfidenceMatch[1])} Sicherheit stabil.`;
  }

  const usableConfidenceMatch = compactRaw.match(/^Forecast confidence is usable at ([\d.]+)\.$/i);
  if (usableConfidenceMatch) {
    return `Die Vorhersage ist mit ${percentFromModelValue(usableConfidenceMatch[1])} Sicherheit nutzbar.`;
  }

  const weakConfidenceMatch = compactRaw.match(/^Forecast confidence is only ([\d.]+)\.$/i);
  if (weakConfidenceMatch) {
    return `Die Vorhersage ist mit ${percentFromModelValue(weakConfidenceMatch[1])} Sicherheit noch recht unsicher.`;
  }

  const revisionHighMatch = compactRaw.match(/^Revision risk is high at ([\d.]+)\.$/i);
  if (revisionHighMatch) {
    return `Das Revisionsrisiko ist mit ${percentFromModelValue(revisionHighMatch[1])} aktuell hoch.`;
  }

  const revisionMaterialMatch = compactRaw.match(/^Revision risk is still material at ([\d.]+)\.$/i);
  if (revisionMaterialMatch) {
    return `Das Revisionsrisiko ist mit ${percentFromModelValue(revisionMaterialMatch[1])} weiter spürbar.`;
  }

  if (/^Revision risk remains visible\.$/i.test(compactRaw)) {
    return 'Ein Revisionsrisiko bleibt sichtbar.';
  }

  if (/^Residual uncertainty is currently limited\.$/i.test(compactRaw)) {
    return 'Die verbleibende Unsicherheit ist aktuell gering.';
  }

  const remainingUncertaintyMatch = compactRaw.match(/^Remaining uncertainty: (.+)\.$/i);
  if (remainingUncertaintyMatch) {
    const parts = remainingUncertaintyMatch[1]
      .split(',')
      .map((item) => uncertaintyItemLabel(item))
      .filter(Boolean);
    return `Es bleibt Unsicherheit wegen ${joinList(parts)}.`;
  }

  const sourceFreshnessMatch = compactRaw.match(/^Primary sources are fresh on average \(([\d.]+) days old\)\.$/i);
  if (sourceFreshnessMatch) {
    return `Die wichtigsten Quellen sind im Schnitt ${localizedNumber(Number(sourceFreshnessMatch[1]), 1)} Tage alt und damit aktuell.`;
  }

  const trendSupportMatch = compactRaw.match(/^Recent trend acceleration is supportive \(([-\d.]+)\)\.$/i);
  if (trendSupportMatch) {
    return 'Die jüngste Dynamik stützt die Einschätzung zusätzlich.';
  }

  if (/^Trend acceleration is not yet convincing \([-\d.]+\)\.$/i.test(compactRaw)) {
    return 'Die aktuelle Dynamik ist noch nicht stark genug für einen klaren nächsten Schritt.';
  }

  if (/^Cross-source agreement does not clearly confirm an upward move\.$/i.test(compactRaw)) {
    return 'Die Quellen bestätigen einen Aufwärtstrend noch nicht eindeutig.';
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
    return `Prioritäts-Score und Event-Wahrscheinlichkeit treiben hier das Ranking.`;
  }

  if (/^Activate regions receive the strongest label multiplier\.$/i.test(compactRaw)) {
    return 'Aktivierungsregionen erhalten in der Budgetlogik den stärksten Zuschlag.';
  }

  if (/^Prepare regions stay eligible, but below Activate in weighting\.$/i.test(compactRaw)) {
    return 'Vorbereitungsregionen bleiben budgetfähig, liegen in der Gewichtung aber unter Aktivierungsregionen.';
  }

  if (/^Watch regions are observation-first and usually receive no spend\.$/i.test(compactRaw)) {
    return 'Beobachtungsregionen bleiben vorerst in der Prüfung und erhalten meist kein zusätzliches Budget.';
  }

  const confidenceLowPenaltyMatch = compactRaw.match(/^Confidence ([\d.]+) keeps the allocation penalty low\.$/i);
  if (confidenceLowPenaltyMatch) {
    return `Die Signal-Sicherheit von ${percentFromModelValue(confidenceLowPenaltyMatch[1])} hält den Budgetabschlag gering.`;
  }

  const confidenceModeratePenaltyMatch = compactRaw.match(/^Confidence ([\d.]+) leads to a moderate spend penalty\.$/i);
  if (confidenceModeratePenaltyMatch) {
    return `Die Signal-Sicherheit von ${percentFromModelValue(confidenceModeratePenaltyMatch[1])} führt zu einem moderaten Budgetabschlag.`;
  }

  const lowConfidenceMatch = compactRaw.match(/^Low confidence ([\d.]+) sharply reduces allocation\.$/i);
  if (lowConfidenceMatch) {
    return `Die geringe Signal-Sicherheit von ${percentFromModelValue(lowConfidenceMatch[1])} drückt die Budgetverteilung deutlich.`;
  }

  const populationWeightMatch = compactRaw.match(/^Population weighting contributes ([\d.]+) to addressable reach\.$/i);
  if (populationWeightMatch) {
    return 'Die Reichweitenlogik spricht zusätzlich für die Region.';
  }

  const regionBoostMatch = compactRaw.match(/^Configured region weight ([\d.]+) boosts the allocation score\.$/i);
  if (regionBoostMatch) {
    return `Die hinterlegte Regionsgewichtung stärkt den Allokationswert zusätzlich.`;
  }

  const regionReduceMatch = compactRaw.match(/^Configured region weight ([\d.]+) reduces the allocation score\.$/i);
  if (regionReduceMatch) {
    return `Die hinterlegte Regionsgewichtung reduziert den Allokationswert etwas.`;
  }

  if (/^Low source freshness adds an extra allocation penalty\.$/i.test(compactRaw)) {
    return 'Die geringe Datenfrische führt zu einem zusätzlichen Budgetabschlag.';
  }

  if (/^High revision risk adds an extra allocation penalty\.$/i.test(compactRaw)) {
    return 'Das hohe Revisionsrisiko führt zu einem zusätzlichen Budgetabschlag.';
  }

  const suggestedShareMatch = compactRaw.match(/^Suggested budget share is ([\d.]+)%\.$/i);
  if (suggestedShareMatch) {
    return `Der vorgeschlagene Budgetanteil liegt bei ${percentLabel(suggestedShareMatch[1])}.`;
  }

  const revisionShareMatch = compactRaw.match(/^Revision risk slightly reduces share\.$/i);
  if (revisionShareMatch) {
    return 'Das Revisionsrisiko drückt den Budgetanteil leicht.';
  }

  const sourceSoftMatch = compactRaw.match(/^Source freshness is soft at ([\d.]+)\.$/i);
  if (sourceSoftMatch) {
    return `Die Datenfrische ist mit ${percentFromModelValue(sourceSoftMatch[1])} eher schwach.`;
  }

  const allocationConfidenceMatch = compactRaw.match(
    /^Allocation confidence ([\d.]+) and priority rank (\d+) keep the region in the current wave plan\.$/i,
  );
  if (allocationConfidenceMatch) {
    return `Die Allokations-Sicherheit von ${percentFromModelValue(allocationConfidenceMatch[1])} und Rang ${allocationConfidenceMatch[2]} halten die Region im aktuellen Wochenplan.`;
  }

  const productFitMatch = compactRaw.match(/^(.+?) scores ([\d.]+) for the available product set (.+)\.$/i);
  if (productFitMatch) {
    const productList = compactListLabel(productFitMatch[3]);
    return `${normalizeGermanText(productFitMatch[1])} passt mit ${localizedNumber(Number(productFitMatch[2]), 2)} gut zum verfügbaren Produktsortiment${productList ? ` ${normalizeGermanText(productList)}` : ''}.`;
  }

  const regionProductBoostMatch = compactRaw.match(/^Region\/product fit boosts this cluster by ([\d.]+)\.$/i);
  if (regionProductBoostMatch) {
    return 'Die Kombination aus Region und Produkt stärkt diesen Cluster zusätzlich.';
  }

  const keywordFitMatch = compactRaw.match(/^(.+?) translates the product cluster into concrete search intent with fit ([\d.]+)\.$/i);
  if (keywordFitMatch) {
    return `${normalizeGermanText(keywordFitMatch[1])} übersetzt den Produktfokus gut in konkrete Suchanfragen.`;
  }

  const budgetAmountMatch = compactRaw.match(/^Suggested campaign budget is ([\d.]+) EUR\.$/i);
  if (budgetAmountMatch) {
    return `Das vorgeschlagene Kampagnenbudget liegt bei ${currencyLabel(budgetAmountMatch[1])}.`;
  }

  const budgetShareContributionMatch = compactRaw.match(/^Budget share contribution is ([\d.]+)%\.$/i);
  if (budgetShareContributionMatch) {
    return `Der Kampagnenvorschlag erhält ${percentLabel(budgetShareContributionMatch[1])} Budgetanteil.`;
  }

  const evidenceClassMatch = compactRaw.match(/^Evidence class is (.+)\.$/i);
  if (evidenceClassMatch) {
    return `Der Evidenzstatus ist ${evidenceClassLabel(evidenceClassMatch[1])}.`;
  }

  const signalOutcomeMatch = compactRaw.match(/^Signal\/outcome agreement is (.+)\.$/i);
  if (signalOutcomeMatch) {
    return `Der Abgleich zwischen Signal und Kundendaten ist ${agreementLabel(signalOutcomeMatch[1])}.`;
  }

  if (/^Spend guardrails are currently satisfied\.$/i.test(compactRaw)) {
    return 'Die Budget- und Freigabegrenzen sind aktuell erfüllt.';
  }

  if (/^Budget is below the standalone threshold and should be bundled with a neighboring region or shared flight\.$/i.test(compactRaw)) {
    return 'Das Budget ist für eine Einzelregion noch zu klein und sollte mit einer Nachbarregion gebündelt werden.';
  }

  if (/^Confidence is below the stage-specific guardrail, so the recommendation needs manual PEIX review\.$/i.test(compactRaw)) {
    return 'Die Signal-Sicherheit liegt unter der Stufengrenze, deshalb braucht der Vorschlag noch eine manuelle Prüfung.';
  }

  if (/^Operational or commercial spend gate is still blocking execution\.$/i.test(compactRaw)) {
    return 'Operative oder kommerzielle Freigaben blockieren die Ausführung noch.';
  }

  if (/^Recommendation stays discussion-only for now\.$/i.test(compactRaw)) {
    return 'Die Empfehlung bleibt vorerst ein Diskussionsvorschlag.';
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
      headline: `Unsere Prognose zeigt im ${horizonDays}-Tage-Fenster die größte Dynamik aktuell in ${cleanedRegion}.`,
      supportingText: 'Damit wird früh sichtbar, wo du als Nächstes priorisieren und Budget gezielter einsetzen solltest.',
      proofPoints: visibleProofPoints,
      cautionText: 'Die Lage bleibt nachvollziehbar, aber keine Vorhersage ist eine Garantie.',
      assertive: true,
    };
  }

  return {
    headline: `Im ${horizonDays}-Tage-Fenster deuten die Daten aktuell auf die größte Dynamik in ${cleanedRegion} hin.`,
    supportingText: 'Dort solltest du zuerst hinschauen. Vor einer Freigabe prüfen wir noch Datenlage und Stabilität.',
    proofPoints: visibleProofPoints,
    cautionText: 'Die Richtung ist erkennbar, aber Warnhinweise bleiben sichtbar und werden vor einer Freigabe geprüft.',
    assertive: false,
  };
}
