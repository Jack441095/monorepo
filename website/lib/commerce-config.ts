// Stripe direct payment links (created 2026-09-18 via API with product_id metadata)
// TODO: paste the Stripe pre-order Payment Link for Submit here as
// STRIPE_SUBMIT_PREORDER_LINK (a buy.stripe.com URL) and point the pre-live
// pre-order CTAs at it. Until then they route to the existing waitlist
// anchors so no surface shows a dead button.
// TODO: paste the Stripe deposit Payment Links for studio services here (each
// a buy.stripe.com URL from the Stripe dashboard). Until a link is pasted the
// matching deposit CTA on /services falls back to a prefilled mailto so no
// surface ever shows a dead button.
export const STRIPE_MIXING_DEPOSIT_LINK = "";
export const STRIPE_MASTERING_DEPOSIT_LINK = "";
export const STRIPE_SLO_LINK = "https://buy.stripe.com/7sY3cwgGFdAk6kN6X75sA04";
export const STRIPE_SUBMIT_LINK = "https://buy.stripe.com/cNiaEYdutbsc38B3KV5sA05";

// Checkout approvals follow docs/STRIPE_COMMERCE.md. Website flags and the
// backend gate must agree before launch; Payment Links have a separate state.
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
