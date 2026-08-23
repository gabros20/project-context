---
version: alpha
name: Ledger Relay
description: A precise, editorial-technical identity for the project-context static website.
omitted:
  - section: spacing
    reason: Layout uses a documented 8px rhythm without exporting named spacing tokens that could collide with framework sizing namespaces.
colors:
  primary: "#325BFF"
  primary-hover: "#2448D8"
  on-primary: "#FFFFFF"
  ink: "#151821"
  ink-muted: "#5E6577"
  surface: "#F7F9FC"
  surface-raised: "#FFFFFF"
  line: "#D9DEE8"
  signal: "#F05A35"
  signal-soft: "#FFF0EB"
  primary-soft: "#E9EEFF"
typography:
  display:
    fontFamily: "Arial Narrow, Avenir Next Condensed, sans-serif"
    fontSize: 112px
    fontWeight: 700
    lineHeight: 0.88
    letterSpacing: -0.03em
  heading:
    fontFamily: "Avenir Next, Segoe UI Variable, sans-serif"
    fontSize: 48px
    fontWeight: 650
    lineHeight: 1.02
    letterSpacing: -0.025em
  body:
    fontFamily: "Avenir Next, Segoe UI, sans-serif"
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: 0em
  utility:
    fontFamily: "SFMono-Regular, Consolas, Liberation Mono, monospace"
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: 0.08em
rounded:
  sm: 6px
  md: 12px
  lg: 20px
  full: 9999px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.utility}"
    rounded: "{rounded.sm}"
    padding: 16px
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
  button-secondary:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.utility}"
    rounded: "{rounded.sm}"
    padding: 16px
  navigation-shell:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.md}"
  visualizer-ledger:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
  visualizer-observation:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
  visualizer-handoff:
    backgroundColor: "{colors.signal-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
  visualizer-active:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
  divider:
    backgroundColor: "{colors.line}"
    textColor: "{colors.ink}"
  display-copy:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.display}"
  section-heading:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.heading}"
  body-copy:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.body}"
---

# Ledger Relay

## Overview

This is a design-is-the-product marketing surface for developers who move between coding-agent harnesses. It should feel like a carefully engineered field instrument: legible, dependable, and active without borrowing terminal cosplay. The visual reference is an append-only lab ledger crossed with a relay map—records arrive, durable understanding forms, and the next operator takes the baton.

The memorable signature is the **memory relay**: an explanatory visualization in which distinct agent nodes feed timestamped observations into one ledger, a reflection consolidates the source-backed history, and a bounded packet reaches a new agent. Everything outside that moment stays restrained.

## Colors

The canvas uses cool near-white rather than cream. Ink is a blue-black chosen for long-form contrast without turning the whole page into the common near-black SaaS default.

- **Primary cobalt (`#325BFF`)** identifies durable observations, links, focus, and the primary action.
- **Signal orange (`#F05A35`)** is not a second decorative accent. It appears only when the handoff frontier is active or a process state needs attention.
- **Cool surfaces (`#F7F9FC`, `#FFFFFF`)** separate editorial layers with value rather than shadows.
- **Ink and muted ink (`#151821`, `#5E6577`)** carry hierarchy and remain readable on both surface levels.

Never use gradient-filled text. Never introduce purple, acid green, or a decorative rainbow. Cobalt owns interaction; orange owns active relay state.

## Typography

The hero uses a condensed system display stack at a deliberately oversized scale. Its narrow letterforms evoke log columns and leave space for the asymmetric visualization. Tracking stops at `-0.03em`; glyphs must never touch.

Body and headings use the platform's humanist UI sans stack for reliable rendering without a font download. Utility labels, JSONL fragments, timestamps, and commands use the platform mono stack. Each section uses no more than three sizes, and prose stays within 45–70 characters per line.

## Layout

The desktop shell is a 12-column grid capped at 1440px with fluid 24–64px gutters. The hero is a 7:5 asymmetric split: thesis on the wider side, live ledger artifact on the narrower side. Approximately 80% of content honors the grid; the system visualization is the one deliberate breakout.

The page alternates density rather than mechanically alternating colors: open hero, dense system explanation, open record model, compact proof band, dense install surface, open final action. Spacing follows an 8px base rhythm with 4px reserved for optical adjustment.

On mobile, preserve hierarchy rather than merely stacking everything: the hero remains type-first, the memory relay becomes a vertical sequence, and command surfaces scroll internally instead of forcing page overflow.

## Elevation & Depth

Depth comes from three tonal planes: the cool page canvas, white content planes, and the dark ledger interior. Use hairline borders, inset rim light, and small contact shadows only where a floating control needs separation. Do not place a large blurred shadow and a border on the same container.

The relay visualization may use a faded coordinate grid because it encodes the system's paths. No faux-organic grain, aurora glow, glassmorphism, or decorative blur is allowed.

## Shapes

The mark and containers use **open brackets, straight ledger rules, and clipped corners**. Radius is controlled: 6px for controls and records, 12px for navigation, 20px only for the major visualization stage. Pills are limited to live-status indicators whose circular continuity has semantic meaning.

The logo combines an open ledger spine with two opposing context brackets. It must remain recognizable at 16px and work in one color.

## Components

- **Primary button:** cobalt fill, white utility label, 6px radius, visible 3px focus ring, and a 2px upward hover translation on fine pointers only.
- **Secondary button:** raised white surface, ink label, hairline border, no large shadow.
- **Command block:** dark ledger plane with copyable commands, explicit labels, and horizontal overflow on narrow screens.
- **Record strip:** thin, timestamped row using mono metadata and a narrative body. Observation is cobalt-tinted; the active handoff alone is signal-tinted.
- **Capability proof:** use a typographic matrix or inline harness rail, never three identical feature cards.
- **Navigation:** four or fewer destinations plus one GitHub action. The wordmark is a real SVG asset, not reconstructed text.

## Do's and Don'ts

- Do make the memory relay the only conspicuous animated moment.
- Do keep every claim specific to the shipped protocol and verified adapter capabilities.
- Do expose strong focus states, 44px targets, semantic headings, and reduced-motion behavior.
- Do use cobalt for action and orange only for active continuation state.
- Don't center every section or repeat uniform card grids.
- Don't use eyebrow chips, decorative section numbers, gradient text, emoji icons, or hand-drawn faux texture.
- Don't imply that every harness supports equivalent Stop behavior.
- Don't animate data the reader is actively trying to inspect.
- Don't add a second ornamental device when spacing, type, or alignment can solve the problem.

## Motion

Motion frequency is rare and its named purpose is **explanation**. The relay plays once when it first enters view and can be replayed with a real button.

- Use CSS animations for the predetermined packet path and WAAPI only to restart a grouped sequence.
- Animate only `transform` and `opacity`.
- Entrances use `cubic-bezier(0.23, 1, 0.32, 1)`; on-screen packet movement uses `cubic-bezier(0.77, 0, 0.175, 1)`; constant connector progress is linear.
- UI hover/press feedback stays between 100–180ms. The explanatory sequence may run for 7 seconds because it carries a four-stage mental model.
- Under `prefers-reduced-motion: reduce`, remove packet travel and position changes. Show every stage in its final state with a 200ms opacity transition at most.
- Hover motion is gated behind `(hover: hover) and (pointer: fine)`.
