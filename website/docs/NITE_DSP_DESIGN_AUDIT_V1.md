# NITE DSP — PHASE 1 DESIGN AUDIT V1

Scope: public website (`platform/website`) as of `design/website-v22-interactive-demos`.
Reference set: Apple, Ableton, FabFilter, Native Instruments, Linear,
Raycast, Vercel, Teenage Engineering — principles extracted, nothing copied.

## Strengths (keep)

1. **Coherent signal identity.** Palette B + the NITE Signal interaction
   language (light fields, signal tracks, transients) is genuinely
   distinctive — closer to Teenage Engineering's "instrument as brand" than
   to any generic SaaS template.
2. **Honest demos.** The V2.2 demonstration layer (SIMULATION / CONCEPT
   DEMO labels, confidence language, reset states) already embodies
   local-first trust and explainable intelligence.
3. **Performance discipline.** Zero motion dependencies, static prerender,
   compositor-only animation, 45/45 tests.
4. **Accessibility posture.** Reduced motion, keyboard operability, glyph +
   text (never colour-only) state marking.
5. **Typography foundation.** Geist Sans/Mono is technical-human and
   highly legible; tabular numerals already enforced.

## Weaknesses

1. **Marketing site, not product company site.** Pages *describe*; only the
   demos *demonstrate*. Apple/Linear/Vercel lead with the product surface
   itself; NITE DSP leads with prose.
2. **No product pages for Submit / KENN / Thursday.** Submit and KENN are
   cards on /products; their intelligence (the actual differentiator) has no
   dedicated explorable surface.
3. **Inconsistent typographic hierarchy.** Section titles, eyebrows, and
   mono labels are used well individually but sizes/weights vary page to
   page; no defined type roles (display vs UI vs metadata vs data).
4. **Information density is uneven.** Homepage alternates airy marketing
   sections with dense hardware panels; FabFilter/Linear hold a consistent
   professional density.
5. **Commercial surfaces lag the brand.** Pricing is honest but visually
   flat next to the product story; no licensing/download/onboarding
   narrative; trust messaging is scattered across pages rather than a
   first-class section.
6. **Ecosystem story is implicit.** Nothing explains how Submit/SLO/KENN/
   Thursday relate as one system (the intelligence layer story).
7. **Evidence UI is ad-hoc.** Demo readouts are bespoke per demo; there is
   no reusable confidence/evidence/reasoning component vocabulary — the
   core of explainable intelligence.

## Inconsistencies

- Border radii and panel paddings vary (4/8/12px tokens exist but pages
  improvise).
- Status chips: three different patterns (chip-neutral, badge-experimental,
  bespoke bordered spans on /products).
- Eyebrow treatment varies (some tracked caps, some not).
- CTA hierarchy: primary/secondary buttons consistent, but tertiary
  text-links behave differently per page.

## Commercial blockers

1. No conversion path from demo excitement → product understanding →
   pricing (demos live far from commercial surfaces).
2. "Pricing TBC" is honest but presented without a value narrative or
   licensing model explanation.
3. No roadmap/vision section — buyers of professional tools want to see
   trajectory (Linear/Vercel publish theirs).
4. Trust/privacy facts (local analysis, no upload) exist but are buried in
   FAQ/callouts rather than owned as a headline section.
5. Submit/KENN have no commercial narrative at all (positioning exists now,
   surfaces don't).

## Verdict

The brand core is strong and rare. What's missing is **product-company
structure**: dedicated product experiences, a formalised design system
(especially Intelligence UI), and commercial surfaces that carry the same
confidence as the demos. Phases 2–4 address exactly these.
