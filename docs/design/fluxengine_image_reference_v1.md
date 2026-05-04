# FluxEngine Cockpit Image Reference Prompts v1

Local art-direction pack for generating one horizontal design-reference image per cockpit section.

## Global Direction

**Visual thesis:** FluxEngine feels like a calibrated epidemiological instrument for marketing decisions: dark graphite lab surface, off-white evidence panels, vermilion signal accents, precise typography, no decorative dashboard noise.

**Content spine:** Evidence first, forecast second, budget last. The product earns trust by showing what it knows, what it does not know, and why money stays paused until gates are green.

**Interaction thesis:** Pinned narrative sections, subtle data-scrub reveal energy, and restrained parallax drift on maps and evidence artifacts.

**Palette**

- Primary: graphite black `#090A0F`
- Surface: lab paper `#F7F5EF`
- Secondary: muted zinc `#71717A`
- Accent: signal vermilion `#DC2626`
- Positive: clinical green `#4FA66A`
- Warning: amber `#C98A22`
- Hairline: black/white at 12-18 percent opacity

**Typography**

- Display: Space Grotesk / Neue Montreal style
- Utility: Inter / Swiss rational sans
- Mono: JetBrains Mono style for dates, gates, source labels

**Narrative / concept spine:** Tool / precision instrument.

**Second-read moment:** One narrow vertical editorial side-rail note appears once, in the Validierung section, to explain: "Heutige Welle != historische Modellguete."

**Signature components**

- Product UI Panel Stack
- Vertical Rhythm Lines
- Off-Grid Editorial Layout
- Layered Image Crop Frames

**Motion language to imply**

- pinned narrative section energy
- scrubbing text reveal energy

**Strict avoid**

- purple/blue AI glow
- floating blobs/orbs
- generic KPI-card spam
- fake celebratory budget approval
- tiny unreadable dashboards
- overpacked text
- "Diagnosemodus" wording

---

## Section 01: Loading / Passwort-Gate

**Job:** Quietly communicate that the system is loading a clean snapshot, not old numbers.

**Canvas:** Horizontal 16:9.

**Composition anchor:** Stacked center, ultra minimalist.

**Background mode:** Solid graphite surface with subtle technical field.

**Prompt**

```text
High-end website UI reference, horizontal 16:9. A minimalist loading and password-gate screen for "FluxEngine", a respiratory virus early-warning cockpit for a GELO pilot. Deep graphite black background with a very subtle technical dotted field, not sci-fi, not blue/purple. In the center: a small pulsating diamond mark "◆" as the only loading symbol, perfectly centered. Below for the password state: tiny eyebrow "peix · labpulse", large refined wordmark "FluxEngine", one short line "Frühwarnung für Atemwegsviren. Pilot mit GELO.", a single password input and a restrained button "Cockpit öffnen". Premium Swiss/grotesk typography, lots of negative space, vermilion accent on focus ring only, clean implementation-ready spacing. No extra dashboard cards, no decorative blobs, no fake stats.
```

---

## Section 02: Topbar + Statusleiste

**Job:** Make current operating state obvious in four badges.

**Canvas:** Horizontal 21:9.

**Composition anchor:** Top-left lead, support bottom-right.

**Background mode:** Solid surface with inline product UI.

**Prompt**

```text
Premium product cockpit UI reference, horizontal 21:9. Top navigation for "FLUXENGINE" on deep graphite header, week ticker KW16 KW17 KW18 KW19 KW20 with KW18 active, virus tabs Flu-A Flu-B RSV. Beneath it, an off-white status strip with exactly four large readable badges: "System: läuft", "Wissenschaft: Review", "Daten: 2 von 3 Quellen", "Budget-Gate: geschlossen — Kalibrierungsfenster". Each badge hints at a tooltip with small mono detail text, e.g. AMELAG date, SurvStat date, Feature-Lag, nächster Lauf. Use vertical rhythm lines between badges, generous spacing, no red CAN_CHANGE_BUDGET flag, no insider labels. Palette graphite, paper, zinc, vermilion accent. Make it feel precise and operational, not like a marketing landing page.
```

---

## Section 03: Hero / Evidence Summary

**Job:** Hook the customer with the current signal while staying honest.

**Canvas:** Horizontal 16:9.

**Composition anchor:** Bottom-left text over full-bleed map image.

**Background mode:** Image as entire visual plus tonal overlay.

**Prompt**

```text
Awwwards-level website section reference, horizontal 16:9, image-led hero for an evidence-first epidemic media cockpit. Full-bleed dark cinematic Germany map visualization as the main background, with regional signal coloring in muted greens and vermilion hotspots, not a generic map. Text anchored bottom-left in a calm safe area: eyebrow "Evidence Summary · GELO Pilot · KW 18", giant headline "Atemwegsdruck steigt in Hamburg.", second line smaller "Prüfen, ob ein Media-Shift sich lohnt." Short subline: "Frühsignal aus Abwasser und Notaufnahmen. Budget erst nach Sell-Out-Kalibrierung." Primary CTA "Signal-Evidenz öffnen", secondary inline link "Methodik". Three restrained KPI tiles only: "Signal-Status: 1 Region riser", "Daten-Reife: 0 / 12 Wochen Sell-Out", "Nächster Schritt: GELO-CSV anschließen". Premium dark lab instrument mood, clear hierarchy, no clutter, no happy budget approval.
```

---

## Section 04: Was wir sehen, was uns fehlt

**Job:** Show the three-source asymmetry: AMELAG and SurvStat live, GELO Sales missing.

**Canvas:** Horizontal 16:10.

**Composition anchor:** Centered statement with three asymmetric evidence blocks below.

**Background mode:** Subtle texture / paper / grid.

**Prompt**

```text
High-fidelity frontend section reference, horizontal 16:10. Off-white lab paper background with faint grid and hairline rules. Section title: "Was wir sehen — und was uns fehlt". Subtitle: "Drei Datenströme. Zwei laufen, einer wartet auf euch." Below, three large evidence blocks with asymmetric widths, not identical cards: AMELAG · Abwasser, SurvStat · klinische Fälle, GELO · Sell-Out. AMELAG block says "● Lebt. Hamburg, Berlin, Brandenburg sind Top-Riser." SurvStat block says "● Lebt. Bestätigt klinisch, mit Meldeverzug." GELO block says "○ Wartet auf euch. Drei Monate Sales-Daten machen das Modell budget-fähig. → CSV anschließen." Include small source-weight bars and dates, but keep readable. Refined grotesk display, mono labels, vermilion action accent only on CSV link.
```

---

## Section 05: AMELAG Standort-Frühwarnung

**Job:** Explain local baseline logic and show site alerts.

**Canvas:** Horizontal 16:9.

**Composition anchor:** Left-third caption + right-two-thirds visual.

**Background mode:** Editorial side-image with map as product visual.

**Prompt**

```text
Premium analytics cockpit section, horizontal 16:9. Left third contains concise title "AMELAG Standort-Frühwarnung" and subtitle "Jeder Standort wird gegen sich selbst gemessen — nicht gegen den Schnitt." Below: short primer "Rote Punkte = Anstieg gegen die eigene Baseline. Frühwarnung, kein Budget-Trigger." Right two-thirds: large detailed Germany map with site-level wastewater points, yellow and red dots, a side Top-Riser list, and a compact table strip "Standort · Virus · Aktuell · Baseline · Δ · Qualitäts-Flags". Use dark map panel on paper background with thin technical borders. Strong image-led composition, not a generic dashboard grid. Make baseline comparison visually obvious with small before/after mini-lines per site.
```

---

## Section 06: Forecast-Zeitreise

**Job:** Show forecast as time-aligned evidence, not magic prediction.

**Canvas:** Horizontal 21:9.

**Composition anchor:** Right-third caption + left-two-thirds visual.

**Background mode:** Solid surface with inline product visualization.

**Prompt**

```text
Horizontal 21:9 frontend reference for a forecast time-travel section. Left two-thirds: beautiful layered time-series visualization, three stacked strips labeled "Notaufnahmen (ED)", "Abwasser (AMELAG)", "Modell". A vertical today marker, median forecast line, quantile band, vintage ghost traces, and a small drift banner "Drift erkannt — Modell weicht von Beobachtung ab." Right third: title "Forecast-Zeitreise", subtitle "Drei Zeitreihen übereinander: Notaufnahmen, Abwasser, Modell." Toggle control "Einfach / Volle Sicht" with "Volle Sicht" active. Footer details: "Lead-Time: ED führt SurvStat um 9 Tage", "Beobachtet bis 2026-04-27", "Forecast ab 2026-04-28". Graphite and paper palette, vermilion only for today/drift, very codeable chart structure.
```

---

## Section 07: Validierung

**Job:** Resolve the Hamburg paradox and prove walk-forward discipline.

**Canvas:** Horizontal 16:10.

**Composition anchor:** Off-grid editorial offset.

**Background mode:** Quiet textured paper with product UI panels.

**Prompt**

```text
Premium research-validation section, horizontal 16:10. Off-white paper background, off-grid editorial layout. Title: "Validierung". Subtitle: "So gut war das Modell historisch. Walk-forward, gegen Persistenz-Baseline." One-line explainer: "Wir tun rückblickend so, als hätten wir die Zukunft nicht gekannt." Top-line metrics: "Top-3 richtig 95,5 %", "PR-AUC gesamt .800", "Median Lead-Time 1 d". Include a ranking list by Bundesland and a weekly hit barcode. Add exactly one narrow vertical side-rail note as the second-read moment: "Heutige Welle ≠ historische Modellgüte. Hamburg kann heute oben stehen und historisch schwach validiert sein." Use mono labels, precise hairlines, no celebratory styling. Make it feel like a serious lab review that a marketing lead can still read.
```

---

## Section 08: Media-Budget-Gates

**Job:** Make discipline the product: no money moves until four gates are green.

**Canvas:** Horizontal 16:9.

**Composition anchor:** Centered statement with bottom-right CTA cluster.

**Background mode:** Solid paper surface with product UI panel stack.

**Prompt**

```text
High-end decision cockpit section, horizontal 16:9. Title "Media-Budget-Entscheidung". Subtitle "Signal vorhanden. Daten noch nicht reif für einen Euro-Shift." Big primer text, readable and human: "Eine Budget-Empfehlung muss vier Gates passieren. In den meisten Wochen sind nicht alle vier grün — und dann empfehlen wir nichts." Center: four gate rows with status dots and thresholds: green Signal-Konfidenz 0.78 / Schwelle 0.70, green Lead-Time 9 d / Schwelle 5 d, red Sales-Validierung — / Schwelle 12 Wochen Daten, yellow Coverage 11/16 / Schwelle 14/16. Right side: Media status block "Modus: Kalibrierungsfenster", "budget_can_change=false", "Shadow-Lauf läuft mit. Echtgeld pausiert." Bottom-right small simulation input "angenommenes Wochenbudget" and clearly labeled "Simulation". No approved budget vibe, no green money graphics.
```

---

## Section 09: Wirkung & Feedback-Loop

**Job:** Show outcome accountability and honest empty states.

**Canvas:** Horizontal 16:10.

**Composition anchor:** Top-left lead, support bottom-right.

**Background mode:** Flat color block plus small evidence crop accents.

**Prompt**

```text
Horizontal 16:10 product UI reference for an impact feedback section. Deep graphite background with paper panels. Title top-left: "Wirkung & Feedback-Loop". Subtitle: "Was haben unsere Empfehlungen bewirkt? Honest-by-default. Wo nichts, da Strich." Central timeline: "Woche 0 (heute) · +1 · +4" with sparse empty-state markers. Three honest KPIs: "Empfehlungen ausgegeben —", "Real umgesetzt —", "Mit Outcome verknüpft —". Bottom: log table "KW · Empfehlung · Umsetzung · Outcome · Notiz", mostly dashes, one highlighted pending row. Include tiny receipt-like image crop of an imported CSV as a tactile proof object. Calm, restrained, very readable. The absence of data should look intentional, not broken.
```

---

## Section 10: Nächste Schritte / Data Office CTA

**Job:** Make the first GELO CSV the unmistakable next action.

**Canvas:** Horizontal 16:9.

**Composition anchor:** Massive image-first hero with restrained text.

**Background mode:** Full-bleed image background with tonal overlay.

**Prompt**

```text
Final CTA section reference, horizontal 16:9. Full-bleed editorial image: close macro crop of a clean CSV sheet / data rows reflected on a matte black lab surface, tonally matched to graphite and paper palette. Text anchored centered-low: eyebrow "Nächste Schritte", giant headline "Erste GELO-CSV hochladen". Subline "Drei Monate Verkaufsdaten machen das Modell empfehlungsfähig." Primary CTA as classic vermilion pill "Data Office öffnen", secondary underlined link "M2M-API später anbinden". Below or side: three smaller subdued next-step cards: "Forecast mit Sales-Anchor neu rechnen", "Budget-Effizienz auswerten", "Data Office öffnen". The first card/action must be visually dominant, about 1.5x stronger than the others. Premium, spacious, decisive closing section.
```

---

## Optional Generation Order

1. Generate Section 03 first to lock the brand world.
2. Generate Sections 02 and 08 next because they define cockpit semantics.
3. Generate Sections 04, 05, 06, 07 for evidence flow.
4. Generate Sections 01, 09, 10 last for system states and conversion close.

## Implementation Notes

- These are reference images, not final UI screenshots.
- The cockpit should remain a product surface, not a landing page.
- If generated images invent text, use them for composition only and keep production copy from the app.
- If any image shows `Budget-Gate offen` while Sell-Out is `0 / 12`, reject and regenerate.
- If AMELAG and SurvStat look budget-effective directly, reject and regenerate.
- If a section feels like generic SaaS cards, reject and regenerate.
