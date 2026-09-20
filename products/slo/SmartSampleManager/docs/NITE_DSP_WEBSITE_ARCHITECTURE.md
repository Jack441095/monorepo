# NITE DSP — Company Website Architecture (Design Only)

Phase 2, Sections 58-68. **Design document only — the website is not built this pass**, per the
master prompt's Section 67 ("Do not build the website yet unless required for architecture
scaffolding"). This defines the target structure so a future implementation pass doesn't need to
redesign it.

## Governing framing

The website is **the NITE DSP company website**, not a SmartSampleManager microsite — it must be
architected to eventually sell/support multiple products, while today's actual public content is
exactly one product. This mirrors `docs/NITE_DSP_COMMERCIAL_ARCHITECTURE.md`'s data-model
principle: multi-product-capable architecture, single-product-actual content.

## Route structure

```text
/                          Homepage — company-first, flagship product second
/products                  Product catalogue (renders only entries in the product registry)
/products/smart-sample-manager   The one live product page
/downloads                 Authenticated download portal (post-purchase / trial)
/support                   Support hub, links into per-product docs
/docs/smart-sample-manager Product documentation (only public doc set right now)
/account                   NITE DSP Account dashboard ("My Products")
/login                     Auth
/about                     Company page
/privacy                   Privacy policy
/terms                     Terms of service
/eula                      End-user license agreement
/refund-policy             Refund policy
```

`/products/[slug]` is a dynamic route in the code, but the product registry (below) currently
contains one entry, so `/products/future-product` legitimately 404s rather than rendering a
placeholder — matching Section 61's "do not display empty cards or 'Coming Soon'."

## Product registry

```typescript
interface Product {
    id: string;            // "smart-sample-manager"
    name: string;           // "Smart Sample Manager"
    slug: string;            // "smart-sample-manager"
    description: string;
    status: "active" | "hidden";
    purchasable: boolean;
    platforms: ("macos" | "windows")[];
    currentVersion: string;
}
```

**The registry contains exactly one entry today.** Adding a second product later is a single
new object in this registry plus its own `/products/[slug]` content — the routing/rendering
code doesn't change. No WIP product (KENN, AutoMix, AudioGen, MIDI Generator) gets a registry
entry until it's genuinely ready to be commercialised, per `docs/COMMERCIAL_SCOPE.md`.

## Homepage hierarchy

```text
NITE DSP
"Professional audio software" (company tagline)
    ↓
SMART SAMPLE MANAGER
"Current flagship product" framing, not "our only product"
    ↓
Real product demo / screenshots (once they exist — none fabricated for this doc)
    ↓
Why it exists (the actual problem it solves — library management + acoustic search)
    ↓
Features (only ones verified to exist — see claims list below)
    ↓
Workflow (scan → search → organize)
    ↓
Compatibility (macOS confirmed; Windows explicitly marked unverified per
    docs/WINDOWS_READINESS.md — never claim cross-platform support that
    hasn't been tested)
    ↓
Try / Buy
```

The homepage must establish NITE DSP as the company identity first (logo, tagline, About link in
nav) so that adding "Product B" later to the products page doesn't feel like retrofitting a
company brand onto what was actually a single-product site.

## Verified-claims-only feature list

Per Section 64-65 of the master prompt, cross-checked against what actually ships (Phase 1's
`docs/SEARCH_QUALITY_AUDIT.md`/`docs/PRODUCT_READINESS_AUDIT.md`):

**Safe to advertise** (confirmed to exist and work):
- Library scanning with automatic BPM/key/instrument-type detection (TagLib + DSP feature
  extraction)
- Acoustic similarity search ("find similar") — HNSW-powered, verified with a real 0.989 vs.
  0.669 similarity separation between related/unrelated audio
- Visual similarity map (UMAP 2D projection)
- Duplicate detection (content-hash based, survives file renames/retagging)
- Ableton taxonomy classification + Places-folder-compatible XMP export
- Waveform preview

**Explicitly NOT to advertise** until actually built:
- Natural-language / semantic text search (e.g. "search for a dark punchy kick") — Phase 1
  confirmed this does not exist; the product does acoustic *similarity*, not text-to-audio
  search. Conflating the two on the website would be a false claim.
- Any specific "handles N samples" library-size claim — `docs/PERFORMANCE_BASELINE_RELEASE.md`
  and `docs/MEMORY_PROFILE.md` only have clean data through 1,000 files; nothing above that is a
  measured claim.
- Windows support — unverified, see `docs/WINDOWS_READINESS.md`.

## Ableton positioning

The Ableton taxonomy/XMP integration is commercially interesting and safe to describe factually
(e.g. "organizes samples into Ableton's Places-compatible category folders") — but must **never
imply endorsement, partnership, or affiliation with Ableton**. "Ableton" and "Live" are Ableton's
trademarks; use them only in a purely descriptive, nominative sense ("works with Ableton Live's
sample browser"), the same way any third-party plugin vendor correctly describes DAW
compatibility without claiming a business relationship.

## Visual direction

Per Section 63: dark-first, restrained, technical, modern, audio-centric, minimal, high-quality
typography, generous spacing, real software UI screenshots, real workflows. Avoid: generic SaaS
templates, crypto-adjacent neon aesthetics, fake AI imagery, musical-note logo clichés, stock
photos of producers, gratuitous glassmorphism. No visual design work was produced this pass —
this is a written brief for whoever builds the site, not a mockup.

## Technology recommendation

Not implemented this pass, per the master prompt's own instruction. Recommendation for when it
is: **Next.js + TypeScript + React**, a standard component/styling system (not prescribed
further — this is a UI framework choice, not an architecture one), **Postgres** as the backend
(shared with the licensing service's database per `docs/NITE_DSP_COMMERCIAL_ARCHITECTURE.md`,
avoiding a second database technology for no reason), and a managed deployment platform (Vercel
or equivalent — again, a hosting cost/ops decision for you, not resolved here).

## Boundary from existing business infrastructure

Per `docs/COMMERCIAL_SCOPE.md`: the existing `Audio_Too/business/app/` website/backend is
general-purpose and largely out of scope. `smart_sample_manager_bridge.py` (a 29-line
build-status check — confirmed by reading it directly this pass) is the one existing touchpoint,
and it may be extended later for real entitlement checks once the licensing backend exists — but
the NITE DSP commercial website described here is architecturally a **separate** system with its
own database and its own account/product model, not a further extension of the general business
app. Building it inside that existing app merely because the app already exists would violate the
"do not expose WIP" boundary, since that app's other routes touch unrelated business systems this
document has no reason to couple to.

## Privacy boundary

The NITE DSP backend (account, licensing, purchases) never needs and must never receive: sample
files, filenames, folder paths, embeddings, waveforms, or DAW project contents.
SmartSampleManager remains local-first — the website/backend only ever sees commercial/account
data, matching Section 69's explicit requirement.

## Pricing (Phase 3, Sections 56-58)

**Model: perpetual license, updates for the current major version included, paid upgrade for a
future major version.** Matches how most desktop production-software tools in this category
price (a familiar model for the target buyer — producers who already own perpetual-license
plugins), and avoids the support/billing complexity of a subscription for a single-developer
product at launch.

### Launch price recommendation: £59, framed as an introductory price against a £79 regular price

```text
Regular price:      £79
Launch price:        £59  (marked as introductory, not a permanent discount)
```

Reasoning, weighing the candidates Phase 3 lists (£39-£129) against what SmartSampleManager
actually offers per the verified-claims feature list above: acoustic similarity search, a visual
similarity map, Ableton-taxonomy/XMP integration, and duplicate detection are a genuinely
differentiated feature set relative to a plain file browser, which argues against the low end of
the range (£39-49 undersells real AI-driven functionality). But the product is pre-beta, with no
public track record, no reviews, and unverified library-size ceiling (`docs/MEMORY_PROFILE.md`
only has clean data through 1,000 files) — which argues against the top end (£99-129, typically
reserved for mature tools with an established reputation). £59-79 sits in the credible middle for
a first release from a new (if technically capable) developer, with the £59 introductory price
giving early beta-to-launch customers a real, time-bounded incentive without setting a permanent
"wait for the sale" expectation (Section 58's explicit warning against permanent discount
culture).

**This is a recommendation, not a decision** — final pricing is a business call only you can
make; this section exists so the website's pricing page has a concrete, reasoned starting point
rather than a placeholder.

### Pricing page structure

```text
Smart Sample Manager
£59  (was £79 — introductory price)

Perpetual license
Free updates for v1.x
[Buy Now]  [Start 14-Day Trial]

What's included:
    Acoustic similarity search
    Visual similarity map
    Duplicate detection
    Ableton taxonomy + XMP integration
    macOS (Windows: not yet available — see platform compatibility)
```

Configurable, not hardcoded per-instance across the codebase — the price and feature-bullet list
live in the product registry (`docs/NITE_DSP_WEBSITE_ARCHITECTURE.md`'s registry section above),
not scattered across marketing copy, matching Section 56's "do not hardcode business decisions
everywhere."

## Legal page infrastructure (Phase 3, Section 65)

```text
/privacy          -- structural placeholder, PROFESSIONAL REVIEW REQUIRED
/terms             -- structural placeholder, PROFESSIONAL REVIEW REQUIRED
/eula                -- structural placeholder, PROFESSIONAL REVIEW REQUIRED
/refund-policy         -- structural placeholder, PROFESSIONAL REVIEW REQUIRED
```

Each page's structural sections (what a privacy policy/EULA/terms/refund-policy page
conventionally needs to cover — data collected, license grant, refund window, etc.) can be
drafted as a skeleton once the website is actually built, but **no page goes live without
professional legal review** — see `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`'s "Legal document
review" entry. Marked here so this isn't silently forgotten once the rest of the site looks
finished — a polished-looking but legally unreviewed EULA is a real business risk, not a
formality.

## UK/international commerce considerations (Section 66) — flagged for professional review, not resolved here

UK business registration, UK GDPR, EU GDPR, digital-software consumer rights (the UK/EU both have
specific distance-selling rules for digital goods, including mandatory pre-purchase disclosures
and a modified right-of-withdrawal for software once downloaded), VAT, international sales tax,
refunds, privacy, and trademark all require actual professional (accounting/legal) review — see
`docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`. Choosing Paddle as Merchant of Record
(`docs/COMMERCE_PROVIDER_DECISION.md`) meaningfully reduces the *tax administration* burden (VAT
collection/remittance is Paddle's responsibility, not NITE DSP's) but does **not** eliminate
every business/legal obligation — UK company/tax registration, GDPR compliance for the data NITE
DSP itself collects (account emails, purchase records), and consumer-rights compliance in the
website's own checkout/refund UX all remain NITE DSP's responsibility regardless of which
commerce provider is used.
