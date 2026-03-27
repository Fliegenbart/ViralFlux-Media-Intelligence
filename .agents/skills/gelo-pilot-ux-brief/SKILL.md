---
name: gelo-pilot-ux-brief
description: Use for PEIX/GELO-facing frontend and media UX work in this repository when the task involves weekly planning, weekly briefings, overview screens, landing pages, regions, campaigns, recommendations, evidence, reporting, exports, pilot-demo framing, or decision-first copy and hierarchy. Keep the product GELO-specific and focused on what PEIX/GELO should do this week. Do not use for backend/model-only tasks or generic multi-tenant SaaS refactors.
---

# Purpose

Keep UX work aligned to the real product goal:

- This is a PEIX Healthcare pilot tool for presenting and operating with GELO.
- The UI should feel like a weekly media planning console, not a generic operator cockpit.
- The primary question every important screen should answer is:
  "What should PEIX/GELO do this week, where, and why?"

# Non-negotiables

- Keep GELO explicit in copy and framing for this phase.
- Do not genericize into multi-client or white-label UX unless the task explicitly asks for it.
- Preserve Bundesland-level framing.
- Do not imply city-level precision.
- Keep evidence and reliability visible, but secondary to action.
- Prefer decision-first language over model-first language.
- Avoid exposing raw ML terminology in the primary viewport unless the task explicitly asks for expert mode.

# Primary UX lens

For every affected screen, identify these five things before changing code:

1. Who is the user on this screen?
   - PEIX strategist
   - PEIX operator
   - GELO stakeholder
   - analyst/reviewer

2. What decision should the screen enable in under 10 seconds?

3. What are the top 1–3 actions on the screen?

4. What evidence must be visible to support trust?

5. What should be hidden behind secondary disclosure?

# Preferred framing by area

## Now / landing / overview

Lead with:

- weekly situation
- top 3 recommended moves
- regions to focus on
- reliability/evidence badges
- next action

## Regions

Lead with:

- increase / hold / reduce
- why this region
- readiness / timing
- bridge to recommendation or campaign

## Campaigns

Lead with:

- approval status
- budget direction
- channel mix
- expected impact
- blockers and handoff

## Evidence

Lead with:

- data completeness
- quality / reliability
- blockers
- readiness to act

## Reporting

Lead with:

- what changed this week
- what should be reviewed
- what can be exported or presented

# Language rules

Prefer:

- Weekly briefing
- Focus this week
- Recommended move
- Ready for review
- Evidence available
- Reliability
- Data gap
- Needs approval
- Export weekly readout

Avoid in primary UI:

- operator
- raw backtest jargon
- object-like field labels
- technical implementation language

# Implementation rules

- Reuse existing page structure and components where practical.
- Keep changes small and reviewable.
- Prefer re-ordering, relabeling, and composing existing data over inventing large new data flows.
- Do not invent fake precision if the backend does not support it.
- Directional recommendations are acceptable when exact budget values are not supported.
- Preserve existing routes unless the task explicitly asks to change navigation.

# Required output style when this skill is used

Before or alongside implementation, explicitly state:

- primary user
- screen decision
- primary CTA
- trust layer
- any constraint you preserved

At the end, always report:

1. files changed
2. exact pages/components changed
3. UX acceptance criteria with pass/fail
4. build/test commands run
5. residual UX risks
