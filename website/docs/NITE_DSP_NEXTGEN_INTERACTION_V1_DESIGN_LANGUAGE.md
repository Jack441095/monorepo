# NITE DSP INTERACTION LANGUAGE V1 — DESIGN LANGUAGE / DESIGN SPEC

## Concept — THE NITE SIGNAL

The site behaves like a carefully engineered piece of audio equipment that
senses an incoming signal (the user) and responds with controlled energy.
The metaphor chain is always:

    USER INPUT → SIGNAL → PROCESSING → RESULT

Three brand energies, unchanged from the approved palette:

| Energy | Colour | Meaning | Where it appears |
| --- | --- | --- | --- |
| INPUT | Electric blue `#397BFF` / `#56A8FF` | interaction, scanning, indexing | cursor light fields, border bloom, scanner, nav indicator |
| PROCESSING | Violet `#7148E8` | transformation in progress | scan trails, workflow trace, intermediate bloom |
| TRANSIENT | Red `#F0445A` / `#FF5C69` | peak events, completed analysis | ~200 ms transient pulses, transient markers only |

## Motion hierarchy (depth system)

| Depth | Layer | Movement budget | Used on |
| --- | --- | --- | --- |
| 0 | Static content | none | headings, body copy, forms, legal, docs |
| 1 | Ambient environment | 10–42 px drift, heavy lag | hero / product-hero light fields |
| 2 | Visual depth | 1–4 px parallax, ≤ 1.6° tilt | product screenshot frames, flagship card |
| 3 | Interactive controls | ≤ 3 px magnetic content shift inside a stationary hit target | flagship CTAs only (2 per page max) |

Priority when effects would collide (choreography):
user action response → active content → product visual response → ambient
environment. Ambient motion always yields to direct interaction (light
fields stop tracking when the pointer works inside a control).

## Intensity

Development evaluated three levels: A MINIMAL, B PREMIUM BALANCED,
C EXPRESSIVE. **Shipped level: B — PREMIUM BALANCED.** No intensity
selector is exposed to users.

## The signature: NITE SIGNAL system

One coherent energy system, five manifestations (never all at once, never
site-wide loops):

1. **Light field** — diffuse blue/violet/red radial fields drift with
   delayed inertia behind hero surfaces (three lag rates: 0.06 / 0.035 /
   0.02 per frame ⇒ visible propagation, no trail).
2. **Border bloom** — pointer-proximity blue energy ring masked to the
   1px border of flagship frames; violet intermediate tone; fades in/out.
3. **Scanner** — the demo's analysis line gains a violet processing trail
   behind the blue head; single-pass per scan, never looping site-wide.
4. **Signal track** — homepage workflow connector fills blue→violet as the
   reader progresses; stage numbers activate at the reading line.
5. **Transient pulse** — one red ring impulse (~220 ms) when the demo
   resolves a classification or a sample is selected. Shape-based,
   never screen-filling, never repeated automatically.

## Component specifications

### LightField (`components/motion/LightField.tsx`)
- 3 absolutely-positioned radial-gradient blobs (no CSS blur filters).
- Shared pointer engine drives `translate3d` on refs; ranges 26/34/42 px x,
  16/22/26 px y; skips work when off-screen (±80 px) or tab hidden.
- Static authored fallback when JS absent, coarse pointer, or reduced motion.

### Magnetic (`components/motion/Magnetic.tsx`)
- Wraps **content inside** a semantic control; hit target never moves.
- Max 3 px horizontal, 2.1 px vertical; CSS-transition smoothed
  (100 ms linear engaged / 380 ms spring-like return).
- Pointer-events only — keyboard focus never displaces anything.

### TiltSurface (`components/motion/TiltSurface.tsx`)
- Perspective 1200px; ≤ 1.6° tilt; `is-engaged` tightens transition while
  hovered, 420 ms premium ease on release.
- Border bloom + interior sheen track pointer via CSS custom properties.
- Children marked `data-depth="n"` get px-parallax layers (frame bar 1.5,
  screenshot 3). Negative depth reserved for reflections (unused V1).

### Reveal (`components/motion/Reveal.tsx`)
- IntersectionObserver, threshold 0.12, rootMargin −48px; opacity + 14px
  rise, 640 ms, once; hidden state scoped under `html.js` so no-JS users
  always see content; delays ≤ 90 ms; reduced motion ⇒ instant visible.

### WorkflowFlow (`components/motion/WorkflowFlow.tsx`)
- Scroll-linked `--flow` (0.04→1) fills the signal track; rAF-throttled
  passive scroll listener; stage `.is-active` toggles at 58% viewport line.
- Reduced motion: full trace static; activation states still update
  (state clarity preserved, decoration dropped).

### SiteHeader nav indicator
- Absolutely-positioned 2px gradient bar morphs (position+width) between
  active-route links; 300ms spring-ish ease; labels never move; state also
  conveyed by `aria-current="page"`; re-measures on resize + fonts.ready.

### AudioAnalysisDemo premium pass
- Header gains restrained `SIMULATION` chip; footer disclosure preserved
  verbatim (claim safety).
- Pointer examination band: soft blue radial band follows cursor across
  the waveform display (CSS-eased, event-driven, no loops).
- Scan line gains violet trail; readouts scramble during the ~800ms scan
  (derived from existing progress ticks — no extra state updates).
- Transient pulse on selection + on classification resolve.

### Grain (`.grain::after` on body)
- 160px SVG fractal-noise tile, opacity 0.032, overlay blend, animated by
  composited `transform` steps(5) 1.4s; static under reduced motion.

### Status energy (`.status-chip` + `StatusDot`)
- Shape-first: 6px dot + text label; colour assists. Maturity labels are
  static; the PRIVATE BETA dot breathes only under pointer attention of
  its owning card.

### Spotlight groups (`.spotlight-group`)
- Hover/focus-within quiets sibling cards to opacity 0.82. CSS-only,
  hover AND keyboard equivalent, fine-pointer + no-preference gated.

## Easing / tokens added

    --motion-ease-premium: cubic-bezier(0.22, 1, 0.36, 1);
    --motion-ease-spring:  cubic-bezier(0.34, 1.28, 0.48, 1);
    --motion-magnetic-max: 4px;
    --motion-parallax-small: 2px;
    --motion-parallax-medium: 4px;

No bounce/elastic anywhere; overshoot limited to the nav indicator's
subtle spring.

## Route intensity map (shipped)

| Route | Intensity | Applied |
| --- | --- | --- |
| `/` | HIGH | light field, tilt frame, magnetic CTA, reveals, workflow signal track, spotlight capabilities, demo pass, grain |
| `/products/smart-sample-manager` | HIGH | light field, tilt screenshot, magnetic CTA, reveals, demo pass |
| `/products` | MEDIUM | flagship tilt card + bloom, status dots, card hover depth, reveal |
| `/pricing`, `/support` | LOW | standard buttons only |
| `/learn/*`, `/account`, `/auth/verify`, legal | MINIMAL | untouched |

## Claim safety

No product copy changed. Preserved verbatim: "Pricing TBC", private-beta
read-only wording, local-analysis claims, AU/VST3/Ableton qualification
wording, and the demo's "Illustrative workflow simulation…" disclosure.
The demo additionally labels itself `SIMULATION` in its header bar.
