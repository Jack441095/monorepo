# SLO UX/UI V3 Design System

## Product direction

SLO is the NITE DSP sample-library workspace: dark, precise, compact and
audio-first. The interface prioritises finding, auditioning and comparing a
sound over exposing engineering detail.

## Tokens

`Source/DesignTokens.h` is the visual source of truth. New UI must use its
semantic surfaces, text, border, state, spacing, radius and typography tokens
rather than locally defined RGB values.

- Surfaces progress from `background` to `surfaceRaised2`; hover and active
  states are named separately.
- `accentInteractive` is the operational selection/playback accent. Website
  V3's mineral-green signal is retained here for active, playing and
  analysis-ready state.
- `productBlue` is the product/discovery accent. It may support SLO identity,
  non-operational discovery context and map explanation, but never replaces
  operational state or error colour.
- Amber communicates experimental or attention-required actions; red is only
  destructive/stop state.
- `foreground`, `muted`, `mutedDim` and `disabled` express text hierarchy.

## Layout and type

The compact header carries product identity, workspace mode and live context.
Search and filters form a dedicated second row. The workspace is primary;
the scrollable right inspector is selected-sample context rather than global
navigation. Minimum editor size is 700 x 520. Below 900px wide, nonessential
live status and category chips step back before they can crowd primary actions.

Use title, heading, body and metadata sizes from `DesignTokens.h`. Table
sample names are strong; secondary metadata is deliberately quieter.

## Controls and accessibility

Controls have clear primary, neutral, transport and warning semantics. Focus
uses `focusRing`; selected table rows also have a left-edge indicator, so the
state is not colour-only. ⌘F focuses search, Space auditions a selection,
F toggles a favourite, S opens Similar, and Escape closes overlays.

## Motion and performance

Motion is restricted to existing lightweight JUCE state updates. No visual
work enters `processBlock`; search remains debounced and browser virtualisation
is retained. No continuous decorative animation is part of V3.

## Website handoff

The plugin and website share the monochrome dark surface scale, restrained
green operational accent, blue product/discovery accent, warm amber warning
treatment, compact spacing and direct control language. This document changes
no website code.
