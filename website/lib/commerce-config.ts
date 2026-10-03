// Stripe direct payment links (created 2026-09-18 via API with product_id metadata)
export const STRIPE_SLO_LINK = "https://buy.stripe.com/7sY3cwgGFdAk6kN6X75sA04";
export const STRIPE_SUBMIT_LINK = "https://buy.stripe.com/cNiaEYdutbsc38B3KV5sA05";

// Central commercial-maturity switch (docs/NITE_DSP_CONVERSION_COMMERCIAL_UX_V1.md §1).
// Launch procedure: set NEXT_PUBLIC_CHECKOUT_LIVE=1 at build time once Stripe
// prices are approved and the backend reports 200 from /commerce/checkout.
// Every CtaButton asking for BUY_LIVE then renders the buy flow; until then
// they fall back to BETA_REQUEST so no surface ever shows a dead Buy button.
export const STRIPE_MODE = process.env.NEXT_PUBLIC_STRIPE_MODE;
export const LEGAL_REVIEW_APPROVED =
  process.env.NEXT_PUBLIC_LEGAL_REVIEW_APPROVED === "1";
export const RELEASE_READY =
  process.env.NEXT_PUBLIC_RELEASE_READY === "1";

// Sandbox remains available for controlled rehearsals. A real-money button is
// impossible unless checkout, legal approval, and a public release are all
// explicitly enabled in the production build.
export const CHECKOUT_LIVE =
  process.env.NEXT_PUBLIC_CHECKOUT_LIVE === "1" &&
  (STRIPE_MODE === "test" ||
    (STRIPE_MODE === "live" && LEGAL_REVIEW_APPROVED && RELEASE_READY));

export const PUBLIC_CHECKOUT_LIVE =
  CHECKOUT_LIVE && STRIPE_MODE === "live";
