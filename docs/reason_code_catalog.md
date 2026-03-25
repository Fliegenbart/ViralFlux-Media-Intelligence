# Reason Code Catalog

Stand: 2026-03-24

Basis:
- [backend/app/services/ml/regional_decision_engine.py](/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py)
- [backend/app/services/ml/regional_media_allocation_engine.py](/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_engine.py)
- [backend/app/services/media/campaign_recommendation_service.py](/Users/davidwegener/Desktop/viralflux/backend/app/services/media/campaign_recommendation_service.py)
- [backend/app/services/media/pilot_readout_service.py](/Users/davidwegener/Desktop/viralflux/backend/app/services/media/pilot_readout_service.py)
- [frontend/src/lib/plainLanguage.ts](/Users/davidwegener/Desktop/viralflux/frontend/src/lib/plainLanguage.ts)

## Ziel

Diese Datei erklaert in einfachen Worten, welche festen Reason-Codes es gibt und was sie bedeuten.

Der Grundgedanke:

- Das Backend liefert nicht nur freie Saetze.
- Es liefert zusaetzlich stabile Codes mit Parametern.
- Das Frontend uebersetzt diese Codes in lesbare Saetze.

So bleibt die Bedeutung stabil, auch wenn sich ein Rohtext spaeter einmal aendert.

## Standardformat

Ein Reason-Objekt sieht so aus:

```json
{
  "code": "event_probability_activate_threshold",
  "message": "Event probability 0.81 clears the Activate threshold 0.70.",
  "params": {
    "event_probability": 0.81,
    "threshold": 0.70
  }
}
```

Regeln:

- `code` ist die stabile fachliche Bedeutung.
- `message` ist ein lesbarer Rohsatz aus dem Backend.
- `params` enthaelt die Zahlen oder Zusatzwerte fuer die spaetere Uebersetzung.

## Decision-Layer

Diese Codes kommen aus der regionalen Decision-Logik.

### Schwellen und Stufen

- `event_probability_activate_threshold`
  Bedeutet: Die Forecast-Wahrscheinlichkeit liegt ueber der Schwelle fuer Aktivierung.
- `event_probability_prepare_threshold`
  Bedeutet: Die Forecast-Wahrscheinlichkeit reicht fuer Vorbereitung, aber noch nicht fuer volle Aktivierung.
- `event_probability_below_prepare_threshold`
  Bedeutet: Die Forecast-Wahrscheinlichkeit reicht noch nicht fuer Vorbereitung.

### Forecast-Sicherheit

- `forecast_confidence_strong`
  Bedeutet: Das Signal ist fuer die aktuelle Entscheidung stabil genug.
- `forecast_confidence_usable`
  Bedeutet: Das Signal ist brauchbar, aber nicht maximal stark.
- `forecast_confidence_low`
  Bedeutet: Die Entscheidung bleibt noch unsicher.

### Datenqualitaet und Quellenlage

- `primary_sources_fresh`
  Bedeutet: Die wichtigsten Quellen sind aktuell.
- `primary_sources_stale`
  Bedeutet: Die wichtigsten Quellen sind eher veraltet.
- `revision_risk_high`
  Bedeutet: Nachtraegliche Aenderungen an den Daten sind wahrscheinlich.
- `revision_risk_material`
  Bedeutet: Revisionsrisiko ist sichtbar, aber nicht maximal.
- `trend_acceleration_supportive`
  Bedeutet: Die aktuelle Dynamik stuetzt das Signal.
- `trend_acceleration_not_convincing`
  Bedeutet: Die Dynamik ist noch nicht stark genug.
- `cross_source_agreement_low_evidence`
  Bedeutet: Es gibt zu wenige Quellen fuer einen belastbaren Richtungsabgleich.
- `cross_source_agreement_upward`
  Bedeutet: Mehrere Quellen zeigen in dieselbe Aufwaertsrichtung.
- `cross_source_agreement_not_upward`
  Bedeutet: Die Quellen bestaetigen keinen klaren Aufwaertstrend.
- `quality_gate_not_passed`
  Bedeutet: Die Forecast-Qualitaetspruefung ist noch nicht bestanden.

### Policy und Zusammenfassungen

- `final_stage_policy_overlay`
  Bedeutet: Die Endstufe ist wegen Freigaberegeln konservativer als das Rohsignal.
- `policy_override_watch_only`
  Bedeutet: Eine Regel haelt die Region bewusst im Beobachten-Modus.
- `policy_override_quality_gate`
  Bedeutet: Die Qualitaetspruefung blockiert eine hoehere Freigabe.
- `policy_override`
  Bedeutet: Eine andere Freigaberegel veraendert die Endstufe.
- `decision_summary`
  Kompakte Zusammenfassung der Decision-Lage fuer eine Region.
- `uncertainty_summary`
  Kompakte Zusammenfassung der Restunsicherheit fuer eine Region.

## Allocation-Layer

Diese Codes kommen aus der Budget- und Allokationslogik.

### Grundlogik

- `decision_stage_base`
  Bedeutet: Die Decision-Stufe setzt die Basis fuer die Allokation.
- `ranking_priority_and_probability`
  Bedeutet: Prioritaet und Forecast-Wahrscheinlichkeit bestimmen die Reihenfolge.

### Budget-Treiber

- `budget_driver_activate_multiplier`
  Aktivieren-Regionen erhalten den staerksten Zuschlag.
- `budget_driver_prepare_weighting`
  Vorbereiten-Regionen bleiben allokierbar, aber unter Aktivieren.
- `budget_driver_watch_observe_only`
  Beobachten-Regionen erhalten meist kein zusaetzliches Budget.
- `budget_driver_confidence_low_penalty`
  Hoehere Signalsicherheit fuehrt nur zu kleinem Abschlag.
- `budget_driver_confidence_moderate_penalty`
  Mittlere Signalsicherheit fuehrt zu moderatem Abschlag.
- `budget_driver_confidence_high_penalty`
  Niedrige Signalsicherheit drueckt die Allokation deutlich.
- `budget_driver_population_weight`
  Reichweite oder Bevoelkerung stuetzt die Allokation.
- `budget_driver_region_weight_boost`
  Eine hinterlegte Regionsgewichtung erhoeht den Score.
- `budget_driver_region_weight_reduce`
  Eine hinterlegte Regionsgewichtung senkt den Score.
- `budget_driver_source_freshness_penalty`
  Schlechte Datenfrische fuehrt zu Zusatzabschlag.
- `budget_driver_revision_risk_penalty`
  Hohes Revisionsrisiko fuehrt zu Zusatzabschlag.
- `budget_driver_suggested_share`
  Nennt den vorgeschlagenen Budgetanteil.

### Unsicherheit und Blocker

- `upstream_uncertainty`
  Uebernimmt Unsicherheit aus dem Decision-Layer.
- `uncertainty_revision_risk_material`
  Revisionsrisiko bleibt in der Allokation sichtbar.
- `uncertainty_source_freshness_soft`
  Datenfrische bleibt in der Allokation sichtbar.
- `spend_blocker`
  Globaler Spend-Blocker verhindert Freigabe.
- `budget_ineligible_region`
  Region ist unter den aktuellen Regeln nicht budgetfaehig.

## Campaign-Layer

Diese Codes kommen aus dem Kampagnenvorschlag.

### Warum dieser Vorschlag

- `campaign_stage_budget_share`
  Verbindet Region, Stufe und Budgetanteil.
- `campaign_wave_plan_support`
  Begruendet, warum die Region im Wochenplan bleibt.

### Produkt- und Keyword-Fit

- `campaign_product_cluster_fit`
  Begruendet den Produktcluster.
- `campaign_region_product_fit_boost`
  Region und Produkt passen besonders gut zusammen.
- `campaign_keyword_cluster_fit`
  Begruendet den Keywordcluster.

### Budget und Evidenz

- `campaign_budget_amount`
  Nennt das absolute Kampagnenbudget.
- `campaign_budget_share`
  Nennt den Budgetanteil.
- `campaign_evidence_class`
  Zeigt den Evidenzstatus des Vorschlags.
- `campaign_signal_outcome_agreement`
  Zeigt, wie gut Forecast-Signal und Outcome-Lage zusammenpassen.

### Guardrails

- `campaign_guardrail_ready`
  Vorschlag ist im aktuellen Rahmen freigabefaehig.
- `campaign_guardrail_bundle_neighbor`
  Budget ist zu klein und sollte gebuendelt werden.
- `campaign_guardrail_low_confidence_review`
  Vorschlag braucht wegen zu geringer Sicherheit noch Pruefung.
- `campaign_guardrail_blocked`
  Ein operativer oder kommerzieller Blocker haelt den Vorschlag auf.
- `campaign_guardrail_discussion_only`
  Vorschlag bleibt vorerst nur Diskussionsmaterial.

## Pilot-Readout

Der Pilot-Readout erzeugt keine eigenen fachlichen Codes.
Er sammelt die vorhandenen Codes aus den drei Layern und reicht sie weiter.

Wichtige Felder:

- `reason_trace_details`
  Sammelliste aus Decision, Allocation und Campaign-Layer.
- `uncertainty_summary_detail`
  Kompakte Restunsicherheit fuer Region oder Executive Summary.

## Frontend-Regel

Die UI soll immer so arbeiten:

1. Erst strukturierte Reason-Codes lesen.
2. Dann mit `plainLanguage.ts` in klare Sprache uebersetzen.
3. Nur wenn keine strukturierten Details vorliegen, auf Freitext zurueckfallen.

## Pflege-Regel

Wenn ein neuer Reason-Code eingefuehrt wird, muessen immer drei Dinge mitgezogen werden:

1. Backend-Code mit `code`, `message` und `params`
2. Frontend-Uebersetzung in [plainLanguage.ts](/Users/davidwegener/Desktop/viralflux/frontend/src/lib/plainLanguage.ts)
3. Ein Test im betroffenen Layer
