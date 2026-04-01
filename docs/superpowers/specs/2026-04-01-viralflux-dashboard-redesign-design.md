# ViralFlux Dashboard Redesign Design

Date: 2026-04-01
Status: Approved design direction
Scope: Frontend UX and visual redesign on existing routes and data flows
Recommended path: Option 2, targeted product polish

## 1. Goal

ViralFlux should feel like a bright, calm operations dashboard with briefing character for PEIX and GELO weekly steering.

The product should no longer feel like a neon control room at night. It should feel like a modern working tool that helps PEIX answer one question quickly:

What should PEIX and GELO do this week, where, and why?

## 2. Product Framing

Primary user:
- PEIX strategist or operator

Primary decision in under 10 seconds:
- What is the most important move this week?

Primary CTA:
- Open the focus case, review the recommendation, or prepare approval

Trust layer:
- Evidence, data quality, and approval readiness must stay visible, but below the main decision

Constraints to preserve:
- Keep existing routes
- Keep GELO explicit in the copy
- Keep Bundesland-level framing
- Do not imply city-level precision
- Reuse existing page structure and components where practical
- Preserve current API hookups unless implementation explicitly requires otherwise

## 3. Chosen Direction

The chosen visual direction is:

- modern operations dashboard
- calm and professional, not alarm-driven
- bright by default
- briefing-like, but still operational

This means:

- clear decisions first
- restrained use of status color
- light, readable surfaces
- low visual noise
- no neon-heavy sci-fi atmosphere

## 4. What Problem The Redesign Solves

The current main branch mixes multiple incompatible visual ideas:

- warm editorial premium styling
- dark observatory / glass / neon styling
- a theme system that still behaves as if light mode were the main baseline

As a result, the product feels visually inconsistent and more decorative than trustworthy.

The redesign should solve these issues:

- too much visual effect competing with actual content
- unclear hierarchy between decision, evidence, and detail
- navigation and shell styling pulling too much attention
- status colors reading as atmosphere instead of signal
- UI controls that feel more like a demo than a stable working product

## 5. Core UX Principle

Every important screen should follow this order:

1. what is happening
2. what matters most this week
3. what should I do next
4. why should I trust this
5. what details can I inspect if needed

This order should drive layout, copy, panel order, and emphasis.

## 6. Structural Design

### Global shell

The global shell should become lighter and quieter:

- slimmer left navigation
- calmer header with fewer competing actions
- stronger emphasis on current section and primary page action
- less decorative chrome

The shell should orient the user, not dominate the experience.

### Weekly plan

The weekly plan should become the strongest decision-first screen in the product:

- top briefing block with the main weekly recommendation
- clear next step directly below
- supporting evidence and alternatives below that
- charts and deeper detail pushed lower or behind disclosure

### Regions

The regions screen should answer:

- where should we look harder this week
- where should we hold back
- why

The page should feel comparative and operational, not exploratory for its own sake.

### Campaigns

The campaigns screen should answer:

- which case is ready
- which case needs review
- which case is blocked

Approval and readiness should be easy to scan.

### Evidence

The evidence screen should answer:

- is the recommendation currently reliable enough to act on
- what is missing
- what needs review

Evidence should support action, not bury it.

## 7. Visual Design Rules

### Color

The product should be bright by default:

- soft neutral background, slightly warm rather than cold blue-gray
- dark readable text
- one restrained brand accent, preferably teal or muted blue-green
- status colors used as signal, not as ambient lighting

Avoid:

- neon indigo glow as a core identity
- glassmorphism as a default surface treatment
- heavy gradients or noisy atmospheric backgrounds

### Typography

Typography should be clear and workmanlike:

- modern readable sans-serif as the primary font
- any secondary display font, if used at all, should be very limited
- headings should be strong and calm, not theatrical

The typography should say:

- reliable
- current
- operational

Not:

- cinematic
- futuristic
- luxury editorial

### Surfaces

Panels and cards should look like work modules:

- light surfaces
- subtle depth
- clear grouping
- enough contrast to scan quickly

Cards should answer one question each, for example:

- what is the recommendation
- what is the readiness
- what evidence supports it
- what should happen next

### Navigation and controls

Navigation should be calm and precise:

- low-emphasis icons
- clear active state without glow
- obvious current location

Controls should prioritize one action:

- one primary CTA
- one secondary CTA
- everything else reduced

## 8. Copy Direction

Primary UI language should stay decision-first and GELO-specific for the pilot.

Prefer:

- Focus this week
- Recommended move
- Ready for review
- Evidence available
- Needs approval
- Data gap
- Export weekly readout

Avoid in the primary viewport:

- operator cockpit language
- raw ML terminology
- technical field names
- implementation wording

## 9. Implementation Strategy

Recommended option:
- Option 2, targeted product polish

This means:

- keep routes and main data flows
- redesign shell, hierarchy, and visual system
- improve the most important screens first
- avoid a total rebuild

Why this option:

- high design impact
- low to medium technical risk
- preserves functioning product structure
- avoids turning the redesign into a large refactor

## 10. Screen Priority

Recommended order:

1. Login
2. App shell including sidebar and header
3. Weekly plan
4. Regions
5. Evidence
6. Campaigns

## 11. Acceptance Criteria

The redesign is successful when:

- the product feels bright, calm, and professional
- the first screen answers the weekly decision quickly
- status colors guide attention without dominating the page
- navigation supports the task without becoming the visual focus
- evidence remains visible but secondary to action
- the product feels like a stable tool for weekly steering, not a design experiment

## 12. Out Of Scope

This redesign does not require:

- backend data model changes
- route changes
- new fake data
- city-level precision
- a multi-tenant or white-label UX refactor

## 13. Final Recommendation

Build ViralFlux as a bright, calm operations dashboard with briefing character.

Use a restrained visual system, clear page hierarchy, and stronger weekly decision framing.

The redesign should make the product feel more trustworthy, more useful, and more aligned with PEIX and GELO weekly steering without rewriting the application architecture.
