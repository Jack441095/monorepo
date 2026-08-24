# NITE DSP WEBSITE MOTION V1 — DESIGN SPEC

Full design language: `docs/NITE_DSP_NEXTGEN_INTERACTION_V1_DESIGN_LANGUAGE.md`
(same programme). This spec summarises the shipped motion layer against the
V2.1 motion-pass requirements:

- **Preserved:** the approved V2.1 palette, layout, typography, product
  hierarchy, content, routes, and commercial claim-safety. Nothing was
  redesigned; copy is untouched.
- **Pointer gate:** every enhanced behaviour runs only under
  `(hover: hover) and (pointer: fine)` AND absent
  `prefers-reduced-motion: reduce` (via `useReactivePointer`).
- **Depth system shipped:**
  - DEPTH 0 static: headings/body/forms/legal — hero heading never moves.
  - DEPTH 1 ambient: hero/product-hero light fields, 26–42 px lagged drift.
  - DEPTH 2 visual: product frames/screenshots, 1.5–3 px layers, ≤ 1.6°.
  - DEPTH 3 controls: magnetic content in 3 flagship CTAs, ≤ 3 px,
    hit targets stationary, spring return, keyboard never displaces.
- **Hero motion:** background light field + frame micro-parallax +
  magnetic CTA; text static.
- **Magnetic buttons:** Explore SLO (home), See pricing (home CTA band),
  See pricing (SLO hero). Nothing else.
- **Product card depth:** flagship products card 1.2° tilt + bloom +
  sheen; research cards hover depth (1 px rise, no scale).
- **Border illumination:** pointer-masked blue ring, violet intermediate,
  red unused in bloom (reserved for transients).
- **Screenshot/device parallax:** frame bar 1.5 px, display 3 px, sheen
  independent; contents never distorted.
- **Audio demo motion:** scanner trail, pointer examination band, readout
  scramble, transient pulses; illustrative-demo disclosure preserved
  verbatim + `SIMULATION` header chip; no fabricated performance claims.
- **Navigation:** morphing active indicator only; labels stationary.
- **Cursor:** native cursor kept; no augmentation.
- **Forms/account/auth/pricing/support:** standard focus/border/button
  transitions only — no magnetic inputs, no cursor-reactive backgrounds.
- **Docs/legal:** static.
- **Motion tokens:** `--motion-ease-premium`, `--motion-ease-spring`,
  `--motion-magnetic-max`, `--motion-parallax-small/medium` added beside
  the existing `--motion-fast/standard/slow/easing`.
- **Easing:** premium ease-out family; single subtle spring (nav
  indicator); no cartoon bounce anywhere.
- **Entry animations:** one-shot reveals (opacity + 14 px), delays ≤ 90 ms,
  never blocking content, no replay on scroll.
- **Scroll motion:** passive rAF-throttled workflow trace only; no
  scroll-jacking, no smooth-scroll libraries.
- **Third-party libraries:** none added; **no WebGL**; no canvas.
- **Intensity:** A/B/C evaluated; **B — PREMIUM BALANCED** shipped; no
  user-facing intensity selector.
