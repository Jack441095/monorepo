# NITE DSP INTERACTION V1 / WEBSITE MOTION V1 — VISUAL REVIEW

Assets: `docs/motion-review/` (committed for owner review; nothing
uploaded externally).

- Static captures (JPEG, full-page): `home|slo|products @ 1440|768|390`
- Utility spot-checks: `utility/pricing|support|learn|account-1440`
- Motion recordings (WebM, 1280×800, local only): `video/1…5*.webm`
  1. hero pointer lighting  2. magnetic CTA  3. product-frame parallax
  4. SLO waveform response  5. signal-flow storytelling

## Findings by route

### Homepage (HIGH)
- Hero light field reads as slow studio illumination; text contrast
  unaffected; heading fully static.
- Frame: bloom ring + sheen only on pointer engagement; bar and screenshot
  parallax at different rates; screenshot contents never distorted.
- Demo: SIMULATION chip + preserved disclosure; scanner trail reads as
  processing; transient pulse fires once per resolved scan; pointer band
  gives local waveform illumination.
- Workflow: signal track fills blue→violet with scroll; stage numbers
  activate at the reading line — the page explains processing by behaving
  like processing.
- Capabilities: spotlight quiets siblings subtly; no scale/zoom anywhere.
- CTA band: gradient border brightens on hover; magnetic "See pricing".

### SLO product page (HIGH)
- Product hero light field + magnetic primary CTA.
- Full-width screenshot frame with bloom/sheen + layered parallax.
- Demo identical to homepage instance (one system, consistent).

### Products (MEDIUM)
- Flagship card: 1.2° tilt ceiling, bloom, status chip now carries a live
  blue dot (breathes only under pointer attention).
- Research cards: hover depth (1px rise + shadow + border), status dots
  (muted/warning), spotlight group.

### Pricing / Support / Learn / Account (LOW/MINIMAL)
- No new motion. Token fix restored intended arrow/list accent colours.
  Pricing TBC + Register Interest untouched.

## Intensity assessment

- 30-second continuous interaction test: not tiring; cursor never sticky;
  reading unaffected; red only appears on explicit demo actions.
- 5-minute navigation test: effects remain background texture; nothing
  competes with content; novelty decay leaves a "precise hardware" feel.
- Everything still composes correctly as a static screenshot (reveals are
  one-shot and settle; capture script sweeps then shoots).

## Issues found & fixed during review

1. `.tilt-surface__layer` forced `display:block`, breaking the frame bar's
   flex layout — removed (transform-only layer class).
2. Capture script raced smooth-scrolling, shooting reveals mid-transition —
   script now disables smooth scroll, sweeps, settles, then captures.
3. Stale manually-started server caused one flaky full-suite run — killed;
   suite green on fresh webServer.

## Overall intensity

**B — PREMIUM BALANCED.** Ambient motion yields to interaction; nothing
loops site-wide except (intentionally) the near-invisible grain.
