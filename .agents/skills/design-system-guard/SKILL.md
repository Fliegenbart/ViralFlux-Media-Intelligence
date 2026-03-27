---
name: design-system-guard
description: Use when editing frontend UI so changes stay visually coherent, high-signal, accessible, polished, and responsive. Use for layout, spacing, typography, visual hierarchy, card design, badges, chips, tables, buttons, interaction states, empty/loading/error states, and overall screen polish. Do not use for backend work or as a substitute for product framing on its own.
---

# Purpose

Protect the interface from becoming noisy, inconsistent, or visually cheap.

This skill is the guardrail for "world-class" feel:

- clear hierarchy
- restrained density
- consistent actions
- strong scanability
- accessible interaction states
- polished empty/loading/error behavior

# Visual principles

## 1. One dominant idea per viewport

The first viewport should usually communicate:

- one headline
- one core interpretation
- one primary action
- a small number of supporting signals

Avoid equal emphasis on too many cards.

## 2. Strong hierarchy beats more content

Prefer:

- fewer panels
- more meaningful grouping
- clearer spacing
- better labels

over adding more information.

## 3. Action before detail

The user should understand:

- what changed
- what to do
- whether to trust it

before seeing implementation detail.

## 4. Reliability should support, not dominate

Reliability/evidence must be visible, but should not visually overpower the recommended action.

# Component-level rules

## Cards

- each card answers one clear question
- avoid nested card clutter unless necessary
- use concise titles
- remove duplicate subtitles and repeated metadata

## Buttons and CTAs

- one clear primary action per area
- secondary actions visually subordinate
- destructive or risky actions should never look primary by accident

## Badges and chips

- every badge must mean something concrete
- avoid too many badge colors in one view
- keep label language human-readable

## Tables and lists

- optimize for scanning
- put the most decision-relevant columns first
- de-emphasize supporting metadata

## Drawers and modals

- use for focused review or approval
- make the headline outcome-oriented
- do not dump raw data structures into the first visible section

# State quality checklist

Every touched screen/component must be checked for:

- loading state
- empty state
- error state
- low-data / low-confidence state
- disabled / blocked action state
- responsive behavior

# Accessibility rules

When touching UI:

- preserve semantic headings where practical
- ensure buttons/links are distinguishable
- avoid color-only meaning when possible
- keep labels understandable out of context
- preserve or improve keyboard/focus usability where visible in code

# Implementation rules

- Reuse existing tokens, patterns, and components where possible.
- Avoid introducing a new visual language in one isolated screen.
- Prefer small, disciplined polish over flashy redesigns.
- Do not add decorative complexity that does not improve decisions or trust.
- If you find an inconsistency you do not fix, call it out explicitly in residual risks.

# Output requirements

When this skill is used, include:

1. hierarchy improvements made
2. interaction/state improvements made
3. consistency risks avoided
4. remaining visual debt
