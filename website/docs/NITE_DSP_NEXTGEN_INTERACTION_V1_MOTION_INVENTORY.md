# NITE DSP INTERACTION V1 / WEBSITE MOTION V1 — MOTION & COMPONENT INVENTORY

Every motion behaviour added by this programme. Registry JSON:
`docs/nextgen_interaction_components.json` (mirrored as
`docs/website_motion_v1_components.json`).

| # | Name | Files | Routes | Purpose | Trigger | Max movement | Reduced motion | Touch | Performance strategy |
|---|------|-------|--------|---------|---------|--------------|----------------|-------|----------------------|
| 1 | Pointer engine | `lib/motion.ts` | global | Single shared pointer signal + rAF loop | pointermove (passive) | n/a (writes only) | loop still runs only if a subscriber is active; all subscribers gated off | gated off via `(hover:hover) and (pointer:fine)` | 1 listener + 1 rAF total; parks on 0 subscribers & `document.hidden` |
| 2 | Capability hooks | `lib/motion.ts` | global | `useReducedMotion`, `useFinePointer`, `useReactivePointer` | matchMedia | — | — | — | change-event driven |
| 3 | Light field | `components/motion/LightField.tsx` | `/`, SLO hero | Ambient studio lighting (DEPTH 1) | shared pointer signal | 26–42 px blob drift | static authored composition | static | transform writes to refs; skips offscreen; no blur filters; no state |
| 4 | Magnetic content | `components/motion/Magnetic.tsx` | hero Explore SLO, homepage See pricing, SLO See pricing | Tactile CTA (DEPTH 3) | element pointer enter/move/leave | 3 px x / 2.1 px y | inert span | inert span | CSS-transition smoothing; zero JS loops; hit target stationary |
| 5 | Tilt surface | `components/motion/TiltSurface.tsx` | hero frame, SLO screenshot, products flagship card | Micro-3D hardware frame (DEPTH 2) | element pointer enter/move/leave | 1.6° tilt; layers 1.5/3 px; bloom+sheen | static frame | static frame | CSS vars + transitions; event-driven writes only |
| 6 | Border bloom + sheen | `globals.css` (`.tilt-surface__bloom/__sheen`) | same as 5 | Proximity edge illumination | pointer vars from 5 | opacity ≤ 0.55 ring | off (static) | off | masked gradient, opacity transition |
| 7 | Hover depth | `globals.css` (`.depth-hover`) | products research cards, homepage CTA panel | Rise without scale | CSS :hover | 1 px translateY | CSS-gated off | gated off | transform + shadow transition |
| 8 | Scroll reveal | `components/motion/Reveal.tsx` | homepage + SLO section headers/copy | Entrance without blocking | IntersectionObserver once | 14 px rise | instant visible | same as desktop | IO disconnects after reveal; `html.js` scoping keeps no-JS visible |
| 9 | Workflow signal track | `components/motion/WorkflowFlow.tsx` + CSS | homepage workflow | Signal-flow storytelling | scroll (passive, rAF) | height of trace ≤ list height | static full trace; activation states kept | hidden <640 px | 1 rAF-throttled listener pair; cleans up |
| 10 | Stage activation | same as 9 | homepage workflow | Reading-line state | same as 9 | colour only | kept (state, not decoration) | kept | class toggles |
| 11 | Nav indicator | `components/SiteHeader.tsx` + CSS | all (desktop nav) | Morphing active state | pathname change / resize / fonts.ready | position+width morph ≤ 300 ms | transition killed globally ⇒ instant jump (state clarity kept) | n/a (hidden <640 px) | rAF-deferred measure; `aria-current` carries meaning |
| 12 | Demo examination band | `components/AudioAnalysisDemo.tsx` | homepage + SLO demo | Waveform pointer response | element pointermove | opacity-only band, 160 ms trail | not rendered | not rendered | event-driven transform; parked on leave |
| 13 | Demo scan trail | same as 12 | demo | Processing visualisation | scan state | width of trail ≤ panel | global reduce kills transition; scan itself is functional content | functional | existing 40 ms scan ticks reused |
| 14 | Transient pulse | same as 12 + CSS `.transient-pulse` | demo chips + classification badge | Peak-event feedback | selection / scan complete | 1 ring, 220 ms, scale 1.06 | suppressed via matchMedia check | active (tap feedback) | timeout cleanup; never auto-repeats |
| 15 | Readout scramble | same as 12 | demo readouts | Instrumentation feel | scan in progress | text only | active (functional feedback) | active | derived from existing progress state |
| 16 | Status dot breathe | `components/motion/StatusDot.tsx` + CSS | products page | Attention response on live status | hover/focus of owning card | 5 px shadow ring | global reduce ⇒ off | gated off | box-shadow keyframes, attention-only |
| 17 | Spotlight group | `globals.css` | homepage capabilities, products grid | Attentional hierarchy | :hover / :focus-within | sibling opacity 0.82 | gated off | gated off | pure CSS opacity |
| 18 | Grain | `app/layout.tsx` + CSS `.grain::after` | global | Anti-flat texture | time (steps) | ±0.6 % translate | animation off, static grain remains | active | composited transform; 160 px tile; opacity 0.032 |
| 19 | Energy seams | `globals.css` `.energy-seam` | available; reserved | Section energy continuity | static | none | static | static | pure CSS gradient (currently reserved — see FINAL REPORT weaknesses) |
| 20 | CTA border glow | `globals.css` `.cta-panel::after` (pre-existing, retained) | homepage CTA band | Edge energy on hover | CSS :hover | opacity 0.15→0.35 | global reduce ⇒ instant | gated | masked gradient |

## Deliberately NOT implemented

- Custom cursor / cursor replacement — native cursor retained (spec §19).
- WebGL / canvas / particles — prohibited by spec; achieved with CSS/DOM.
- Third-party motion libraries (Framer Motion, GSAP, Lenis, Three.js) —
  zero dependencies added; native primitives sufficient.
- Magnetic nav links, magnetic form fields, scroll-jacking, looping
  site-wide scans, animated headings — all rejected as hierarchy violations.
