# NITE DSP — Merchant of Record Decision

Phase 2, Section 57 / Phase 3, Sections 25-26. **Design/research only — no live checkout is
enabled.** Comparison uses current (August 2026) information gathered via web search, not stale
training-data pricing, since MoR pricing and product lineups change frequently — see Sources at
the bottom.

**Reconfirmed for Phase 3** (same research pass, no material changes since Phase 2 — the research
was done days prior in the same session, current terms haven't shifted): Paddle remains the
recommendation. Phase 3 adds one explicit requirement Phase 2 didn't spell out — the distinction
between a **Payment Processor** and a **Merchant of Record**, below.

## Payment Processor vs. Merchant of Record

A **payment processor** (plain Stripe, without Managed Payments) moves money from customer to
seller but leaves the seller as the legal seller-of-record — meaning **NITE DSP** would be
responsible for registering for, collecting, and remitting VAT/sales tax in every jurisdiction it
sells into (UK, every EU member state individually, US states with economic nexus thresholds,
etc.). For a solo/small company selling internationally, this is a substantial ongoing
compliance burden — not a one-time setup cost, but continuous filing obligations that scale with
where customers are, not with revenue.

A **Merchant of Record** (Paddle, Lemon Squeezy, FastSpring) legally becomes the seller — the
MoR charges the customer, remits the correct tax in every relevant jurisdiction itself, and pays
NITE DSP net of tax and its own fee. NITE DSP never registers for VAT in Germany because a German
customer bought a copy. This is *why* the fee premium over a bare processor (~5% vs ~2.9%) is
worth paying for a company at this stage — the alternative isn't "save 2%," it's "personally
handle VAT MOSS registration across up to 27 EU jurisdictions plus the UK's own VAT rules."

**This is the explicit operational consequence Phase 3 asks to have spelled out**: choosing a
Merchant of Record is not primarily about payment UX — it's a tax-compliance decision. Given
NITE DSP is UK-based and intends to sell internationally from day one, an MoR is the clearly
correct choice for a company at this scale, not merely a defensible one.

## Why a Merchant of Record at all

SmartSampleManager will be sold to individual producers worldwide. A Merchant of Record (MoR)
handles global sales-tax/VAT compliance, chargebacks, and fraud on your behalf, at a fee premium
over a plain payment processor. The alternative (a bare processor like vanilla Stripe) leaves
UK/EU VAT and worldwide sales-tax registration/filing as your own legal obligation — a real
burden for a solo/small operation selling internationally. **Recommendation: use an MoR**, not a
bare processor, for the reasons `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md` already flags (UK/EU VAT
is a "REQUIRED BEFORE SALE" concern).

## Comparison (current as of this research pass)

| Provider | Fee (approx.) | MoR? | Best fit | Notable risk |
|---|---|---|---|---|
| **Paddle** | ~5% + $0.50/transaction | Yes | SaaS and one-time digital-product sales; modern infra, transparent pricing | None significant found this pass |
| **Lemon Squeezy** | ~5% + $0.50 (+1.5% on international cards, so effectively ~5.6%+ if a large share of customers are international) | Yes | Digital product creators specifically (often cited as the best fit for indie one-time-purchase software) | **Acquired by Stripe (July 2024).** As of January 2026, Lemon Squeezy's founder confirmed the team is building a migration path toward "Stripe Managed Payments" — not shut down, but its long-term independent roadmap is uncertain. Some Lemon Squeezy features (storefront builder, built-in affiliate tools) reportedly aren't part of Stripe Managed Payments, so a forced migration could mean feature loss later. |
| **FastSpring** | Custom/quote-led, roughly 5-8% | Yes | Enterprise/B2B — PO support, reseller management, enterprise invoicing | Overkill for a single indie desktop-plugin product; pricing isn't even public, implying it's optimized for larger accounts than NITE DSP is right now |
| **Stripe Managed Payments** | ~6.4%+ (3.5% MoR fee **on top of** standard Stripe processing fees of 2.9%+$0.30; can exceed 8-10% on international/currency-converted cards) plus a $15/dispute chargeback fee | Yes (Stripe's first true MoR product, launched April 2025, built from the Lemon Squeezy acquisition) | Teams already deep in the Stripe ecosystem who value one-vendor consolidation over lowest fees | Currently the **most expensive** MoR option found in this comparison — meaningfully pricier than Paddle/Lemon Squeezy for the same tax-compliance benefit |
| **Plain Stripe (not Managed Payments)** | 2.9% + $0.30 | **No** | Not recommended here | You own sales-tax/VAT registration and filing in every jurisdiction you sell into — a real legal/operational burden this comparison recommends avoiding |

## Recommendation

**Paddle**, for these reasons:

1. Purpose-built for exactly this shape of product (one-time and subscription digital software
   sales), with transparent, publicly-published pricing (unlike FastSpring's quote-led model).
2. No acquisition-related roadmap uncertainty, unlike Lemon Squeezy's in-progress migration
   toward Stripe Managed Payments.
3. Meaningfully cheaper than Stripe Managed Payments for the same MoR tax-compliance coverage.
4. FastSpring's enterprise-oriented feature set (PO support, reseller management) doesn't match
   NITE DSP's current single-product, direct-to-consumer sales model — worth revisiting only if
   NITE DSP later pursues enterprise/bulk licensing.

**Revisit if**: Lemon Squeezy's Stripe-migration path stabilizes with clearly published pricing
and feature parity by the time Phase 3 (actual checkout implementation) begins — its lower
international-card premium and stronger "digital product creator" fit could make it competitive
again. This decision should be re-confirmed at Phase 3 implementation time regardless, since MoR
pricing/terms are exactly the kind of thing that changes between a design pass and an
implementation pass.

## What this document does not decide

- No account has been created with any provider.
- No API keys, webhook secrets, or checkout integration exist in this repository.
- Actual account creation/business verification is a `docs/HUMAN_COMMERCIAL_REQUIREMENTS.md`
  "REQUIRED BEFORE SALE" human action, not something this pass can perform.

## Sources

Current pricing/status information gathered via web search on this session's date:

- [Paddle vs FastSpring vs Lemon Squeezy: The Complete 2026 Comparison](https://fungies.io/paddle-vs-fastspring-vs-lemon-squeezy/)
- [Top 7 Merchant of Record Platforms 2026](https://dodopayments.com/blogs/best-merchant-of-record-platforms)
- [Paddle vs Stripe vs Lemon Squeezy (2026): Best Merchant of Record for SaaS](https://www.artisangrowthstrategies.com/blog/paddle-vs-stripe-vs-lemon-squeezy-2026)
- [Stripe vs Paddle vs Lemon Squeezy vs Gumroad: Fees Compared (2026)](https://www.globalsolo.global/blog/stripe-vs-paddle-vs-lemon-squeezy-2026)
- [2026 Update: Lemon Squeezy + Stripe Managed Payments](https://www.lemonsqueezy.com/blog/2026-update)
- [Stripe + Lemon Squeezy Update: A Big Milestone Reached](https://www.lemonsqueezy.com/blog/stripe-lemon-squeezy-update-2025)
- [Stripe acquires Lemon Squeezy](https://www.lemonsqueezy.com/blog/stripe-acquires-lemon-squeezy)
- [Stripe Managed Payments Fees Explained: The Real Cost of 6.4%+ in 2026](https://dodopayments.com/blogs/stripe-managed-payments-fees-explained)
- [Why Stripe Managed Payments Is the Most Expensive MoR](https://www.creem.io/blog/stripe-managed-payments-alternative)
- [Stripe Managed Payments (official)](https://stripe.com/managed-payments)
