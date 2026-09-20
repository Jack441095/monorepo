# NITE DSP Website V3 Design System

## Brand direction

NITE DSP is precise, nocturnal and audio-focused. The visual language is
technical without becoming clinical, and experimental without borrowing the
visual clichés of gaming, crypto or generic AI products.

## Visual system

- **Surfaces:** near-black background with subtle stepped panels and borders.
- **Palette:** near-black surfaces (`#09090b` to `#202027`), off-white type
  (`#f4f4f5`), muted grey support text, restrained mineral green
  (`#a7d7b8`) for active/operational signals, and clear product blue
  (`#8ab4f8`) for product availability or identity. Blue and green are
  accents, never page-filling glow effects.
- **Type:** Sansation Bold is reserved for the NITE DSP wordmark. Geist is
  used for interface and body copy; technical labels are compact and spaced.
- **Grid:** `--content-width` and `--grid-gutter` define the responsive page
  frame. Sections have a visible rule when a change of thought is useful.
- **Radii:** small controls, medium cards and larger product frames form a
  small intentional scale.

## Components

Primary buttons signal commercial or product intent. Secondary buttons support
comparison and navigation. Text links carry low-emphasis onward actions.
Product frames use a labelled top rail and genuine application screenshots.

## Plugin palette handoff

Future NITE DSP plugin interfaces should inherit the same palette and visual
hierarchy: near-black canvas, stepped charcoal panels, off-white primary type,
and low-contrast borders. Use green for live operational state such as active
selection, playback, success, or analysis-ready status. Use blue for product
identity, available/new product labels, and non-operational discovery context.
Amber remains reserved for experimental or cautionary actions; red remains
reserved for stop, destructive, or failed states. Do not use Sansation for
dense plugin controls or data tables; it is a wordmark face.

## Motion and accessibility

Hover states are short and restrained. All motion respects
`prefers-reduced-motion`. Keyboard focus is explicitly visible, navigation
uses landmarks and mobile controls retain a 40px target.

## Copy voice

Write for producers and engineers: concise, specific and technically literate.
Describe the sound-discovery workflow before mentioning ML. Avoid generic
claims, repetitive slogan structures and em-dash-heavy copy.

## Responsive imagery

The primary product image is visible in the hero at every size. Duplicate full
application screenshots are hidden on narrow screens rather than reduced until
their UI becomes illegible.
