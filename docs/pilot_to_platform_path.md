# Pilot To Platform Path

Stand: 2026-04-12

## Zweck dieses Dokuments

Dieses Dokument ist eine interne Go-to-Market- und Rollout-Notiz.

Es ist **nicht** die maßgebliche Quelle für den aktuellen Produktionszustand.
Für den nachweisbaren Live-Stand siehe
[docs/live_release_evidence_2026-04-12.md](./live_release_evidence_2026-04-12.md).

## Aktueller Live-Stand

Am 12. April 2026 ist der laufende Stand:

- Live erreichbar: ja
- `health/live`: `200`
- `health/ready`: `200`
- moderner Kernpfad-Smoke: grün
- regionale Forecast-, Allocation- und Campaign-Endpoints: live `200`
- Public-Risk-API lehnt kaputte Eingaben sauber mit `422` ab

Das ist ein klarer Fortschritt gegenüber dem früheren Stand, bei dem Repo, Doku und Server nicht sauber übereinstimmten.

## Was daraus **nicht** folgt

Der grüne Live-Stand bedeutet noch nicht automatisch:

- vollständig generisches Multi-Tenant-Produkt
- kausal validiertes Outcome-System
- völlig bereinigtes internes Pilot-Vokabular im gesamten Repo
- endgültig käuferfertige Dokumentation ohne interne Altlasten

In einfachen Worten: Der operative Kern ist jetzt deutlich glaubwürdiger, aber die Käuferhygiene ist noch nicht vollständig fertig.

## Die vier Stufen

## Stufe 0: Live Demonstrable System

### Was diese Stufe ist

Das System ist live, überprüfbar und technisch als Produktkern erkennbar.

### Was diese Stufe noch nicht ist

- kein voll standardisierter Plattformvertrag
- keine unbegrenzte Scope-Freigabe
- keine Aussage, dass alle internen Altlasten bereinigt sind

### Aktueller Stand

- diese Stufe ist erreicht

## Stufe 1: Internal Shadow Or Guided Pilot

### Ziel

Ein enger Partner oder das interne Team arbeitet regelmäßig mit dem System, aber noch mit bewusst engem Scope und klarer Governance.

### Was geliefert wird

- Dashboard und Wochensteuerung
- regionale Forecast-/Decision-Views
- Allocation- und Recommendation-Outputs
- Truth-/Outcome-Readouts
- nachvollziehbare Release- und Smoke-Checks

### Eintrittskriterien

- Kernpfad bleibt grün
- Support-Scope ist schriftlich begrenzt
- bekannte fachliche Grenzen sind dokumentiert

## Stufe 2: Paid Operational Pilot

### Ziel

ViralFlux wird im Wochenrhythmus operativ genutzt und nicht nur als Demo oder Einmal-Readout.

### Zusätzliche Anforderungen

- klarer Go/No-Go-Prozess
- definierte Rollen und Freigaben
- dokumentierte Known Limitations
- wiederholbare Reporting- und Review-Schleife

## Stufe 3: Platform Contract

### Ziel

Aus dem Pilot wird ein dauerhaftes Decision- und Activation-Layer mit belastbarer Betriebsroutine.

### Was dafür zusätzlich nötig ist

- saubere Release-Provenienz
- weniger brand-/pilot-spezifische Altlasten im Daten- und Admin-Layer
- belastbare Käuferdoku statt verstreuter interner Fachdokumente
- klarer Sprachvertrag zwischen Signal, Forecast, Priorität und Recommendation

## Ehrliche Vertriebslogik

Heute lässt sich ViralFlux glaubwürdig als:

- live laufender,
- technisch überprüfbarer,
- aber noch nicht vollständig auspolierter

operativer Produktkern darstellen.

Nicht glaubwürdig wäre es, schon jetzt so zu verkaufen, als sei das System in jedem Layer vollständig ent-pilotisiert und generisch standardisiert.

## Nächster Schritt

Der richtige nächste Schritt ist nicht „größer behaupten“, sondern:

1. Repo- und Käuferdoku weiter bereinigen
2. verbliebene brand-spezifische Admin-/Backoffice-Reste entfernen
3. Release-Nachweise und Known Limitations kompakt und belastbar dokumentieren
