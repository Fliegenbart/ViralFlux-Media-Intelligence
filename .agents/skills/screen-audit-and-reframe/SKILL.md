---
name: screen-audit-and-reframe
description: Use when a task asks to redesign, simplify, restructure, or improve a specific frontend screen, page, drawer, or workflow. This skill audits the current screen first, then reframes it around a clearer decision and action hierarchy. Do not use for backend-only tasks or broad design-system work without a concrete screen.
---

# Purpose

Turn vague UI requests into a disciplined screen-level workflow:

1. inspect the current screen
2. identify what it is trying to do
3. identify why it feels weak or cluttered
4. reframe it around one primary decision
5. implement the smallest high-value change set

# Audit workflow

For every target screen, complete this audit before making substantial changes.

## A. Screen purpose

Answer:

- What is this screen for today?
- What should it be for after the change?
- What single decision should a user be able to make here?

## B. Information hierarchy

List:

- what appears above the fold
- what steals attention
- what should be primary
- what should become secondary
- what can move behind disclosure

## C. CTA hierarchy

Identify:

- primary CTA
- secondary CTA
- noisy or competing CTAs
- missing next step

## D. State coverage

Check for:

- loading
- empty
- error
- stale data
- blocked/unavailable state
- low-confidence / low-evidence state

## E. Trust and explanation

Check:

- what makes this recommendation believable?
- is reliability/evidence visible enough?
- is it overexposed and crowding the action?

## F. Structural issues

Look for:

- repeated cards with overlapping meaning
- labels that read like database fields
- unexplained badges
- panels that answer no clear user question
- actions that require too much scrolling or interpretation

# Reframe rules

After the audit, rebuild the screen around this order:

1. what is happening
2. what matters most
3. what should I do next
4. why should I trust this
5. what details can I inspect if needed

# Implementation rules

- Prefer reordering and simplifying before adding new UI.
- Reduce simultaneous emphasis.
- Use progressive disclosure for technical detail.
- Keep each card or panel responsible for one user question.
- Preserve working API hookups unless a task explicitly asks for data-shape changes.
- Avoid fake demo data unless the task explicitly asks for placeholder content.

# Output requirements when this skill is used

Before coding, provide this exact structure:

1. Current screen purpose
2. Target screen purpose
3. Primary user question
4. Current hierarchy problems
5. Proposed hierarchy
6. Proposed CTA hierarchy
7. States to improve
8. Minimal change set

If the prompt asks for implementation, perform the audit first, then implement.

At the end, report:

- what changed structurally
- what moved up/down in hierarchy
- which states were improved
- what still remains weak
