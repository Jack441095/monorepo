# NITE DSP UX System

2026-08-13. What actually exists, grounded in the real design-token values in
`nitedsp/website/app/globals.css` — not a theoretical spec.

## Scope decision made this pass

The originating prompt asked for a combined website + JUCE-plugin design system. This document
covers the **website only**. The plugin UI (`Source/PluginEditor.cpp`) was audited (real findings
in `docs/SMART_SAMPLE_MANAGER_UX_AUDIT.md`) but not modified — it's real-time audio product code,
and this engagement has repeatedly established that changes there need a full rebuild → native-
test → real-launch verification cycle, which a website-focused session shouldn't rush. A shared
product-side component system (Section 6 of the originating prompt) is deferred to whichever
session actually implements the UX-P1 fixes.

## Color hierarchy (real values)

```
--background:    #09090b   page background
--surface:        #111114   card/panel background
--surface-raised: #17171b   raised/hover surface
--border:         #26262b   default border
--border-strong:  #34343a   emphasized border (hover, focus-adjacent)
--foreground:     #f4f4f5   primary text
--muted:          #a1a1aa   secondary text
--muted-dim:      #7d7d80   tertiary text -- see the "Accessibility fix" note below
--accent:         #f4f4f5   currently identical to --foreground (monochrome, deliberate)
--accent-contrast:#09090b   text-on-accent
--warning-border: #7c5a1a   experimental/warning callout border
--warning-bg:     rgba(124,90,26,0.12)
--warning-text:   #e3b34d
```

**Accessibility fix made this pass**: `--muted-dim` was `#71717a`, which computed to 4.12:1
against `--background` and 3.90:1 against `--surface` — both fail WCAG AA for normal-size text
(needs 4.5:1). It's used in 20 places across the site, several at `text-sm` (14px, not "large
text" by WCAG's definition). Lightened to `#7d7d80` — the minimal change that clears AA on both
backgrounds (4.85:1 / 4.59:1) while staying visually the dimmest tier of text. Computed with the
real WCAG relative-luminance formula, not eyeballed.

## Deliberately monochrome, not "an accent color"

`--accent` equals `--foreground`. There's no blue/purple/brand-hue accent anywhere in the site.
This is a real, existing decision (not new) worth stating explicitly: it's why the site doesn't
read as "generic SaaS" — the restraint itself is the identity. The one exception is the amber
warning/experimental treatment, used narrowly and consistently (see below), and `--blue`-ish
tones that exist only inside the *plugin's* own UI (`FF60A5FA` in `PluginEditor.cpp`, unrelated
to the website's tokens — the two surfaces are related in spirit, not pixel-identical, per the
originating prompt's own "coherence without identity" instruction).

## New this pass

- **`.callout-warning`** — replaces two previously-duplicated inline hex-value blocks (the legal-
  page disclaimer, the Ableton integration Learn page) with one token-driven class.
- **`.badge-experimental`** — a small pill badge, used consistently now on every place "Ableton
  workflow" appears (homepage, product page) instead of inconsistent "(experimental)" text
  appended to a title. Same warning tokens as the callout, different shape, for a smaller/inline
  context.
- Both are built from the same three warning tokens, so a future palette change updates every
  consumer at once instead of requiring a find-and-replace across hex strings.

## Typography

Geist Sans (UI) / Geist Mono (technical, e.g. license keys) via `next/font/google` — unchanged,
already a deliberate two-family-max system per the brand direction's "restrained" principle. No
changes made this pass.

## Motion

`prefers-reduced-motion` already fully respected (`globals.css`'s media query zeroes animation/
transition durations). Existing transitions are limited to `opacity`/`border-color`/`background`
at 150ms — already "fast, subtle" per the originating prompt's Section 26, nothing to change.

## What's still theoretical / not built this pass

- No formal component system exists for badges/alerts/status states beyond what's listed above —
  `.callout-warning` and `.badge-experimental` are the first two, not a complete set. Success/
  error/info variants would need their own tokens (`--success-*`, `--error-*`) when a real use
  case demands them — not invented speculatively here.
- No shared container/layout component exists yet; `style={{ maxWidth: "var(--content-width)" }}`
  is still repeated per-section (flagged in `docs/WEBSITE_PROFESSIONAL_AUDIT.md` P2 #9, not fixed
  this pass — real but low-urgency duplication, not a visible defect).
