# NITE DSP INTERACTION V1 / WEBSITE MOTION V1 — ACCESSIBILITY

Target: WCAG 2.2 AA. Motion is progressive enhancement only; no meaning is
carried by animation alone.

## Reduced motion (`prefers-reduced-motion: reduce`)

- Global kill-switch (pre-existing, retained): all animation/transition
  durations collapse to 0.01ms.
- Programme-specific handling on top:
  - light fields: blobs pinned (`transform: none !important`), pointer
    engine never subscribes;
  - tilt/parallax/magnetic: listeners never attach; transforms neutralised
    in CSS as defence-in-depth;
  - reveals: `html.js .reveal` forced visible, no transition;
  - workflow trace: rendered full/static; stage activation (a state change)
    still updates;
  - grain: static tile, no stepping animation;
  - demo transient pulses: suppressed in JS (`matchMedia` check);
  - scan animation: retained — it is functional feedback for the demo's
    explicit user action, and text state changes (ANALYSING → result) carry
    the meaning without it.
- Verified by automated test: reduced-motion context renders all content at
  opacity > 0.9 and the primary CTA still navigates.

## Keyboard

- Magnetic/tilt/light effects are pointer-event-only; focus never causes
  displacement.
- Nav active state is conveyed by `aria-current="page"` — the morphing
  indicator is `aria-hidden` decoration.
- Spotlight groups treat `:focus-within` identically to `:hover`.
- Skip link, focus-visible outline (2px brand-blue-bright, 2px offset) and
  tab order unchanged.
- Demo controls remain native `<button>`s; scan state is readable text
  (ANALYSING… / CALCULATING… / result).

## Focus

- `:focus-visible` styling preserved globally; no glow effect obscures the
  outline (bloom layers are `pointer-events:none` and render under focus
  outlines).
- No focus traps introduced; no new focusable elements.

## Hover-independence

- No functionality is hover-only: every hover effect is decorative.
  All actions (nav, demo, CTAs) work via tap/click/keyboard.
- No content exists only during pointer proximity.

## Contrast & flashing

- Text colours unchanged; light fields/bloom sit behind content and never
  under body text at meaningful opacity (verified in 1440/768/390 captures).
- Red usage remains sparse: transient markers, one ~220ms pulse per explicit
  user action — no flashing sequences (well under WCAG 2.3.1 thresholds).
- Status system never relies on colour alone: dot shape + uppercase text
  label + (where applicable) chip border.

## Touch

- All reactive behaviour gated behind `(hover: hover) and (pointer: fine)`.
- Touch devices receive static premium surfaces, native tap feedback,
  normal transitions, full functionality. No simulated magnetism.
- Automated test asserts zero horizontal overflow at 390px with touch on
  all key routes.

## Known limitations

- `scroll-behavior: smooth` (pre-existing) remains enabled for anchor
  jumps; reduced-motion users get `auto` via the pre-existing media query.
- The demo scan (~800ms) animates regardless of reduced motion because it
  represents an explicitly triggered process; all decorative motion around
  it is suppressed. Judged acceptable; revisit if owner disagrees.
