import { RecommendationCard } from '../../types/media';
import {
  formatPercent,
  formatSignalScore,
  primarySignalScore,
} from './cockpitUtils';

export type SignalPrediction = {
  event_probability_calibrated?: number | null;
  trend?: string | null;
} | null;

type WorkspaceStatusLike = {
  data_freshness?: string | null;
  summary?: string | null;
  blocker_count?: number | null;
  open_blockers?: string | null;
};

type EvidenceLike = {
  truth_gate?: {
    state?: string | null;
    passed?: boolean | null;
    message?: string | null;
  } | null;
  business_validation?: {
    validation_status?: string | null;
  } | null;
};

type CampaignsViewLike = {
  summary?: {
    publishable_cards?: number | null;
    active_cards?: number | null;
  } | null;
};

export function formatProbability(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  const percent = value <= 1 ? value * 100 : value;
  return formatPercent(percent, 0);
}

export function formatSignedPercent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value >= 0 ? '+' : ''}${value.toFixed(0)}%`;
}

export function formatSignedPercentPrecise(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

export function buildTrendInsight({
  regionName,
  changePct,
  trend,
  virus,
  hasTimeline,
}: {
  regionName: string;
  changePct?: number | null;
  trend?: string | null;
  virus: string;
  hasTimeline: boolean;
}): {
  tone: 'rising' | 'falling' | 'steady' | 'pending';
  headline: string;
  copy: string;
  metricValue: string;
  metricDetail: string;
  footer: string;
} {
  if (!hasTimeline) {
    return {
      tone: 'pending',
      headline: 'Signal wird gerade aufgebaut.',
      copy: 'Sobald genügend Verlaufspunkte vorliegen, wird hier sichtbar, ob sich das Signal wirklich aufbaut oder wieder abkühlt.',
      metricValue: '-',
      metricDetail: regionName || 'Fokusregion',
      footer: `Der 7-Tage-Verlauf für ${virus} wird gerade geladen.`,
    };
  }

  const safeRegionName = regionName || 'Die Fokusregion';
  const roundedDelta = formatSignedPercentPrecise(changePct);
  const trendLabel = trend ? `Trend ${trend}` : 'Trend wird eingeordnet';

  if (changePct == null || Number.isNaN(changePct)) {
    return {
      tone: 'pending',
      headline: 'Verlauf sichtbar, Vorwochenvergleich noch offen.',
      copy: `${safeRegionName} ist bereits als Verlauf sichtbar. Der Vergleich zur Vorwoche wird nachgezogen, sobald der Referenzwert vollständig vorliegt.`,
      metricValue: '-',
      metricDetail: safeRegionName,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  if (changePct >= 25) {
    return {
      tone: 'rising',
      headline: 'Signal baut sich deutlich auf.',
      copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche und zieht damit klar an. Das spricht für erhöhte Aufmerksamkeit in dieser Woche.`,
      metricValue: roundedDelta,
      metricDetail: `${safeRegionName} · ${trendLabel}`,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  if (changePct >= 5) {
    return {
      tone: 'rising',
      headline: 'Signal zieht weiter an.',
      copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche. Der Ausschlag ist sichtbar, aber noch kein maximaler Peak.`,
      metricValue: roundedDelta,
      metricDetail: `${safeRegionName} · ${trendLabel}`,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  if (changePct <= -25) {
    return {
      tone: 'falling',
      headline: 'Signal fällt deutlich zurück.',
      copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche. Das spricht eher für Beobachten als für zusätzlichen Mediadrück in dieser Woche.`,
      metricValue: roundedDelta,
      metricDetail: `${safeRegionName} · ${trendLabel}`,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  if (changePct <= -5) {
    return {
      tone: 'falling',
      headline: 'Signal kühlt wieder ab.',
      copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche. Der Verlauf ist noch relevant, aber nicht mehr so scharf wie zuletzt.`,
      metricValue: roundedDelta,
      metricDetail: `${safeRegionName} · ${trendLabel}`,
      footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
    };
  }

  return {
    tone: 'steady',
    headline: 'Signal bleibt weitgehend stabil.',
    copy: `${safeRegionName} liegt ${roundedDelta} zur Vorwoche. Der Verlauf verändert sich aktuell nur leicht und spricht eher für Beobachten als für einen harten Richtungswechsel.`,
    metricValue: roundedDelta,
    metricDetail: `${safeRegionName} · ${trendLabel}`,
    footer: `${trendLabel} · 7-Tage-Verlauf für ${virus}.`,
  };
}

export function buildSignalTiles({
  workspaceStatus,
  evidence,
  campaigns,
  topPrediction,
}: {
  workspaceStatus: WorkspaceStatusLike | null | undefined;
  evidence: EvidenceLike | null | undefined;
  campaigns: CampaignsViewLike | null | undefined;
  topPrediction: SignalPrediction;
}) {
  return [
    {
      label: 'Signalstärke',
      value: formatProbability(topPrediction?.event_probability_calibrated),
      detail: topPrediction?.trend ? `Trend ${topPrediction.trend}` : 'Trend wird eingeordnet',
      tone: scoreTone(topPrediction?.event_probability_calibrated),
    },
    {
      label: 'Evidenz',
      value: evidence?.truth_gate?.state || evidence?.business_validation?.validation_status || 'Noch offen',
      detail: evidence?.truth_gate?.message || 'Truth- und Business-Lage für diese Woche',
      tone: stateTone(evidence?.truth_gate?.passed ? 'success' : 'warning'),
    },
    {
      label: 'Datenfrische',
      value: workspaceStatus?.data_freshness || 'Noch offen',
      detail: workspaceStatus?.summary || 'Datenstand wird geladen',
      tone: stateTone(workspaceStatus?.data_freshness),
    },
    {
      label: 'Kampagnen-Reife',
      value: campaigns?.summary?.publishable_cards != null ? String(campaigns.summary.publishable_cards) : '-',
      detail: campaigns?.summary?.active_cards != null ? `${campaigns.summary.active_cards} aktive Vorschläge` : 'Noch keine Kampagnen geladen',
      tone: stateTone((campaigns?.summary?.publishable_cards || 0) > 0 ? 'success' : 'warning'),
    },
    {
      label: 'Blocker',
      value: workspaceStatus?.blocker_count != null ? String(workspaceStatus.blocker_count) : '-',
      detail: workspaceStatus?.open_blockers || 'Keine offenen Blocker',
      tone: stateTone((workspaceStatus?.blocker_count || 0) > 0 ? 'danger' : 'success'),
    },
  ];
}

export function buildWhyNowItems(
  reasons: string[],
  drivers?: Array<{ label: string; strength_pct: number }>,
): string[] {
  const driverLines = (drivers || []).slice(0, 2).map((driver) => `${driver.label} trägt aktuell ${formatPercent(driver.strength_pct, 0)} zum Signal bei.`);
  const combined = [...reasons.slice(0, 3), ...driverLines].filter(Boolean);
  return combined.length > 0 ? combined : ['Noch keine klare Kurzbegründung vorhanden.'];
}

export function buildRiskItems(
  blockers?: string[],
  risks?: string[],
  knownLimits?: string[],
): string[] {
  const combined = [...(blockers || []), ...(risks || []), ...(knownLimits || [])].filter(Boolean);
  return combined.slice(0, 4).length > 0 ? combined.slice(0, 4) : ['Aktuell sind keine zusätzlichen Risiken dokumentiert.'];
}

export function buildActivationQueueModel(
  items: Array<{
    region_name?: string | null;
    priority?: string | null;
    signal_score?: number | null;
    impact_probability?: number | null;
    reason?: string | null;
  }>,
): { headline: string; copy: string } {
  if (items.length === 0) {
    return {
      headline: 'Die nächste Reihenfolge ist noch offen.',
      copy: 'Sobald die Aktivierung klarer wird, siehst du hier sofort, welche Region als Nächstes dran ist.',
    };
  }

  const lead = items[0];
  const leadRegion = lead.region_name || 'Die Fokusregion';
  const leadPriority = lead.priority || 'Beobachten';
  const leadSignal = formatSignalScore(primarySignalScore(lead));

  return {
    headline: `${leadRegion} ist als Nächstes dran.`,
    copy: `${leadPriority} ist jetzt der sinnvollste Schritt.${leadSignal !== '-' ? ` ${leadSignal} Signalwert.` : ' Signal wird noch eingeordnet.'}${lead.reason ? ` ${lead.reason}` : ''}`,
  };
}

export function buildCampaignReadinessModel({
  cards,
  publishableCards,
  activeCards,
}: {
  cards: RecommendationCard[];
  publishableCards?: number | null;
  activeCards?: number | null;
}): { headline: string; copy: string } {
  const publishable = publishableCards ?? 0;
  const active = activeCards ?? 0;

  if (cards.length === 0) {
    return {
      headline: 'Noch nichts ist freigabereif.',
      copy: active > 0
        ? `${active} Vorschläge sind sichtbar, aber noch nicht bereit für Review. Sobald sich das ändert, steht hier der nächste konkrete Move.`
        : 'Sobald aus Analyse konkrete Vorschläge werden, siehst du hier sofort, was direkt ins Review gehen kann.',
    };
  }

  const lead = cards[0];
  const leadTitle = lead.display_title || lead.campaign_name || lead.region || 'Der nächste Vorschlag';

  return {
    headline: publishable > 0
      ? `${publishable} Vorschlag${publishable === 1 ? '' : 'e'} kann${publishable === 1 ? '' : 'en'} jetzt ins Review.`
      : `${leadTitle} ist der nächste stärkste Move.`,
    copy: `${active} aktive Karte${active === 1 ? '' : 'n'} im Blick. ${lead.reason || lead.decision_brief?.summary_sentence || 'Die Kurzbegründung ist sichtbar und kann direkt geprüft werden.'}`,
  };
}

export function buildWhyNowModel({
  regionName,
  virus,
  items,
}: {
  regionName: string;
  virus: string;
  items: string[];
}): {
  headline: string;
  copy: string;
  items: string[];
} {
  const safeRegion = regionName || 'Die Fokusregion';
  const primaryItem = items[0] || 'Noch keine klare Kurzbegründung vorhanden.';
  const detailItems = items.slice(1);

  return {
    headline: `${safeRegion} bleibt für ${virus} im Fokus.`,
    copy: primaryItem,
    items: detailItems.length > 0 ? detailItems : ['Weitere Treiber werden nachgeladen, sobald zusätzliche Evidenzpunkte vorliegen.'],
  };
}

export function buildRiskModel({
  regionName,
  items,
}: {
  regionName: string;
  items: string[];
}): {
  headline: string;
  copy: string;
  items: string[];
} {
  const safeRegion = regionName || 'Die Fokusregion';
  const realItems = items.filter((item) => item && item !== 'Aktuell sind keine zusätzlichen Risiken dokumentiert.');

  if (realItems.length === 0) {
    return {
      headline: 'Aktuell keine harten Stopps sichtbar.',
      copy: `${safeRegion} hat derzeit keine zusätzlichen Risikohinweise. Beobachten bleibt sinnvoll, aber es gibt keinen klaren Showstopper.`,
      items: ['Die Freigabe bleibt trotzdem an die allgemeine Datenlage und Evidenz gekoppelt.'],
    };
  }

  const primaryItem = realItems[0];
  const detailItems = realItems.slice(1);
  const headline = realItems.length === 1
    ? 'Ein Prüfpunkt bleibt vor der Freigabe offen.'
    : `${realItems.length} Punkte bremsen die Freigabe noch.`;

  return {
    headline,
    copy: primaryItem,
    items: detailItems.length > 0 ? detailItems : ['Dieser Punkt sollte vor einer aktiven Budgetverschiebung noch geprüft werden.'],
  };
}

export function resolveRegionStage(
  activationPriority?: string | null,
  decisionLabel?: string | null,
  probability?: number | null,
): string {
  const raw = String(activationPriority || decisionLabel || '').toLowerCase();
  if (raw.includes('aktiv') || raw.includes('activate')) return 'Aktivieren';
  if (raw.includes('vorbereit') || raw.includes('prepare') || raw.includes('halt')) return 'Vorbereiten';
  if (raw.includes('beobacht') || raw.includes('watch')) return 'Beobachten';

  if (probability == null || Number.isNaN(probability)) return 'Beobachten';
  const normalized = probability <= 1 ? probability : probability / 100;
  if (normalized >= 0.7) return 'Aktivieren';
  if (normalized >= 0.45) return 'Vorbereiten';
  return 'Beobachten';
}

export function regionStageTone(stage: string): 'activate' | 'prepare' | 'watch' {
  if (stage === 'Aktivieren') return 'activate';
  if (stage === 'Vorbereiten') return 'prepare';
  return 'watch';
}

export function buildRegionDetail({
  regionName,
  stage,
  trend,
  changePct,
  signalScore,
  reason,
}: {
  regionName: string;
  stage: string;
  trend?: string | null;
  changePct?: number | null;
  signalScore?: number | null;
  reason?: string | null;
}): {
  regionName: string;
  meta: string;
  copy: string;
} {
  const signalLabel = formatSignalScore(signalScore);
  const deltaLabel = changePct == null || Number.isNaN(changePct)
    ? 'Vorwochenvergleich offen'
    : `${changePct >= 0 ? '+' : ''}${changePct.toFixed(1)}% zur Vorwoche`;
  const trendLabel = trend ? `Trend ${trend}` : 'Trend noch offen';

  return {
    regionName,
    meta: `${stage} · ${signalLabel} Signalwert · ${deltaLabel}`,
    copy: reason || `${regionName} steht aktuell weit oben im Ranking. ${trendLabel} und der Signalwert sprechen für eine genauere Prüfung in dieser Woche.`,
  };
}

export function scoreTone(value?: number | null): 'success' | 'warning' | 'danger' | 'neutral' {
  if (value == null || Number.isNaN(value)) return 'neutral';
  const normalized = value <= 1 ? value : value / 100;
  if (normalized >= 0.7) return 'danger';
  if (normalized >= 0.4) return 'warning';
  return 'success';
}

export function stateTone(value?: string | boolean | null): 'success' | 'warning' | 'danger' | 'neutral' {
  const normalized = String(value || '').toLowerCase();
  if (value === true) return 'success';
  if (normalized.includes('krit') || normalized.includes('block') || normalized.includes('offen') || normalized.includes('fehl')) {
    return 'danger';
  }
  if (normalized.includes('watch') || normalized.includes('warn') || normalized.includes('vorsicht') || normalized.includes('aufbau')) {
    return 'warning';
  }
  if (normalized.includes('ok') || normalized.includes('ready') || normalized.includes('aktuell') || normalized.includes('fresh') || normalized.includes('go')) {
    return 'success';
  }
  return 'neutral';
}
